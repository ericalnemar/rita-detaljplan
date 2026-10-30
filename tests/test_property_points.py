"""Egenskapspunkter (ärende 1): t.ex. markens höjd över nollplanet i en punkt. Ritas på en användningsyta, får sin höjd
som beteckning ("+31,8"), levereras som geometri av typen punkt och visas som en rad i teckenförklaringen (QGIS)."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, LEFT, PLAN, RIGHT, filled, pick  # noqa: E402

if HAVE_QGIS:
    from osgeo import ogr
    from qgis.core import QgsGeometry, QgsPointXY, QgsProject
    from rita_detaljplan.controller import ASSIGN_TARGETS, PlanController
    from rita_detaljplan.core import assignments, geopackage, legend, model, storage, validation
    from rita_detaljplan.core import bestammelse as bm
    from rita_detaljplan.core import catalog as cat
    from rita_detaljplan.core import export_ngp as ex
    from rita_detaljplan.core.project import create_plan_project, load_plan
    from schema_check import Checker
    from test_export import ExportCase
    from test_toolbar import GuiCase

    BUNDLED = cat.Catalog.load(ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json")
    CHECKER = Checker()
else:  # pragma: no cover
    GuiCase = ExportCase = unittest.TestCase

POINT_ON_LEFT = "MultiPoint((20 30))"
POINT_OUTSIDE = "MultiPoint((150 150))"


def height(form="Kvartersmark", over=True):
    start = "Markens höjd över" if over else "Markens höjd under"
    return next(e for e in BUNDLED.search(layer="egenskap_punkt")
                if e.anvandningsform == form and e.formulering.startswith(start))


def height_values(entry, value="31,8"):
    return [bm.VariableValue(entry.variables[0], value, "exakt", "meter")]


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class PointDrawingTests(GuiCase):
    """Planområde med två användningar på kvartersmark (vänster och höger)."""

    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.draw("detaljplan", PLAN)
        self.use = self.draw("anvandning_yta", LEFT)
        self.draw("anvandning_yta", RIGHT)
        use_entry = pick(self.catalog, "DP_KM_J2")  # kvartersmark
        for feature in self.layers["anvandning_yta"].getFeatures():
            self.controller.add_bestammelse("anvandning_yta", feature.id(), use_entry, filled(use_entry))

    def point(self, wkt=POINT_ON_LEFT):
        return self.draw("egenskap_punkt", wkt)

    def test_the_point_layer_is_part_of_the_plan(self):
        self.assertTrue(self.layers["egenskap_punkt"].isValid())
        self.assertIn("egenskap_punkt", cat.PROPERTY_LAYERS)
        self.assertIn("egenskap_punkt", ASSIGN_TARGETS)

    def test_points_can_be_drawn_once_there_is_a_use(self):
        self.assertTrue(self.controller.can_draw("egenskap_punkt")[0])

    def test_a_point_on_a_use_is_kept_and_one_outside_is_removed(self):
        self.assertIsNotNone(self.point())
        self.assertIsNone(self.point(POINT_OUTSIDE), "utanför all användning: tas bort")
        self.assertTrue(any("Egenskapspunkten ligger inte" in e for e in self.errors))

    def test_a_height_point_gets_the_height_as_its_label(self):
        point = self.point()
        entry = height()
        self.controller.add_bestammelse("egenskap_punkt", point.id(), entry, height_values(entry))
        feature = self.layers["egenskap_punkt"].getFeature(point.id())
        self.assertEqual((feature["beteckning"], feature["bestammelser"]), ("+31,8", 1))

    def test_only_point_provisions_for_the_land_use_form_are_offered(self):
        point = self.point()
        entries = self.controller.entries_for(BUNDLED, "egenskap_punkt", point.id())
        self.assertTrue(entries)
        self.assertTrue(all(e.layer_name == "egenskap_punkt" for e in entries))
        self.assertTrue(all(e.anvandningsform in ("Kvartersmark", "Planområdet") for e in entries))

    def test_a_point_is_found_when_clicking_on_it_before_the_use_under_it(self):
        self.point()
        found = self.controller.candidates_at(QgsPointXY(20, 30), 0.5)
        self.assertEqual(found[0].table, "egenskap_punkt")
        self.assertEqual(found[-1].table, "anvandning_yta")

    def test_a_helper_point_becomes_a_property_point(self):
        helper = self.add("hjalppunkt", POINT_ON_LEFT)
        self.assertTrue(self.controller.has_assignable_helpers())
        entry = height()
        new = self.controller.assign_helper("hjalppunkt", helper.id(), entry, height_values(entry))
        self.assertEqual(new.table, "egenskap_punkt")
        self.assertEqual((self.layers["hjalppunkt"].featureCount(), self.layers["egenskap_punkt"].featureCount()),
                         (0, 1))

    def test_removing_the_use_removes_the_point_on_it(self):
        point = self.point()
        entry = height()
        self.controller.add_bestammelse("egenskap_punkt", point.id(), entry, height_values(entry))
        self.layers["anvandning_yta"].deleteFeature(self.use.id())
        from plan_case import pump
        pump()
        self.assertEqual(self.layers["egenskap_punkt"].featureCount(), 0)
        self.assertEqual(assignments.read_rows(self.controller.project, "egenskap_punkt"), [])


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class PointDeliveryTests(ExportCase):
    """Testsvitens färdiga plan (se ``test_export.ExportCase``) med en höjdpunkt på den vänstra användningen."""

    def setUp(self):
        super().setUp()
        point = self.point()
        entry = height()
        self.controller.add_bestammelse("egenskap_punkt", point.id(), entry, height_values(entry))

    def point(self, wkt=POINT_ON_LEFT):
        return self.draw("egenskap_punkt", wkt)

    def test_the_point_is_delivered_as_a_point_geometry_that_follows_the_schema(self):
        collection = self.controller.export_ngp()
        problems = CHECKER.problems(collection)
        self.assertEqual(problems, [], "\n".join(problems))
        point = next(f["properties"] for f in collection["features"][1:]
                     if f["properties"]["bestammelseformulering"].startswith("Markens höjd över"))
        geometry = point["bestammelsegeometri"][0]["geometri"]
        self.assertEqual(geometry["typ"], "punkt")
        self.assertEqual(geometry["position"], {"type": "Point", "coordinates": [20.0, 30.0]})
        self.assertEqual(point["bestammelsevarde"][0]["variabelvarde"], "31.8")
        self.assertTrue(point["reglerarAnvandningsbestammelse"], "punkten hör till användningen den ligger på")

    def test_a_delivery_with_a_point_can_be_imported_again(self):
        collection = self.controller.export_ngp()
        gpkg, _ = create_plan_project(self.dir, "importerad", "Eskilstuna", "0484", 3006)
        project = QgsProject()
        layers = load_plan(gpkg, project)
        controller = PlanController(lambda *_: None, lambda *_: None, project=project)
        self.addCleanup(controller.detach)
        controller.import_ngp(collection, BUNDLED)
        self.assertEqual(layers["egenskap_punkt"].featureCount(), 1)
        self.assertEqual(next(layers["egenskap_punkt"].getFeatures())["beteckning"], "+31,8")

    def test_a_point_outside_the_uses_is_reported_by_the_check(self):
        data = validation.collect(self.controller.project)
        point = next(a for a in data.areas if a.table == "egenskap_punkt")
        point.geometry = QgsGeometry.fromWkt(POINT_OUTSIDE)
        texts = [i.text for i in validation.check_geometry(data)]
        self.assertIn("Punkten ligger utanför användningsområdena.", texts)

    def test_heights_are_one_row_in_the_legend(self):
        second = self.point("MultiPoint((30 60))")
        entry = height()
        self.controller.add_bestammelse("egenskap_punkt", second.id(), entry, height_values(entry, "32,5"))
        rows = assignments.read_rows(self.controller.project)
        entries = [e for s in legend.property_sections(rows, BUNDLED) for e in s.entries]
        heights = [e for e in entries if e.code.startswith("+")]
        self.assertEqual([(e.code, e.text) for e in heights], [("+0,0", "Markens höjd över nollplanet")])


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class PointUpgradeTests(unittest.TestCase):
    """En plan från en äldre version får lagret för egenskapspunkter när den öppnas."""

    @classmethod
    def setUpClass(cls):
        from qgis_app import get_app
        cls.app = get_app()

    def old_plan(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        gpkg, _ = create_plan_project(Path(self.tmp.name), "gammal", "Eskilstuna", "0484", 3006)
        ds = ogr.Open(str(gpkg), 1)
        for index in range(ds.GetLayerCount()):
            if ds.GetLayer(index).GetName() == "egenskap_punkt":
                ds.DeleteLayer(index)
                break
        ds = None
        con = sqlite3.connect(gpkg)
        con.execute("UPDATE dp_meta SET value='9' WHERE key='schema_version'")
        con.commit()
        con.close()
        return gpkg

    def test_schema_10_adds_the_point_layer(self):
        self.assertEqual(model.SCHEMA_VERSION, 10)
        gpkg = self.old_plan()
        self.assertTrue(geopackage.upgrade(gpkg))
        ds = ogr.Open(str(gpkg))
        self.assertIsNotNone(ds.GetLayerByName("egenskap_punkt"))
        ds = None
        self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], "10")

    def test_an_old_plan_can_be_opened_and_drawn_on_afterwards(self):
        layers = load_plan(self.old_plan(), QgsProject())
        self.assertTrue(layers["egenskap_punkt"].isValid())

    def test_the_postgis_upgrade_creates_the_point_table_before_it_is_altered(self):
        sql = storage.postgis_upgrade("dp", 3, 3006)
        create = next(i for i, s in enumerate(sql) if 'CREATE TABLE IF NOT EXISTS "dp"."egenskap_punkt"' in s)
        altered = [i for i, s in enumerate(sql) if 'ALTER TABLE "dp"."egenskap_punkt"' in s]
        self.assertTrue(all(i > create for i in altered))
        self.assertIn("geometry(MultiPoint, 3006)", sql[create])
        self.assertFalse(any("egenskap_punkt" in s for s in storage.postgis_upgrade("dp", 10, 3006)))


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class PointGeometryExportTests(unittest.TestCase):
    def test_each_point_of_a_multipoint_becomes_its_own_point(self):
        parts = ex.geometry_parts(QgsGeometry.fromWkt("MultiPoint((1.00049 2), (3 4))"))
        self.assertEqual(parts, [("punkt", {"type": "Point", "coordinates": [1.0, 2.0]}),
                                 ("punkt", {"type": "Point", "coordinates": [3.0, 4.0]})])


if __name__ == "__main__":
    unittest.main()
