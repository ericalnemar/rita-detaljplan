"""Export till NGP (JSON), beslut och handlingar (kräver QGIS)."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, LEFT, LINE_INSIDE, PLAN, RIGHT, filled, pick, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsGeometry, QgsPointXY, QgsProject
    from rita_detaljplan.core import export_ngp as ex
    from rita_detaljplan.core import validation
    from rita_detaljplan.core.project import create_plan_project, load_plan
    from rita_detaljplan.gui.decision_dialog import DocumentDialog, describe_document, valid_date
    from rita_detaljplan.gui.plan_info_dialog import PlanInfoDialog
    from qgis_app import get_app
    from schema_check import Checker
    from test_toolbar import GuiCase

if HAVE_QGIS:
    CHECKER = Checker()

BESLUT = {"instansInomKommunen": "kommunfullmäktige", "diarienummerKommun": "KS 2023/45",
          "beslutstyp": "antagande av ny detaljplan", "datumPaborjat": "2023-01-10", "datumAntagande": "2024-03-01",
          "datumLagakraft": "2024-04-01; 2024-04-15", "genomforandetid": 5, "genomforandetidStartar": "2024-04-01",
          "foregaendePlansBeteckning": "DP 12; DP 13"}
DOCUMENTS = [
    {"roll": "planbeskrivning", "namn": "Planbeskrivning", "lank": "https://exempel.se/pb.pdf"},
    {"roll": "beslutshandling", "innehall": "plankarta", "namn": "Plankarta", "datum": "2024-03-01",
     "handelse": "skapad", "referensIdentitet": "0f0e0d0c-0b0a-4090-8080-070605040302"},
    {"roll": "planeringsunderlag", "huvudomrade": "utredningar", "underlagstyp": "bullerutredning",
     "namn": "Bullerutredning", "lank": "https://exempel.se/buller.pdf", "specifikReferens": "kap 3; kap 4"},
]


def sq(x0, y0, x1, y1):
    return f"MultiPolygon((({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0})))"


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class GeometryTests(unittest.TestCase):
    def parts(self, wkt):
        return ex.geometry_parts(QgsGeometry.fromWkt(wkt))

    def test_a_multipolygon_becomes_one_polygon_per_part(self):
        parts = self.parts("MultiPolygon(((0 0, 10 0, 10 10, 0 10, 0 0)), ((20 0, 30 0, 30 10, 20 10, 20 0)))")
        self.assertEqual([kind for kind, _ in parts], ["yta", "yta"])
        self.assertTrue(all(p["type"] == "Polygon" for _, p in parts), "inga multigeometrier")

    def test_exterior_rings_run_counter_clockwise_and_holes_clockwise(self):
        clockwise = "Polygon((0 0, 0 10, 10 10, 10 0, 0 0), (2 2, 8 2, 8 8, 2 8, 2 2))"
        (_, position), = self.parts(clockwise)
        exterior, hole = position["coordinates"]
        self.assertGreater(ex._signed_area([tuple(p) for p in exterior[:-1]]), 0)
        self.assertLess(ex._signed_area([tuple(p) for p in hole[:-1]]), 0)
        self.assertEqual(exterior[0], exterior[-1])

    def test_coordinates_are_rounded_to_millimetres_and_repeated_points_removed(self):
        (_, position), = self.parts("Polygon((0 0, 10.00049 0, 10.00051 0.0001, 10 10, 0 10, 0 0))")
        self.assertIn([10.0, 0.0], position["coordinates"][0])
        self.assertEqual(len(position["coordinates"][0]), len(set(map(tuple, position["coordinates"][0]))) + 1)
        self.assertNotIn([-0.0, 0.0], [[abs(x) * -1 if x == 0 else x, y] for x, y in position["coordinates"][0]][:0])

    def test_lines_become_linestrings_and_multilines_are_split(self):
        parts = self.parts("MultiLineString((( 0 0, 10 0)), ((0 5, 10 5, 10 9)))")
        self.assertEqual([(k, p["type"]) for k, p in parts], [("linje", "LineString")] * 2)

    def test_points_and_empty_geometries_are_skipped(self):
        self.assertEqual(self.parts("Point(1 1)"), [])
        self.assertEqual(ex.geometry_parts(QgsGeometry()), [])
        self.assertEqual(ex.geometry_parts(None), [])

    def test_a_degenerate_polygon_is_dropped(self):
        self.assertEqual(self.parts("Polygon((0 0, 0.0001 0, 0.0002 0, 0 0))"), [])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class HelperTests(unittest.TestCase):
    def test_semicolon_lists_are_split_and_empty_values_dropped(self):
        self.assertEqual(ex._split("a; b;;  c "), ["a", "b", "c"])
        self.assertEqual(ex._split(None), [])
        target = {}
        for key, value in (("a", None), ("b", ""), ("c", []), ("d", {}), ("e", 0), ("f", "x")):
            ex._put(target, key, value)
        self.assertEqual(target, {"e": 0, "f": "x"})

    def test_quality_needs_both_booleans_once_it_exists(self):
        self.assertEqual(ex.quality({}), {})
        self.assertEqual(ex.quality({"beskrivningNiva": "text"}),
                         {"beskrivningNiva": "text", "korrigeradeGranser": False, "kontrolleratPlaneringsunderlag": False})
        self.assertEqual(ex.quality({"korrigeradeGranser": True, "kontrolleratPlaneringsunderlag": False,
                                     "digitaliseringsniva": "komplett"})["korrigeradeGranser"], True)

    def test_the_position_method_carries_its_variant_and_only_a_place_method_carries_a_scale(self):
        meta = ex.geometry_metadata({"lagesmetodTyp": "lägesplacering", "lagesmetodVariant": "digital karta",
                                     "presentationsskala": 1000, "tidpunktForLagesbestamning": "2026-01-01T10:00:00Z"})
        self.assertEqual(meta["lagesbestamningsmetodIPlan"],
                         {"typ": "lägesplacering", "variant": "digital karta", "presentationsskala": 1000})
        other = ex.geometry_metadata({"lagesmetodTyp": "geodetisk detaljmätning", "lagesmetodVariant": "DGNSS",
                                      "presentationsskala": 1000})
        self.assertNotIn("presentationsskala", other["lagesbestamningsmetodIPlan"])
        self.assertEqual(ex.geometry_metadata({}), {})

    def test_a_document_reference_needs_a_link_or_an_identity(self):
        self.assertEqual(ex.document_reference({"namn": "X"})["referens"], [])
        self.assertEqual(ex.document_reference({"namn": "X", "lank": "https://a.se"})["referens"],
                         [{"lank": "https://a.se"}])
        both = ex.document_reference({"namn": "X", "lank": "https://a.se", "referensIdentitet": "id"})
        self.assertEqual(both["referens"], [{"identitet": "id", "lank": "https://a.se"}])
        dated = ex.document_reference({"namn": "X", "datum": "2024-03-01", "handelse": "skapad"})
        self.assertEqual(dated["datum"], {"datum": "2024-03-01", "handelse": "skapad"})
        self.assertNotIn("datum", ex.document_reference({"namn": "X", "datum": "2024-03-01"}), "händelse saknas")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class CheckerTests(unittest.TestCase):
    """Schemakontrollen ska kunna se fel, annars bevisar den ingenting."""

    def good(self):
        return {"type": "FeatureCollection", "feature:mediatyp": "application/vnd.lm.detaljplan.v4+json",
                "features": []}

    def test_a_bare_collection_passes(self):
        self.assertEqual(CHECKER.problems(self.good()), [])

    def test_a_wrong_media_type_and_a_wrong_feature_are_found(self):
        bad = self.good()
        bad["feature:mediatyp"] = "text/plain"
        self.assertTrue(CHECKER.problems(bad))
        bad = self.good()
        bad["features"] = [{"type": "Feature", "geometry": None, "properties": {"feature:typ": "hus"}}]
        self.assertTrue(CHECKER.problems(bad))


class ExportCase(GuiCase):
    """En färdig plan: två användningar med bestämmelser, en egenskapsyta, en egenskapslinje, beslut och handlingar."""

    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.left, self.right = self.build_plan()
        self.use_entry = pick(self.catalog, "DP_KM_J2")
        self.controller.add_bestammelse("anvandning_yta", self.left.id(), self.use_entry, filled(self.use_entry))
        self.controller.add_bestammelse("anvandning_yta", self.right.id(), self.use_entry, filled(self.use_entry),
                                        motiv="Industri behövs")
        self.prop = self.draw("egenskap_yta", INSIDE)
        self.prop_entry = pick(self.catalog, layer="egenskap_yta", form="Kvartersmark", variables=True)
        self.controller.add_bestammelse("egenskap_yta", self.prop.id(), self.prop_entry, filled(self.prop_entry))
        self.line = self.draw("egenskap_linje", LINE_INSIDE)
        self.line_entry = pick(self.catalog, layer="egenskap_linje")
        self.controller.add_bestammelse("egenskap_linje", self.line.id(), self.line_entry, filled(self.line_entry))
        self.controller.set_plan_values({"kommun": "Eskilstuna", "namn": "Kv Väktaren", "syfte": "Industri",
                                         "status": "påbörjad", "typ": "detaljplan", "beteckning": "DP 1"})
        self.controller.set_decision(BESLUT)
        self.controller.set_documents(DOCUMENTS)

    def export(self):
        return self.controller.export_ngp()

    def plan(self, collection=None):
        return (collection or self.export())["features"][0]["properties"]

    def provisions(self, collection=None):
        return [f["properties"] for f in (collection or self.export())["features"][1:]]


class ExportTests(ExportCase):
    def test_the_export_follows_the_schema_of_the_specification(self):
        problems = CHECKER.problems(self.export())
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_collection_has_the_media_type_one_plan_and_one_object_per_provision(self):
        collection = self.export()
        self.assertEqual(collection["type"], "FeatureCollection")
        self.assertEqual(collection["feature:mediatyp"], "application/vnd.lm.detaljplan.v4+json")
        self.assertEqual(len(collection["features"]), 1 + 4)
        self.assertEqual(collection["features"][0]["properties"]["feature:typ"], "detaljplan")
        self.assertTrue(all(f["geometry"] is None for f in collection["features"]))

    def test_the_plan_object_carries_the_plans_details_and_geometry(self):
        plan = self.plan()
        self.assertEqual((plan["kommun"], plan["namn"], plan["syfte"], plan["status"], plan["typ"], plan["beteckning"]),
                         ("Eskilstuna", "Kv Väktaren", "Industri", "påbörjad", "detaljplan", "DP 1"))
        self.assertEqual(plan["objektidentitet"], self.controller.plan_feature()["objektidentitet"])
        self.assertEqual(plan["objektversion"], 1)
        self.assertEqual(len(plan["plangeometri"]), 1)
        geometry = plan["plangeometri"][0]["geometri"]
        self.assertEqual((geometry["typ"], geometry["koordinatsystemPlan"], geometry["dimension"]), ("yta", "EPSG:3006", 2))
        self.assertEqual(plan["kvalitetsbeskrivning"], {"korrigeradeGranser": False, "kontrolleratPlaneringsunderlag": False})

    def test_every_provision_row_becomes_its_own_object_with_its_own_identity(self):
        provisions = self.provisions()
        ids = [p["objektidentitet"] for p in provisions]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(p["feature:typ"] for p in provisions),
                         ["användningsbestämmelse", "användningsbestämmelse", "egenskapsbestämmelse",
                          "egenskapsbestämmelse"])
        plan_id = self.plan()["objektidentitet"]
        self.assertTrue(all(p["detaljplan"] == plan_id for p in provisions))

    def test_a_provision_carries_catalog_reference_formulation_values_and_motive(self):
        use = next(p for p in self.provisions() if p["feature:typ"] == "användningsbestämmelse"
                   and "planbestammelsebeskrivning" in p)
        self.assertEqual(use["planbestammelsekatalogreferens"], self.use_entry.id)
        self.assertEqual(use["bestammelseformulering"], self.use_entry.formulering)
        self.assertEqual(use["planbestammelsebeskrivning"], {"motiv": "Industri behövs"})
        prop = next(p for p in self.provisions() if p["planbestammelsekatalogreferens"] == self.prop_entry.id)
        if self.prop_entry.variables:
            self.assertEqual([v["beskrivning"] for v in prop["bestammelsevarde"]],
                             [v.name for v in self.prop_entry.variables])

    def test_plugin_only_columns_never_reach_the_delivery(self):
        forbidden = {"tabell", "yta", "beteckning", "beteckningsindex", "bestammelsekod", "anvandningsform", "farg",
                     "symbol", "avviker", "bestammelser", "ordning", "label_x", "label_y"}
        for provision in self.provisions():
            self.assertFalse(forbidden & set(provision), forbidden & set(provision))
        self.assertFalse({"label_x", "label_y", "ordning", "tabell"} & set(self.plan()))

    def test_a_property_regulates_the_use_provisions_of_the_uses_it_lies_on(self):
        left_use = next(p for p in self.provisions() if p.get("planbestammelsebeskrivning") is None
                        and p["feature:typ"] == "användningsbestämmelse")
        prop = next(p for p in self.provisions() if p["planbestammelsekatalogreferens"] == self.prop_entry.id)
        self.assertEqual(prop["reglerarAnvandningsbestammelse"], [left_use["objektidentitet"]])
        line = next(p for p in self.provisions() if p["planbestammelsekatalogreferens"] == self.line_entry.id)
        self.assertEqual(line["reglerarAnvandningsbestammelse"], [left_use["objektidentitet"]])
        for use in (p for p in self.provisions() if p["feature:typ"] == "användningsbestämmelse"):
            self.assertNotIn("reglerarAnvandningsbestammelse", use)

    def test_a_property_over_two_uses_regulates_both(self):
        across = self.draw("egenskap_yta", "MultiPolygon(((40 10, 60 10, 60 40, 40 40, 40 10)))")
        entry = pick(self.catalog, layer="egenskap_yta", form="Kvartersmark")
        self.controller.add_bestammelse("egenskap_yta", across.id(), entry, filled(entry))
        row = next(p for p in self.provisions() if p["planbestammelsekatalogreferens"] == entry.id
                   and len(p.get("reglerarAnvandningsbestammelse", [])) == 2)
        uses = [p["objektidentitet"] for p in self.provisions() if p["feature:typ"] == "användningsbestämmelse"]
        self.assertEqual(sorted(row["reglerarAnvandningsbestammelse"]), sorted(uses))

    def test_multigeometries_are_split_into_one_entry_per_part(self):
        two_parts = "MultiPolygon(((10 10, 20 10, 20 20, 10 20, 10 10)), ((30 10, 40 10, 40 20, 30 20, 30 10)))"
        prop = self.draw("egenskap_yta", two_parts)
        entry = pick(self.catalog, layer="egenskap_yta", form="Kvartersmark")
        self.controller.add_bestammelse("egenskap_yta", prop.id(), entry, filled(entry))
        row = next(p for p in self.provisions() if len(p["bestammelsegeometri"]) == 2)
        self.assertTrue(all(g["geometri"]["position"]["type"] == "Polygon" for g in row["bestammelsegeometri"]))
        self.assertEqual(CHECKER.problems(self.export()), [])

    def test_a_plan_with_several_parts_lists_each_in_plangeometri(self):
        self.draw("detaljplan", sq(200, 200, 230, 230))
        self.assertEqual(len(self.plan()["plangeometri"]), 2)

    def test_helper_lines_are_never_exported(self):
        before = json.dumps(self.export(), sort_keys=True)
        self.add("hjalplinje", "MultiLineString((( 5 5, 95 95)))")
        self.assertEqual(json.dumps(self.export(), sort_keys=True), before)

    def test_provisions_of_removed_areas_are_not_delivered(self):
        rows = self.controller.rows_of("egenskap_linje", self.line.id())
        self.layers["egenskap_linje"].deleteFeature(self.line.id())
        provisions = self.provisions()
        self.assertEqual(len(provisions), 3)
        self.assertNotIn(rows[0]["planbestammelsekatalogreferens"],
                         [p["planbestammelsekatalogreferens"] for p in provisions if p["feature:typ"] == "egenskapsbestämmelse"
                          and p["planbestammelsekatalogreferens"] == self.line_entry.id])

    def test_a_customised_formulation_also_delivers_the_original(self):
        other = self.draw("egenskap_yta", "MultiPolygon(((60 60, 90 60, 90 90, 60 90, 60 60)))")
        prop_entry = pick(self.catalog, layer="egenskap_yta", form="Kvartersmark")
        self.controller.add_bestammelse("egenskap_yta", other.id(), prop_entry, filled(prop_entry),
                                        formulation=prop_entry.formulering + " (särskilt)")
        row = next(p for p in self.provisions() if p["bestammelseformulering"].endswith("(särskilt)"))
        self.assertEqual(row["ursprungligBestammelseformulering"], prop_entry.formulering)

    def test_timestamps_are_in_utc_with_a_z(self):
        for stamp in (self.plan()["versionGiltigFran"], self.provisions()[0]["versionGiltigFran"]):
            self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_the_position_method_metadata_is_delivered_with_each_geometry(self):
        meta = self.plan()["plangeometri"][0]["geometrimetadata"]
        self.assertEqual(meta["lagesbestamningsmetodIPlan"]["typ"], "lägesplacering")
        self.assertIn("tidpunktForLagesbestamning", meta)

    def test_the_json_text_keeps_swedish_letters_and_reads_back_identically(self):
        collection = self.export()
        text = ex.dumps(collection)
        self.assertIn("användningsbestämmelse", text)
        self.assertIn("Väktaren", text)
        self.assertEqual(json.loads(text), collection)

    def test_counts_are_reported(self):
        self.assertEqual(ex.counts(self.export()), (4, 4))

    def test_exporting_does_not_change_the_plan(self):
        before = [(f.id(), f.geometry().asWkt(), f.attributes()) for f in self.layers["anvandning_yta"].getFeatures()]
        self.export()
        after = [(f.id(), f.geometry().asWkt(), f.attributes()) for f in self.layers["anvandning_yta"].getFeatures()]
        self.assertEqual(before, after)


class DecisionExportTests(ExportCase):
    def decision(self):
        return self.plan()["beslutsinformation"]

    def test_the_decision_is_delivered_with_lists_and_numbers(self):
        (info,) = self.decision()
        self.assertEqual(info["diarienummerKommun"], "KS 2023/45")
        self.assertEqual(info["datumLagakraft"], ["2024-04-01", "2024-04-15"])
        self.assertEqual(info["genomforandetid"], 5)
        self.assertEqual(info["foregaendePlansBeteckning"], ["DP 12", "DP 13"])
        self.assertEqual(info["datumAntagande"], "2024-03-01")

    def test_the_decision_lists_all_provisions_when_there_is_one_decision(self):
        (info,) = self.decision()
        self.assertEqual(sorted(info["planbestammelse"]), sorted(p["objektidentitet"] for p in self.provisions()))

    def test_decision_documents_hang_on_the_decision_and_the_description_on_the_plan(self):
        (info,) = self.decision()
        (handling,) = info["beslutshandling"]
        self.assertEqual(handling["innehall"], ["plankarta"])
        self.assertEqual(handling["dokument"]["referens"], [{"identitet": "0f0e0d0c-0b0a-4090-8080-070605040302"}])
        self.assertEqual(handling["dokument"]["datum"], {"datum": "2024-03-01", "handelse": "skapad"})
        description = self.plan()["planbeskrivning"]["planbeskrivning"]
        self.assertEqual((description["namn"], description["referens"]), ("Planbeskrivning", [{"lank": "https://exempel.se/pb.pdf"}]))

    def test_background_documents_are_delivered_as_planeringsunderlag(self):
        (item,) = self.plan()["planeringsunderlag"]
        self.assertEqual((item["huvudomrade"], item["underlagstyp"]), ("utredningar", "bullerutredning"))
        self.assertEqual(item["underlag"]["specifikReferens"], ["kap 3", "kap 4"])

    def test_a_document_without_link_or_identity_is_caught_by_the_schema_check(self):
        self.controller.set_documents([{"roll": "planbeskrivning", "namn": "Utan länk"}])
        problems = CHECKER.problems(self.export())
        self.assertTrue(any("referens" in p for p in problems), problems)

    def test_a_plan_without_a_decision_fails_the_schema_check_on_the_missing_decision(self):
        self.controller.set_decision({name: None for name in BESLUT})
        layer = self.layers["beslutsinformation"]
        layer.deleteFeatures([f.id() for f in layer.getFeatures()])
        problems = CHECKER.problems(self.export())
        self.assertTrue(any("beslutsinformation" in p for p in problems), problems)


class DecisionStorageTests(ExportCase):
    def test_the_decision_can_be_read_back_and_changed(self):
        values = self.controller.decision_values()
        self.assertEqual(values["diarienummerKommun"], "KS 2023/45")
        self.assertEqual(str(values["datumAntagande"])[:10], "2024-03-01")
        self.controller.set_decision({**BESLUT, "diarienummerKommun": "KS 9/99", "genomforandetid": None})
        again = self.controller.decision_values()
        self.assertEqual(again["diarienummerKommun"], "KS 9/99")
        self.assertIsNone(again["genomforandetid"])
        self.assertEqual(self.layers["beslutsinformation"].featureCount(), 1, "en beslutsrad")

    def test_setting_documents_replaces_all_and_skips_rows_without_type(self):
        self.controller.set_documents([DOCUMENTS[0], {"roll": None, "namn": "Ingen typ"}])
        documents = self.controller.documents()
        self.assertEqual([d["roll"] for d in documents], ["planbeskrivning"])
        self.controller.set_documents([])
        self.assertEqual(self.controller.documents(), [])

    def test_decision_and_documents_are_saved_with_the_plan(self):
        self.assertEqual(self.controller.stop_editing(save=True), [])
        self.assertEqual(self.controller.decision_values()["diarienummerKommun"], "KS 2023/45")
        self.assertEqual(len(self.controller.documents()), 3)

    def test_an_empty_decision_creates_no_row(self):
        self.controller.set_decision({name: None for name in BESLUT})
        layer = self.layers["beslutsinformation"]
        layer.deleteFeatures([f.id() for f in layer.getFeatures()])
        self.controller.set_decision({name: "" for name in BESLUT})
        self.assertEqual(layer.featureCount(), 0)


class CoordinateSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.project = None
        self.addCleanup(lambda: setattr(self, "project", None))

    def test_the_projection_of_the_plan_is_delivered(self):
        from qgis.core import QgsVectorLayerUtils
        gpkg, _ = create_plan_project(Path(self._tmp.name), "sydost", "Eskilstuna", "0484", 3010)
        self.project = QgsProject()
        layers = load_plan(gpkg, self.project)
        layers["detaljplan"].startEditing()
        feature = QgsVectorLayerUtils.createFeature(layers["detaljplan"], QgsGeometry.fromWkt(PLAN))
        layers["detaljplan"].addFeature(feature)
        collection = ex.export_plan(validation.collect(self.project))
        self.assertEqual(collection["features"][0]["properties"]["plangeometri"][0]["geometri"]["koordinatsystemPlan"],
                         "EPSG:3010")

    def test_exporting_without_a_plan_area_is_refused(self):
        with self.assertRaises(ValueError):
            ex.export_plan(validation.PlanData())


class DocumentDialogTests(GuiCase):
    def dialog(self, values=None):
        dialog = DocumentDialog(None, values)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_dates_are_checked_as_real_dates(self):
        self.assertTrue(valid_date("2024-02-29"))
        for bad in ("", "2024-2-9", "2023-02-29", "24-01-01", "2024-13-01", "idag"):
            self.assertFalse(valid_date(bad), bad)

    def test_a_new_document_needs_a_name_and_the_fields_of_its_kind(self):
        dialog = self.dialog()
        self.assertFalse(dialog.buttons.buttons()[0].isEnabled())
        dialog.namn.setText("Planbeskrivning")
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())
        dialog.roll.setCurrentIndex(dialog.roll.findData("beslutshandling"))
        self.assertFalse(dialog.buttons.buttons()[0].isEnabled(), "innehåll krävs för beslutshandling")
        dialog.innehall.setCurrentIndex(dialog.innehall.findData("plankarta"))
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())
        dialog.roll.setCurrentIndex(dialog.roll.findData("planeringsunderlag"))
        self.assertFalse(dialog.buttons.buttons()[0].isEnabled(), "huvudområde krävs för underlag")
        dialog.huvudomrade.setCurrentIndex(dialog.huvudomrade.findData("annat"))
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())

    def test_only_the_fields_of_the_chosen_kind_are_enabled(self):
        dialog = self.dialog()
        self.assertFalse(dialog.innehall.isEnabled())
        self.assertFalse(dialog.huvudomrade.isEnabled())
        dialog.roll.setCurrentIndex(dialog.roll.findData("beslutshandling"))
        self.assertTrue(dialog.innehall.isEnabled())
        dialog.roll.setCurrentIndex(dialog.roll.findData("planeringsunderlag"))
        self.assertTrue(dialog.huvudomrade.isEnabled() and dialog.underlagstyp.isEnabled())
        self.assertFalse(dialog.innehall.isEnabled())

    def test_date_and_event_belong_together_and_links_must_be_https(self):
        dialog = self.dialog({"roll": "planbeskrivning", "namn": "X"})
        dialog.datum.setText("2024-03-01")
        self.assertIn("Datum och händelse", dialog.error.text())
        dialog.handelse.setCurrentIndex(dialog.handelse.findData("skapad"))
        self.assertEqual(dialog.error.text(), "")
        dialog.lank.setText("http://osaker.se")
        self.assertIn("https://", dialog.error.text())
        dialog.lank.setText("https://sakert.se")
        dialog.identitet.setText("inte-ett-uuid")
        self.assertIn("UUID", dialog.error.text())
        dialog.identitet.setText("0f0e0d0c-0b0a-4090-8080-070605040302")
        self.assertEqual(dialog.error.text(), "")

    def test_the_values_of_an_existing_document_are_loaded_and_returned(self):
        dialog = self.dialog(DOCUMENTS[2])
        values = dialog.values()
        self.assertEqual((values["roll"], values["huvudomrade"], values["underlagstyp"], values["namn"]),
                         ("planeringsunderlag", "utredningar", "bullerutredning", "Bullerutredning"))
        self.assertIsNone(values["innehall"])
        self.assertEqual(values["specifikReferens"], "kap 3; kap 4")

    def test_fields_of_other_kinds_are_not_returned(self):
        dialog = self.dialog(DOCUMENTS[1])
        dialog.roll.setCurrentIndex(dialog.roll.findData("planbeskrivning"))
        values = dialog.values()
        self.assertIsNone(values["innehall"])
        self.assertIsNone(values["huvudomrade"])

    def test_documents_are_described_in_words(self):
        self.assertEqual(describe_document(DOCUMENTS[1]), "Beslutshandling (plankarta): Plankarta")
        self.assertEqual(describe_document(DOCUMENTS[0]), "Planbeskrivning: Planbeskrivning")


class DecisionDialogTests(ExportCase):
    """Beslut och handlingar är flikar i dialogen Planens uppgifter."""

    def dialog(self):
        dialog = PlanInfoDialog(self.controller)
        self.addCleanup(dialog.deleteLater)
        panel = dialog.decision
        panel.buttons = dialog.buttons  # spara-knappen sitter i den gemensamma dialogen
        panel.accept, panel.reject = dialog.accept, dialog.reject
        return panel

    def test_the_existing_decision_and_documents_are_loaded(self):
        dialog = self.dialog()
        self.assertEqual(dialog.diarie_kommun.text(), "KS 2023/45")
        self.assertEqual(dialog.lagakraft.text(), "2024-04-01; 2024-04-15")
        self.assertEqual(dialog.months(), 5)
        self.assertEqual(dialog.beslutstyp.currentData(), "antagande av ny detaljplan")
        self.assertEqual(dialog.list.count(), 3)

    def test_bad_dates_and_durations_block_saving_with_an_explanation(self):
        dialog = self.dialog()
        save = dialog.buttons.buttons()[0]
        self.assertTrue(save.isEnabled())
        dialog.dates["datumAntagande"].setText("1 mars")
        self.assertFalse(save.isEnabled())
        self.assertIn("Datum antagande", dialog.error.text())
        dialog.dates["datumAntagande"].setText("2024-03-01")
        dialog.lagakraft.setText("2024-04-01; snart")
        self.assertIn("laga kraft", dialog.error.text())
        dialog.lagakraft.setText("2024-04-01")
        dialog.impl_unit.setCurrentIndex(dialog.impl_unit.findData("ar"))
        dialog.impl_value.setValue(5)
        self.assertEqual(dialog.months(), 60)
        dialog.impl_unit.setCurrentIndex(dialog.impl_unit.findData("manader"))
        dialog.impl_value.setValue(5)
        self.assertTrue(save.isEnabled())
        dialog.accept()  # ogiltigt block är redan rättat
        self.assertEqual(self.controller.decision_values()["genomforandetid"], 5)

    def test_accepting_writes_the_decision_and_the_documents(self):
        dialog = self.dialog()
        dialog.diarie_kommun.setText("KS 1/24")
        dialog.lagakraft.setText("2024-05-01;;")
        dialog.remove_document() if dialog.list.currentItem() else None
        dialog.list.setCurrentRow(0)
        dialog.remove_document()
        dialog.accept()
        self.assertEqual(self.controller.decision_values()["diarienummerKommun"], "KS 1/24")
        self.assertEqual(self.controller.decision_values()["datumLagakraft"], "2024-05-01")
        self.assertEqual([d["roll"] for d in self.controller.documents()], ["beslutshandling", "planeringsunderlag"])

    def test_cancelling_changes_nothing(self):
        dialog = self.dialog()
        dialog.diarie_kommun.setText("ÄNDRAT")
        dialog.list.setCurrentRow(0)
        dialog.remove_document()
        dialog.reject()
        self.assertEqual(self.controller.decision_values()["diarienummerKommun"], "KS 2023/45")
        self.assertEqual(len(self.controller.documents()), 3)

    def test_documents_are_added_and_edited_through_the_document_dialog(self):
        dialog = self.dialog()
        new = {"roll": "planbeskrivning", "namn": "Ny beskrivning", "lank": "https://ny.se"}
        with mock.patch("rita_detaljplan.gui.decision_dialog.DocumentDialog") as cls:
            cls.return_value.exec.return_value = True
            cls.return_value.values.return_value = new
            dialog.add_document()
            self.assertEqual(dialog.list.count(), 4)
            self.assertEqual(dialog.list.currentRow(), 3)
            cls.return_value.values.return_value = {**new, "namn": "Ändrad"}
            dialog.edit_document()
        self.assertEqual(dialog.documents[3]["namn"], "Ändrad")
        self.assertIn("Ändrad", dialog.list.item(3).text())
        with mock.patch("rita_detaljplan.gui.decision_dialog.DocumentDialog") as cls:
            cls.return_value.exec.return_value = False
            dialog.add_document()
        self.assertEqual(dialog.list.count(), 4, "avbruten dialog lägger inte till något")

    def test_the_document_buttons_follow_the_selection(self):
        dialog = self.dialog()
        dialog.list.setCurrentRow(-1)
        self.assertFalse(dialog.btn_edit.isEnabled() or dialog.btn_remove.isEnabled())
        dialog.list.setCurrentRow(0)
        self.assertTrue(dialog.btn_edit.isEnabled() and dialog.btn_remove.isEnabled())


class CombinedDialogTests(ExportCase):
    def dialog(self):
        dialog = PlanInfoDialog(self.controller)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_dialog_has_the_tabs_plan_decision_and_documents(self):
        dialog = self.dialog()
        self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())], ["Plan", "Beslut", "Handlingar"])
        self.assertEqual(dialog.namn.text(), "Kv Väktaren")
        self.assertEqual(dialog.decision.diarie_kommun.text(), "KS 2023/45")
        self.assertEqual(dialog.decision.list.count(), 3)

    def test_one_save_writes_plan_details_decision_and_documents(self):
        dialog = self.dialog()
        dialog.namn.setText("Nytt namn")
        dialog.decision.diarie_kommun.setText("KS 7/25")
        dialog.decision.list.setCurrentRow(0)
        dialog.decision.remove_document()
        dialog.accept()
        self.assertEqual(self.controller.plan_values()["namn"], "Nytt namn")
        self.assertEqual(self.controller.decision_values()["diarienummerKommun"], "KS 7/25")
        self.assertEqual(len(self.controller.documents()), 2)

    def test_cancelling_discards_changes_on_every_tab(self):
        dialog = self.dialog()
        dialog.namn.setText("Kastas")
        dialog.decision.diarie_kommun.setText("KASTAS")
        dialog.reject()
        self.assertEqual(self.controller.plan_values()["namn"], "Kv Väktaren")
        self.assertEqual(self.controller.decision_values()["diarienummerKommun"], "KS 2023/45")

    def test_a_mistyped_decision_value_blocks_saving_and_marks_the_tab(self):
        dialog = self.dialog()
        save = dialog.buttons.button(dialog.buttons.StandardButton.Save)
        self.assertTrue(save.isEnabled())
        dialog.decision.dates["datumAntagande"].setText("i går")
        self.assertFalse(save.isEnabled())
        self.assertEqual(dialog.tabs.tabText(1), "Beslut ✘")
        dialog.namn.setText("Ska inte sparas")
        dialog.accept()  # ignoreras: dialogen stannar och visar fliken med felet
        self.assertEqual(dialog.tabs.currentIndex(), 1)
        self.assertEqual(self.controller.plan_values()["namn"], "Kv Väktaren")
        dialog.decision.dates["datumAntagande"].setText("2024-03-01")
        self.assertTrue(save.isEnabled())
        self.assertEqual(dialog.tabs.tabText(1), "Beslut")

    def test_an_empty_decision_and_no_documents_never_block_saving(self):
        self.controller.set_decision({name: None for name in BESLUT})
        self.controller.set_documents([])
        dialog = self.dialog()
        self.assertTrue(dialog.buttons.button(dialog.buttons.StandardButton.Save).isEnabled())
        dialog.accept()


class ToolBarFileTests(ExportCase):
    """Spara som JSON-fil via NGP-dialogen."""

    def setUp(self):
        super().setUp()
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)
        self.out = self.dir / "leverans.json"

    def run_save(self, path=None, choice="file"):
        chosen = str(self.out) if path is None else str(path)
        with mock.patch.object(self.toolbar, "_ask_ngp", return_value=choice) as ask, \
                mock.patch.object(self.toolbar, "_ask_export_path", return_value=chosen) as ask_path:
            result = self.toolbar.deliver()
        return result, ask, ask_path

    def test_there_is_no_separate_export_button(self):
        self.assertFalse(hasattr(self.toolbar, "act_export"))
        self.assertFalse([a for a in self.toolbar.actions() if "Exportera" in a.text()])

    def test_the_icon_files_are_valid_svg(self):
        import xml.etree.ElementTree as ET
        from rita_detaljplan.gui.plan_toolbar import ICONS
        for name in ("deliver.svg", "validate.svg"):
            self.assertTrue(ET.parse(ICONS / name).getroot().tag.endswith("svg"), name)
        self.assertFalse((ICONS / "export.svg").exists(), "ikonen för den borttagna knappen är borta")

    def test_the_dialog_is_asked_with_the_plan_details_and_the_result_of_the_check(self):
        _, ask, _ = self.run_save()
        request = ask.call_args.args[0]
        self.assertEqual((request.plan_name, request.kommun, request.kommunkod), ("Kv Väktaren", "Eskilstuna", "0484"))
        self.assertIsInstance(request.errors, int)
        self.assertFalse(request.resuming)

    def test_choosing_file_writes_a_file_that_follows_the_schema(self):
        result, _, ask_path = self.run_save()
        self.assertTrue(result)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(CHECKER.problems(data), [])
        self.assertTrue(ask_path.call_args.args[0].endswith(".json"))
        self.assertIn("Kv_Väktaren", ask_path.call_args.args[0], "förslaget på filnamn följer plannamnet")
        self.assertTrue(any("Sparade planen som leverans.json: 4 bestämmelser med 4 geometrier" in m
                            for m in self.messages()), self.messages())

    def test_a_plan_with_errors_can_still_be_saved_and_the_errors_are_stated(self):
        self.layers["anvandning_yta"].deleteFeature(self.right.id())  # halva planområdet saknar användning
        result, ask, _ = self.run_save()
        self.assertTrue(result)
        self.assertGreater(ask.call_args.args[0].errors, 0)
        self.assertTrue(any("fel som NGP stoppar" in m for m in self.messages()))

    def test_cancelling_the_ngp_dialog_writes_nothing_and_asks_for_no_path(self):
        result, _, ask_path = self.run_save(choice=None)
        self.assertFalse(result)
        ask_path.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_cancelling_the_file_dialog_writes_nothing(self):
        result, _, _ = self.run_save(path="")
        self.assertFalse(result)
        self.assertFalse(self.out.exists())

    def test_a_write_error_is_reported(self):
        result, _, _ = self.run_save(path=self.dir / "finns_inte" / "x.json")
        self.assertFalse(result)
        self.assertTrue(any("Kunde inte spara" in m for m in self.messages()))

    def test_there_is_a_single_button_for_plan_details_decision_and_documents(self):
        self.assertFalse(hasattr(self.toolbar, "act_decision"))
        self.assertIn("beslut och handlingar", self.toolbar.act_info.toolTip())


if __name__ == "__main__":
    unittest.main()
