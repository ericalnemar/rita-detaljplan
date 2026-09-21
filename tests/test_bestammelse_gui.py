"""Tester för bestämmelseväljaren och den riktiga nätverkskoden (kräver QGIS med offscreen-grafik)."""
import json
import sys
import tempfile
import threading
import unittest
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from qgis_app import get_app
    from qgis.PyQt.QtWidgets import QDialogButtonBox
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

if HAVE_QGIS:
    from rita_detaljplan.core import bestammelse as bm
    from rita_detaljplan.core import catalog as cat
    from rita_detaljplan.core.catalog_store import CatalogError, CatalogService, qgis_fetch
    from rita_detaljplan.gui.bestammelse_dialog import DEVIATION_TEXT, BestammelseDialog

FIXTURE = json.loads((ROOT / "tests" / "data" / "katalog_urval.json").read_text(encoding="utf-8"))
LUTNING = "DP_KM_Eg_MarkensAnordOchVeg_Markforhallanden_StorstaLutning"
RIVNING = "DP_AP_Eg_Rivningsforbud_Rivningsforbud_Annan"
UTNYTT = "DP_KM_Eg_Utnytt_StorstaAreaProc_ByggnadsEgen"
BUNDLED = ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json"


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()
        cls.catalog = cat.Catalog.from_api_release(FIXTURE)

    def entry(self, kod):
        return next(e for e in self.catalog.entries if e.kod == kod)

    def select(self, dialog, text):
        dialog.search.setText(text)
        self.assertEqual(dialog.table.rowCount(), 1, text)
        dialog.table.selectRow(0)

    def ok(self, dialog):
        return dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()

    def test_lists_current_deliverable_entries_only_by_default(self):
        dialog = BestammelseDialog(self.catalog)
        self.assertEqual(dialog.table.rowCount(), len(self.catalog.search()))
        self.assertFalse(self.ok(dialog), "inget val ännu")
        self.assertIsNone(dialog.selected_entry())

    def test_text_variable_must_be_filled_before_ok(self):
        dialog = BestammelseDialog(self.catalog)
        self.select(dialog, "rivning")
        self.assertFalse(self.ok(dialog))
        self.assertIn("Värde saknas för [rivningsförbud]", dialog.problems.text())
        dialog._editors[0]["value"].setText("Byggnaden får inte rivas")
        self.assertTrue(self.ok(dialog))
        self.assertEqual(dialog.preview.text(), "Byggnaden får inte rivas")
        attrs = dialog.attributes()
        self.assertEqual(attrs["planbestammelsekatalogreferens"], self.entry(RIVNING).id)
        self.assertEqual(attrs["bestammelseformulering"], "[rivningsförbud:text]")

    def test_decimal_entry_prefills_unit_and_value_type(self):
        dialog = BestammelseDialog(self.catalog)
        self.select(dialog, "StorstaAreaProc")
        editor = dialog._editors[0]
        self.assertEqual(editor["enhet"].currentData(), "procent")
        self.assertEqual(editor["vardetyp"].currentText(), "max")
        self.assertFalse(self.ok(dialog), "värdet saknas")
        editor["value"].setText("30")
        self.assertTrue(self.ok(dialog))
        self.assertIn("30", dialog.preview.text())

    def test_slope_needs_units_chosen_by_the_user(self):
        dialog = BestammelseDialog(self.catalog)
        self.select(dialog, "StorstaLutning")
        first, second = dialog._editors
        first["value"].setText("1")
        second["value"].setText("20")
        self.assertFalse(self.ok(dialog))
        self.assertIn("Enhet saknas", dialog.problems.text())
        for editor in (first, second):
            editor["enhet"].setCurrentIndex(editor["enhet"].findData("antal"))
        self.assertTrue(self.ok(dialog))
        self.assertEqual(dialog.preview.text(), "Största lutning är 1:20. (Pilen pekar uppåt)")

    def test_technical_installations_lock_the_motive_and_the_formulation(self):
        dialog = BestammelseDialog(self.catalog)
        self.select(dialog, "Tekniska anläggningar")
        self.assertTrue(self.ok(dialog))
        self.assertFalse(dialog.motiv.isEnabled())
        self.assertFalse(dialog.chk_custom.isEnabled(), "Tekniska anläggningar får inte preciseras")
        self.assertEqual(dialog.motive(), "Tekniska anläggningar")
        self.assertEqual(dialog.attributes()["motiv"], "Tekniska anläggningar")
        self.assertFalse(dialog.values_box.isVisible())

    def test_layer_filter_limits_the_list_to_one_layer(self):
        for layer in ("egenskap_yta", "egenskap_linje", "anvandning_yta"):
            dialog = BestammelseDialog(self.catalog, layer)
            self.assertGreater(dialog.table.rowCount(), 0, layer)
            for row in range(dialog.table.rowCount()):
                entry = self.catalog.get(dialog.table.item(row, 0).data(0x0100))
                self.assertEqual(entry.layer_name, layer)
            self.assertFalse(dialog.type_combo.isEnabled(), "lagret avgör redan typen")

    def test_custom_formulation_shows_a_deviation_warning(self):
        dialog = BestammelseDialog(self.catalog)
        self.select(dialog, "StorstaAreaProc")
        dialog._editors[0]["value"].setText("30")
        self.assertEqual(dialog.deviation.text(), "")
        self.assertIsNone(dialog.custom_formulation())

        dialog.chk_custom.setChecked(True)
        self.assertEqual(dialog.formulation_edit.toPlainText(), self.entry(UTNYTT).formulering)
        self.assertEqual(dialog.deviation.text(), "", "oförändrad text är ingen avvikelse")
        dialog.formulation_edit.setPlainText("Byggnadsarean är högst [utnyttjandegrad:decimaltal] % av tomten.")
        self.assertEqual(dialog.deviation.text(), DEVIATION_TEXT)
        self.assertTrue(self.ok(dialog), "en avvikelse varnar men stoppar inte")
        self.assertEqual(dialog.preview.text(), "Byggnadsarean är högst 30 % av tomten.")
        attrs = dialog.attributes()
        self.assertTrue(attrs["avviker"])
        self.assertIn("[utnyttjandegrad:decimaltal]", attrs["bestammelseformulering"])

    def test_custom_formulation_that_loses_its_variable_order_is_rejected(self):
        dialog = BestammelseDialog(self.catalog)
        self.select(dialog, "StorstaLutning")
        dialog.chk_custom.setChecked(True)
        dialog.formulation_edit.setPlainText("Lutning [lutning2:decimaltal] och [lutning1:decimaltal].")
        self.assertFalse(self.ok(dialog))
        self.assertIn("samma ordning", dialog.problems.text())
        dialog.chk_custom.setChecked(False)
        self.assertIsNone(dialog.custom_formulation())

    def test_editing_an_existing_bestammelse_prefills_the_dialog(self):
        entry = self.entry(LUTNING)
        values = [bm.VariableValue(entry.variables[0], "1", "max", "antal"),
                  bm.VariableValue(entry.variables[1], "20", "max", "antal")]
        custom = "Lutningen är högst [lutning1:decimaltal]:[lutning2:decimaltal]."
        dialog = BestammelseDialog(self.catalog, "egenskap_yta", entry, values, "Bra motiv", custom)
        self.assertEqual(dialog.selected_entry().kod, LUTNING)
        self.assertEqual([e["value"].text() for e in dialog._editors], ["1", "20"])
        self.assertEqual(dialog.motive(), "Bra motiv")
        self.assertTrue(dialog.chk_custom.isChecked())
        self.assertEqual(dialog.custom_formulation(), custom)
        self.assertTrue(self.ok(dialog))

    def test_historic_entries_need_a_full_catalog(self):
        dialog = BestammelseDialog(self.catalog)
        self.assertTrue(dialog.chk_historic.isEnabled())  # testunderlaget innehåller upphörda bestämmelser
        before = dialog.table.rowCount()
        dialog.chk_historic.setChecked(True)
        self.assertGreater(dialog.table.rowCount(), before)
        bundled_dialog = BestammelseDialog(cat.Catalog.load(BUNDLED))
        self.assertFalse(bundled_dialog.chk_historic.isEnabled())

    def test_bundled_catalog_opens_and_is_searchable(self):
        dialog = BestammelseDialog(cat.Catalog.load(BUNDLED))
        self.assertGreater(dialog.table.rowCount(), 500)
        dialog.search.setText("prickmark")
        self.assertGreater(dialog.table.rowCount(), 0)


class _Handler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):  # noqa: N802
        body = self.routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class QgisFetchTests(unittest.TestCase):
    """Provar den riktiga nätverkskoden (QgsBlockingNetworkRequest) mot en lokal server."""

    @classmethod
    def setUpClass(cls):
        get_app()
        _Handler.routes = {"/release": [{"id": 7, "typ": {"namn": "Juridisk"}}], "/release/full/platt/7": FIXTURE}
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_fetches_and_parses_json(self):
        self.assertEqual(qgis_fetch("/release", base=self.base)[0]["id"], 7)
        catalog = cat.Catalog.from_api_release(qgis_fetch("/release/full/platt/7", base=self.base))
        self.assertEqual(len(catalog), len(FIXTURE["bestammelser"]))

    def test_http_error_becomes_catalog_error(self):
        with self.assertRaises(CatalogError) as caught:
            qgis_fetch("/finns/inte", base=self.base)
        self.assertIn("Kunde inte nå Boverkets", str(caught.exception))

    def test_unreachable_server_becomes_catalog_error(self):
        with self.assertRaises(CatalogError):
            qgis_fetch("/release", base="http://127.0.0.1:1")

    def test_service_can_update_through_the_real_network_stack(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            bundled = Path(tmp) / "bundled.json"
            cat.Catalog.from_api_release(FIXTURE).only_current().save(bundled)
            service = CatalogService(Path(tmp) / "cache", bundled, partial(qgis_fetch, base=self.base))
            result = service.update()
        self.assertTrue(result.updated)
        self.assertTrue(result.catalog.has_historic)


if __name__ == "__main__":
    unittest.main()
