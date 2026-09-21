"""Kontrollerar att datamodellen överensstämmer med Lantmäteriets JSON-scheman i spec/. Kräver inte QGIS."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import generate_codelists  # noqa: E402
from rita_detaljplan.core import model  # noqa: E402
from rita_detaljplan.core import rows  # noqa: E402


def _defs(name):
    return json.loads((ROOT / "spec" / name).read_text(encoding="utf-8"))["definitions"]


DP = _defs("detaljplan-4.1.json")

# Kolumner som inte är egna JSON-fält utan avbildas på nästlade objekt (se model.py).
GEOMETRIMETADATA = {"lagesmetodTyp", "lagesmetodVariant", "tidpunktForLagesbestamning",
                    "absolutLagesosakerhetPlan", "presentationsskala", "tidpunktForKontrollAvGeometri"}
PLUGIN_ONLY = set(model.PLUGIN_ONLY_FIELDS)  # används bara av pluginet, ingår inte i leveransen


def _props(*names):
    out = set()
    for name in names:
        node = DP[name]
        for part in node.get("allOf", [node]):
            out |= set(part.get("properties", {}))
    return out


class CodelistsUpToDate(unittest.TestCase):
    def test_generated_module_matches_spec(self):
        generated = generate_codelists.OUT.read_text(encoding="utf-8")
        self.assertEqual(generated, generate_codelists.build(),
                         "codelists.py är inte uppdaterad – kör python tools/generate_codelists.py")


class ModelMatchesSchema(unittest.TestCase):
    def _names(self, layer):
        return {f.name for f in layer.fields}

    def test_field_names_are_unique(self):
        for layer in model.LAYERS:
            names = [f.name for f in layer.fields]
            self.assertEqual(len(names), len(set(names)), layer.name)

    def test_detaljplan_fields(self):
        allowed = _props("utbytesobjekt", "detaljplan", "kvalitet") | GEOMETRIMETADATA
        unknown = self._names(model.DETALJPLAN) - allowed
        self.assertFalse(unknown, f"Fält som inte finns i schemat: {sorted(unknown)}")

    def test_detaljplan_required_fields_present_and_required(self):
        schema_required = set(DP["detaljplan"]["allOf"][1]["required"]) | set(DP["utbytesobjekt"]["required"])
        # feature:typ sätts av exporten; plangeometri = geometrin; beslutsinformation = egen tabell
        expected = schema_required - {"feature:typ", "plangeometri", "beslutsinformation"}
        required = {f.name for f in model.DETALJPLAN.fields if f.required}
        self.assertTrue(expected <= required, f"Saknar obligatoriska fält: {sorted(expected - required)}")

    def test_area_layers_only_hold_identity_geometry_metadata_and_display_columns(self):
        allowed = _props("utbytesobjekt") | GEOMETRIMETADATA | PLUGIN_ONLY | {"detaljplan"}
        for layer in model.AREA_LAYERS:
            unknown = self._names(layer) - allowed
            self.assertFalse(unknown, f"{layer.name}: {sorted(unknown)}")
            self.assertLessEqual({"beteckning", "farg", "symbol", "anvandningsform", "bestammelser"}, self._names(layer))

    def test_provisions_live_in_their_own_table_not_on_the_areas(self):
        provision_fields = {"planbestammelsekatalogreferens", "bestammelseformulering", "bestammelsevarde", "motiv"}
        for layer in model.AREA_LAYERS:
            self.assertFalse(provision_fields & self._names(layer), layer.name)
        self.assertLessEqual(provision_fields, self._names(model.BESTAMMELSE))
        self.assertIsNone(model.BESTAMMELSE.geometry, "en yta kan ha flera bestämmelser: raderna är en tabell")

    def test_provision_table_fields_exist_in_the_schema(self):
        allowed = (_props("planbestammelse", "anvandningsbestammelse", "egenskapsbestammelse", "kvalitet")
                   | _props("utbytesobjekt") | PLUGIN_ONLY | {"motiv"})
        unknown = self._names(model.BESTAMMELSE) - allowed
        self.assertFalse(unknown, sorted(unknown))

    def test_provision_required_fields_are_marked_required(self):
        expected = set(DP["planbestammelse"]["required"]) - {"feature:typ", "bestammelsegeometri"}
        required = {f.name for f in model.BESTAMMELSE.fields if f.required}
        self.assertTrue(expected <= required, sorted(expected - required))
        self.assertLessEqual({"tabell", "yta"}, required, "varje bestämmelse hör till en yta")

    def test_the_link_to_use_provisions_is_derived_at_export_not_stored(self):
        for layer in model.LAYERS:
            self.assertNotIn("reglerarAnvandningsbestammelse", self._names(layer), layer.name)

    def test_geometry_types_match_the_layers(self):
        self.assertEqual({layer.name: layer.geometry for layer in model.AREA_LAYERS},
                         {"anvandning_yta": "MultiPolygon", "egenskap_yta": "MultiPolygon",
                          "egenskap_linje": "MultiLineString"})

    def test_there_are_no_property_point_layers(self):
        self.assertNotIn("egenskap_punkt", {layer.name for layer in model.LAYERS})

    def test_a_row_can_store_everything_a_provision_needs(self):
        for key in rows.ATTRIBUTE_KEYS:
            self.assertIn(key, self._names(model.BESTAMMELSE), key)
        self.assertLessEqual({"beteckning", "beteckningsindex", "tabell", "yta"}, self._names(model.BESTAMMELSE))

    def test_beslutsinformation_fields(self):
        allowed = _props("beslutsinformation") | {"detaljplan"}
        unknown = self._names(model.BESLUTSINFORMATION) - allowed
        self.assertFalse(unknown, sorted(unknown))
        # handlingar, grundkarta och bestämmelsereferenser lagras i andra tabeller
        missing = _props("beslutsinformation") - self._names(model.BESLUTSINFORMATION)
        self.assertEqual(missing, {"beslutshandling", "grundkarta", "planbestammelse"})

    def test_codelist_defaults_are_valid_values(self):
        for layer in model.LAYERS:
            for f in layer.fields:
                if f.codelist and f.default and f.default.startswith("'"):
                    self.assertIn(f.default.strip("'"), f.codelist, f"{layer.name}.{f.name}")

    def test_relations_point_at_existing_fields(self):
        for name, child, child_field, parent_field in model.RELATIONS:
            self.assertIn(child_field, self._names(model.layer_by_name(child)), name)
            self.assertIn(parent_field, self._names(model.DETALJPLAN), name)


if __name__ == "__main__":
    unittest.main()
