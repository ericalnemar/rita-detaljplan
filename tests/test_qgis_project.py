"""Funktionstester mot QGIS (kör med QGIS Python, se tests/run_tests.bat)."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from qgis.core import (Qgis, QgsEditFormConfig, QgsExpressionContext, QgsExpressionContextUtils, QgsGeometry,
                           QgsProject, QgsVectorLayer, QgsVectorLayerUtils)
    from qgis.PyQt.QtGui import QPainter
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from qgis_app import get_app
    HAVE_QGIS = True
except ImportError:  # kördes utanför QGIS
    HAVE_QGIS = False

if HAVE_QGIS:
    from rita_detaljplan.core import geopackage, model
    from rita_detaljplan.core.project import create_plan_project, load_plan

UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
GEOM = {"MultiPolygon": Qgis.WkbType.MultiPolygon, "MultiLineString": Qgis.WkbType.MultiLineString,
        "MultiPoint": Qgis.WkbType.MultiPoint, None: Qgis.WkbType.NoGeometry} if HAVE_QGIS else {}


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class QgisProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        # Windows håller GeoPackage-filer låsta så länge lager lever; städa på bästa sätt.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(QgsProject.instance().clear)
        self.dir = Path(self._tmp.name)
        QgsProject.instance().clear()

    def test_geopackage_layers_geometry_and_crs(self):
        gpkg = geopackage.create_geopackage(self.dir / "plan.gpkg", 3010, {"kommun": "Eskilstuna"})
        for layer_def in model.LAYERS:
            layer = QgsVectorLayer(f"{gpkg.as_posix()}|layername={layer_def.name}", "x", "ogr")
            self.assertTrue(layer.isValid(), layer_def.name)
            self.assertEqual(layer.wkbType(), GEOM[layer_def.geometry], layer_def.name)
            for field in layer_def.fields:
                self.assertGreaterEqual(layer.fields().indexOf(field.name), 0, f"{layer_def.name}.{field.name}")
            if layer_def.geometry:
                self.assertEqual(layer.crs().authid(), "EPSG:3010")
        self.assertEqual(geopackage.read_meta(gpkg)["kommun"], "Eskilstuna")

    def test_rejects_non_sweref_crs_and_existing_file(self):
        with self.assertRaises(ValueError):
            geopackage.create_geopackage(self.dir / "a.gpkg", 3857)
        geopackage.create_geopackage(self.dir / "b.gpkg", 3006)
        with self.assertRaises(FileExistsError):
            geopackage.create_geopackage(self.dir / "b.gpkg", 3006)

    def test_create_plan_project_writes_openable_project(self):
        gpkg, qgz = create_plan_project(self.dir, "dp_test", "Eskilstuna", "0482", 3006)
        self.assertTrue(gpkg.exists() and qgz.exists())
        project = QgsProject()
        self.assertTrue(project.read(str(qgz)))
        self.assertEqual(len(project.mapLayers()), len(model.LAYERS))
        self.assertEqual(project.crs().authid(), "EPSG:3006")
        self.assertEqual(len(project.relationManager().relations()), len(model.RELATIONS))
        self.assertTrue(project.snappingConfig().enabled())

    def test_value_maps_and_constraints(self):
        _, qgz = create_plan_project(self.dir, "dp_test", "Eskilstuna", "0482", 3006)
        project = QgsProject()
        project.read(str(qgz))
        layer = project.mapLayersByName("Detaljplan (planområde)")[0]
        status = layer.fields().indexOf("status")
        setup = layer.editorWidgetSetup(status)
        self.assertEqual(setup.type(), "ValueMap")
        values = [next(iter(entry.values())) for entry in setup.config()["map"]]
        self.assertIn("laga kraft", values)
        self.assertEqual(len(values), 9)
        constraints = layer.fields().field("namn").constraints()
        self.assertTrue(constraints.constraints() & constraints.Constraint.ConstraintNotNull)

    def test_defaults_create_uuid_and_link_children_to_the_plan(self):
        gpkg = geopackage.create_geopackage(self.dir / "plan.gpkg", 3006,
                                            {"kommun": "Eskilstuna", "kommunkod": "0482"})
        project = QgsProject.instance()  # aggregate() slår upp lager via globala projektet
        layers = load_plan(gpkg, project)

        def context(layer):
            ctx = QgsExpressionContext()
            ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
            return ctx

        polygon = QgsGeometry.fromWkt("MultiPolygon(((0 0, 10 0, 10 10, 0 10, 0 0)))")
        plan_layer = layers["detaljplan"]
        feature = QgsVectorLayerUtils.createFeature(plan_layer, polygon, {}, context(plan_layer))
        self.assertRegex(feature["objektidentitet"], UUID_RE)
        self.assertEqual(feature["kommun"], "Eskilstuna")
        self.assertEqual(feature["status"], "påbörjad")
        self.assertEqual(feature["typ"], "detaljplan")
        self.assertEqual(feature["lagesmetodTyp"], "lägesplacering")
        plan_layer.startEditing()
        self.assertTrue(plan_layer.addFeature(feature))
        self.assertTrue(plan_layer.commitChanges(), plan_layer.commitErrors())

        area = layers["egenskap_yta"]
        child = QgsVectorLayerUtils.createFeature(area, polygon, {}, context(area))
        self.assertEqual(child["detaljplan"], feature["objektidentitet"])
        self.assertRegex(child["objektidentitet"], UUID_RE)
        self.assertNotEqual(child["objektidentitet"], feature["objektidentitet"])

    def test_technical_fields_are_hidden_and_new_features_skip_the_form(self):
        _, qgz = create_plan_project(self.dir, "dp_test", "Eskilstuna", "0482", 3006)
        project = QgsProject()
        project.read(str(qgz))
        layer = project.mapLayersByName("Egenskap (yta)")[0]
        idx = layer.fields().indexOf
        for name in ("objektidentitet", "detaljplan", "farg", "symbol", "anvandningsform", "bestammelser",
                     "lagesmetodTyp"):
            self.assertEqual(layer.editorWidgetSetup(idx(name)).type(), "Hidden", name)
        config = layer.editFormConfig()
        self.assertTrue(config.readOnly(idx("beteckning")), "beteckningen sätts av pluginet")
        self.assertEqual(config.suppress(), QgsEditFormConfig.FeatureFormSuppress.SuppressOn)

        rows_layer = project.mapLayersByName("Planbestämmelser")[0]
        ridx = rows_layer.fields().indexOf
        for name in ("objektidentitet", "yta", "tabell", "planbestammelsekatalogreferens", "bestammelsekod",
                     "bestammelsevarde"):
            self.assertEqual(rows_layer.editorWidgetSetup(ridx(name)).type(), "Hidden", name)
        self.assertNotEqual(rows_layer.editorWidgetSetup(ridx("motiv")).type(), "Hidden")
        self.assertTrue(rows_layer.editFormConfig().readOnly(ridx("bestammelseformulering")))

    def test_layers_are_styled_from_the_bundled_style_library(self):
        _, qgz = create_plan_project(self.dir, "dp_test", "Eskilstuna", "0482", 3006)
        project = QgsProject()
        project.read(str(qgz))

        use = project.mapLayersByName("Användning (yta)")[0]
        self.assertEqual(use.renderer().type(), "categorizedSymbol")
        self.assertIn('"farg"', use.renderer().classAttribute())
        self.assertIn("ej tilldelad", {c.value() for c in use.renderer().categories()})
        categories = {c.value(): c for c in use.renderer().categories()}
        self.assertLessEqual({"Gul", "Blågrå", "Ljusgrön", "Röd"}, set(categories))
        self.assertGreaterEqual(categories["Gul"].symbol().symbolLayerCount(), 2, "fyllning + användningsgräns")
        self.assertTrue(use.labelsEnabled())

        prop = project.mapLayersByName("Egenskap (yta)")[0]
        values = {c.value() for c in prop.renderer().categories()}
        self.assertIn("Marken får inte förses med byggnad/byggnadsverk", values)
        line = project.mapLayersByName("Egenskap (linje)")[0]
        self.assertLessEqual({"Utfart får inte finnas", "Stängsel ska finnas"},
                             {c.value() for c in line.renderer().categories()})
        self.assertIsNotNone(project.mapLayersByName("Detaljplan (planområde)")[0].renderer())

    def test_the_layer_order_gives_the_hierarchy_plan_over_use_over_property(self):
        _, qgz = create_plan_project(self.dir, "dp_test", "Eskilstuna", "0482", 3006)
        project = QgsProject()
        project.read(str(qgz))
        order = [node.layer().name() for node in project.layerTreeRoot().findLayers()]
        self.assertEqual(order[:5], ["Hjälplinjer", "Egenskap (linje)", "Detaljplan (planområde)",
                                     "Användning (yta)", "Egenskap (yta)"])
        # användningen multipliceras med det som ligger under, så att egenskapsytornas mönster syns igenom
        use = project.mapLayersByName("Användning (yta)")[0]
        self.assertEqual(use.blendMode(), QPainter.CompositionMode.CompositionMode_Multiply)

    def test_the_plan_layer_uses_no_form_because_the_plugin_asks_for_the_plans_details(self):
        _, qgz = create_plan_project(self.dir, "dp_test", "Eskilstuna", "0482", 3006)
        project = QgsProject()
        project.read(str(qgz))
        config = project.mapLayersByName("Detaljplan (planområde)")[0].editFormConfig()
        self.assertEqual(config.suppress(), QgsEditFormConfig.FeatureFormSuppress.SuppressOn)

    def test_plans_from_an_older_schema_are_refused_with_an_explanation(self):
        gpkg = geopackage.create_geopackage(self.dir / "gammal.gpkg", 3006, {"schema_version": "1"})
        with self.assertRaises(ValueError) as caught:
            load_plan(gpkg, QgsProject())
        self.assertIn("äldre version", str(caught.exception))
        self.assertIn("Ny detaljplan", str(caught.exception))

    def test_all_plan_layers_lie_in_one_group_named_after_the_plan(self):
        from rita_detaljplan.core.project import find_plan_group, set_plan_name
        gpkg, _ = create_plan_project(self.dir, "dp_grupp", "Eskilstuna", "0484", 3006)
        project = QgsProject()
        layers = load_plan(gpkg, project)
        group = find_plan_group(project)
        self.assertIsNotNone(group)
        self.assertEqual(group.name(), "dp_grupp", "filnamnet tills planen fått ett namn")
        self.assertEqual(len(group.findLayers()), len(layers))
        self.assertEqual(len(project.layerTreeRoot().findLayers()), len(layers), "inga lager utanför gruppen")
        self.assertIs(project.layerTreeRoot().children()[0], group)
        set_plan_name(project, "Kv Väktaren")
        self.assertEqual(group.name(), "Kv Väktaren")
        self.assertEqual(project.title(), "Kv Väktaren")
        set_plan_name(project, "   ")
        self.assertEqual(group.name(), "Kv Väktaren", "tomt namn ändrar inget")

    def test_the_group_takes_its_name_from_the_plan_when_the_plan_is_reloaded(self):
        from rita_detaljplan.core.project import find_plan_group
        gpkg, _ = create_plan_project(self.dir, "dp_namn", "Eskilstuna", "0484", 3006)
        first = QgsProject()
        layers = load_plan(gpkg, first)
        plan = layers["detaljplan"]
        self.assertTrue(plan.startEditing())
        feature = QgsVectorLayerUtils.createFeature(plan)
        feature.setGeometry(QgsGeometry.fromWkt("MultiPolygon(((0 0,10 0,10 10,0 10,0 0)))"))
        feature.setAttribute("namn", "Kv Väktaren")
        self.assertTrue(plan.addFeature(feature))
        self.assertTrue(plan.commitChanges(), plan.commitErrors())
        second = QgsProject()
        load_plan(gpkg, second)
        self.assertEqual(find_plan_group(second).name(), "Kv Väktaren")

    def test_the_plan_group_is_collapsed_by_default(self):
        from rita_detaljplan.core.project import find_plan_group
        gpkg, _ = create_plan_project(self.dir, "dp_fall", "Eskilstuna", "0484", 3006)
        project = QgsProject()
        load_plan(gpkg, project)
        self.assertFalse(find_plan_group(project).isExpanded())

    def test_the_group_can_be_collapsed_again_after_it_has_been_expanded(self):
        from rita_detaljplan.core.project import collapse_plan_group, find_plan_group
        gpkg, _ = create_plan_project(self.dir, "dp_fall2", "Eskilstuna", "0484", 3006)
        project = QgsProject()
        load_plan(gpkg, project)
        find_plan_group(project).setExpanded(True)  # t.ex. när ett lager blir aktivt
        collapse_plan_group(project)
        self.assertFalse(find_plan_group(project).isExpanded())

    def test_a_saved_new_plan_project_opens_with_the_group_collapsed(self):
        from rita_detaljplan.core.project import find_plan_group
        _, qgz = create_plan_project(self.dir, "dp_fall3", "Eskilstuna", "0484", 3006)
        project = QgsProject()
        self.assertTrue(project.read(str(qgz)))
        self.assertFalse(find_plan_group(project).isExpanded())

    def test_helper_lines_are_a_plain_line_layer_that_is_never_delivered(self):
        gpkg, _ = create_plan_project(self.dir, "dp_hjalp", "Eskilstuna", "0484", 3006)
        project = QgsProject()
        layers = load_plan(gpkg, project)
        helper = layers["hjalplinje"]
        self.assertEqual(helper.wkbType(), Qgis.WkbType.MultiLineString)
        self.assertIn("hjalplinje", model.NOT_DELIVERED)
        self.assertNotIn("hjalplinje", [r[1] for r in model.RELATIONS], "hör inte till planen")
        self.assertEqual(helper.editFormConfig().suppress(), QgsEditFormConfig.FeatureFormSuppress.SuppressOn)

    def test_a_schema_3_plan_is_upgraded_with_helper_lines(self):
        import sqlite3
        from osgeo import ogr
        gpkg, _ = create_plan_project(self.dir, "dp_gammal", "Eskilstuna", "0484", 3006)
        ds = ogr.Open(str(gpkg), 1)
        ds.DeleteLayer("hjalplinje")
        ds = None
        con = sqlite3.connect(str(gpkg))
        con.execute("UPDATE dp_meta SET value='3' WHERE key='schema_version'")
        con.commit()
        con.close()
        project = QgsProject()
        layers = load_plan(gpkg, project)
        self.assertTrue(layers["hjalplinje"].isValid())
        self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))

    def test_load_plan_rejects_foreign_geopackage(self):
        from osgeo import ogr
        path = self.dir / "other.gpkg"
        ogr.GetDriverByName("GPKG").CreateDataSource(str(path)).FlushCache()
        with self.assertRaises(ValueError):
            load_plan(path, QgsProject())


if __name__ == "__main__":
    unittest.main()
