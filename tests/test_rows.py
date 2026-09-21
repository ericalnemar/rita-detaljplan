"""Tilldelade bestämmelser (rader): numrering, sammansatta beteckningar och visning. Kräver inte QGIS."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_detaljplan.core import bestammelse as bm  # noqa: E402
from rita_detaljplan.core import catalog as cat  # noqa: E402
from rita_detaljplan.core import rows  # noqa: E402

FIXTURE = json.loads((ROOT / "tests" / "data" / "katalog_urval.json").read_text(encoding="utf-8"))
CATALOG = cat.Catalog.from_api_release(FIXTURE)
UTNYTT = "DP_KM_Eg_Utnytt_StorstaAreaProc_ByggnadsEgen"


def entry(kod):
    return next(e for e in CATALOG.entries if e.kod == kod)


def filled(e, text="5"):
    values = []
    for item in bm.default_values(e):
        if item.variable.datatype == "decimaltal":
            values.append(bm.VariableValue(item.variable, text, item.vardetyp or "max", item.enhet or "antal"))
        else:
            values.append(bm.VariableValue(item.variable, "text"))
    return values


def row(kod, existing=(), value="5", **kwargs):
    e = entry(kod)
    return rows.build_row(e, filled(e, value), existing_rows=list(existing), **kwargs)


class Numbering(unittest.TestCase):
    def test_indexed_labels_are_numbered_per_letter(self):
        first = row("DP_KM_R2_Motorsport")
        second = row("DP_KM_R2_Bygdegard", [first])
        self.assertEqual((first["beteckning"], first["beteckningsindex"]), ("R1", 1))
        self.assertEqual((second["beteckning"], second["beteckningsindex"]), ("R2", 2))

    def test_fixed_labels_get_no_index(self):
        industri = row("DP_KM_J2")
        self.assertEqual((industri["beteckning"], industri["beteckningsindex"]), ("J", None))

    def test_the_same_provision_gets_the_same_label_everywhere_in_the_plan(self):
        first = row(UTNYTT, value="30")
        again = row(UTNYTT, [first], value="30")
        self.assertEqual((again["beteckning"], again["beteckningsindex"]), (first["beteckning"], 1))

    def test_the_same_provision_with_other_values_gets_the_next_number(self):
        a = row(UTNYTT, value="30")
        b = row(UTNYTT, [a], value="40")
        self.assertEqual((a["beteckning"], b["beteckning"]), ("e1", "e2"))

    def test_the_motive_does_not_make_two_provisions_different(self):
        a = row(UTNYTT, value="30", motiv="Motiv A")
        b = row(UTNYTT, [a], value="30", motiv="Motiv B")
        self.assertEqual(a["beteckning"], b["beteckning"])
        self.assertEqual(rows.identity(a), rows.identity(b))

    def test_a_freed_index_is_reused(self):
        first = row("DP_KM_R2_Motorsport")
        second = row("DP_KM_R2_Bygdegard", [first])
        third = rows.build_row(entry("DP_KM_R2_Motorsport"), [], existing_rows=[second])
        self.assertEqual(third["beteckning"], "R1", "R1 är ledig när första raden tagits bort")

    def test_different_letters_are_numbered_independently(self):
        motor = row("DP_KM_R2_Motorsport")
        area = row(UTNYTT, [motor])
        self.assertEqual(area["beteckning"], "e1")

    def test_non_deliverable_provisions_cannot_be_added(self):
        transitional = next(e for e in CATALOG.entries if e.typ == "Övergångsbestämmelse")
        with self.assertRaises(ValueError):
            rows.build_row(transitional, [])


class RowContents(unittest.TestCase):
    def test_a_row_knows_its_layer_but_not_a_separate_type_column(self):
        self.assertEqual(row("DP_KM_J2")["tabell"], "anvandning_yta")
        self.assertEqual(row(UTNYTT)["tabell"], "egenskap_yta")
        self.assertNotIn("bestammelsetyp", row("DP_KM_J2"))

    def test_a_row_carries_colour_form_and_symbol_for_symbology(self):
        industri = row("DP_KM_J2")
        self.assertEqual((industri["farg"], industri["anvandningsform"]), ("Blågrå", "Kvartersmark"))
        line = next(e for e in CATALOG.search(layer="egenskap_linje") if e.symbol.startswith("Utfart"))
        self.assertEqual(rows.build_row(line, filled(line))["symbol"], "Utfart får inte finnas")

    def test_the_row_keeps_the_catalog_formulation_and_stores_values_separately(self):
        built = row(UTNYTT, value="30")
        self.assertIn("[utnyttjandegrad:decimaltal]", built["bestammelseformulering"])
        self.assertEqual(json.loads(built["bestammelsevarde"])[0]["variabelvarde"], "30")


class AreaSummary(unittest.TestCase):
    def test_an_area_without_provisions_is_unassigned(self):
        summary = rows.summarize([])
        self.assertEqual(summary["bestammelser"], 0)
        self.assertIsNone(summary["beteckning"])
        self.assertIsNone(summary["farg"])

    def test_a_combined_use_writes_its_letters_together(self):
        b = {**row("DP_KM_J2"), "beteckning": "B"}
        c = {**row("DP_KM_J2"), "beteckning": "C"}
        summary = rows.summarize([b, c])
        self.assertEqual((summary["beteckning"], summary["bestammelser"]), ("BC", 2))

    def test_properties_are_written_with_a_space_between(self):
        a = row(UTNYTT, value="30")
        b = row(UTNYTT, [a], value="40")
        self.assertEqual(rows.summarize([a, b])["beteckning"], "e1 e2")

    def test_the_same_label_twice_is_written_once(self):
        a = row(UTNYTT, value="30")
        self.assertEqual(rows.summarize([a, dict(a)])["beteckning"], "e1")

    def test_colour_symbol_and_form_come_from_the_first_row_that_has_them(self):
        plain = {"tabell": "egenskap_yta", "beteckning": "x"}
        symbolic = {"tabell": "egenskap_yta", "beteckning": "y", "symbol": "Stängsel ska finnas",
                    "anvandningsform": "Kvartersmark"}
        summary = rows.summarize([plain, symbolic])
        self.assertEqual((summary["symbol"], summary["anvandningsform"]), ("Stängsel ska finnas", "Kvartersmark"))

    def test_provisions_without_any_label_still_count_as_assigned(self):
        summary = rows.summarize([{"tabell": "egenskap_linje", "beteckning": None}])
        self.assertEqual((summary["bestammelser"], summary["beteckning"]), (1, ""))


class Presentation(unittest.TestCase):
    def test_display_text_fills_in_stored_values(self):
        built = row(UTNYTT, value="30")
        self.assertEqual(rows.display_text(built), "Största byggnadsarea är 30 % av fastighetsarean inom egenskapsområdet.")
        self.assertTrue(rows.describe(built).startswith("e1 – Största byggnadsarea är 30 %"))

    def test_describe_without_label_is_just_the_text(self):
        built = {"beteckning": None, "bestammelseformulering": "Utfartsförbud", "bestammelsevarde": None}
        self.assertEqual(rows.describe(built), "Utfartsförbud")

    def test_broken_stored_values_do_not_crash_the_display(self):
        built = {"bestammelseformulering": "Höjd [h:decimaltal] m", "bestammelsevarde": "inte json"}
        self.assertEqual(rows.display_text(built), "Höjd [h:decimaltal] m")


if __name__ == "__main__":
    unittest.main()
