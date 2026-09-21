"""Tester för planbestämmelsekatalogen och bestämmelselogiken. Kräver inte QGIS.

Testunderlaget tests/data/katalog_urval.json är ett urval av Boverkets API-svar
(/release/full/platt/7) och skapas av tools/update_bundled_catalog.py --fixture.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_detaljplan.core import bestammelse as bm  # noqa: E402
from rita_detaljplan.core import catalog as cat  # noqa: E402
from rita_detaljplan.core import model  # noqa: E402

FIXTURE = json.loads((ROOT / "tests" / "data" / "katalog_urval.json").read_text(encoding="utf-8"))
BUNDLED = ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json"

LUTNING = "DP_KM_Eg_MarkensAnordOchVeg_Markforhallanden_StorstaLutning"
UTNYTT = "DP_KM_Eg_Utnytt_StorstaAreaProc_ByggnadsEgen"
BYGGLOV = "DP_KM_Eg_VillkorLov_SkyddSakerhet_Bygglov"
RIVNING = "DP_AP_Eg_Rivningsforbud_Rivningsforbud_Annan"
TEKNISK = "DP_KM_E2"


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = cat.Catalog.from_api_release(FIXTURE)

    def entry(self, kod):
        found = [e for e in self.catalog.entries if e.kod == kod]
        self.assertEqual(len(found), 1, kod)
        return found[0]


class CatalogParsing(Fixture):
    def test_variables_are_parsed_in_order(self):
        variables = self.entry(LUTNING).variables
        self.assertEqual([(v.name, v.datatype) for v in variables],
                         [("lutning1", "decimaltal"), ("lutning2", "decimaltal")])
        self.assertEqual(self.entry(RIVNING).variables[0].token, "[rivningsförbud:text]")

    def test_only_text_variable_named_text_is_optional(self):
        self.assertTrue(cat.Variable("text", "text", "[text:text]").optional)
        self.assertFalse(cat.Variable("orsak", "text", "[orsak:text]").optional)
        self.assertFalse(cat.Variable("text", "decimaltal", "[text:decimaltal]").optional)

    def test_render_fills_variables_in_order(self):
        text = cat.render("Största lutning är [a:decimaltal]:[b:decimaltal].", ["1", "20"])
        self.assertEqual(text, "Största lutning är 1:20.")

    def test_guess_unit(self):
        utnytt = self.entry(UTNYTT)
        self.assertEqual(cat.guess_unit(utnytt.formulering, utnytt.variables[0]), "procent")
        lutning = self.entry(LUTNING)
        self.assertIsNone(cat.guess_unit(lutning.formulering, lutning.variables[0]))
        self.assertIsNone(cat.guess_unit("[x:text]", cat.Variable("x", "text", "[x:text]")))

    def test_layer_and_delivery_type_mapping(self):
        self.assertEqual(self.entry(UTNYTT).layer_name, "egenskap_yta")
        self.assertEqual(self.entry(UTNYTT).delivery_type, "egenskapsbestämmelse")
        self.assertEqual(self.entry(TEKNISK).layer_name, "anvandning_yta")
        self.assertEqual(self.entry(TEKNISK).delivery_type, "användningsbestämmelse")
        self.assertTrue(self.entry(TEKNISK).is_use)
        for entry in self.catalog.entries:
            if entry.deliverable and entry.geometrityp == "Linje":
                self.assertEqual(entry.layer_name, "egenskap_linje")
            self.assertNotEqual(entry.layer_name, "egenskap_punkt")

    def test_property_points_are_not_used(self):
        """Egenskapspunkter saknar funktion i planen: alla egenskaper gäller hela ytan, linjer är bara utfart/stängsel."""
        bundled = cat.Catalog.load(ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json")
        points = [e for e in bundled.entries if e.geometrityp == "Punkt"]
        self.assertTrue(points, "katalogen har punktbestämmelser som ska vara ointressanta")
        self.assertFalse(any(e.deliverable for e in points))
        self.assertFalse(any(e.geometrityp == "Punkt" for e in bundled.search()))
        lines = bundled.search(layer="egenskap_linje")
        self.assertTrue(lines and all(e.symbol in ("Utfart får inte finnas", "Stängsel ska finnas") for e in lines),
                        "egenskapslinjer är bara utfartsförbud och stängsel")

    def test_labels_and_symbol_names_are_cleaned(self):
        self.assertEqual(cat._clean_symbol_name("Utfart får inte finnas (1987 - pågående)"), "Utfart får inte finnas")
        self.assertEqual(cat._clean_symbol_name("Höjd (över) nollplanet (1949 - 2012-11-02)"), "Höjd (över) nollplanet")
        self.assertEqual(cat._clean_symbol_name(None), "")
        motor = next(e for e in self.catalog.entries if e.kod == "DP_KM_R2_Motorsport")
        self.assertEqual((motor.beteckning, motor.label_base), ("R#", "R"))
        self.assertEqual(self.entry("DP_KM_J2").label_base, "J")

    def test_use_provisions_have_a_colour_and_line_provisions_a_symbol(self):
        self.assertTrue(all(e.farg for e in self.catalog.entries if e.is_use and e.is_current))
        lines = [e for e in self.catalog.search(layer="egenskap_linje")]
        self.assertTrue(any(e.symbol == "Utfart får inte finnas" for e in lines))
        self.assertTrue(any(e.symbol == "Stängsel ska finnas" for e in lines))

    def test_search_can_be_limited_to_one_layer(self):
        for layer in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            found = self.catalog.search(layer=layer)
            self.assertTrue(found, layer)
            self.assertTrue(all(e.layer_name == layer for e in found))

    def test_transitional_provisions_are_not_deliverable(self):
        transitional = [e for e in self.catalog.entries if e.typ == "Övergångsbestämmelse"]
        self.assertTrue(transitional, "testunderlaget ska innehålla en övergångsbestämmelse")
        self.assertFalse(any(e.deliverable for e in transitional))

    def test_technical_installations_flag(self):
        self.assertTrue(self.entry(TEKNISK).is_technical)
        self.assertFalse(self.entry(UTNYTT).is_technical)

    def test_json_roundtrip_preserves_entries(self):
        again = cat.Catalog.from_json(self.catalog.to_json())
        self.assertEqual(again.release_id, self.catalog.release_id)
        self.assertEqual(again.entries, self.catalog.entries)

    def test_save_and_load_is_atomic_file_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "katalog.json"
            self.catalog.save(path)
            self.assertEqual(len(cat.Catalog.load(path)), len(self.catalog))
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_latest_release_ignores_technical_releases(self):
        releases = [
            {"id": 7, "publicerad": "2025-12-01", "typ": {"namn": "Juridisk"}},
            {"id": 9, "publicerad": "2026-03-01", "typ": {"namn": "Teknisk"}},
            {"id": 6, "publicerad": "2024-05-02", "typ": {"namn": "Juridisk"}},
        ]
        self.assertEqual(cat.latest_release(releases)["id"], 7)
        with self.assertRaises(ValueError):
            cat.latest_release([{"id": 1, "publicerad": "x", "typ": {"namn": "Teknisk"}}])


class CatalogSearch(Fixture):
    def test_search_matches_all_words_case_insensitively(self):
        self.assertEqual([e.kod for e in self.catalog.search("RIVNING")], [RIVNING])
        self.assertEqual(self.catalog.search("rivning xyz"), [])

    def test_search_by_code_and_category(self):
        self.assertTrue(any(e.kod == UTNYTT for e in self.catalog.search("StorstaAreaProc")))
        self.assertTrue(any(e.kod == BYGGLOV for e in self.catalog.search("villkor för lov")))

    def test_historic_and_interpretation_entries_are_hidden_by_default(self):
        default = self.catalog.search()
        self.assertTrue(all(e.is_current and not e.tolkning for e in default))
        self.assertGreater(len(self.catalog.search(include_historic=True)), len(default))
        self.assertTrue(any(e.tolkning for e in self.catalog.search(include_interpretation=True)))

    def test_geometry_and_form_filters(self):
        lines = self.catalog.search(geometrityp="Linje")
        self.assertTrue(lines and all(e.geometrityp == "Linje" for e in lines))
        self.assertEqual(self.catalog.search(geometrityp="Punkt"), [], "punktbestämmelser används inte")
        self.assertTrue(all(e.anvandningsform == "Allmän plats" for e in self.catalog.search(anvandningsform="Allmän plats")))


class BestammelseAttributes(Fixture):
    def test_text_variable_becomes_bestammelsevarde_and_formulation_stays_the_catalog_text(self):
        entry = self.entry(RIVNING)
        values = [bm.VariableValue(entry.variables[0], "Byggnaden får inte rivas")]
        attrs = bm.feature_attributes(entry, values, motiv="Värdefull byggnad")
        self.assertEqual(attrs["bestammelseformulering"], "[rivningsförbud:text]")
        self.assertEqual(attrs["planbestammelsekatalogreferens"], entry.id)
        self.assertEqual(attrs["bestammelsekod"], RIVNING)
        self.assertNotIn("bestammelsetyp", attrs, "lagret avgör typen")
        self.assertEqual(attrs["anvandningsform"], "Allmän plats")
        self.assertIs(attrs["avviker"], False)
        self.assertEqual(json.loads(attrs["bestammelsevarde"]),
                         [{"datatyp": "text", "variabelvarde": "Byggnaden får inte rivas",
                           "beskrivning": "rivningsförbud"}])
        self.assertEqual(attrs["motiv"], "Värdefull byggnad")

    def test_decimal_needs_value_type_and_unit(self):
        entry = self.entry(UTNYTT)
        values = bm.default_values(entry)
        self.assertEqual(values[0].vardetyp, "max")
        self.assertEqual(values[0].enhet, "procent")
        self.assertIn("Värde saknas för [utnyttjandegrad].", bm.check(entry, values))
        values[0] = bm.VariableValue(values[0].variable, "30", None, None)
        problems = bm.check(entry, values)
        self.assertTrue(any("Värdetyp" in p for p in problems))
        self.assertTrue(any("Enhet" in p for p in problems))
        values[0] = bm.VariableValue(values[0].variable, "30,5", "max", "procent")
        self.assertEqual(bm.check(entry, values), [])
        varde = json.loads(bm.feature_attributes(entry, values)["bestammelsevarde"])
        self.assertEqual(varde, [{"datatyp": "decimaltal", "variabelvarde": "30.5", "beskrivning": "utnyttjandegrad",
                                  "vardetyp": "max", "enhet": "procent"}])

    def test_invalid_number_is_rejected(self):
        entry = self.entry(UTNYTT)
        values = [bm.VariableValue(entry.variables[0], "trettio", "max", "procent")]
        self.assertTrue(any("måste vara ett tal" in p for p in bm.check(entry, values)))

    def test_slope_has_two_decimal_values_in_order(self):
        entry = self.entry(LUTNING)
        values = [bm.VariableValue(entry.variables[0], "1", "max", "antal"),
                  bm.VariableValue(entry.variables[1], "20", "max", "antal")]
        stored = json.loads(bm.feature_attributes(entry, values)["bestammelsevarde"])
        self.assertEqual([v["beskrivning"] for v in stored], ["lutning1", "lutning2"])
        self.assertEqual(bm.display_text(entry, values), "Största lutning är 1:20. (Pilen pekar uppåt)")

    def test_wrong_number_of_values_is_reported(self):
        entry = self.entry(LUTNING)
        self.assertTrue(bm.check(entry, [bm.VariableValue(entry.variables[0], "1", "max", "antal")]))

    def test_technical_installations_force_generic_motive(self):
        entry = self.entry(TEKNISK)
        attrs = bm.feature_attributes(entry, [], motiv="Pumpstation för dagvatten")
        self.assertEqual(attrs["bestammelseformulering"], "Tekniska anläggningar")
        self.assertEqual(attrs["motiv"], "Tekniska anläggningar")
        self.assertIsNone(attrs["bestammelsevarde"])

    def test_transitional_provision_cannot_be_used(self):
        entry = next(e for e in self.catalog.entries if e.typ == "Övergångsbestämmelse")
        self.assertTrue(any("kan inte levereras" in p for p in bm.check(entry, bm.default_values(entry))))

    def test_values_can_be_restored_from_stored_json(self):
        entry = self.entry(UTNYTT)
        original = [bm.VariableValue(entry.variables[0], "30", "max", "procent")]
        stored = bm.feature_attributes(entry, original)["bestammelsevarde"]
        restored = bm.values_from_attributes(entry, stored)
        self.assertEqual(restored, original)
        self.assertEqual(bm.values_from_attributes(entry, "inte json")[0].value, "")

    def test_attribute_names_exist_in_the_plan_layers(self):
        for kod in (TEKNISK, UTNYTT):
            entry = self.entry(kod)
            columns = {f.name for f in model.BESTAMMELSE.fields}
            values = bm.default_values(entry)
            if entry.variables:
                values = [bm.VariableValue(v.variable, "30", v.vardetyp, v.enhet) for v in values]
            self.assertLessEqual(set(bm.feature_attributes(entry, values, motiv="x")), columns, kod)
        for name in (cat.USE_LAYER, *cat.PROPERTY_LAYERS):
            model.layer_by_name(name)  # ska finnas

    def test_custom_formulation_keeps_variables_but_is_flagged_as_deviating(self):
        entry = self.entry(UTNYTT)
        values = [bm.VariableValue(entry.variables[0], "30", "max", "procent")]
        custom = "Byggnadsarean får som mest vara [utnyttjandegrad:decimaltal] % av fastigheten."
        attrs = bm.feature_attributes(entry, values, formulation=custom)
        self.assertEqual(attrs["bestammelseformulering"], custom)
        self.assertIs(attrs["avviker"], True)
        self.assertEqual(json.loads(attrs["bestammelsevarde"])[0]["variabelvarde"], "30")
        self.assertEqual(bm.display_text(entry, values, custom), "Byggnadsarean får som mest vara 30 % av fastigheten.")
        # samma text som katalogen är inte en avvikelse
        same = bm.feature_attributes(entry, values, formulation=entry.formulering)
        self.assertIs(same["avviker"], False)

    def test_custom_formulation_must_keep_the_variables_in_order(self):
        entry = self.entry(LUTNING)
        values = [bm.VariableValue(v, "1", "max", "antal") for v in entry.variables]
        problems = bm.check(entry, values, "Lutning [lutning2:decimaltal] och [lutning1:decimaltal].")
        self.assertTrue(any("samma ordning" in p for p in problems))
        problems = bm.check(entry, values, "Lutning [okänd:decimaltal].")
        self.assertTrue(any("samma ordning" in p for p in problems))
        self.assertTrue(any("tom" in p for p in bm.check(entry, values, "  ")))

    def test_a_variable_removed_from_a_custom_formulation_drops_its_value(self):
        entry = self.entry(LUTNING)
        values = [bm.VariableValue(entry.variables[0], "1", "max", "antal"),
                  bm.VariableValue(entry.variables[1], "20", "max", "antal")]
        attrs = bm.feature_attributes(entry, values, formulation="Lutningen är högst 1:[lutning2:decimaltal].")
        stored = json.loads(attrs["bestammelsevarde"])
        self.assertEqual([v["beskrivning"] for v in stored], ["lutning2"])

    def test_normalize_decimal(self):
        self.assertEqual(bm.normalize_decimal("12,5"), "12.5")
        self.assertEqual(bm.normalize_decimal(" 37 "), "37")
        self.assertEqual(bm.normalize_decimal("-3"), "-3")
        self.assertIsNone(bm.normalize_decimal("1e3"))
        self.assertIsNone(bm.normalize_decimal(""))


@unittest.skipUnless(BUNDLED.exists(), "medföljande katalog saknas")
class BundledCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = cat.Catalog.load(BUNDLED)

    def test_contains_only_current_entries_with_codes(self):
        self.assertGreater(len(self.catalog), 800)
        self.assertTrue(all(e.is_current for e in self.catalog.entries))
        self.assertTrue(all(e.kod for e in self.catalog.entries))
        self.assertEqual(len({e.id for e in self.catalog.entries}), len(self.catalog))

    def test_every_deliverable_entry_has_a_target_layer(self):
        names = {layer.name for layer in model.LAYERS}
        for entry in self.catalog.search():
            self.assertIn(entry.layer_name, names, entry.kod)

    def test_contains_technical_installations(self):
        self.assertTrue(any(e.kod == TEKNISK and e.is_technical for e in self.catalog.entries))

    def test_all_variables_are_well_formed_and_defaults_work(self):
        for entry in self.catalog.entries:
            self.assertEqual(entry.formulering.count("["), len(entry.variables), entry.kod)
            values = bm.default_values(entry)
            self.assertEqual(len(values), len(entry.variables))

    def test_decimal_entries_offer_a_value_type(self):
        missing = [e.kod for e in self.catalog.search() if any(v.datatype == "decimaltal" for v in e.variables)
                   and not cat.value_type(e.uttryckt_varde)]
        self.assertLessEqual(len(missing), 2, missing)  # användaren väljer värdetyp själv i dessa fall


if __name__ == "__main__":
    unittest.main()
