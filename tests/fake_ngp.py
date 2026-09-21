"""Låtsas-NGP: en lokal HTTP-server som beter sig som Uppdatering-API:et i spec/uppdatering-api-1.1.yaml.

Den finns för att kunna testa klienten (och hela leveransflödet) utan tillgång till Lantmäteriets verifieringsmiljö.
Att klienten fungerar mot den bevisar alltså att den följer specifikationen som den läses här, inte att den fungerar mot
NGP."""
from __future__ import annotations

import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MEDIA_V4 = "application/vnd.lm.detaljplan.v4+json"
UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"


def default_rule(content: dict) -> list[dict]:
    """Valideringsregler i låtsasservern: minst en beslutsinformation och planbeskrivning-liknande krav."""
    features = content.get("features") or []
    plan = features[0]["properties"] if features else {}
    cases = [{"id": "6.1-02", "label": "Uppgift om geometri ska finnas för alla detaljplaner.", "time": 0,
              "status": "OK" if plan.get("plangeometri") else "FAILURE",
              **({} if plan.get("plangeometri") else {"message": ["Planen saknar geometri"]})}]
    if not plan.get("beslutsinformation"):
        cases.append({"id": "5.2-01", "label": "Beslutsinformation ska finnas.", "time": 0, "status": "FAILURE",
                      "message": [f"Detaljplanen {plan.get('objektidentitet')} saknar beslutsinformation"]})
    if not plan.get("beteckning"):
        cases.append({"id": "5.1-07", "label": "Planen bör ha en beteckning.", "time": 0, "status": "WARNING",
                      "message": ["Beteckning saknas"]})
    cases.append({"id": "9.9-99", "label": "Alla bestämmelser ska ha formulering.", "time": 0,
                  "status": "OK" if all(f["properties"].get("bestammelseformulering") for f in features[1:]) else "FAILURE"})
    return cases


class FakeNgp:
    """Tillstånd och inställningar för låtsasservern. Starta med ``start()``, stoppa med ``stop()``."""

    def __init__(self):
        self.allowed_providers = {"0484"}
        self.require_token = True
        self.accept_media = {MEDIA_V4}
        self.validate_after = 1  # antal statusfrågor efter uppladdning innan valideringen är klar
        self.publish_after = 2  # ytterligare frågor tills en validerad mottagning är publicerad
        self.stuck = False  # valideringen blir aldrig klar
        self.rule = default_rule
        self.expire_token_once = False
        self.receptions: dict[str, dict] = {}
        self.requests: list[tuple] = []  # (metod, sökväg, rubriker)
        self.tokens_issued = 0
        self.valid_tokens: set[str] = set()
        self.report_gets_during_upload = 0
        self._server = None

    # -- livscykel ------------------------------------------------------------------------
    def start(self) -> str:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # tyst
                pass

            def do_GET(self):  # noqa: N802
                fake.handle(self, "GET")

            def do_POST(self):  # noqa: N802
                fake.handle(self, "POST")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self.base_url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/uppdatering/v1"

    @property
    def token_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/token"

    # -- hjälpmedel -------------------------------------------------------------------------
    @staticmethod
    def _send(handler, status, body=None, headers=None, content_type="application/json"):
        data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))
        handler.send_response(status)
        if data:
            handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            handler.send_header(name, value)
        handler.end_headers()
        handler.wfile.write(data)

    def _fault(self, handler, status, reason, *errors):
        self._send(handler, status, {"code": status, "reason": reason, "errors": list(errors)})

    @staticmethod
    def _status(kind, message=""):
        return {"typ": kind, "tidsstampel": "2026-09-20T10:00:00.000+02:00", **({"felmeddelande": message} if message else {})}

    def _authorised(self, handler) -> bool:
        if not self.require_token:
            return True
        header = handler.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        if token in self.valid_tokens:
            return True
        self._fault(handler, 401, "Unauthorized", "Ogiltig eller utgången token")
        return False

    # -- själva svaren ------------------------------------------------------------------------
    def handle(self, handler, method: str) -> None:
        path = handler.path.split("?")[0]
        length = int(handler.headers.get("Content-Length") or 0)
        body = handler.rfile.read(length) if length else b""
        self.requests.append((method, path, dict(handler.headers)))
        base = "/uppdatering/v1"
        if path == "/token" and method == "POST":
            return self._token(handler, body)
        if not path.startswith(base):
            return self._fault(handler, 404, "Not Found", "Okänd adress")
        path = path[len(base):]
        if path == "/health":
            return self._send(handler, 200, {"status": "UP"})
        if not self._authorised(handler):
            return
        if path == "/mottagning" and method == "POST":
            return self._register(handler, body)
        match = re.fullmatch(rf"/mottagning/({UUID})", path)
        if match and method == "GET":
            return self._reception(handler, match.group(1))
        match = re.fullmatch(rf"/mottagning/({UUID})/forandringar", path)
        if match and method == "POST":
            return self._changes(handler, match.group(1), body)
        if match and method == "GET":
            return self._list_changes(handler, match.group(1))
        match = re.fullmatch(rf"/mottagning/({UUID})/forandringar/({UUID})", path)
        if match and method == "GET":
            return self._change(handler, match.group(1), match.group(2))
        match = re.fullmatch(rf"/mottagning/({UUID})/forandringar/({UUID})/leverans", path)
        if match and method == "POST":
            return self._upload(handler, match.group(1), match.group(2), body)
        if match and method == "GET":
            return self._report(handler, match.group(1), match.group(2))
        self._fault(handler, 404, "Not Found", "Resursen finns inte")

    def _token(self, handler, body: bytes) -> None:
        if b"grant_type=client_credentials" not in body:
            return self._fault(handler, 400, "Bad Request", "grant_type saknas")
        token = f"token-{uuid.uuid4()}"
        self.valid_tokens.add(token)
        self.tokens_issued += 1
        self._send(handler, 200, {"access_token": token, "token_type": "Bearer", "expires_in": 3600})

    def _register(self, handler, body: bytes) -> None:
        try:
            info = json.loads(body)["leveransinfo"]
            assert info["informationstyp"] == "detaljplan"
        except (ValueError, KeyError, AssertionError, TypeError):
            return self._fault(handler, 400, "Bad Request", "Felaktig leveransinfo")
        if info["provider"] not in self.allowed_providers:
            return self._fault(handler, 403, "Forbidden", f"Producenten {info['provider']} får inte leverera detaljplaner")
        identity = str(uuid.uuid4())
        self.receptions[identity] = {"provider": info["provider"], "changes": {}, "uploaded_at": None, "polls": 0}
        self._send(handler, 201, {"id": identity, "leveransinfo": info, "status": self._status("registrerad")},
                   {"Location": f"{self.base_url}/mottagning/{identity}"})

    def _changes(self, handler, identity: str, body: bytes) -> None:
        reception = self.receptions.get(identity)
        if reception is None:
            return self._fault(handler, 404, "Not Found", "Mottagningen finns inte")
        try:
            changes = json.loads(body)["forandringar"]
            assert changes and all(c["typ"] in ("leverans", "radering") and c["objektidentitet"] for c in changes)
        except (ValueError, KeyError, AssertionError, TypeError):
            return self._fault(handler, 400, "Bad Request", "Felaktiga förändringar")
        for change in changes:
            reception["changes"][change["objektidentitet"]] = {"typ": change["typ"], "status": "registrerad",
                                                               "content": None, "media": None}
        self._send(handler, 201, {"forandringar": [
            {**c, "status": self._status("registrerad")} for c in changes]})

    def _upload(self, handler, identity: str, plan: str, body: bytes) -> None:
        reception = self.receptions.get(identity)
        change = reception["changes"].get(plan) if reception else None
        if change is None:
            return self._fault(handler, 404, "Not Found", "Förändringen finns inte")
        media = handler.headers.get("Content-Type", "")
        if media not in self.accept_media:
            return self._fault(handler, 415, "Unsupported Media Type", f"Mediatypen {media} stöds inte")
        if change["status"] not in ("registrerad", "valideringsfel"):
            return self._fault(handler, 400, "Bad Request", f"Kan inte ladda upp när status är {change['status']}")
        try:
            change["content"] = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._fault(handler, 400, "Bad Request", "Filen är inte JSON")
        change.update(status="mottagen", media=media, polls=0)
        reception["polls"] = 0
        # som i specifikationens exempel: omdirigering till .../leveranser/{objekt}, som här inte finns (404)
        target = f"{self.base_url}/mottagning/{identity}/leveranser/{plan}"
        self._send(handler, 303, {"href": target}, {"Location": target})

    def _advance(self, reception: dict) -> None:
        """Låtsasvalideringen: efter ``validate_after`` statusfrågor blir förändringen validerad eller får valideringsfel."""
        for change in reception["changes"].values():
            if change["status"] == "mottagen" and not self.stuck:
                change["polls"] = change.get("polls", 0) + 1
                if change["polls"] > self.validate_after:
                    failed = any(c["status"] == "FAILURE" for c in self.rule(change["content"]))
                    change["status"] = "valideringsfel" if failed else "validerad"
                    change["polls"] = 0
            elif change["status"] == "validerad" and not self.stuck:
                change["polls"] = change.get("polls", 0) + 1
                if change["polls"] > self.publish_after:
                    change["status"] = "publicerad"

    @staticmethod
    def _aggregate(reception: dict) -> str:
        kinds = [c["status"] for c in reception["changes"].values()]
        for worst in ("fel", "valideringsfel"):
            if worst in kinds:
                return worst
        for level in ("registrerad", "mottagen", "validerad", "publicerad"):
            if kinds and all(k == level for k in kinds):
                return level
        return "mottagen" if kinds else "registrerad"

    def _reception(self, handler, identity: str) -> None:
        reception = self.receptions.get(identity)
        if reception is None:
            return self._fault(handler, 404, "Not Found", "Mottagningen finns inte")
        self._advance(reception)
        if self.expire_token_once:  # provar att klienten hämtar ny token vid 401
            self.expire_token_once = False
            self.valid_tokens.clear()
        self._send(handler, 200, {"id": identity, "leveransinfo": {"informationstyp": "detaljplan",
                                                                 "provider": reception["provider"]},
                                  "status": self._status(self._aggregate(reception))})

    def _change(self, handler, identity: str, plan: str) -> None:
        reception = self.receptions.get(identity)
        change = reception["changes"].get(plan) if reception else None
        if change is None:
            return self._fault(handler, 404, "Not Found", "Förändringen finns inte")
        self._send(handler, 200, {"objektidentitet": plan, "typ": change["typ"], "status": self._status(change["status"])})

    def _list_changes(self, handler, identity: str) -> None:
        reception = self.receptions.get(identity)
        if reception is None:
            return self._fault(handler, 404, "Not Found", "Mottagningen finns inte")
        self._send(handler, 200, {"forandringar": [
            {"objektidentitet": key, "typ": c["typ"], "status": self._status(c["status"])}
            for key, c in reception["changes"].items()]})

    def _report(self, handler, identity: str, plan: str) -> None:
        reception = self.receptions.get(identity)
        change = reception["changes"].get(plan) if reception else None
        if change is None:
            return self._fault(handler, 404, "Not Found", "Förändringen finns inte")
        if change["status"] not in ("validerad", "valideringsfel", "publicerad"):
            self.report_gets_during_upload += 1
            return self._send(handler, 204)
        cases = self.rule(change["content"])
        failures = sum(c["status"] == "FAILURE" for c in cases)
        warnings = sum(c["status"] == "WARNING" for c in cases)
        self._send(handler, 200, {"name": "Resultat för validering av detaljplan.v4", "timestamp": "2026-09-20T10:00:01.000+02:00",
                                  "tests": len(cases), "failures": failures, "warnings": warnings, "errors": 0,
                                  "skipped": 0, "time": 0.05, "testcase": cases})
