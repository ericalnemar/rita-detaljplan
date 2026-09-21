"""Klient för Lantmäteriets Uppdatering-API (geodatakatalogen/NGP), enligt spec/uppdatering-api-1.1.yaml.

Leveransen sker i fyra steg (se specifikationen):

  1. ``POST /mottagning``                                   registrerar en mottagning (informationstyp + producent),
  2. ``POST /mottagning/{id}/forandringar``                 registrerar en förändring per domänobjekt,
  3. ``POST /mottagning/{id}/forandringar/{objekt}/leverans`` laddar upp domänobjektet (JSON, mediatyp v4),
  4. ``GET /mottagning/{id}``                               följer statusen tills planen är validerad/publicerad, och
     ``GET …/leverans`` hämtar valideringsrapporten.

Detaljplanen levereras som ett domänobjekt: förändringens objektidentitet är planens objektidentitet och filen är hela
``FeatureCollection`` från ``export_ngp`` (plan + bestämmelser).

**Overifierat mot NGP.** Klienten följer specifikationen och är testad mot en låtsasserver, men har inte körts mot
Lantmäteriets verifieringsmiljö (det kräver producentbehörighet). Uppgifter som specifikationen inte anger är
antaganden och kan ändras i inställningarna: adressen till tokentjänsten (OAuth 2, ``client_credentials``, nyckel och
hemlighet som Basic-autentisering) och mediatypen v4 (specifikationens lista nämner bara v1–v3).

Nätverksanropen görs av en ``Transport`` som kan bytas ut; standardtransporten använder QGIS nätverkslager (proxy,
certifikat och autentiseringskonfigurationer) och får köras i en bakgrundsuppgift.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import quote, urlparse

from . import model

INFORMATIONSTYP = "detaljplan"
MEDIA_TYPE = model.MEDIATYP  # application/vnd.lm.detaljplan.v4+json
VER_BASE = "https://api-ver.lantmateriet.se/distribution/geodatakatalog/uppdatering/v1"
PROD_BASE = "https://api.lantmateriet.se/distribution/geodatakatalog/uppdatering/v1"
VER_TOKEN = "https://api-ver.lantmateriet.se/token"  # antagande: standardtjänsten i Lantmäteriets API-portal
PROD_TOKEN = "https://api.lantmateriet.se/token"
TIMEOUT_MS = 60000
STATUSES = ("registrerad", "mottagen", "validerad", "valideringsfel", "publicerad", "fel")
DONE = ("validerad", "valideringsfel", "publicerad", "fel")  # när klienten slutar vänta
POLL_SECONDS = 3.0
WAIT_SECONDS = 300.0
_UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")


@dataclass(frozen=True)
class Environment:
    key: str
    title: str
    base_url: str
    token_url: str


ENVIRONMENTS = {
    "ver": Environment("ver", "Verifiering", VER_BASE, VER_TOKEN),
    "prod": Environment("prod", "Produktion", PROD_BASE, PROD_TOKEN),
}


@dataclass(frozen=True)
class NgpConfig:
    """Vart och hur planen levereras. Nyckel och hemlighet lagras inte här utan i en av QGIS autentiseringskonfigurationer
    (``authcfg``, av typen Grundläggande autentisering: nyckel som användarnamn, hemlighet som lösenord)."""
    environment: str = "ver"  # "ver", "prod" eller "egen"
    base_url: str = VER_BASE
    token_url: str = VER_TOKEN
    authcfg: str = ""
    media_type: str = MEDIA_TYPE

    @property
    def title(self) -> str:
        return ENVIRONMENTS[self.environment].title if self.environment in ENVIRONMENTS else "Egen adress"

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"

    def problems(self) -> list[str]:
        """Vad som saknas eller är fel i inställningarna innan man kan leverera."""
        found = []
        if not self.base_url.strip():
            found.append("Adress till Uppdatering-API:et saknas.")
        elif not _safe_url(self.base_url):
            found.append("Adressen till API:et måste börja med https:// (http:// tillåts bara mot den egna datorn).")
        if self.token_url.strip() and not _safe_url(self.token_url):
            found.append("Adressen till tokentjänsten måste börja med https://.")
        if self.token_url.strip() and not self.authcfg:
            found.append("Välj en autentiseringskonfiguration med nyckel och hemlighet från API-portalen.")
        return found


def _safe_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme == "https" and parsed.netloc:
        return True
    return parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")


def environment_config(key: str, authcfg: str = "") -> NgpConfig:
    env = ENVIRONMENTS[key]
    return NgpConfig(environment=key, base_url=env.base_url, token_url=env.token_url, authcfg=authcfg)


class NgpError(RuntimeError):
    """Något gick fel mot NGP. ``status`` är HTTP-status om svaret kom från tjänsten. Meddelandet är avsett för användaren."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass
class Response:
    status: int
    headers: dict = field(default_factory=dict)  # gemena nycklar
    body: bytes = b""

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8")) if self.body else None
        except (ValueError, UnicodeDecodeError) as exc:
            raise NgpError(f"Oväntat svar från tjänsten (inte JSON): {exc}", self.status) from exc


Transport = Callable[[str, str, dict, Optional[bytes], str], Response]  # metod, url, rubriker, kropp, authcfg


def qgis_transport(method: str, url: str, headers: dict, body: Optional[bytes], authcfg: str = "") -> Response:
    """Standardtransport: QGIS nätverkshanterare (proxy, certifikat och autentiseringskonfigurationer) med en egen
    händelseslinga, så den fungerar både i huvudtråden och i en bakgrundsuppgift. Omdirigeringar följs inte: en 303
    efter en uppladdning ska inte leda till att filen skickas en gång till."""
    from qgis.core import QgsApplication, QgsNetworkAccessManager
    from qgis.PyQt.QtCore import QByteArray, QEventLoop, QTimer, QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest

    request = QNetworkRequest(QUrl(url))
    for name, value in headers.items():
        request.setRawHeader(name.encode("ascii"), value.encode("utf-8"))
    request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
    if authcfg and not QgsApplication.authManager().updateNetworkRequest(request, authcfg):
        raise NgpError("Kunde inte använda autentiseringskonfigurationen (är den borttagen eller låst?).")
    if method not in ("GET", "POST"):
        raise ValueError(f"Metoden {method} stöds inte")
    manager = QgsNetworkAccessManager.instance()
    reply = manager.get(request) if method == "GET" else manager.post(request, QByteArray(body or b""))
    loop = QEventLoop()
    reply.finished.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(TIMEOUT_MS)
    if not reply.isFinished():
        loop.exec()
    timer.stop()
    timed_out = not reply.isFinished()
    if timed_out:
        reply.abort()
    status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    try:
        if timed_out or status is None:  # inget svar från tjänsten alls: anslutningen misslyckades
            reason = "tidsgränsen överskreds" if timed_out else reply.errorString()
            raise NgpError(f"Ingen kontakt med {urlparse(url).netloc}: {reason}")
        reply_headers = {bytes(name).decode("latin-1").lower(): bytes(reply.rawHeader(name)).decode("utf-8", "replace")
                         for name in reply.rawHeaderList()}
        return Response(int(status), reply_headers, bytes(reply.readAll()))
    finally:
        reply.deleteLater()


# -- svarsmodeller --------------------------------------------------------------------------
@dataclass(frozen=True)
class Status:
    typ: str
    tidsstampel: str = ""
    felmeddelande: str = ""

    @classmethod
    def parse(cls, data: Optional[dict]) -> "Status":
        data = data or {}
        return cls(str(data.get("typ", "")), str(data.get("tidsstampel", "")), str(data.get("felmeddelande", "")))

    @property
    def done(self) -> bool:
        return self.typ in DONE


@dataclass(frozen=True)
class ReportCase:
    id: str
    label: str
    status: str  # OK | FAILURE | WARNING | ERROR | SKIPPED
    messages: tuple = ()


@dataclass(frozen=True)
class Report:
    """Valideringsrapporten (validering-1.0) för ett levererat domänobjekt."""
    name: str = ""
    timestamp: str = ""
    tests: int = 0
    failures: int = 0
    warnings: int = 0
    errors: int = 0
    skipped: int = 0
    cases: tuple = ()

    @classmethod
    def parse(cls, data: Optional[dict]) -> Optional["Report"]:
        if not isinstance(data, dict):
            return None
        cases = []
        for item in data.get("testcase") or []:
            messages = item.get("message") or []
            cases.append(ReportCase(str(item.get("id", "")), str(item.get("label", "")), str(item.get("status", "")),
                                  tuple([messages] if isinstance(messages, str) else [str(m) for m in messages])))
        number = lambda key: int(data.get(key) or 0)  # noqa: E731
        return cls(str(data.get("name", "")), str(data.get("timestamp", "")), number("tests"), number("failures"),
                   number("warnings"), number("errors"), number("skipped"), tuple(cases))

    @property
    def problems(self) -> list[ReportCase]:
        """Testfall som inte gick igenom, allvarligaste först (FAILURE, ERROR, WARNING, SKIPPED)."""
        order = {"FAILURE": 0, "ERROR": 1, "WARNING": 2, "SKIPPED": 3}
        return sorted((c for c in self.cases if c.status != "OK"), key=lambda c: (order.get(c.status, 9), c.id))

    @property
    def summary(self) -> str:
        return (f"{self.tests} kontroller: {self.failures} fel, {self.warnings} varningar"
                + (f", {self.errors} kunde inte utföras" if self.errors else "")
                + (f", {self.skipped} hoppades över" if self.skipped else ""))


@dataclass
class Delivery:
    """Resultatet av en leverans: var den ligger hos NGP, hur det gick och rapporten."""
    mottagningsid: str
    plan_id: str
    status: Status
    report: Optional[Report] = None
    steps: list = field(default_factory=list)  # vad som gjordes, i ordning (för visning)

    @property
    def ok(self) -> bool:
        return self.status.typ in ("validerad", "publicerad")


def _fault_text(response: Response) -> str:
    """Texten ur ett felsvar (fault-1.0: code, reason, errors) eller ur kroppen."""
    try:
        data = json.loads(response.body.decode("utf-8")) if response.body else None
    except (ValueError, UnicodeDecodeError):
        data = None
    if isinstance(data, dict):
        errors = data.get("errors")
        detail = "; ".join(str(e) for e in errors) if isinstance(errors, list) else ""
        return " – ".join(part for part in (str(data.get("reason") or ""), detail) if part)
    return response.body.decode("utf-8", "replace").strip()[:300]


def _explain(response: Response, action: str) -> NgpError:
    hints = {
        400: "Anropet avvisades som felaktigt.",
        401: "Inloggningen avvisades. Kontrollera nyckel och hemlighet i autentiseringskonfigurationen.",
        403: "Behörighet saknas. Nyckeln måste tillhöra en producent med rätt att leverera detaljplaner för "
             "kommunen (kontakta NGP-supporten).",
        404: "Resursen finns inte hos tjänsten (fel adress eller fel id).",
        413: "Filen är för stor för tjänsten.",
        415: "Tjänsten godtar inte mediatypen (application/vnd.lm.detaljplan.v4+json). Specifikationen för "
             "Uppdatering-API:et nämner bara v1–v3: kontrollera med NGP-supporten.",
    }
    hint = hints.get(response.status, "Tjänsten svarade med ett fel." if response.status >= 500
                     else f"Oväntat svar ({response.status}).")
    detail = _fault_text(response)
    return NgpError(f"{action}: {hint}" + (f" ({detail})" if detail else ""), response.status)


# -- klienten -------------------------------------------------------------------------------
class NgpClient:
    def __init__(self, config: NgpConfig, transport: Optional[Transport] = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.config = config
        self._transport = transport or qgis_transport
        self._sleep = sleep
        self._clock = clock
        self._token: Optional[str] = None
        self._token_expires = 0.0

    # -- grundläggande anrop ---------------------------------------------------------------
    def _url(self, path: str) -> str:
        return self.config.base_url.rstrip("/") + path

    def token(self) -> Optional[str]:
        """Hämtar (och cachar) en åtkomsttoken med nyckel och hemlighet. None om ingen tokentjänst är angiven."""
        if not self.config.token_url.strip():
            return None
        if self._token and self._clock() < self._token_expires - 30:
            return self._token
        response = self._transport("POST", self.config.token_url.strip(),
                                   {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                                   b"grant_type=client_credentials", self.config.authcfg)
        if response.status != 200:
            raise _explain(response, "Kunde inte logga in hos Lantmäteriet")
        data = response.json() or {}
        token = data.get("access_token")
        if not token:
            raise NgpError("Inloggningen gav ingen åtkomsttoken.", response.status)
        self._token = str(token)
        self._token_expires = self._clock() + float(data.get("expires_in") or 300)
        return self._token

    def _call(self, method: str, path: str, action: str, *, body: Optional[bytes] = None,
              content_type: str = "application/json", ok: tuple = (200,), strict: bool = True) -> Response:
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = content_type
        for attempt in (1, 2):
            token = self.token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            response = self._transport(method, self._url(path), dict(headers), body, "")
            if response.status == 401 and attempt == 1 and token:
                self._token = None  # tokenen kan ha gått ut: hämta en ny en gång
                continue
            break
        if strict and response.status not in ok:
            raise _explain(response, action)
        return response

    # -- API:ets anrop ----------------------------------------------------------------------
    def health(self) -> str:
        """Tjänstens hälsostatus (UP, DOWN …). Kräver ingen inloggning."""
        response = self._transport("GET", self._url("/health"), {"Accept": "application/json"}, None, "")
        if response.status not in (200, 503):
            raise _explain(response, "Hälsokontrollen misslyckades")
        return str((response.json() or {}).get("status", "UNKNOWN"))

    def register(self, provider: str, informationstyp: str = INFORMATIONSTYP) -> str:
        """Registrerar en mottagning och returnerar dess id (``mottagningsid``)."""
        body = json.dumps({"leveransinfo": {"informationstyp": informationstyp, "provider": provider}}).encode()
        response = self._call("POST", "/mottagning", "Kunde inte registrera leveransen", body=body, ok=(201, 200))
        identity = (response.json() or {}).get("id")
        if not identity or not _UUID_RE.match(str(identity)):
            raise NgpError("Tjänsten gav inget giltigt id för mottagningen.", response.status)
        return str(identity)

    def register_changes(self, reception: str, changes: list[dict]) -> list[dict]:
        """Registrerar förändringar: ``[{"objektidentitet": uuid, "typ": "leverans" | "radering"}]``."""
        body = json.dumps({"forandringar": changes}).encode()
        response = self._call("POST", f"/mottagning/{quote(reception)}/forandringar",
                              "Kunde inte registrera förändringen", body=body, ok=(201, 200))
        return (response.json() or {}).get("forandringar") or []

    def upload(self, reception: str, identity: str, content: bytes) -> None:
        """Laddar upp domänobjektet. Tjänsten svarar med en omdirigering (303) till valideringsrapporten.

        Omdirigeringen följs inte. Vid ett svar som inte är godkänt kontrolleras förändringens status: har den gått
        vidare från ``registrerad``/``valideringsfel`` gick uppladdningen ändå igenom."""
        action = "Kunde inte ladda upp planen"
        response = self._call("POST", f"/mottagning/{quote(reception)}/forandringar/{quote(identity)}/leverans",
                              action, body=content, content_type=self.config.media_type, strict=False)
        if response.status in (303, 200, 201, 202, 204):
            return
        try:
            state = self.change_status(reception, identity).typ
        except NgpError:
            state = ""
        if state not in ("mottagen", "validerad", "publicerad"):
            raise _explain(response, action)

    def change_status(self, reception: str, identity: str) -> Status:
        """Statusen för en enskild förändring."""
        response = self._call("GET", f"/mottagning/{quote(reception)}/forandringar/{quote(identity)}",
                              "Kunde inte hämta förändringens status")
        return Status.parse((response.json() or {}).get("status"))

    def reception(self, reception: str) -> Status:
        response = self._call("GET", f"/mottagning/{quote(reception)}", "Kunde inte hämta leveransens status")
        return Status.parse((response.json() or {}).get("status"))

    def changes(self, reception: str) -> list[dict]:
        response = self._call("GET", f"/mottagning/{quote(reception)}/forandringar",
                              "Kunde inte hämta förändringarna")
        return (response.json() or {}).get("forandringar") or []

    def report(self, reception: str, identity: str) -> Optional[Report]:
        """Valideringsrapporten, eller None om den inte skapats än (204)."""
        response = self._call("GET", f"/mottagning/{quote(reception)}/forandringar/{quote(identity)}/leverans",
                              "Kunde inte hämta valideringsrapporten", ok=(200, 204))
        return None if response.status == 204 else Report.parse(response.json())

    def wait(self, reception: str, on_status: Optional[Callable[[Status], None]] = None,
             timeout: float = WAIT_SECONDS, interval: float = POLL_SECONDS) -> Status:
        """Följer mottagningens status tills valideringen är klar (validerad, valideringsfel, publicerad eller fel)."""
        deadline = self._clock() + timeout
        while True:
            status = self.reception(reception)
            if on_status:
                on_status(status)
            if status.done:
                return status
            if self._clock() >= deadline:
                raise NgpError(f"Valideringen var inte klar efter {timeout:.0f} sekunder (status {status.typ}). "
                               "Kontrollera statusen senare.")
            self._sleep(interval)

    # -- hela leveransen ----------------------------------------------------------------------
    def deliver(self, collection: dict, provider: str, existing: Optional[str] = None,
                on_progress: Optional[Callable[[str], None]] = None, timeout: float = WAIT_SECONDS,
                interval: float = POLL_SECONDS) -> Delivery:
        """Levererar planen: registrerar (eller återanvänder) en mottagning, laddar upp, väntar på valideringen och
        hämtar rapporten. ``existing`` = id för en tidigare mottagning som fick valideringsfel (eller aldrig laddades
        upp): då laddas planen upp igen på den, i stället för att skapa en ny."""
        plan = _plan_identity(collection)
        steps: list[str] = []

        def step(text: str) -> None:
            steps.append(text)
            if on_progress:
                on_progress(text)

        reception = None
        if existing:
            try:
                previous = self.reception(existing)
            except NgpError:
                previous = None
            if previous is not None and previous.typ in ("registrerad", "valideringsfel"):
                reception = existing
                step(f"Återanvänder mottagning {existing} (status {previous.typ}).")
        if reception is None:
            step("Registrerar leveransen …")
            reception = self.register(provider)
            step(f"Mottagning {reception} skapad.")
            self.register_changes(reception, [{"objektidentitet": plan, "typ": "leverans"}])
            step("Förändring registrerad för planen.")
        content = json.dumps(collection, ensure_ascii=False).encode("utf-8")
        step(f"Laddar upp planen ({len(content) / 1024:.0f} kB) …")
        self.upload(reception, plan, content)
        step("Planen är uppladdad. Väntar på valideringen …")
        status = self.wait(reception, lambda s: on_progress and on_progress(f"Status: {s.typ}"), timeout, interval)
        step(f"Status: {status.typ}" + (f" ({status.felmeddelande})" if status.felmeddelande else ""))
        report = None
        if status.typ in ("validerad", "valideringsfel", "publicerad"):
            report = self.report(reception, plan)
            if report is not None:
                step("Valideringsrapporten hämtad.")
        return Delivery(reception, plan, status, report, steps)

    def refresh(self, reception: str, plan: str) -> Delivery:
        """Hämtar aktuell status och rapport för en tidigare leverans (t.ex. för att se om planen publicerats)."""
        status = self.reception(reception)
        report = self.report(reception, plan) if status.typ in ("validerad", "valideringsfel", "publicerad") else None
        return Delivery(reception, plan, status, report, [f"Status: {status.typ}"])


def _plan_identity(collection: dict) -> str:
    """Planens objektidentitet: förändringen och domänobjektet har samma identitet."""
    try:
        identity = collection["features"][0]["properties"]["objektidentitet"]
    except (KeyError, IndexError, TypeError):
        raise NgpError("Leveransen saknar detaljplanobjekt.") from None
    if not identity or not _UUID_RE.match(str(identity)):
        raise NgpError("Planen saknar giltig objektidentitet (UUID).")
    return str(identity)
