"""Leverans till NGP: klienten mot en låtsasserver, inställningar, dialoger och flödet i verktygsfältet.

Ingen riktig NGP-tjänst används (den kräver producentbehörighet). Klienten körs över riktig HTTP mot ``fake_ngp`` som
beter sig som spec/uppdatering-api-1.1.yaml; att det fungerar bevisar alltså inte att det fungerar mot Lantmäteriets miljö."""
import json
import re
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, LEFT, PLAN, PlanCase, filled, pick, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsProject, QgsSettings
    from rita_detaljplan.core import ngp_client as ngp
    from rita_detaljplan.core import settings
    from rita_detaljplan.gui.delivery_dialog import DeliveryDialog, confirmation_text
    from rita_detaljplan.gui.ngp_dialog import FILE, UPLOAD, NgpDialog, NgpRequest
    from rita_detaljplan.gui.settings_dialog import SettingsDialog
    from fake_ngp import MEDIA_V4, FakeNgp
    from qgis_app import get_app
    from test_export import BESLUT, DOCUMENTS, ExportCase


def no_sleep(_seconds):
    pass


def collection(plan_id="0f0e0d0c-0b0a-4090-8080-070605040302", decision=True, label="DP 1"):
    props = {"feature:typ": "detaljplan", "objektidentitet": plan_id, "plangeometri": [{"geometri": {}}]}
    if label:
        props["beteckning"] = label
    if decision:
        props["beslutsinformation"] = [{"diarienummerKommun": "KS 1/24"}]
    return {"type": "FeatureCollection", "feature:mediatyp": MEDIA_V4, "features": [
        {"type": "Feature", "geometry": None, "properties": props},
        {"type": "Feature", "geometry": None, "properties": {"feature:typ": "användningsbestämmelse",
                                                             "bestammelseformulering": "Industri"}}]}


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.fake = FakeNgp()
        self.fake.start()
        self.addCleanup(self.fake.stop)
        self.config = ngp.NgpConfig("egen", self.fake.base_url, self.fake.token_url, "test-cfg")
        self.client = ngp.NgpClient(self.config, transport=self.transport(), sleep=no_sleep)

    def transport(self):
        """Riktig HTTP via QGIS nätverkslager. Tokenförfrågan skickas utan autentiseringskonfiguration (låtsasservern
        kräver ingen Basic-inloggning)."""
        return lambda method, url, headers, body, authcfg: ngp.qgis_transport(method, url, headers, body, "")

    def new_client(self, **config):
        cfg = ngp.NgpConfig(**{"environment": "egen", "base_url": self.fake.base_url, "token_url": self.fake.token_url,
                               "authcfg": "x", **config})
        return ngp.NgpClient(cfg, transport=self.transport(), sleep=no_sleep)


class ConfigTests(unittest.TestCase):
    def test_the_environments_match_the_servers_of_the_specification(self):
        spec = (ROOT / "spec" / "uppdatering-api-1.1.yaml").read_text(encoding="utf-8")
        self.assertIn(ngp.VER_BASE, spec)
        self.assertIn(ngp.PROD_BASE, spec)
        self.assertEqual(ngp.ENVIRONMENTS["ver"].base_url, ngp.VER_BASE)
        self.assertEqual(ngp.environment_config("prod", "abc").base_url, ngp.PROD_BASE)
        self.assertTrue(ngp.environment_config("prod").is_production)
        self.assertFalse(ngp.environment_config("ver").is_production)

    def test_the_media_type_is_version_4_of_the_detaljplan_format(self):
        self.assertEqual(ngp.MEDIA_TYPE, "application/vnd.lm.detaljplan.v4+json")

    def test_only_https_is_accepted_except_towards_the_own_computer(self):
        for good in ("https://api.lantmateriet.se/x", "http://127.0.0.1:8000/x", "http://localhost/x"):
            self.assertTrue(ngp._safe_url(good), good)
        for bad in ("http://api.lantmateriet.se", "ftp://x", "api.lantmateriet.se", "", "https://"):
            self.assertFalse(ngp._safe_url(bad), bad)

    def test_a_config_lists_what_is_missing(self):
        self.assertEqual(ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, "abc").problems(), [])
        found = ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, "").problems()
        self.assertEqual(len(found), 1)
        self.assertIn("autentiseringskonfiguration", found[0])
        self.assertTrue(ngp.NgpConfig("egen", "", "", "").problems())
        self.assertTrue(ngp.NgpConfig("egen", "http://osaker.se", "", "").problems())
        self.assertEqual(ngp.NgpConfig("egen", ngp.VER_BASE, "", "").problems(), [], "ingen tokentjänst: ingen inloggning")
        self.assertTrue(ngp.NgpConfig("egen", ngp.VER_BASE, "http://osaker.se/token", "x").problems())

    def test_the_titles_name_the_environment(self):
        self.assertEqual(ngp.environment_config("ver").title, "Verifiering")
        self.assertEqual(ngp.environment_config("prod").title, "Produktion")
        self.assertEqual(ngp.NgpConfig("egen").title, "Egen adress")


class ModelTests(unittest.TestCase):
    def test_a_report_is_parsed_and_the_worst_problems_come_first(self):
        report = ngp.Report.parse({
            "name": "Resultat", "timestamp": "t", "tests": 4, "failures": 1, "warnings": 1, "errors": 0, "skipped": 1,
            "testcase": [{"id": "b", "label": "Varning", "status": "WARNING", "message": ["x"]},
                         {"id": "a", "label": "OK", "status": "OK"},
                         {"id": "c", "label": "Fel", "status": "FAILURE", "message": ["y", "z"]},
                         {"id": "d", "label": "Hoppad", "status": "SKIPPED"}]})
        self.assertEqual([c.id for c in report.problems], ["c", "b", "d"])
        self.assertEqual(report.problems[0].messages, ("y", "z"))
        self.assertEqual(report.summary, "4 kontroller: 1 fel, 1 varningar, 1 hoppades över")
        self.assertIsNone(ngp.Report.parse(None))

    def test_a_single_message_string_is_accepted(self):
        report = ngp.Report.parse({"testcase": [{"id": "a", "label": "l", "status": "FAILURE", "message": "ett"}]})
        self.assertEqual(report.cases[0].messages, ("ett",))

    def test_a_status_knows_when_waiting_is_over(self):
        for kind, done in (("registrerad", False), ("mottagen", False), ("validerad", True), ("valideringsfel", True),
                           ("publicerad", True), ("fel", True)):
            self.assertEqual(ngp.Status.parse({"typ": kind, "tidsstampel": "t"}).done, done, kind)
        self.assertEqual(ngp.Status.parse(None).typ, "")

    def test_fault_answers_become_readable_messages(self):
        body = json.dumps({"code": 403, "reason": "Forbidden", "errors": ["Ingen rätt", "för kommunen"]}).encode()
        error = ngp._explain(ngp.Response(403, {}, body), "Kunde inte registrera")
        self.assertIn("Behörighet saknas", str(error))
        self.assertIn("Ingen rätt; för kommunen", str(error))
        self.assertEqual(error.status, 403)
        self.assertIn("v4", str(ngp._explain(ngp.Response(415, {}, b""), "x")))
        self.assertIn("Inloggningen avvisades", str(ngp._explain(ngp.Response(401, {}, b"text"), "x")))
        self.assertIn("Tjänsten svarade med ett fel", str(ngp._explain(ngp.Response(503, {}, b""), "x")))

    def test_the_plan_identity_is_taken_from_the_first_object(self):
        self.assertEqual(ngp._plan_identity(collection("0f0e0d0c-0b0a-4090-8080-070605040302")),
                         "0f0e0d0c-0b0a-4090-8080-070605040302")
        for bad in ({}, {"features": []}, collection("inte-ett-uuid")):
            with self.assertRaises(ngp.NgpError):
                ngp._plan_identity(bad)


class ClientTests(ServerCase):
    def test_health_needs_no_login(self):
        self.assertEqual(self.client.health(), "UP")
        self.assertEqual(self.fake.tokens_issued, 0)

    def test_the_token_is_fetched_once_and_reused(self):
        reception = self.client.register("0484")
        self.client.reception(reception)
        self.client.reception(reception)
        self.assertEqual(self.fake.tokens_issued, 1)
        auth = [h.get("Authorization") for m, p, h in self.fake.requests if p.endswith(reception)]
        self.assertTrue(all(a and a.startswith("Bearer token-") for a in auth))

    def test_no_token_service_means_no_login(self):
        self.fake.require_token = False
        client = self.new_client(token_url="")
        self.assertIsNone(client.token())
        self.assertTrue(client.register("0484"))
        self.assertFalse([1 for m, p, h in self.fake.requests if "Authorization" in h])

    def test_an_expired_token_is_replaced_once_and_the_call_repeated(self):
        reception = self.client.register("0484")
        self.fake.expire_token_once = True
        self.client.reception(reception)  # den här kan gå igenom; nästa möter en ogiltig token
        self.assertEqual(self.client.reception(reception).typ, "registrerad")
        self.assertEqual(self.fake.tokens_issued, 2)

    def test_a_rejected_login_is_explained(self):
        self.fake.require_token = True
        self.fake.valid_tokens.clear()
        client = self.new_client()
        client._token = "gammal"
        client._token_expires = time.monotonic() + 1000

        def stuck_token(*_):
            return ngp.Response(401, {}, b'{"code":401,"reason":"Unauthorized","errors":["Ogiltig nyckel"]}')

        broken = ngp.NgpClient(self.config, transport=lambda m, u, h, b, a: stuck_token() if u.endswith("/token")
                               else ngp.qgis_transport(m, u, h, b, ""), sleep=no_sleep)
        with self.assertRaises(ngp.NgpError) as caught:
            broken.register("0484")
        self.assertIn("logga in", str(caught.exception))
        self.assertIn("Ogiltig nyckel", str(caught.exception))

    def test_registering_a_reception_returns_its_id_and_checks_the_provider(self):
        identity = self.client.register("0484")
        self.assertRegex(identity, r"^[a-f0-9-]{36}$")
        self.assertIn(identity, self.fake.receptions)
        with self.assertRaises(ngp.NgpError) as caught:
            self.client.register("9999")
        self.assertEqual(caught.exception.status, 403)
        self.assertIn("producent", str(caught.exception))

    def test_changes_are_registered_for_the_plan(self):
        identity = self.client.register("0484")
        plan = "0f0e0d0c-0b0a-4090-8080-070605040302"
        result = self.client.register_changes(identity, [{"objektidentitet": plan, "typ": "leverans"}])
        self.assertEqual(result[0]["status"]["typ"], "registrerad")
        self.assertEqual(self.fake.receptions[identity]["changes"][plan]["typ"], "leverans")
        self.assertEqual(self.client.changes(identity)[0]["objektidentitet"], plan)

    def test_upload_is_done_once_and_the_redirect_is_not_followed(self):
        identity = self.client.register("0484")
        plan = "0f0e0d0c-0b0a-4090-8080-070605040302"
        self.client.register_changes(identity, [{"objektidentitet": plan, "typ": "leverans"}])
        content = json.dumps(collection(plan), ensure_ascii=False).encode("utf-8")
        self.client.upload(identity, plan, content)
        posts = [(p, h) for m, p, h in self.fake.requests if m == "POST" and p.endswith("/leverans")]
        self.assertEqual(len(posts), 1, "uppladdningen görs en gång")
        self.assertFalse([1 for m, p, h in self.fake.requests if "/leveranser/" in p], "omdirigeringen följs inte")
        self.assertEqual(posts[0][1]["Content-Type"], MEDIA_V4)
        stored = self.fake.receptions[identity]["changes"][plan]
        self.assertEqual(stored["content"], collection(plan))
        self.assertEqual(stored["status"], "mottagen")

    def test_a_media_type_the_service_does_not_accept_is_explained(self):
        self.fake.accept_media = {"application/vnd.lm.detaljplan.v3+json"}
        with self.assertRaises(ngp.NgpError) as caught:
            self.client.deliver(collection(), "0484", interval=0)
        self.assertEqual(caught.exception.status, 415)
        self.assertIn("v1–v3", str(caught.exception))

    def test_the_report_is_missing_until_the_validation_is_done(self):
        identity = self.client.register("0484")
        plan = "0f0e0d0c-0b0a-4090-8080-070605040302"
        self.client.register_changes(identity, [{"objektidentitet": plan, "typ": "leverans"}])
        self.client.upload(identity, plan, json.dumps(collection(plan)).encode())
        self.assertIsNone(self.client.report(identity, plan))
        self.client.wait(identity, interval=0)
        self.assertGreaterEqual(self.client.report(identity, plan).tests, 2)

    def test_an_unknown_reception_gives_404(self):
        with self.assertRaises(ngp.NgpError) as caught:
            self.client.reception("0f0e0d0c-0b0a-4090-8080-070605040399")
        self.assertEqual(caught.exception.status, 404)

    def test_no_contact_is_reported_with_the_host(self):
        server = FakeNgp()
        server.start()
        config = ngp.NgpConfig("egen", server.base_url, "", "")
        server.stop()
        client = ngp.NgpClient(config, transport=self.transport(), sleep=no_sleep)
        with self.assertRaises(ngp.NgpError) as caught:
            client.health()
        self.assertIn("Ingen kontakt med 127.0.0.1", str(caught.exception))

    def test_waiting_gives_up_with_an_explanation(self):
        self.fake.stuck = True
        ticks = iter(range(0, 10 ** 6, 100))
        client = ngp.NgpClient(self.config, transport=self.transport(), sleep=no_sleep, clock=lambda: float(next(ticks)))
        identity = client.register("0484")
        plan = "0f0e0d0c-0b0a-4090-8080-070605040302"
        client.register_changes(identity, [{"objektidentitet": plan, "typ": "leverans"}])
        client.upload(identity, plan, json.dumps(collection(plan)).encode())
        with self.assertRaises(ngp.NgpError) as caught:
            client.wait(identity, timeout=250, interval=1)
        self.assertIn("inte klar efter 250", str(caught.exception))
        self.assertIn("mottagen", str(caught.exception))


class DeliveryTests(ServerCase):
    plan = "0f0e0d0c-0b0a-4090-8080-070605040302"

    def test_a_valid_plan_is_delivered_end_to_end(self):
        progress = []
        delivery = self.client.deliver(collection(self.plan), "0484", on_progress=progress.append, interval=0)
        self.assertTrue(delivery.ok)
        self.assertIn(delivery.status.typ, ("validerad", "publicerad"))
        self.assertEqual(delivery.plan_id, self.plan)
        self.assertEqual(delivery.report.failures, 0)
        self.assertEqual(delivery.report.warnings, 0)
        self.assertEqual(len(self.fake.receptions), 1)
        reception = self.fake.receptions[delivery.mottagningsid]
        self.assertEqual(reception["provider"], "0484")
        self.assertEqual(list(reception["changes"]), [self.plan])
        self.assertEqual(reception["changes"][self.plan]["content"], collection(self.plan))
        self.assertEqual(reception["changes"][self.plan]["media"], MEDIA_V4)
        self.assertTrue(any("Registrerar" in text for text in progress))
        self.assertTrue(any("Laddar upp" in text for text in progress))
        self.assertTrue(any(text.startswith("Status: ") for text in progress))
        self.assertEqual(delivery.steps[-1].startswith("Valideringsrapporten"), True)

    def test_the_steps_happen_in_the_order_of_the_specification(self):
        self.client.deliver(collection(self.plan), "0484", interval=0)
        calls = [(m, re.sub(r"[a-f0-9]{8}-[a-f0-9-]{27}", "{id}", p).replace("/uppdatering/v1", ""))
                 for m, p, _ in self.fake.requests if p != "/token"]
        self.assertEqual(calls[:4], [("POST", "/mottagning"), ("POST", "/mottagning/{id}/forandringar"),
                                     ("POST", "/mottagning/{id}/forandringar/{id}/leverans"),
                                     ("GET", "/mottagning/{id}")])
        self.assertEqual(calls[-1], ("GET", "/mottagning/{id}/forandringar/{id}/leverans"))

    def test_a_plan_with_validation_errors_gets_the_report_with_the_reasons(self):
        delivery = self.client.deliver(collection(self.plan, decision=False), "0484", interval=0)
        self.assertFalse(delivery.ok)
        self.assertEqual(delivery.status.typ, "valideringsfel")
        problems = delivery.report.problems
        self.assertEqual(problems[0].status, "FAILURE")
        self.assertIn("saknar beslutsinformation", problems[0].messages[0])
        self.assertEqual(delivery.report.failures, 1)

    def test_warnings_do_not_stop_the_plan(self):
        delivery = self.client.deliver(collection(self.plan, label=""), "0484", interval=0)
        self.assertTrue(delivery.ok)
        self.assertEqual([c.status for c in delivery.report.problems], ["WARNING"])

    def test_after_a_validation_error_the_plan_is_uploaded_again_on_the_same_reception(self):
        first = self.client.deliver(collection(self.plan, decision=False), "0484", interval=0)
        self.assertEqual(first.status.typ, "valideringsfel")
        second = self.client.deliver(collection(self.plan), "0484", existing=first.mottagningsid, interval=0)
        self.assertEqual(second.mottagningsid, first.mottagningsid)
        self.assertEqual(len(self.fake.receptions), 1, "ingen ny mottagning skapades")
        self.assertTrue(second.ok)
        self.assertTrue(any("Återanvänder" in step for step in second.steps))

    def test_a_published_plan_is_delivered_on_a_new_reception(self):
        self.fake.publish_after = 0
        first = self.client.deliver(collection(self.plan), "0484", interval=0)
        self.client.refresh(first.mottagningsid, self.plan)
        self.assertEqual(self.client.refresh(first.mottagningsid, self.plan).status.typ, "publicerad")
        second = self.client.deliver(collection(self.plan), "0484", existing=first.mottagningsid, interval=0)
        self.assertNotEqual(second.mottagningsid, first.mottagningsid)
        self.assertEqual(len(self.fake.receptions), 2)

    def test_an_unknown_earlier_reception_is_ignored_and_a_new_one_created(self):
        delivery = self.client.deliver(collection(self.plan), "0484",
                                       existing="0f0e0d0c-0b0a-4090-8080-070605040399", interval=0)
        self.assertTrue(delivery.ok)

    def test_a_producer_without_rights_gets_a_clear_message_and_nothing_is_uploaded(self):
        with self.assertRaises(ngp.NgpError) as caught:
            self.client.deliver(collection(self.plan), "9999", interval=0)
        self.assertIn("Behörighet saknas", str(caught.exception))
        self.assertFalse(self.fake.receptions)

    def test_a_delivery_without_a_valid_plan_identity_is_refused_before_any_call(self):
        with self.assertRaises(ngp.NgpError):
            self.client.deliver(collection("inte-ett-uuid"), "0484")
        self.assertFalse(self.fake.requests)

    def test_refresh_reads_the_current_status_and_report(self):
        delivery = self.client.deliver(collection(self.plan), "0484", interval=0)
        again = self.client.refresh(delivery.mottagningsid, self.plan)
        self.assertEqual(again.plan_id, self.plan)
        self.assertIsNotNone(again.report)


class QgisTransportTests(ServerCase):
    def test_the_authentication_configuration_is_applied_to_the_request(self):
        with mock.patch("qgis.core.QgsApplication.authManager") as manager:
            manager.return_value.updateNetworkRequest.return_value = True
            self.fake.require_token = False
            response = ngp.qgis_transport("GET", self.fake.base_url + "/health", {}, None, "abc123")
        manager.return_value.updateNetworkRequest.assert_called_once()
        self.assertEqual(manager.return_value.updateNetworkRequest.call_args.args[1], "abc123")
        self.assertEqual(response.status, 200)

    def test_an_unusable_authentication_configuration_is_reported(self):
        with mock.patch("qgis.core.QgsApplication.authManager") as manager:
            manager.return_value.updateNetworkRequest.return_value = False
            with self.assertRaises(ngp.NgpError) as caught:
                ngp.qgis_transport("GET", self.fake.base_url + "/health", {}, None, "borta")
        self.assertIn("autentiseringskonfigurationen", str(caught.exception))

    def test_no_authentication_configuration_means_the_manager_is_not_asked(self):
        with mock.patch("qgis.core.QgsApplication.authManager") as manager:
            ngp.qgis_transport("GET", self.fake.base_url + "/health", {}, None, "")
        manager.assert_not_called()

    def test_headers_body_status_and_response_headers_go_through(self):
        self.fake.require_token = False
        response = ngp.qgis_transport("POST", self.fake.base_url + "/mottagning", {"Content-Type": "application/json"},
                                      b'{"leveransinfo": {"informationstyp": "detaljplan", "provider": "0484"}}', "")
        self.assertEqual(response.status, 201)
        self.assertIn("location", response.headers)
        self.assertEqual(response.json()["status"]["typ"], "registrerad")
        self.assertEqual(self.fake.requests[-1][2]["Content-Type"], "application/json")

    def test_error_statuses_are_returned_not_raised(self):
        self.fake.require_token = False
        response = ngp.qgis_transport("GET", self.fake.base_url + "/finns-inte", {}, None, "")
        self.assertEqual(response.status, 404)

    def test_a_redirect_is_returned_as_it_is_and_not_followed(self):
        self.fake.require_token = False
        reception = ngp.qgis_transport("POST", self.fake.base_url + "/mottagning", {},
                                       b'{"leveransinfo": {"informationstyp": "detaljplan", "provider": "0484"}}', "").json()["id"]
        plan = "0f0e0d0c-0b0a-4090-8080-070605040302"
        ngp.qgis_transport("POST", f"{self.fake.base_url}/mottagning/{reception}/forandringar", {},
                           json.dumps({"forandringar": [{"objektidentitet": plan, "typ": "leverans"}]}).encode(), "")
        response = ngp.qgis_transport("POST", f"{self.fake.base_url}/mottagning/{reception}/forandringar/{plan}/leverans",
                                      {"Content-Type": ngp.MEDIA_TYPE}, b"{}", "")
        self.assertEqual(response.status, 303)
        self.assertIn("/leveranser/", response.headers["location"])
        self.assertFalse([1 for m, p, h in self.fake.requests if "/leveranser/" in p], "omdirigeringen följdes inte")

    def test_other_methods_are_refused(self):
        with self.assertRaises(ValueError):
            ngp.qgis_transport("DELETE", "https://x.se", {}, None, "")

    def test_it_also_works_from_a_background_thread(self):
        results = []
        from qgis.core import QgsApplication, QgsTask

        def work(task):
            return ngp.qgis_transport("GET", self.fake.base_url + "/health", {}, None, "").status

        task = QgsTask.fromFunction("test", work, on_finished=lambda exc, res=None: results.append((exc, res)))
        QgsApplication.taskManager().addTask(task)
        deadline = time.time() + 20
        while not results and time.time() < deadline:
            pump(0.05)
        self.assertEqual(results, [(None, 200)])


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.addCleanup(self._clear)
        self._clear()

    @staticmethod
    def _clear():
        store = QgsSettings()
        for key in ("environment", "base_url", "token_url", "authcfg"):
            store.remove(settings.KEY_NGP + key)

    def test_the_default_is_the_verification_environment_without_a_login(self):
        config = settings.ngp_config()
        self.assertEqual((config.environment, config.base_url, config.token_url, config.authcfg),
                         ("ver", ngp.VER_BASE, ngp.VER_TOKEN, ""))

    def test_the_settings_are_remembered(self):
        settings.set_ngp_config(ngp.NgpConfig("prod", ngp.PROD_BASE, ngp.PROD_TOKEN, "cfg42"))
        config = settings.ngp_config()
        self.assertEqual((config.environment, config.base_url, config.authcfg), ("prod", ngp.PROD_BASE, "cfg42"))
        self.assertTrue(config.is_production)

    def test_an_own_address_is_kept_as_typed(self):
        settings.set_ngp_config(ngp.NgpConfig("egen", " https://min.server/api ", "", "cfg"))
        config = settings.ngp_config()
        self.assertEqual((config.environment, config.base_url, config.token_url), ("egen", "https://min.server/api", ""))

    def test_an_unreadable_authentication_database_gives_an_empty_list(self):
        with mock.patch("rita_detaljplan.core.settings.QgsApplication") as app:
            app.authManager.side_effect = RuntimeError("låst")
            self.assertEqual(settings.auth_configs(), [])


class SettingsDialogTests(SettingsTests):
    def dialog(self):
        with mock.patch.object(settings, "auth_configs", return_value=[("abc1234", "NGP-nyckel"), ("def5678", "Annan")]):
            dialog = SettingsDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_section_lists_environments_and_authentication_configurations(self):
        dialog = self.dialog()
        self.assertEqual([dialog.ngp_env.itemText(i) for i in range(dialog.ngp_env.count())],
                         ["Verifiering", "Produktion", "Egen adress"])
        self.assertEqual([dialog.ngp_auth.itemData(i) for i in range(dialog.ngp_auth.count())], ["", "abc1234", "def5678"])
        self.assertIn("Grundläggande autentisering", dialog.ngp_note.text())
        self.assertIn("inte verifierad", dialog.ngp_note.text())

    def test_choosing_an_environment_fills_the_addresses_and_locks_them(self):
        dialog = self.dialog()
        dialog.ngp_env.setCurrentIndex(dialog.ngp_env.findData("prod"))
        self.assertEqual((dialog.ngp_base.text(), dialog.ngp_token.text()), (ngp.PROD_BASE, ngp.PROD_TOKEN))
        self.assertTrue(dialog.ngp_base.isReadOnly())
        dialog.ngp_env.setCurrentIndex(dialog.ngp_env.findData("egen"))
        self.assertFalse(dialog.ngp_base.isReadOnly() or dialog.ngp_token.isReadOnly())

    def test_saving_writes_the_ngp_settings(self):
        dialog = self.dialog()
        dialog.ngp_env.setCurrentIndex(dialog.ngp_env.findData("prod"))
        dialog.ngp_auth.setCurrentIndex(dialog.ngp_auth.findData("def5678"))
        dialog.accept()
        config = settings.ngp_config()
        self.assertEqual((config.environment, config.authcfg), ("prod", "def5678"))

    def test_the_saved_authentication_configuration_is_selected_when_reopened(self):
        settings.set_ngp_config(ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, "abc1234"))
        self.assertEqual(self.dialog().ngp_auth.currentData(), "abc1234")

    def test_a_config_from_a_deleted_authentication_entry_is_still_shown(self):
        settings.set_ngp_config(ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, "borttagen"))
        self.assertEqual(self.dialog().ngp_auth.currentData(), "borttagen")

    def test_the_connection_test_explains_what_is_missing(self):
        dialog = self.dialog()
        self.assertFalse(dialog.test_connection())
        self.assertIn("autentiseringskonfiguration", dialog.ngp_result.text())

    def test_the_connection_test_reports_success_and_failure(self):
        dialog = self.dialog()
        dialog.ngp_auth.setCurrentIndex(dialog.ngp_auth.findData("abc1234"))
        good = mock.Mock()
        good.health.return_value = "UP"
        with mock.patch.object(dialog, "_client", return_value=good):
            self.assertTrue(dialog.test_connection())
        self.assertIn("Tjänsten är UP och inloggningen fungerar", dialog.ngp_result.text())
        good.token.assert_called_once()
        bad = mock.Mock()
        bad.health.side_effect = ngp.NgpError("Ingen kontakt med servern")
        with mock.patch.object(dialog, "_client", return_value=bad):
            self.assertFalse(dialog.test_connection())
        self.assertIn("Ingen kontakt", dialog.ngp_result.text())


class DeliveryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def delivery(self, kind="valideringsfel", cases=None):
        report = ngp.Report.parse({"tests": 3, "failures": 1, "warnings": 1, "testcase": cases or [
            {"id": "5.2-01", "label": "Beslutsinformation ska finnas.", "status": "FAILURE", "message": ["saknas"]},
            {"id": "5.1-07", "label": "Beteckning", "status": "WARNING", "message": ["Beteckning saknas"]},
            {"id": "6.1-02", "label": "Geometri", "status": "OK"}]})
        return ngp.Delivery("0f0e0d0c-0b0a-4090-8080-070605040302", "plan", ngp.Status(kind, "t"), report)

    def dialog(self, delivery, refresh=None):
        dialog = DeliveryDialog(delivery, "Verifiering", refresh)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_status_is_explained_and_only_problems_are_listed(self):
        dialog = self.dialog(self.delivery())
        self.assertIn("Valideringsfel", dialog.status.text())
        self.assertIn("leverera igen", dialog.status.text())
        rows = [dialog.list.item(i).text() for i in range(dialog.list.count())]
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].startswith("✘  [5.2-01] Beslutsinformation ska finnas."))
        self.assertIn("saknas", rows[0])
        self.assertTrue(rows[1].startswith("▲"))
        self.assertIn("3 kontroller: 1 fel, 1 varningar", dialog.summary.text())
        self.assertIn("Verifiering", dialog.info.text())
        self.assertIn("0f0e0d0c", dialog.info.text())

    def test_a_clean_report_says_everything_passed(self):
        dialog = self.dialog(self.delivery("publicerad", [{"id": "a", "label": "l", "status": "OK"}]))
        self.assertIn("Publicerad", dialog.status.text())
        self.assertEqual(dialog.list.item(0).text(), "✔  Alla kontroller gick igenom.")

    def test_a_delivery_without_a_report_says_so(self):
        dialog = self.dialog(ngp.Delivery("id", "plan", ngp.Status("mottagen", "t")))
        self.assertEqual(dialog.summary.text(), "Ingen valideringsrapport än.")
        self.assertEqual(dialog.list.count(), 0)

    def test_the_error_message_of_the_status_is_shown(self):
        dialog = self.dialog(ngp.Delivery("id", "plan", ngp.Status("fel", "t", "Något gick sönder")))
        self.assertIn("Något gick sönder", dialog.status.text())

    def test_refresh_shows_the_new_status_or_the_error(self):
        newer = self.delivery("publicerad", [{"id": "a", "label": "l", "status": "OK"}])
        dialog = self.dialog(self.delivery("validerad"), refresh=lambda: newer)
        dialog.btn_refresh.click()
        self.assertIn("Publicerad", dialog.status.text())
        failing = self.dialog(self.delivery(), refresh=mock.Mock(side_effect=ngp.NgpError("Ingen kontakt")))
        failing.btn_refresh.click()
        self.assertEqual(failing.summary.text(), "Ingen kontakt")

    def test_there_is_no_refresh_button_without_a_callback(self):
        self.assertTrue(self.dialog(self.delivery()).btn_refresh.isHidden())

    def test_the_confirmation_names_the_environment_the_producer_and_the_consequences(self):
        text = confirmation_text(ngp.environment_config("ver", "x"), "Kv Väktaren", "Eskilstuna", "0484", 0, False)
        for expected in ("Kv Väktaren", "Eskilstuna", "0484", "Verifiering", ngp.VER_BASE, "kan inte ångras"):
            self.assertIn(expected, text)
        self.assertNotIn("produktionsmiljön", text)

    def test_production_errors_and_resuming_are_stated_plainly(self):
        text = confirmation_text(ngp.environment_config("prod", "x"), "", "Eskilstuna", "0484", 3, True)
        self.assertIn("produktionsmiljön", text)
        self.assertIn("publiceras i geodatakatalogen", text)
        self.assertIn("3 fel", text)
        self.assertIn("laddas upp igen", text)
        self.assertIn("utan namn", text)


class ToolBarDeliveryTests(ExportCase):
    """Leverans via NGP-dialogen med en låtsasklient; bakgrundsuppgiften ersätts av ett direkt anrop."""

    def setUp(self):
        super().setUp()
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)
        self.addCleanup(lambda: SettingsTests._clear())
        settings.set_ngp_config(ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, "cfg"))
        self.client = mock.Mock()
        self.delivery = ngp.Delivery("0f0e0d0c-0b0a-4090-8080-0706050403aa", "planid", ngp.Status("validerad", "t"),
                                     ngp.Report.parse({"tests": 1, "testcase": []}))
        self.client.deliver.return_value = self.delivery
        self.requests = []
        self.answer = UPLOAD
        self.patches = [
            mock.patch.object(self.toolbar, "_make_client", return_value=self.client),
            mock.patch.object(self.toolbar, "_run_delivery", side_effect=self.run_inline),
            mock.patch.object(self.toolbar, "_ask_ngp", side_effect=self.ask),
            mock.patch("rita_detaljplan.gui.plan_toolbar.DeliveryDialog"),
        ]
        self.dialog_cls = [p.start() for p in self.patches][-1]
        for p in self.patches:
            self.addCleanup(p.stop)

    def ask(self, request):
        self.requests.append(request)
        return self.answer

    @staticmethod
    def run_inline(work, done):
        try:
            result = work(lambda text: None)
        except Exception as exc:  # noqa: BLE001
            done(exc, None)
        else:
            done(None, result)

    def test_the_button_has_an_icon_and_follows_the_plan_area(self):
        self.assertFalse(self.toolbar.act_deliver.icon().isNull())
        pump()
        self.toolbar.refresh()
        self.assertTrue(self.toolbar.act_deliver.isEnabled())
        QgsProject.instance().clear()
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_deliver.isEnabled())

    def test_the_dialog_opens_even_when_the_delivery_settings_are_missing(self):
        settings.set_ngp_config(ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, ""))
        self.answer = None
        self.assertFalse(self.toolbar.deliver())
        self.assertEqual(len(self.requests), 1, "alla får komma in i dialogen")

    def test_a_delivery_chosen_with_missing_settings_is_stopped_with_a_pointer_to_the_settings(self):
        settings.set_ngp_config(ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, ""))
        self.assertFalse(self.toolbar.deliver())
        self.assertTrue(any("autentiseringskonfiguration" in m and "Inställningar" in m for m in self.messages()))
        self.client.deliver.assert_not_called()

    def test_a_missing_municipality_stops_the_delivery_but_not_the_dialog(self):
        self.controller.set_plan_values({"kommun": None})
        self.assertFalse(self.toolbar.deliver())
        self.assertEqual(self.requests[0].kommunkod, "")
        self.assertTrue(any("Kommunen är inte angiven" in m for m in self.messages()))
        self.client.deliver.assert_not_called()

    def test_cancelling_the_dialog_delivers_nothing(self):
        self.answer = None
        self.assertFalse(self.toolbar.deliver())
        self.client.deliver.assert_not_called()

    def test_a_confirmed_delivery_uploads_the_export_for_the_municipality_and_shows_the_result(self):
        self.assertTrue(self.toolbar.deliver())
        collection, provider, existing, progress = self.client.deliver.call_args.args
        self.assertEqual(provider, "0484")
        self.assertIsNone(existing)
        self.assertEqual(collection["features"][0]["properties"]["namn"], "Kv Väktaren")
        self.assertEqual(collection["feature:mediatyp"], MEDIA_V4)
        request = self.requests[0]
        self.assertEqual((request.plan_name, request.kommun, request.kommunkod), ("Kv Väktaren", "Eskilstuna", "0484"))
        self.dialog_cls.assert_called_once()
        self.dialog_cls.return_value.exec.assert_called_once()
        self.assertTrue(any("fick status validerad" in m for m in self.messages()), self.messages())

    def test_the_reception_is_remembered_with_the_environment(self):
        self.toolbar.deliver()
        self.assertEqual(self.controller.last_delivery(),
                         {"mottagning": "0f0e0d0c-0b0a-4090-8080-0706050403aa", "plan": "planid", "miljo": "ver"})

    def test_after_a_validation_error_the_next_delivery_reuses_the_reception(self):
        self.controller.remember_delivery("0f0e0d0c-0b0a-4090-8080-0706050403bb", "planid", "ver")
        self.toolbar.deliver()
        self.assertEqual(self.client.deliver.call_args.args[2], "0f0e0d0c-0b0a-4090-8080-0706050403bb")
        self.assertTrue(self.requests[0].resuming)

    def test_a_reception_from_another_environment_is_not_reused(self):
        self.controller.remember_delivery("0f0e0d0c-0b0a-4090-8080-0706050403bb", "planid", "prod")
        self.toolbar.deliver()
        self.assertIsNone(self.client.deliver.call_args.args[2])
        self.assertFalse(self.requests[0].resuming)

    def test_errors_in_the_plan_are_passed_to_the_dialog(self):
        self.layers["anvandning_yta"].deleteFeature(self.right.id())
        self.toolbar.deliver()
        self.assertGreater(self.requests[0].errors, 0)

    def test_a_failed_delivery_is_reported_and_nothing_is_remembered(self):
        self.client.deliver.side_effect = ngp.NgpError("Behörighet saknas")
        self.toolbar.deliver()
        self.assertTrue(any("misslyckades" in m and "Behörighet saknas" in m for m in self.messages()))
        self.assertEqual(self.controller.last_delivery(), {})
        self.dialog_cls.assert_not_called()

    def test_an_unexpected_exception_is_reported_with_its_type(self):
        self.client.deliver.side_effect = KeyError("x")
        self.toolbar.deliver()
        self.assertTrue(any("KeyError" in m for m in self.messages()))

    def test_a_delivery_with_validation_errors_is_reported_as_a_warning(self):
        self.client.deliver.return_value = ngp.Delivery("0f0e0d0c-0b0a-4090-8080-0706050403cc", "p",
                                                        ngp.Status("valideringsfel", "t"), None)
        self.toolbar.deliver()
        bar = self.iface.messageBar()
        self.assertTrue(any("valideringsfel" in c.args[1] for c in bar.pushWarning.call_args_list + bar.pushInfo.call_args_list))

    def test_the_dialog_can_refresh_the_status(self):
        self.toolbar.deliver()
        refresh = self.dialog_cls.call_args.args[2]
        refresh()
        self.client.refresh.assert_called_once_with("0f0e0d0c-0b0a-4090-8080-0706050403aa", "planid")


class NgpDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    GOOD = ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, "cfg")
    REQUEST = NgpRequest("Kv Väktaren", "Eskilstuna", "0484", 2, 3, False)

    def dialog(self, config=None, request=None, open_settings=None, open_validation=None):
        holder = {"config": config or self.GOOD}
        dialog = NgpDialog(request or self.REQUEST, lambda: holder["config"], open_settings,
                           open_validation=open_validation)
        dialog.holder = holder
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_validation_button_calls_the_check_and_is_hidden_without_one(self):
        calls = []
        dialog = self.dialog(open_validation=lambda: calls.append("kontroll"))
        self.assertFalse(dialog.btn_validate.isHidden())
        dialog.btn_validate.click()
        self.assertEqual(calls, ["kontroll"])
        self.assertTrue(self.dialog().btn_validate.isHidden())

    def ok(self, dialog):
        return dialog.buttons.button(dialog.buttons.StandardButton.Ok)

    def test_with_complete_settings_delivery_is_the_default_and_both_choices_are_open(self):
        dialog = self.dialog()
        self.assertTrue(dialog.upload.isEnabled())
        self.assertEqual(dialog.choice(), UPLOAD)
        self.assertEqual(self.ok(dialog).text(), "Leverera")
        self.assertIn("2 fel", dialog.check.text())
        self.assertIn("Verifiering", dialog.upload_info.text())
        self.assertFalse(dialog.problems.isVisibleTo(dialog))

    def test_missing_settings_turn_delivery_off_but_the_file_choice_still_works(self):
        dialog = self.dialog(ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, ""))
        self.assertFalse(dialog.upload.isEnabled())
        self.assertEqual(dialog.choice(), FILE)
        self.assertEqual(self.ok(dialog).text(), "Spara fil…")
        self.assertTrue(self.ok(dialog).isEnabled())
        self.assertIn("autentiseringskonfiguration", dialog.problems.text())
        self.assertTrue(dialog.problems.isVisibleTo(dialog))

    def test_a_missing_municipality_turns_delivery_off_with_an_explanation(self):
        dialog = self.dialog(request=NgpRequest("Plan", "", "", 0, 0, False))
        self.assertFalse(dialog.upload.isEnabled())
        self.assertIn("Kommunen är inte angiven", dialog.problems.text())
        self.assertEqual(dialog.choice(), FILE)

    def test_the_two_choices_exclude_each_other(self):
        dialog = self.dialog()
        dialog.file.setChecked(True)
        self.assertFalse(dialog.upload.isChecked())
        self.assertEqual(dialog.choice(), FILE)
        self.assertEqual(self.ok(dialog).text(), "Spara fil…")
        dialog.upload.setChecked(True)
        self.assertFalse(dialog.file.isChecked())

    def test_the_settings_button_opens_the_settings_and_re_reads_them(self):
        dialog = self.dialog(ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, ""),
                             open_settings=lambda: dialog.holder.update(config=self.GOOD))
        self.assertTrue(dialog.btn_settings.isVisibleTo(dialog))
        self.assertFalse(dialog.upload.isEnabled())
        dialog.btn_settings.click()
        self.assertTrue(dialog.upload.isEnabled())
        self.assertEqual(dialog.choice(), UPLOAD)
        self.assertFalse(dialog.btn_settings.isVisibleTo(dialog))

    def test_the_users_choice_of_file_is_kept_when_the_settings_are_re_read(self):
        dialog = self.dialog()
        dialog.file.setChecked(True)
        dialog.refresh()
        self.assertEqual(dialog.choice(), FILE)

    def test_production_needs_an_explicit_acknowledgement_before_delivery(self):
        dialog = self.dialog(ngp.NgpConfig("prod", ngp.PROD_BASE, ngp.PROD_TOKEN, "cfg"))
        self.assertTrue(dialog.understand.isVisibleTo(dialog))
        self.assertFalse(self.ok(dialog).isEnabled())
        self.assertIn("produktionsmiljön", dialog.upload_info.text())
        dialog.understand.setChecked(True)
        self.assertTrue(self.ok(dialog).isEnabled())
        dialog.file.setChecked(True)
        self.assertTrue(self.ok(dialog).isEnabled(), "att spara en fil kräver ingen bekräftelse")

    def test_the_verification_environment_needs_no_acknowledgement(self):
        dialog = self.dialog()
        self.assertFalse(dialog.understand.isVisibleTo(dialog))
        self.assertTrue(self.ok(dialog).isEnabled())

    def test_a_clean_plan_says_so_and_resuming_is_mentioned(self):
        dialog = self.dialog(request=NgpRequest("Plan", "Eskilstuna", "0484", 0, 0, True))
        self.assertIn("inga avvikelser", dialog.check.text())
        self.assertIn("laddas upp igen", dialog.upload_info.text())

    def test_the_file_choice_explains_what_the_file_is_for(self):
        dialog = self.dialog()
        self.assertIn("NGP-supporten", dialog.file_info.text())


class BackgroundTaskTests(ExportCase):
    def test_the_delivery_runs_in_a_background_task_and_reports_back(self):
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(toolbar.deleteLater)
        finished = []
        toolbar._run_delivery(lambda progress: (progress("steg"), "klart")[1], lambda exc, result: finished.append((exc, result)))
        deadline = time.time() + 15
        while not finished and time.time() < deadline:
            pump(0.05)
        self.assertEqual(finished, [(None, "klart")])
        self.assertEqual(toolbar._tasks, [])

    def test_an_exception_in_the_task_reaches_the_callback(self):
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(toolbar.deleteLater)
        finished = []

        def broken(progress):
            raise ngp.NgpError("nej")

        toolbar._run_delivery(broken, lambda exc, result: finished.append(exc))
        deadline = time.time() + 15
        while not finished and time.time() < deadline:
            pump(0.05)
        self.assertEqual(len(finished), 1)
        self.assertIsInstance(finished[0], ngp.NgpError)


class RealExportOverHttp(ExportCase):
    def test_the_export_of_a_complete_plan_is_delivered_and_validated(self):
        fake = FakeNgp()
        fake.start()
        self.addCleanup(fake.stop)
        client = ngp.NgpClient(ngp.NgpConfig("egen", fake.base_url, fake.token_url, "x"),
                               transport=lambda m, u, h, b, a: ngp.qgis_transport(m, u, h, b, ""), sleep=no_sleep)
        delivery = client.deliver(self.controller.export_ngp(), "0484", interval=0)
        self.assertTrue(delivery.ok, delivery.report and delivery.report.problems)
        stored = fake.receptions[delivery.mottagningsid]["changes"][delivery.plan_id]["content"]
        self.assertEqual(len(stored["features"]), 5)
        self.assertEqual(stored["features"][0]["properties"]["beslutsinformation"][0]["diarienummerKommun"], "KS 2023/45")


if __name__ == "__main__":
    unittest.main()
