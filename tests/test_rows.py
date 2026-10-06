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


BUNDLED = cat.Catalog.load(ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json")
DAGV = "DP_AP_Eg_UtformAP_Dagv_Annan"  # katalogens beteckning är mallen "[beteckning:text]#"
ROMAN = "DP_KM_Eg_Hojd_LagstaHojd_LagstaVan_Aldre"  # "[romerska siffror:text]", utan index


class FreeLabel(unittest.TestCase):
    """Katalogens beteckning kan vara en mall med en variabel: planförfattaren väljer själv bokstäverna."""

    def built(self, kod, label, existing=(), **kwargs):
        e = next(x for x in BUNDLED.entries if x.kod == kod)
        return rows.build_row(e, filled(e), existing_rows=list(existing), label=label, **kwargs)

    def test_the_label_the_user_chose_is_used_with_the_index_added(self):
        first = self.built(DAGV, "Dv")
        self.assertEqual((first["beteckning"], first["beteckningsindex"]), ("Dv1", 1))
        self.assertNotIn("[", first["beteckning"], "mallen ska aldrig hamna på plankartan")

    def test_the_index_counts_per_chosen_label(self):
        first = self.built(DAGV, "Dv")
        other = self.built(DAGV, "Dv", [first])
        self.assertEqual(other["beteckning"], "Dv1", "samma bestämmelse och beteckning delar index")
        different = self.built(DAGV, "Dx", [first])
        self.assertEqual(different["beteckning"], "Dx1", "en annan beteckning har egen numrering")
        self.assertNotEqual(different["beteckning"], first["beteckning"])

    def test_digits_typed_at_the_end_are_dropped_because_the_number_is_added_automatically(self):
        """Regression: skrev man "dagvatten1" blev det "dagvatten11", och två bestämmelser kunde få likadan beteckning."""
        first = self.built(DAGV, "dagvatten1")
        self.assertEqual((first["beteckning"], first["beteckningsindex"]), ("dagvatten1", 1))
        second = self.built(DAGV, "dagvatten1", [first], formulation="Annan text [utformning av områden för dagvatten:text]")
        self.assertEqual(second["beteckning"], "dagvatten2", "olika bestämmelser får olika beteckningar")
        self.assertEqual(self.built(DAGV, "f 12")["beteckning"], "f1")
        e = next(x for x in BUNDLED.entries if x.kod == DAGV)
        self.assertTrue(rows.label_problems(e, "123"), "bara siffror ger ingen beteckning")
        self.assertEqual(rows.chosen_label(next(x for x in BUNDLED.entries if x.kod == ROMAN), "II"), "II")
        self.assertEqual(rows.chosen_label(next(x for x in BUNDLED.entries if x.kod == ROMAN), "2"), "2",
                         "utan index är siffror en del av beteckningen")

    def test_a_label_without_index_is_used_as_it_is(self):
        self.assertEqual(self.built(ROMAN, "II")["beteckning"], "II")
        self.assertIsNone(self.built(ROMAN, "II")["beteckningsindex"])

    def test_a_hash_in_the_text_is_ignored_and_a_missing_label_is_reported(self):
        e = next(x for x in BUNDLED.entries if x.kod == DAGV)
        self.assertEqual(self.built(DAGV, "D#v")["beteckning"], "Dv1")
        self.assertTrue(rows.label_problems(e, ""))
        self.assertTrue(rows.label_problems(e, "  "))
        self.assertEqual(rows.label_problems(e, "Dv"), [])
        plain = next(x for x in BUNDLED.entries if x.kod == "DP_KM_J2")
        self.assertEqual(rows.label_problems(plain, None), [], "bestämmelser med fast beteckning kräver ingen")

    def test_the_label_text_can_be_read_back_from_the_row(self):
        e = next(x for x in BUNDLED.entries if x.kod == DAGV)
        self.assertEqual(rows.label_text(e, self.built(DAGV, "Dv")), "Dv")
        plain = next(x for x in BUNDLED.entries if x.kod == "DP_KM_J2")
        self.assertIsNone(rows.label_text(plain, row("DP_KM_J2")))

    def test_a_template_saved_by_an_older_version_is_read_back_as_an_empty_label(self):
        e = next(x for x in BUNDLED.entries if x.kod == DAGV)
        self.assertEqual(rows.label_text(e, {"beteckning": "[beteckning:text]1", "beteckningsindex": 1}), "")

    def test_the_list_label_of_such_an_entry_does_not_show_the_template(self):
        e = next(x for x in BUNDLED.entries if x.kod == DAGV)
        self.assertEqual(e.label_base, "")


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
