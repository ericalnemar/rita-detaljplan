"""Hjälplager: tre lager i en grupp, import av rena geometrier och tilldelning som flyttar hjälpobjektet till planen (QGIS)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, LEFT, LINE_INSIDE, PLAN, RIGHT, filled, pick, pump  # noqa: E402

if HAVE_QGIS:
    import rita_detaljplan
    from osgeo import ogr
    from qgis.core import (QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer)
    from qgis.PyQt.QtWidgets import QToolButton
    from rita_detaljplan.controller import (ASSIGN_TARGETS, HELPER_AREA, HELPER_LAYER, HELPER_POINT, HELPER_TABLES,
                                            SELECTABLE)
    from rita_detaljplan.core import assignments, geopackage, importer, model, storage, symbology
    from rita_detaljplan.core.project import (HELPER_GROUP_NAME, create_plan_project, find_layer, find_plan_group,
                                              load_plan, upgrade_symbology)
    from rita_detaljplan.gui.assign_dialog import AssignDialog
    from rita_detaljplan.gui.plan_toolbar import HELPER_NAMES, ICONS, PlanToolBar
    from test_toolbar import GuiCase
else:  # pragma: no cover
    GuiCase = unittest.TestCase

HELPER_AREA_WKT = "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))"
OUTSIDE_WKT = "MultiPolygon(((200 200, 240 200, 240 240, 200 240, 200 200)))"
PARTLY_OUTSIDE_WKT = "MultiPolygon(((80 80, 120 80, 120 120, 80 120, 80 80)))"


def source_layer(kind, wkts, crs="EPSG:3006"):
    layer = QgsVectorLayer(f"{kind}?crs={crs}&field=namn:string", "källa", "memory")
    features = []
    for number, wkt in enumerate(wkts):
        feature = QgsFeature(layer.fields())
        feature.setAttribute(0, f"objekt {number}")
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    return layer


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class HelperModelTests(GuiCase):
    def test_there_are_three_helper_layers_and_none_of_them_is_ever_delivered(self):
        self.assertEqual([d.name for d in model.HELPER_LAYERS], ["hjalppunkt", "hjalplinje", "hjalpyta"])
        for table in ("hjalppunkt", "hjalplinje", "hjalpyta"):
            self.assertIn(table, model.NOT_DELIVERED)
        self.assertEqual({d.name: d.geometry for d in model.HELPER_LAYERS},
                         {"hjalppunkt": "MultiPoint", "hjalplinje": "MultiLineString", "hjalpyta": "MultiPolygon"})

    def test_the_helper_layers_sit_together_in_a_group_inside_the_plans_group_topmost(self):
        group = find_plan_group(QgsProject.instance())
        first = group.children()[0]
        self.assertEqual(first.name(), HELPER_GROUP_NAME)
        self.assertEqual(HELPER_GROUP_NAME, "Hjälplager")
        self.assertEqual([child.layer().name() for child in first.children()],
                         ["Hjälppunkter", "Hjälplinjer", "Hjälpytor"])
        for table in ("hjalppunkt", "hjalplinje", "hjalpyta"):
            self.assertIs(find_layer(QgsProject.instance(), table), self.layers[table], table)

    def test_the_other_layers_keep_their_places_below_the_helper_group(self):
        group = find_plan_group(QgsProject.instance())
        names = [child.layer().name() for child in group.children()[1:]]
        self.assertEqual(names[:4], ["Egenskap (linje)", "Detaljplan (planområde)", "Egenskap (yta)", "Användning (yta)"])

    def test_a_new_plan_has_the_current_schema_and_the_helper_layers_have_symbology(self):
        self.assertEqual(geopackage.read_meta(self.gpkg)["schema_version"], str(model.SCHEMA_VERSION))
        self.assertEqual(model.SCHEMA_VERSION, 9)
        self.assertEqual(self.layers["hjalpyta"].renderer().symbol().type().name, "Fill")
        self.assertEqual(self.layers["hjalppunkt"].renderer().symbol().type().name, "Marker")
        self.assertFalse(self.layers["hjalpyta"].labelsEnabled())

    def test_a_freshly_loaded_plan_is_not_restyled_again_every_time_it_is_opened(self):
        self.assertFalse(upgrade_symbology(QgsProject.instance()))


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class HelperUpgradeTests(unittest.TestCase):
    """Äldre planer får de nya tabellerna när de öppnas."""

    @classmethod
    def setUpClass(cls):
        from qgis_app import get_app
        cls.app = get_app()

    def old_plan(self, version="8"):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        gpkg, _ = create_plan_project(Path(self.tmp.name), "gammal", "Eskilstuna", "0484", 3006)
        ds = ogr.Open(str(gpkg), 1)
        for name in ("hjalpyta", "hjalppunkt"):
            for index in range(ds.GetLayerCount()):
                if ds.GetLayer(index).GetName() == name:
                    ds.DeleteLayer(index)
                    break
        ds = None
        import sqlite3
        con = sqlite3.connect(gpkg)
        con.execute("UPDATE dp_meta SET value=? WHERE key='schema_version'", (version,))
        con.commit()
        con.close()
        return gpkg

    def tables(self, gpkg):
        ds = ogr.Open(str(gpkg))
        return {ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())}

    def test_a_plan_without_helper_areas_and_points_gets_them(self):
        gpkg = self.old_plan()
        self.assertNotIn("hjalpyta", self.tables(gpkg))
        self.assertTrue(geopackage.upgrade(gpkg))
        self.assertLessEqual({"hjalpyta", "hjalppunkt", "hjalplinje"}, self.tables(gpkg))
        self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))

    def test_an_old_plan_can_be_opened_and_has_the_helper_group_afterwards(self):
        gpkg = self.old_plan()
        project = QgsProject()
        layers = load_plan(gpkg, project)
        self.assertTrue(layers["hjalpyta"].isValid() and layers["hjalppunkt"].isValid())
        self.assertEqual(find_plan_group(project).children()[0].name(), HELPER_GROUP_NAME)

    def test_the_postgis_upgrade_adds_the_new_tables_for_old_schemas_only(self):
        old = "\n".join(storage.postgis_upgrade("dp", 8, 3010))
        self.assertIn('CREATE TABLE IF NOT EXISTS "dp"."hjalpyta"', old)
        self.assertIn('CREATE TABLE IF NOT EXISTS "dp"."hjalppunkt"', old)
        self.assertNotIn('"hjalplinje"', old)
        self.assertIn("geometry(MultiPoint, 3010)", old)
        current = "\n".join(storage.postgis_upgrade("dp", model.SCHEMA_VERSION, 3010))
        self.assertNotIn("CREATE TABLE", current)
        from_start = "\n".join(storage.postgis_upgrade("dp", 3, 3010))
        for name in ("hjalplinje", "hjalpyta", "hjalppunkt"):
            self.assertIn(f'"{name}"', from_start)


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class ImporterTests(GuiCase):
    def targets(self):
        return {kind: self.layers[table] for kind, table in importer.TARGET_TABLES.items()}

    def test_areas_lines_and_points_land_in_their_own_helper_layer_without_attributes(self):
        polygons = source_layer("Polygon", ["Polygon((0 0, 10 0, 10 10, 0 10, 0 0))", "Polygon((20 0, 30 0, 30 10, 20 10, 20 0))"])
        lines = source_layer("LineString", ["LineString(0 0, 50 50)"])
        points = source_layer("Point", ["Point(5 5)", "Point(6 6)", "Point(7 7)"])
        for source in (polygons, lines, points):
            result = importer.import_geometries(source, self.targets())
            self.assertEqual(result.skipped, 0)
        self.assertEqual((self.layers["hjalpyta"].featureCount(), self.layers["hjalplinje"].featureCount(),
                          self.layers["hjalppunkt"].featureCount()), (2, 1, 3))
        feature = next(self.layers["hjalpyta"].getFeatures())
        self.assertIsNone(feature["beskrivning"] if feature["beskrivning"] != __import__("qgis.core", fromlist=["NULL"]).NULL else None)
        self.assertRegex(feature["objektidentitet"], r"^[0-9a-f]{8}-[0-9a-f]{4}-")
        self.assertEqual(feature.geometry().wkbType().name, "MultiPolygon")

    def test_the_result_says_how_many_of_each_went_where(self):
        result = importer.import_geometries(source_layer("Point", ["Point(1 1)", "Point(2 2)"]), self.targets())
        self.assertEqual((result.counts["point"], result.total), (2, 2))
        self.assertIn("2 punkter importerades till Hjälplager", result.text())

    def test_only_selected_objects_can_be_imported(self):
        source = source_layer("Point", ["Point(1 1)", "Point(2 2)", "Point(3 3)"])
        source.selectByIds([next(iter(source.getFeatures())).id()])
        result = importer.import_geometries(source, self.targets(), selected_only=True)
        self.assertEqual(result.counts["point"], 1)

    def test_geometry_is_transformed_to_the_plans_coordinate_system(self):
        source = source_layer("Point", ["Point(16.5 59.37)"], crs="EPSG:4326")
        importer.import_geometries(source, self.targets())
        point = next(self.layers["hjalppunkt"].getFeatures()).geometry().asMultiPoint()[0]
        self.assertTrue(400000 < point.x() < 700000 and 6500000 < point.y() < 6700000, point)

    def test_curves_and_height_values_become_plain_straight_geometry(self):
        parts = importer.clean_parts(QgsGeometry.fromWkt("CircularString (0 0, 1 1, 2 0)"))
        self.assertEqual([kind for kind, _ in parts], ["line"])
        self.assertNotIn("Curve", parts[0][1].wkbType().name)
        (kind, geometry), = importer.clean_parts(QgsGeometry.fromWkt("PointZ (1 2 3)"))
        self.assertFalse(geometry.constGet().is3D())

    def test_multipoints_become_one_point_per_part_and_collections_are_split_by_kind(self):
        self.assertEqual([k for k, _ in importer.clean_parts(QgsGeometry.fromWkt("MultiPoint ((1 1),(2 2))"))], ["point", "point"])
        kinds = sorted(k for k, _ in importer.clean_parts(
            QgsGeometry.fromWkt("GeometryCollection (Point (1 1), LineString (0 0, 1 1), Polygon ((0 0, 1 0, 1 1, 0 0)))")))
        self.assertEqual(kinds, ["line", "point", "polygon"])

    def test_objects_without_geometry_are_skipped_and_invalid_ones_are_counted(self):
        source = source_layer("Polygon", ["Polygon((0 0, 10 10, 10 0, 0 10, 0 0))", ""])  # fjärilsform är ogiltig
        result = importer.import_geometries(source, self.targets())
        self.assertEqual((result.counts["polygon"], result.invalid, result.skipped), (1, 1, 1))
        self.assertIn("ogiltiga", result.text())

    def test_nothing_is_written_outside_the_edit_buffer_and_the_source_is_left_alone(self):
        source = source_layer("Point", ["Point(1 1)"])
        importer.import_geometries(source, self.targets())
        self.assertTrue(self.layers["hjalppunkt"].isEditable())
        self.assertEqual(source.featureCount(), 1)
        self.layers["hjalppunkt"].undoStack().undo()
        self.assertEqual(self.layers["hjalppunkt"].featureCount(), 0, "Ångra tar bort det importerade")


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class HelperControllerTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.draw("detaljplan", PLAN)

    def uses(self):
        return self.layers["anvandning_yta"].featureCount()

    def helper(self, table, wkt):
        return self.add(table, wkt)

    def test_helper_tables_can_always_be_drawn_while_editing(self):
        for table in HELPER_TABLES:
            self.assertTrue(self.controller.can_draw(table)[0], table)

    def test_helper_areas_and_lines_are_assignable_targets_but_points_are_only_selectable(self):
        self.assertEqual(ASSIGN_TARGETS[:2], (HELPER_LAYER, HELPER_AREA))
        self.assertNotIn(HELPER_POINT, ASSIGN_TARGETS)
        self.assertIn(HELPER_POINT, SELECTABLE)

    def test_clicking_finds_a_helper_area_before_the_plan_objects_under_it(self):
        self.helper("hjalpyta", HELPER_AREA_WKT)
        found = self.controller.candidates_at(QgsPointXY(20, 20), 0.5)
        self.assertEqual([c.table for c in found], ["hjalpyta"])
        self.assertTrue(found[0].title.startswith("Hjälpyta"))

    def test_a_helper_point_is_described_without_a_size(self):
        feature = self.helper("hjalppunkt", "MultiPoint((5 5))")
        self.assertEqual(self.controller.describe_area("hjalppunkt", feature.id()), "Hjälppunkt")

    def test_a_helper_area_becomes_a_use_area_and_leaves_the_helper_layer(self):
        helper = self.helper("hjalpyta", HELPER_AREA_WKT)
        entry = pick(self.catalog, "DP_KM_J2")
        new = self.controller.assign_helper("hjalpyta", helper.id(), entry, filled(entry))
        self.assertEqual(new.table, "anvandning_yta")
        self.assertEqual(self.layers["hjalpyta"].featureCount(), 0)
        self.assertEqual(self.uses(), 1)
        use = self.layers["anvandning_yta"].getFeature(new.fid)
        self.assertAlmostEqual(use.geometry().area(), 900.0, 1)
        self.assertEqual(len(self.controller.rows_of("anvandning_yta", new.fid)), 1)
        self.assertEqual(use["bestammelser"], 1)
        self.assertTrue(new.title.startswith("Användningsområde"))

    def test_the_use_is_clipped_against_the_plan_area_like_a_drawn_one(self):
        helper = self.helper("hjalpyta", PARTLY_OUTSIDE_WKT)
        entry = pick(self.catalog, "DP_KM_J2")
        new = self.controller.assign_helper("hjalpyta", helper.id(), entry, filled(entry))
        use = self.layers["anvandning_yta"].getFeature(new.fid)
        self.assertAlmostEqual(use.geometry().area(), 400.0, 1, "bara den del som ligger inom planområdet")
        self.assertTrue(self.warnings, "beskärningen sägs till")

    def test_a_helper_area_outside_the_plan_cannot_become_a_use_and_stays_where_it_is(self):
        helper = self.helper("hjalpyta", OUTSIDE_WKT)
        entry = pick(self.catalog, "DP_KM_J2")
        with self.assertRaisesRegex(assignments.AssignmentError, "utanför planområdet"):
            self.controller.assign_helper("hjalpyta", helper.id(), entry, filled(entry))
        self.assertEqual((self.layers["hjalpyta"].featureCount(), self.uses()), (1, 0))

    def test_a_helper_area_can_become_a_property_area_on_a_use(self):
        self.draw("anvandning_yta", LEFT)
        use = next(self.layers["anvandning_yta"].getFeatures())
        street = pick(self.catalog, layer="anvandning_yta", form="Allmän plats", variables=False)
        self.controller.add_bestammelse("anvandning_yta", use.id(), street, filled(street))
        helper = self.helper("hjalpyta", HELPER_AREA_WKT)
        entry = pick(self.catalog, layer="egenskap_yta", form="Allmän plats", variables=False)
        new = self.controller.assign_helper("hjalpyta", helper.id(), entry, filled(entry))
        self.assertEqual(new.table, "egenskap_yta")
        self.assertEqual((self.layers["hjalpyta"].featureCount(), self.layers["egenskap_yta"].featureCount()), (0, 1))
        self.assertEqual(len(self.controller.rows_of("egenskap_yta", new.fid)), 1)

    def test_a_property_for_the_wrong_land_use_form_is_refused_and_leaves_nothing_behind(self):
        self.draw("anvandning_yta", LEFT)
        use = next(self.layers["anvandning_yta"].getFeatures())
        first = pick(self.catalog, "DP_KM_J2")  # kvartersmark
        self.controller.add_bestammelse("anvandning_yta", use.id(), first, filled(first))
        helper = self.helper("hjalpyta", HELPER_AREA_WKT)
        entry = pick(self.catalog, layer="egenskap_yta", form="Allmän plats", variables=False)
        with self.assertRaises(assignments.AssignmentError):
            self.controller.assign_helper("hjalpyta", helper.id(), entry, filled(entry))
        self.assertEqual((self.layers["hjalpyta"].featureCount(), self.layers["egenskap_yta"].featureCount()), (1, 0))
        self.assertEqual(assignments.read_rows(self.controller.project, "egenskap_yta"), [])

    def test_a_helper_line_becomes_a_property_line(self):
        self.draw("anvandning_yta", LEFT)
        helper = self.helper("hjalplinje", LINE_INSIDE)
        entry = pick(self.catalog, layer="egenskap_linje", variables=False)
        new = self.controller.assign_helper("hjalplinje", helper.id(), entry, filled(entry))
        self.assertEqual(new.table, "egenskap_linje")
        self.assertEqual((self.layers["hjalplinje"].featureCount(), self.layers["egenskap_linje"].featureCount()), (0, 1))

    def test_a_provision_for_another_kind_of_object_is_refused_with_an_explanation(self):
        helper = self.helper("hjalplinje", LINE_INSIDE)
        entry = pick(self.catalog, "DP_KM_J2")  # användningsbestämmelse för en yta
        with self.assertRaisesRegex(assignments.AssignmentError, "annan sorts objekt"):
            self.controller.assign_helper("hjalplinje", helper.id(), entry, filled(entry))
        self.assertEqual(self.layers["hjalplinje"].featureCount(), 1)

    def test_helper_points_cannot_get_provisions(self):
        helper = self.helper("hjalppunkt", "MultiPoint((5 5))")
        entry = pick(self.catalog, "DP_KM_J2")
        with self.assertRaisesRegex(assignments.AssignmentError, "Hjälppunkter kan inte få bestämmelser"):
            self.controller.assign_helper("hjalppunkt", helper.id(), entry, filled(entry))
        self.assertEqual(self.layers["hjalppunkt"].featureCount(), 1)

    def test_what_can_be_chosen_depends_on_the_kind_of_helper(self):
        area = self.helper("hjalpyta", HELPER_AREA_WKT)
        line = self.helper("hjalplinje", LINE_INSIDE)
        point = self.helper("hjalppunkt", "MultiPoint((5 5))")
        by_area = self.controller.entries_for(self.catalog, "hjalpyta", area.id())
        self.assertEqual({e.layer_name for e in by_area}, {"anvandning_yta", "egenskap_yta"})
        self.assertEqual(by_area[0].layer_name, "anvandning_yta", "användningsbestämmelserna först")
        self.assertEqual({e.layer_name for e in self.controller.entries_for(self.catalog, "hjalplinje", line.id())},
                         {"egenskap_linje"})
        self.assertEqual(self.controller.entries_for(self.catalog, "hjalppunkt", point.id()), [])

    def test_the_helpers_that_can_be_assigned_are_counted(self):
        self.assertFalse(self.controller.has_assignable_helpers())
        self.helper("hjalppunkt", "MultiPoint((5 5))")
        self.assertFalse(self.controller.has_assignable_helpers(), "punkter räknas inte")
        self.helper("hjalpyta", HELPER_AREA_WKT)
        self.assertTrue(self.controller.has_assignable_helpers())

    def test_selected_helpers_can_be_given_the_same_provision_together(self):
        for wkt in ("MultiPolygon(((10 10, 20 10, 20 20, 10 20, 10 10)))", "MultiPolygon(((30 30, 40 30, 40 40, 30 40, 30 30)))"):
            self.helper("hjalpyta", wkt)
        self.layers["hjalpyta"].selectAll()
        self.assertEqual(len(self.controller.selected_candidates("hjalpyta")), 2)


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class HelperAssignDialogTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.draw("detaljplan", PLAN)
        self.helper = self.add("hjalpyta", HELPER_AREA_WKT)

    def dialog(self):
        candidates = self.controller.candidates_at(QgsPointXY(20, 20), 0.5)
        dialog = AssignDialog(self.controller, lambda: self.catalog, candidates, lambda c: None)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_dialog_offers_use_and_property_provisions_and_explains_what_happens(self):
        dialog = self.dialog()
        self.assertEqual(dialog.candidate().table, "hjalpyta")
        self.assertGreater(dialog.entry_combo.count(), 10)
        self.assertIn("blir en användningsyta eller en egenskapsyta", dialog.filter_note.text())

    def test_adding_a_provision_turns_the_helper_into_a_plan_object_and_the_dialog_follows_it(self):
        dialog = self.dialog()
        entry = pick(self.catalog, "DP_KM_J2")
        dialog.entry_combo.setCurrentIndex(dialog.combo_index(entry))
        dialog.btn_add.click()
        self.assertEqual(dialog.problems.text(), "")
        self.assertEqual(self.layers["hjalpyta"].featureCount(), 0)
        self.assertEqual(self.layers["anvandning_yta"].featureCount(), 1)
        self.assertEqual(dialog.candidate().table, "anvandning_yta", "dialogen fortsätter med det nya objektet")
        self.assertIn("Hjälpobjektet blev användningsområde", dialog.notice.text())
        self.assertEqual(dialog.rows_list.count(), 1, "bestämmelsen syns i listan över objektets bestämmelser")
        self.assertTrue(dialog.area_combo.itemText(0).startswith("Användningsområde"))

    def test_a_provision_that_does_not_fit_is_explained_and_the_helper_stays(self):
        helper = self.add("hjalpyta", OUTSIDE_WKT)
        dialog = self.dialog()
        dialog.candidates[0] = self.controller.candidates_at(QgsPointXY(220, 220), 0.5)[0]
        dialog._on_area()
        entry = pick(self.catalog, "DP_KM_J2")
        dialog.entry_combo.setCurrentIndex(dialog.combo_index(entry))
        dialog.btn_add.click()
        self.assertIn("utanför planområdet", dialog.problems.text())
        self.assertEqual(self.layers["hjalpyta"].featureCount(), 2)
        self.assertEqual(dialog.candidate().table, "hjalpyta")
        self.assertTrue(helper.isValid())

    def test_the_full_dialog_is_limited_to_property_lines_for_a_helper_line_and_unlimited_for_an_area(self):
        line = self.add("hjalplinje", LINE_INSIDE)
        candidates = self.controller.candidates_at(QgsPointXY(20, 50), 0.5)
        self.assertEqual(candidates[0].table, "hjalplinje")
        self.assertEqual(AssignDialog._catalog_layer(candidates[0]), "egenskap_linje")
        area = self.controller.candidates_at(QgsPointXY(30, 30), 0.5)
        self.assertEqual(area[0].table, "hjalpyta")
        self.assertIsNone(AssignDialog._catalog_layer(area[0]))
        self.assertTrue(line.isValid())


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class HelperToolbarTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)

    def test_the_helper_button_has_a_dropdown_with_line_first_then_area_and_point(self):
        button = self.toolbar.widgetForAction(self.toolbar.draw_actions[HELPER_LAYER])
        self.assertIsInstance(button, QToolButton)
        self.assertEqual(button.popupMode(), QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        actions = button.menu().actions()
        self.assertEqual([a.text() for a in actions], ["Hjälplinje", "Hjälpyta", "Hjälppunkt"])
        self.assertEqual(actions, [self.toolbar.draw_actions[t] for t in (HELPER_LAYER, HELPER_AREA, HELPER_POINT)])
        self.assertEqual(list(HELPER_NAMES.values()), ["Hjälplinje", "Hjälpyta", "Hjälppunkt"])

    def test_only_the_line_sits_in_the_toolbar_itself_and_it_is_the_default_action_of_the_button(self):
        in_bar = self.toolbar.actions()
        self.assertIn(self.toolbar.draw_actions[HELPER_LAYER], in_bar)
        self.assertNotIn(self.toolbar.draw_actions[HELPER_AREA], in_bar)
        self.assertNotIn(self.toolbar.draw_actions[HELPER_POINT], in_bar)

    def test_the_three_draw_actions_have_icons_and_tips_and_the_icon_files_are_valid_svg(self):
        import xml.etree.ElementTree as ET
        for table in (HELPER_LAYER, HELPER_AREA, HELPER_POINT):
            action = self.toolbar.draw_actions[table]
            self.assertFalse(action.icon().isNull(), table)
            self.assertTrue("NGP" in action.toolTip() or "leveransen" in action.toolTip(), table)
        for name in ("helper.svg", "helper_area.svg", "helper_point.svg", "import_geometry.svg"):
            self.assertTrue(ET.parse(ICONS / name).getroot().tag.endswith("svg"), name)

    def test_choosing_helper_area_from_the_menu_makes_that_layer_active_for_drawing(self):
        self.toolbar.refresh()
        self.toolbar.draw(HELPER_AREA, True)
        self.iface.setActiveLayer.assert_called_with(self.layers["hjalpyta"])
        self.assertTrue(self.toolbar.draw_actions[HELPER_AREA].isChecked())
        self.assertFalse(self.toolbar.draw_actions[HELPER_LAYER].isChecked())

    def test_the_button_shows_and_draws_with_the_helper_kind_chosen_last(self):
        button = self.toolbar.widgetForAction(self.toolbar.draw_actions[HELPER_LAYER])
        self.assertIs(button.defaultAction(), self.toolbar.draw_actions[HELPER_LAYER])
        for table in (HELPER_AREA, HELPER_POINT, HELPER_LAYER):
            action = self.toolbar.draw_actions[table]
            action.triggered.emit(True)
            self.assertIs(button.defaultAction(), action, table)
            self.assertEqual(button.icon().cacheKey(), action.icon().cacheKey(), table)
            self.assertEqual(button.toolTip(), action.toolTip(), table)
        self.assertIsNotNone(button.menu(), "rullgardinen finns kvar")

    def test_the_import_button_sits_after_the_helper_button_and_follows_the_editing_state(self):
        actions = self.toolbar.actions()
        self.assertEqual(actions.index(self.toolbar.act_import), actions.index(self.toolbar.draw_actions[HELPER_LAYER]) + 1)
        self.toolbar.refresh()
        self.assertTrue(self.toolbar.act_import.isEnabled())
        for layer in self.layers.values():
            layer.rollBack()
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_import.isEnabled())
        self.assertIn("pennan", self.toolbar.act_import.toolTip())

    def test_the_import_button_calls_the_callback(self):
        calls = []
        toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog, on_import=lambda: calls.append(1))
        self.addCleanup(toolbar.deleteLater)
        toolbar.act_import.trigger()
        self.assertEqual(calls, [1])

    def test_assigning_is_possible_with_only_helper_areas_and_no_use_yet(self):
        self.draw("detaljplan", PLAN)
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_assign.isEnabled())
        self.assertIn("användningsytor", self.toolbar.act_assign.toolTip())
        self.add("hjalpyta", HELPER_AREA_WKT)
        self.toolbar.refresh()
        self.assertTrue(self.toolbar.act_assign.isEnabled())
        self.assertFalse(self.toolbar.act_copy.isEnabled(), "att kopiera bestämmelser kräver färdiga planobjekt")

    def test_a_helper_point_alone_does_not_enable_assigning(self):
        self.draw("detaljplan", PLAN)
        self.add("hjalppunkt", "MultiPoint((5 5))")
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_assign.isEnabled())


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class HelperPluginTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.plugin = rita_detaljplan.classFactory(self.iface)
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)
        patcher = mock.patch("rita_detaljplan.plugin.PlanInfoDialog")  # formuläret öppnas annars modalt vid planområdet
        patcher.start()
        self.addCleanup(patcher.stop)

    def start(self):
        self.plugin.controller.start_editing()
        self.draw("detaljplan", PLAN)

    def import_with(self, source, selected_only=False, accepted=True):
        with mock.patch("rita_detaljplan.plugin.ImportDialog") as dialog_cls:
            dialog = dialog_cls.return_value
            dialog.exec.return_value = accepted
            dialog.source.return_value = source
            dialog.selected_only.isChecked.return_value = selected_only
            return self.plugin.import_geometry()

    def test_the_menu_has_the_import_entry_and_the_toolbar_button_calls_the_same_function(self):
        self.assertIn("Importera geometrier…", [a.text() for a in self.plugin.actions])
        with mock.patch.object(self.plugin, "import_geometry") as called:
            self.plugin.toolbar._import_callback = None
        self.assertIsNotNone(self.plugin.toolbar.act_import)

    def test_importing_puts_the_geometries_in_the_helper_layers_and_reports_it(self):
        self.start()
        result = self.import_with(source_layer("Polygon", ["Polygon((0 0, 10 0, 10 10, 0 10, 0 0))"]))
        self.assertEqual(result.counts["polygon"], 1)
        self.assertEqual(self.layers["hjalpyta"].featureCount(), 1)
        self.assertTrue(any("importerades till Hjälplager" in m for m in self.messages()), self.messages())

    def test_a_cancelled_dialog_imports_nothing(self):
        self.start()
        self.assertIsNone(self.import_with(source_layer("Point", ["Point(1 1)"]), accepted=False))
        self.assertEqual(self.layers["hjalppunkt"].featureCount(), 0)

    def test_importing_before_editing_has_started_says_so(self):
        for layer in self.layers.values():
            layer.rollBack()
        self.assertIsNone(self.import_with(source_layer("Point", ["Point(1 1)"])))
        self.assertTrue(any("pennan" in m for m in self.messages()))

    def test_a_plan_without_the_helper_layers_is_told_to_be_opened_again(self):
        self.start()
        QgsProject.instance().removeMapLayer(self.layers["hjalpyta"].id())
        self.assertIsNone(self.import_with(source_layer("Point", ["Point(1 1)"])))
        self.assertTrue(any("saknar hjälplagren" in m for m in self.messages()))

    def test_the_imported_layers_are_made_visible(self):
        root = QgsProject.instance().layerTreeRoot()
        node = root.findLayer(self.layers["hjalppunkt"].id())
        node.setItemVisibilityChecked(False)
        self.start()
        self.import_with(source_layer("Point", ["Point(1 1)"]))
        self.assertTrue(node.itemVisibilityChecked())


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class HelperSymbologyTests(GuiCase):
    def test_helper_areas_are_drawn_with_a_thin_cyan_outline_and_a_faint_fill(self):
        symbol = self.layers["hjalpyta"].renderer().symbol()
        layer = symbol.symbolLayer(0)
        self.assertEqual(layer.strokeColor().name(), "#00ffff")
        self.assertLess(layer.fillColor().alpha(), 60)

    def test_helper_points_are_a_cyan_cross(self):
        layer = self.layers["hjalppunkt"].renderer().symbol().symbolLayer(0)
        self.assertEqual(layer.color().name(), "#00ffff")

    def test_all_three_helper_layers_have_their_labels_off(self):
        for table in ("hjalppunkt", "hjalplinje", "hjalpyta"):
            self.assertFalse(self.layers[table].labelsEnabled(), table)


if __name__ == "__main__":
    unittest.main()
