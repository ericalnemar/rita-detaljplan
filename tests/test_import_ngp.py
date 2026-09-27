"""Tolkningen av en leverans (import_ngp.parse), och att den kan skrivas till en ny plan (kräver QGIS för geometrin)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, PlanCase, pick, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsProject
    from rita_detaljplan.controller import PlanController
    from rita_detaljplan.core import import_ngp as im
    from rita_detaljplan.core import rules
    from rita_detaljplan.core.project import create_plan_project, load_plan


def polygon(coords):
    return {"geometri": {"typ": "yta", "position": {"type": "Polygon", "coordinates": [coords]}}}


def linestring(coords):
    return {"geometri": {"typ": "linje", "position": {"type": "LineString", "coordinates": coords}}}


SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
OTHER_SQUARE = [[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]
LINE = [[0, 0], [10, 0]]

PLAN_FEATURE = {"type": "Feature", "geometry": None, "properties": {
    "feature:typ": "detaljplan", "objektidentitet": "plan-1", "kommun": "Eskilstuna", "namn": "Kv Väktaren",
    "syfte": "Bostäder", "status": "samråd", "typ": "detaljplan", "beteckning": "DP 2026:1",
    "plangeometri": [polygon(SQUARE)],
}}


def use_feature(coords=SQUARE, ref="DP_KM_J2", **extra):
    return {"type": "Feature", "geometry": None, "properties": {
        "feature:typ": "användningsbestämmelse", "objektidentitet": f"row-{id(coords)}",
        "planbestammelsekatalogreferens": ref, "bestammelseformulering": "Bostäder", "bestammelsegeometri": [polygon(coords)],
        **extra,
    }}


def collection(*features):
    return {"type": "FeatureCollection", "feature:mediatyp": "x", "features": [PLAN_FEATURE, *features]}


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ParseTests(unittest.TestCase):
    def test_a_collection_without_a_plan_feature_is_rejected(self):
        with self.assertRaises(im.ImportError_):
            im.parse({"type": "FeatureCollection", "features": []})

    def test_something_that_is_not_a_feature_collection_is_rejected(self):
        with self.assertRaises(im.ImportError_):
            im.parse({"type": "Feature"})

    def test_a_plan_without_geometry_is_rejected(self):
        broken = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": None, "properties": {"feature:typ": "detaljplan"}}]}
        with self.assertRaises(im.ImportError_):
            im.parse(broken)

    def test_the_plan_attributes_are_read(self):
        plan = im.parse(collection())
        self.assertEqual((plan.attrs["kommun"], plan.attrs["namn"], plan.attrs["status"]),
                         ("Eskilstuna", "Kv Väktaren", "samråd"))
        self.assertAlmostEqual(plan.geometry.area(), 100.0)

    def test_two_provisions_on_the_same_geometry_become_one_area(self):
        plan = im.parse(collection(use_feature(), use_feature(ref="DP_KM_B1")))
        self.assertEqual(len(plan.areas), 1)
        self.assertEqual(plan.areas[0].table, "anvandning_yta")
        self.assertEqual([p.catalog_id for p in plan.areas[0].provisions], ["DP_KM_J2", "DP_KM_B1"])

    def test_provisions_on_different_geometries_become_different_areas(self):
        plan = im.parse(collection(use_feature(SQUARE), use_feature(OTHER_SQUARE)))
        self.assertEqual(len(plan.areas), 2)
        self.assertAlmostEqual(sum(a.geometry.area() for a in plan.areas), 200.0)

    def test_a_property_area_is_told_apart_from_a_property_line(self):
        area_feature = {"type": "Feature", "geometry": None, "properties": {
            "feature:typ": "egenskapsbestämmelse", "planbestammelsekatalogreferens": "DP_KM_E1",
            "bestammelseformulering": "e1", "bestammelsegeometri": [polygon(SQUARE)]}}
        line_feature = {"type": "Feature", "geometry": None, "properties": {
            "feature:typ": "egenskapsbestämmelse", "planbestammelsekatalogreferens": "DP_KM_UTFART",
            "bestammelseformulering": "Utfart", "bestammelsegeometri": [linestring(LINE)]}}
        plan = im.parse(collection(area_feature, line_feature))
        self.assertEqual({a.table for a in plan.areas}, {"egenskap_yta", "egenskap_linje"})

    def test_a_secondary_property_boundary_is_detected(self):
        feature = use_feature(ref="DP_KM_E1")
        feature["properties"]["feature:typ"] = "egenskapsbestämmelse"
        feature["properties"]["sekundarEgenskapsgrans"] = True
        plan = im.parse(collection(feature))
        self.assertTrue(plan.areas[0].sekundar)

    def test_values_motive_and_optional_fields_are_carried_over(self):
        feature = use_feature()
        feature["properties"].update({
            "bestammelsevarde": [{"beskrivning": "hojd", "variabelvarde": "10", "vardetyp": "max", "enhet": "meter"}],
            "planbestammelsebeskrivning": {"motiv": "Bostäder behövs i området"},
            "giltighetstid": 24, "borjarGallaEfter": 6,
        })
        plan = im.parse(collection(feature))
        provision = plan.areas[0].provisions[0]
        self.assertEqual(provision.motiv, "Bostäder behövs i området")
        self.assertEqual(provision.values, [{"beskrivning": "hojd", "variabelvarde": "10", "vardetyp": "max",
                                            "enhet": "meter"}])
        self.assertEqual((provision.giltighetstid, provision.borjar_galla_efter), (24, 6))

    def test_a_feature_without_valid_geometry_is_skipped_with_a_warning(self):
        broken = use_feature()
        broken["properties"]["bestammelsegeometri"] = []
        plan = im.parse(collection(broken))
        self.assertEqual(plan.areas, [])
        self.assertTrue(any("hoppades över" in w for w in plan.warnings))

    def test_only_the_first_decision_is_imported_and_extra_ones_warn(self):
        decisions = [{"diarienummerKommun": "KS 1"}, {"diarienummerKommun": "KS 2"}]
        with_plan = {**PLAN_FEATURE, "properties": {**PLAN_FEATURE["properties"], "beslutsinformation": decisions}}
        plan = im.parse({"type": "FeatureCollection", "features": [with_plan]})
        self.assertEqual(plan.decision["diarienummerKommun"], "KS 1")
        self.assertTrue(any("bara det första" in w for w in plan.warnings))

    def test_documents_are_read_from_the_plan(self):
        properties = {**PLAN_FEATURE["properties"], "planbeskrivning": {"planbeskrivning": {"namn": "Beskrivning"}},
                     "beslutsinformation": [{"beslutshandling": [
                         {"innehall": ["plankarta", "beslutsprotokoll"], "dokument": {"namn": "Beslut"}}]}],
                     "planeringsunderlag": [{"huvudomrade": "geoteknik", "underlagstyp": "markundersokning",
                                             "underlag": {"namn": "Undersökning"}}]}
        with_plan = {**PLAN_FEATURE, "properties": properties}
        plan = im.parse({"type": "FeatureCollection", "features": [with_plan]})
        rolls = {d["roll"]: d for d in plan.documents}
        self.assertEqual(rolls["planbeskrivning"]["namn"], "Beskrivning")
        self.assertEqual(rolls["beslutshandling"]["innehall"], "plankarta; beslutsprotokoll")
        self.assertEqual(rolls["beslutshandling"]["namn"], "Beslut")
        self.assertEqual(rolls["planeringsunderlag"]["huvudomrade"], "geoteknik")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ControllerImportTests(PlanCase):
    """``PlanController.import_ngp`` (kräver en tom plan och den laddade katalogen)."""

    def setUp(self):
        super().setUp()
        self.errors, self.warnings = [], []
        self.controller = PlanController(self.errors.append, self.warnings.append)
        self.addCleanup(self.controller.detach)

    def test_importing_into_a_plan_that_already_has_an_area_is_refused(self):
        self.add("detaljplan", "MultiPolygon(((0 0, 10 0, 10 10, 0 10, 0 0)))")
        pump()
        with self.assertRaises(RuntimeError):
            self.controller.import_ngp(collection(), self.catalog)

    def test_an_unknown_catalog_reference_is_skipped_but_the_area_is_still_created(self):
        summary = self.controller.import_ngp(collection(use_feature(ref="DOES-NOT-EXIST")), self.catalog)
        self.assertEqual((summary.areas, summary.provisions, summary.skipped), (1, 0, 1))
        self.assertTrue(any("hoppades över" in w for w in summary.warnings))
        self.assertEqual(self.layers["anvandning_yta"].featureCount(), 1)
        self.assertEqual(self.layers["bestammelse"].featureCount(), 0)

    def test_a_known_reference_is_assigned_with_its_designation(self):
        entry = pick(self.catalog, "DP_KM_J2")
        summary = self.controller.import_ngp(collection(use_feature(ref=entry.id)), self.catalog)
        self.assertEqual((summary.areas, summary.provisions, summary.skipped), (1, 1, 0))
        self.assertEqual(self.warnings, [])
        (use,) = self.layers["anvandning_yta"].getFeatures()
        self.assertEqual(use["beteckning"], "J")
        self.assertEqual(self.layers["bestammelse"].featureCount(), 1)

    def test_the_plan_attributes_are_written(self):
        self.controller.import_ngp(collection(), self.catalog)
        self.assertEqual(self.controller.plan_values()["namn"], "Kv Väktaren")

    def test_import_starts_an_edit_session_by_itself(self):
        for layer in self.layers.values():
            layer.rollBack()
        self.assertFalse(self.controller.editing)
        self.controller.import_ngp(collection(), self.catalog)
        self.assertTrue(self.controller.editing)


if __name__ == "__main__":
    unittest.main()
