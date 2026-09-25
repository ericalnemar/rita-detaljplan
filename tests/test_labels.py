"""Delade ytor, flyttbar text och textverktyget (kräver QGIS)."""
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, LEFT, PLAN, RIGHT, filled, pick, pump  # noqa: E402

if HAVE_QGIS:
    from osgeo import ogr
    from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsPalLayerSettings, \
        QgsPointXY, QgsProject, QgsRectangle
    from qgis.PyQt.QtCore import Qt
    from rita_detaljplan.core import geopackage, model
    from rita_detaljplan.core.project import create_plan_project, load_plan
    from rita_detaljplan.core.symbology import UNASSIGNED, _SYMBOL_CLASS, _USE_CLASS
    from test_toolbar import GuiCase
    from test_symbology_render import RenderCase, is_dark


class SplitCase(GuiCase):
    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.build_plan(uses=(PLAN,))
        pump()

    def assigned_use(self):
        use = self.features("anvandning_yta")[0]
        entry = pick(self.catalog, "DP_KM_J2")
        self.controller.add_bestammelse("anvandning_yta", use.id(), entry, filled(entry))
        return self.layers["anvandning_yta"].getFeature(use.id())

    def split(self, table, x=50.0):
        layer = self.layers[table]
        result = layer.splitFeatures([QgsPointXY(x, -10), QgsPointXY(x, 110)])
        self.assertEqual(int(result), 0)
        pump()
        return sorted(layer.getFeatures(), key=lambda f: f.geometry().centroid().asPoint().x())

    def klass(self, feature, expression):
        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(self.layers["detaljplan"]))
        context.setFeature(feature)
        return QgsExpression(expression).evaluate(context)


class SplitTests(SplitCase):
    def test_a_use_split_in_two_keeps_its_provision_on_one_part_only(self):
        self.assigned_use()
        left, right = self.split("anvandning_yta")
        kept = [f for f in (left, right) if f["bestammelser"] == 1]
        bare = [f for f in (left, right) if f["bestammelser"] == 0]
        self.assertEqual((len(kept), len(bare)), (1, 1))
        self.assertEqual(kept[0]["beteckning"], "J")
        self.assertFalse(bare[0]["beteckning"])
        self.assertFalse(bare[0]["farg"])
        self.assertFalse(bare[0]["anvandningsform"])

    def test_the_new_part_looks_unassigned_while_the_old_part_keeps_its_colour(self):
        self.assigned_use()
        parts = self.split("anvandning_yta")
        classes = sorted(self.klass(f, _USE_CLASS) for f in parts)
        self.assertEqual(classes, sorted([UNASSIGNED, "Blågrå"]))

    def test_the_parts_have_different_identities_and_only_one_owns_the_rows(self):
        self.assigned_use()
        parts = self.split("anvandning_yta")
        ids = [f["objektidentitet"] for f in parts]
        self.assertTrue(all(ids) and ids[0] != ids[1])
        owners = [f for f in parts if self.controller.rows_of("anvandning_yta", f.id())]
        self.assertEqual(len(owners), 1)
        self.assertEqual(owners[0]["bestammelser"], 1)

    def test_a_split_property_area_behaves_the_same(self):
        self.assigned_use()
        prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 90 10, 90 40, 10 40, 10 10)))")
        entry = pick(self.catalog, layer="egenskap_yta", form="Kvartersmark")
        self.controller.add_bestammelse("egenskap_yta", prop.id(), entry, filled(entry))
        parts = self.split("egenskap_yta")
        self.assertEqual(sorted(f["bestammelser"] for f in parts), [0, 1])
        classes = [self.klass(f, _SYMBOL_CLASS) for f in parts]
        self.assertIn(UNASSIGNED, classes)

    def test_the_new_part_starts_with_automatic_text_placement(self):
        use = self.assigned_use()
        self.controller.move_label("anvandning_yta", use.id(), QgsPointXY(20, 20))
        parts = self.split("anvandning_yta")
        with_position = [f for f in parts if f["label_x"] is not None]
        self.assertLessEqual(len(with_position), 1, "bara en del kan behålla det flyttade läget")
        for f in parts:
            if f["bestammelser"] == 0:
                self.assertIsNone(f["label_x"])

    def test_a_pasted_copy_with_the_same_identity_gets_its_own(self):
        use = self.assigned_use()
        copy = self.add("anvandning_yta", "MultiPolygon(((0 0, 10 0, 10 10, 0 10, 0 0)))",
                        objektidentitet=use["objektidentitet"])
        pump()
        ids = [f["objektidentitet"] for f in self.layers["anvandning_yta"].getFeatures()]
        self.assertEqual(len(ids), len(set(ids)))


class SchemaTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_the_area_layers_have_hidden_plugin_only_position_fields(self):
        for layer_def in model.AREA_LAYERS:
            names = [f.name for f in layer_def.fields]
            self.assertIn("label_x", names)
            self.assertIn("label_y", names)
        self.assertLessEqual({"label_x", "label_y"}, set(model.PLUGIN_ONLY_FIELDS))

    def test_a_schema_4_plan_gets_the_position_fields(self):
        gpkg, _ = create_plan_project(self.dir, "gammal", "Eskilstuna", "0484", 3006)
        ds = ogr.Open(str(gpkg), 1)
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            layer = ds.GetLayerByName(name)
            for field in ("label_x", "label_y"):
                layer.DeleteField(layer.GetLayerDefn().GetFieldIndex(field))
        ds = None
        con = sqlite3.connect(str(gpkg))
        con.execute("UPDATE dp_meta SET value='4' WHERE key='schema_version'")
        con.commit()
        con.close()
        project = QgsProject()
        layers = load_plan(gpkg, project)
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            self.assertGreaterEqual(layers[name].fields().indexOf("label_x"), 0, name)
        self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))

    def test_a_schema_6_plan_gets_the_text_width_and_the_secondary_boundary_field(self):
        gpkg, _ = create_plan_project(self.dir, "sex", "Eskilstuna", "0484", 3006)
        ds = ogr.Open(str(gpkg), 1)
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            layer = ds.GetLayerByName(name)
            layer.DeleteField(layer.GetLayerDefn().GetFieldIndex("label_w"))
        layer = ds.GetLayerByName("egenskap_yta")
        layer.DeleteField(layer.GetLayerDefn().GetFieldIndex("sekundar"))
        ds = None
        con = sqlite3.connect(str(gpkg))
        con.execute("UPDATE dp_meta SET value='6' WHERE key='schema_version'")
        con.commit()
        con.close()
        project = QgsProject()
        layers = load_plan(gpkg, project)
        for name in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            self.assertGreaterEqual(layers[name].fields().indexOf("label_w"), 0, name)
        self.assertGreaterEqual(layers["egenskap_yta"].fields().indexOf("sekundar"), 0)
        self.assertEqual(geopackage.read_meta(gpkg)["schema_version"], str(model.SCHEMA_VERSION))

    def test_the_new_fields_are_hidden_plugin_only_fields(self):
        self.assertLessEqual({"label_w", "sekundar"}, set(model.PLUGIN_ONLY_FIELDS))

    def test_an_up_to_date_plan_is_left_alone(self):
        gpkg, _ = create_plan_project(self.dir, "ny", "Eskilstuna", "0484", 3006)
        self.assertFalse(geopackage.upgrade(gpkg))


class LabelPlacementTests(RenderCase):
    def test_every_label_layer_can_be_moved_by_its_position_fields(self):
        for table in ("anvandning_yta", "egenskap_yta", "egenskap_linje"):
            labeling = self.layers[table].labeling()  # måste hållas vid liv så länge inställningarna används
            settings = labeling.settings()
            props = settings.dataDefinedProperties()
            self.assertEqual(props.property(QgsPalLayerSettings.Property.PositionX).field(), "label_x", table)
            self.assertEqual(props.property(QgsPalLayerSettings.Property.PositionY).field(), "label_y", table)
            self.assertTrue(props.isActive(QgsPalLayerSettings.Property.PositionX), table)

    def label_pixels(self, **attrs):
        plan = "MultiPolygon(((0 0, 100 0, 100 60, 0 60, 0 0)))"
        self.add("detaljplan", plan)
        self.add("anvandning_yta", plan, bestammelser=1, farg="Gul", beteckning="BC", **attrs)
        image = self.render(self.in_map_order(["anvandning_yta"]), extent=(-5, -5, 105, 65), size=440)
        pts = [(x, y) for x in range(440) for y in range(440) if is_dark(image.pixelColor(x, y))
               and 20 < x < 420 and 20 < y < 420]
        return (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)) if pts else None

    def test_a_moved_text_is_drawn_at_its_new_position(self):
        default = self.label_pixels()
        self.assertIsNotNone(default)
        for layer in self.layers.values():
            if layer.isSpatial():
                layer.rollBack()
                layer.startEditing()
                for fid in layer.allFeatureIds():
                    layer.deleteFeature(fid)
        moved = self.label_pixels(label_x=15.0, label_y=10.0)
        self.assertIsNotNone(moved)
        self.assertLess(moved[0], default[0] - 100, "flyttad åt vänster")
        self.assertGreater(moved[1], default[1] + 40, "flyttad nedåt (bildens y växer nedåt)")


class LabelToolCase(GuiCase):
    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.uses = self.build_plan(uses=(LEFT, RIGHT))
        self.tool = __import__("rita_detaljplan.gui.label_tool", fromlist=["LabelTool"]).LabelTool(
            self.canvas, self.controller, lambda text, warning=False: self.reports.append((text, warning)))
        self.reports = []
        self.addCleanup(self.tool.deleteLater)
        self.LabelRef = __import__("rita_detaljplan.gui.label_tool", fromlist=["LabelRef"]).LabelRef
        left, right = self.uses
        self.left_label = self.ref("anvandning_yta", left, QgsRectangle(20, 45, 30, 55))
        self.right_label = self.ref("anvandning_yta", right, QgsRectangle(70, 45, 80, 55))
        self.labels = [self.left_label, self.right_label]
        self.tool.labels_at = lambda p: [l for l in self.labels if l.rect.contains(p)]
        self.tool.labels_in = lambda r: [l for l in self.labels if r.contains(l.rect)]

    def ref(self, table, feature, rect):
        return self.LabelRef(table, feature.id(), rect)

    def drag(self, start, end, shift=False):
        self.tool.press(QgsPointXY(*start), shift)
        self.tool.drag_to(QgsPointXY(*end))
        self.tool.release(QgsPointXY(*end))


class LabelToolTests(LabelToolCase):
    def test_a_click_on_a_text_selects_it(self):
        self.drag((25, 50), (25, 50))
        self.assertEqual([l.key for l in self.tool.selected], [self.left_label.key])

    def test_a_click_on_another_text_replaces_the_selection_and_shift_adds(self):
        self.drag((25, 50), (25, 50))
        self.drag((75, 50), (75, 50))
        self.assertEqual([l.key for l in self.tool.selected], [self.right_label.key])
        self.drag((25, 50), (25, 50), shift=True)
        self.assertEqual(len(self.tool.selected), 2)

    def test_a_click_on_empty_ground_clears_the_selection(self):
        self.drag((25, 50), (25, 50))
        self.drag((50, 90), (50, 90))
        self.assertEqual(self.tool.selected, [])

    def test_dragging_from_empty_ground_selects_the_texts_inside_the_rectangle(self):
        self.drag((10, 40), (35, 60))
        self.assertEqual([l.key for l in self.tool.selected], [self.left_label.key])
        self.drag((10, 40), (90, 60))
        self.assertEqual(len(self.tool.selected), 2)

    def test_a_rectangle_around_nothing_reports_it(self):
        self.drag((45, 5), (55, 10))
        self.assertEqual(self.tool.selected, [])
        self.assertTrue(any("Ingen text" in text for text, _ in self.reports))

    def test_shift_rectangle_adds_to_the_selection(self):
        self.drag((25, 50), (25, 50))
        self.drag((60, 40), (90, 60), shift=True)
        self.assertEqual(len(self.tool.selected), 2)

    def test_dragging_a_text_moves_it_and_writes_the_position(self):
        self.drag((25, 50), (30, 30))
        layer = self.layers["anvandning_yta"]
        feature = layer.getFeature(self.left_label.fid)
        self.assertAlmostEqual(feature["label_x"], 30.0)  # textens mitt (25, 50) flyttades (+5, -20)
        self.assertAlmostEqual(feature["label_y"], 30.0)

    def test_the_moved_text_is_kept_selected_at_its_new_place(self):
        self.drag((25, 50), (30, 30))
        self.assertEqual(len(self.tool.selected), 1)
        self.assertAlmostEqual(self.tool.selected[0].rect.center().y(), 30.0)

    def test_every_selected_text_moves_the_same_distance(self):
        self.drag((10, 40), (90, 60))
        self.drag((25, 50), (25, 30))
        layer = self.layers["anvandning_yta"]
        self.assertAlmostEqual(layer.getFeature(self.left_label.fid)["label_y"], 30.0)
        self.assertAlmostEqual(layer.getFeature(self.right_label.fid)["label_y"], 30.0)
        self.assertAlmostEqual(layer.getFeature(self.right_label.fid)["label_x"], 75.0)

    def test_a_text_can_be_moved_outside_its_area(self):
        self.drag((25, 50), (90, 50))  # den vänstra ytan slutar vid x = 50
        feature = self.layers["anvandning_yta"].getFeature(self.left_label.fid)
        self.assertAlmostEqual(feature["label_x"], 90.0)
        self.assertAlmostEqual(feature["label_y"], 50.0)
        from qgis.core import QgsGeometry
        self.assertFalse(feature.geometry().intersects(
            QgsGeometry.fromPointXY(QgsPointXY(feature["label_x"], feature["label_y"]))))

    def test_a_click_without_dragging_moves_nothing(self):
        self.drag((25, 50), (25, 50))
        self.assertIsNone(self.layers["anvandning_yta"].getFeature(self.left_label.fid)["label_x"])

    def test_moving_needs_an_edit_session(self):
        self.controller.stop_editing(save=False)
        self.tool.selected = [self.left_label]
        self.assertEqual(self.tool.move_selected(5, 5), 0)
        self.assertTrue(any("pennan" in text and warning for text, warning in self.reports))

    def test_delete_returns_the_selected_texts_to_automatic_placement(self):
        self.drag((25, 50), (30, 30))
        self.assertEqual(self.tool.reset_selected(), 1)
        feature = self.layers["anvandning_yta"].getFeature(self.left_label.fid)
        self.assertIsNone(feature["label_x"])
        self.assertEqual(self.tool.selected, [])

    def test_escape_clears_the_selection(self):
        from qgis.PyQt.QtGui import QKeyEvent
        from qgis.PyQt.QtCore import QEvent
        self.drag((25, 50), (25, 50))
        self.tool.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.tool.selected, [])

    def test_only_our_label_layers_count(self):
        results = SimpleNamespace(labelsAtPosition=lambda p: [
            SimpleNamespace(layerID=self.layers["anvandning_yta"].id(), featureId=7, labelRect=QgsRectangle(0, 0, 1, 1),
                            isUnplaced=False),
            SimpleNamespace(layerID=self.layers["detaljplan"].id(), featureId=1, labelRect=QgsRectangle(0, 0, 1, 1),
                            isUnplaced=False),
            SimpleNamespace(layerID=self.layers["anvandning_yta"].id(), featureId=8, labelRect=QgsRectangle(0, 0, 1, 1),
                            isUnplaced=True),
            SimpleNamespace(layerID="okänt", featureId=9, labelRect=QgsRectangle(0, 0, 1, 1), isUnplaced=False)])
        tool = type(self.tool)(self.canvas, self.controller, lambda *a: None)
        self.addCleanup(tool.deleteLater)
        with mock.patch.object(self.canvas, "labelingResults", return_value=results):
            found = tool.labels_at(QgsPointXY(0, 0))
        self.assertEqual([(l.table, l.fid) for l in found], [("anvandning_yta", 7)])

    def test_without_a_drawn_map_there_are_no_texts(self):
        tool = type(self.tool)(self.canvas, self.controller, lambda *a: None)
        self.addCleanup(tool.deleteLater)
        self.assertEqual(tool.labels_at(QgsPointXY(1, 1)), [])


class LabelResizeTests(LabelToolCase):
    """Textrutan för egenskapsbestämmelser omformas genom att dra i hörnen; bokstävernas storlek ändras aldrig."""

    def setUp(self):
        super().setUp()
        self.canvas.setExtent(QgsRectangle(0, 0, 100, 100))  # 0,25 m per bildpunkt: hörnens träffyta blir 2 m
        self.prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        self.prop_label = self.ref("egenskap_yta", self.prop, QgsRectangle(15, 20, 35, 30))
        self.labels.append(self.prop_label)
        self.layer = self.layers["egenskap_yta"]

    def values(self, table="egenskap_yta", fid=None):
        feature = self.layers[table].getFeature(self.prop.id() if fid is None else fid)
        return feature["label_x"], feature["label_y"], feature["label_w"]

    def test_dragging_a_corner_of_a_selected_text_sets_its_width_and_middle(self):
        self.drag((25, 25), (25, 25))
        self.assertEqual([l.key for l in self.tool.selected], [self.prop_label.key])
        self.drag((35, 30), (30, 34))  # övre högra hörnet mot det motsatta (15, 20) som ligger fast
        x, y, w = self.values()
        self.assertAlmostEqual(w, 15.0)
        self.assertAlmostEqual(x, 22.5)
        self.assertAlmostEqual(y, 27.0)

    def test_the_selection_follows_the_new_shape(self):
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (30, 34))
        (label,) = self.tool.selected
        self.assertEqual((label.rect.xMinimum(), label.rect.xMaximum()), (15.0, 30.0))

    def test_a_corner_only_works_on_a_text_that_is_already_selected(self):
        self.drag((35, 30), (30, 34))  # texten är inte markerad: klicket träffar bara texten och flyttar den
        self.assertIsNone(self.values()[2])

    def test_the_text_of_a_use_cannot_be_reshaped_only_moved(self):
        self.drag((25, 50), (25, 50))
        self.drag((30, 55), (20, 60))  # hörnet på användningens text
        x, y, w = self.values("anvandning_yta", self.uses[0].id())
        self.assertIsNone(w)
        self.assertIsNotNone(x, "den flyttades i stället")

    def test_the_size_of_the_letters_is_never_changed_by_reshaping(self):
        from qgis.core import QgsPalLayerSettings
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (30, 34))
        settings = self.layer.labeling().settings()
        self.assertFalse(settings.dataDefinedProperties().isActive(QgsPalLayerSettings.Property.Size))
        self.assertFalse(settings.dataDefinedProperties().isActive(QgsPalLayerSettings.Property.FontSizeUnit))

    def test_a_tiny_rectangle_still_gets_a_usable_width(self):
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (15.2, 20.2))
        self.assertGreaterEqual(self.values()[2], self.controller.MIN_LABEL_WIDTH)

    def test_a_click_on_a_corner_without_dragging_changes_nothing(self):
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (35, 30))
        self.assertEqual(self.values(), (None, None, None))

    def test_reshaping_needs_an_edit_session(self):
        self.drag((25, 25), (25, 25))
        self.controller.stop_editing(save=False)
        self.reports.clear()
        self.assertFalse(self.tool.resize_label(self.prop_label, QgsRectangle(15, 20, 30, 34)))
        self.assertTrue(self.reports and self.reports[-1][1])

    def test_delete_gives_the_text_its_original_shape_back(self):
        self.drag((25, 25), (25, 25))
        self.drag((35, 30), (30, 34))
        self.tool.reset_selected()
        self.assertEqual(self.values(), (None, None, None))

    def test_the_handles_are_shown_for_a_selected_property_text_only(self):
        self.drag((25, 25), (25, 25))
        self.assertEqual(self.tool._handles.numberOfVertices(), 4)
        self.drag((25, 50), (25, 50))
        self.assertEqual(self.tool._handles.numberOfVertices(), 0, "användningens text har inga handtag")


class LabelControllerTests(SplitCase):
    def test_move_label_writes_the_position_and_reset_clears_it(self):
        use = self.features("anvandning_yta")[0]
        self.assertEqual(self.controller.move_label("anvandning_yta", use.id(), QgsPointXY(30, 40)), QgsPointXY(30, 40))
        moved = self.layers["anvandning_yta"].getFeature(use.id())
        self.assertEqual((moved["label_x"], moved["label_y"]), (30.0, 40.0))
        self.controller.reset_label("anvandning_yta", use.id())
        self.assertIsNone(self.layers["anvandning_yta"].getFeature(use.id())["label_x"])

    def test_an_outside_position_is_kept_as_is(self):
        use = self.features("anvandning_yta")[0]
        point = self.controller.move_label("anvandning_yta", use.id(), QgsPointXY(150, 50))
        self.assertAlmostEqual(point.x(), 150.0)
        self.assertAlmostEqual(point.y(), 50.0)
        moved = self.layers["anvandning_yta"].getFeature(use.id())
        self.assertAlmostEqual(moved["label_x"], 150.0)

    def test_a_missing_area_is_ignored(self):
        self.assertIsNone(self.controller.move_label("anvandning_yta", 9999, QgsPointXY(1, 1)))


class ResizeLabelControllerTests(SplitCase):
    def test_resize_label_writes_width_and_middle_and_reset_clears_them(self):
        from qgis.core import QgsRectangle as R
        prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        point = self.controller.resize_label("egenskap_yta", prop.id(), R(10, 20, 30, 30))
        self.assertEqual((point.x(), point.y()), (20.0, 25.0))
        stored = self.layers["egenskap_yta"].getFeature(prop.id())
        self.assertEqual((stored["label_x"], stored["label_y"], stored["label_w"]), (20.0, 25.0, 20.0))
        self.controller.reset_label("egenskap_yta", prop.id())
        stored = self.layers["egenskap_yta"].getFeature(prop.id())
        self.assertEqual((stored["label_x"], stored["label_y"], stored["label_w"]), (None, None, None))

    def test_only_property_areas_have_a_reshapable_text(self):
        from qgis.core import QgsRectangle as R
        self.assertEqual(self.controller.RESIZABLE_LABELS, ("egenskap_yta",))
        use = next(iter(self.layers["anvandning_yta"].getFeatures()))
        self.assertIsNone(self.controller.resize_label("anvandning_yta", use.id(), R(0, 0, 10, 10)))
        self.assertIsNone(self.controller.resize_label("egenskap_yta", 9999, R(0, 0, 10, 10)))

    def test_a_new_or_split_area_starts_without_a_reshaped_text(self):
        from rita_detaljplan.core import assignments
        from rita_detaljplan.core.project import apply_attributes
        prop = self.draw("egenskap_yta", "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        apply_attributes(self.layers["egenskap_yta"], [prop.id()], {"label_w": 12.0})
        assignments.reset_new_area(self.controller.project, "egenskap_yta", prop.id())
        self.assertIsNone(self.layers["egenskap_yta"].getFeature(prop.id())["label_w"])


class ToolBarLabelTests(GuiCase):
    def setUp(self):
        super().setUp()
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        for layer in self.layers.values():
            layer.rollBack()
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)

    def test_the_text_button_has_an_icon_and_is_a_click_tool_that_excludes_the_others(self):
        self.assertFalse(self.toolbar.act_label.icon().isNull())
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        pump()
        self.assertTrue(self.toolbar.act_label.isEnabled())
        self.toolbar.act_label.trigger()
        self.assertIs(self.canvas.mapTool(), self.toolbar.label_tool)
        self.assertTrue(self.toolbar.act_label.isChecked())
        self.toolbar.act_select.trigger()
        self.assertFalse(self.toolbar.act_label.isChecked())
        self.toolbar.act_label.trigger()
        self.assertFalse(self.toolbar.act_select.isChecked())
        self.toolbar.act_assign.trigger()
        self.assertFalse(self.toolbar.act_label.isChecked())
        self.toolbar.act_label.trigger()
        self.toolbar.act_fill_property.trigger()
        self.assertFalse(self.toolbar.act_label.isChecked())
        self.toolbar.act_label.trigger()
        self.toolbar.draw_actions["anvandning_yta"].trigger()
        self.assertFalse(self.toolbar.act_label.isChecked())

    def test_the_text_button_needs_a_plan(self):
        QgsProject.instance().clear()
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_label.isEnabled())

    def test_the_icon_is_valid_svg(self):
        import xml.etree.ElementTree as ET
        from rita_detaljplan.gui.plan_toolbar import ICONS
        self.assertTrue(ET.parse(ICONS / "text.svg").getroot().tag.endswith("svg"))


if __name__ == "__main__":
    unittest.main()
