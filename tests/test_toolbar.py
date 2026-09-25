"""Verktygsfältet (ikoner), klickverktyget, tilldelningsdialogen och pluginets livscykel (QGIS, offscreen)."""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, LEFT, LINE_INSIDE, PLAN, RIGHT, PlanCase, filled, pick, pump  # noqa: E402

if HAVE_QGIS:
    import rita_detaljplan
    from qgis.core import QgsPointXY
    from qgis.gui import QgsMapCanvas
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QMessageBox
    from rita_detaljplan.controller import PlanController
    from rita_detaljplan.core import assignments
    from rita_detaljplan.core.catalog_store import CatalogError, CatalogService
    from rita_detaljplan.gui.assign_dialog import AssignDialog, entry_text
    from rita_detaljplan.gui.assign_tool import AssignTool
    from rita_detaljplan.gui.plan_toolbar import DRAW_BUTTONS, ICONS, PlanToolBar
    from test_catalog_store import FakeApi


class GuiCase(PlanCase):
    """En plan, en styrenhet och ett låtsas-QGIS-gränssnitt med riktig kartduk."""

    def setUp(self):
        super().setUp()
        self.errors, self.warnings = [], []
        self.controller = PlanController(self.errors.append, self.warnings.append)
        self.addCleanup(self.controller.detach)
        self.canvas = QgsMapCanvas()
        self.canvas.resize(400, 400)
        self.iface = mock.MagicMock()
        self.iface.mainWindow.return_value = None
        self.iface.mapCanvas.return_value = self.canvas

    def draw(self, table, wkt):
        feature = self.add(table, wkt)
        pump()
        result = self.layers[table].getFeature(feature.id())
        return result if result.isValid() else None

    def messages(self):
        bar = self.iface.messageBar()
        return [c.args[1] for c in bar.pushWarning.call_args_list + bar.pushInfo.call_args_list]

    def build_plan(self, uses=(LEFT, RIGHT)):
        self.draw("detaljplan", PLAN)
        return [self.draw("anvandning_yta", wkt) for wkt in uses]


class ToolBarTests(GuiCase):
    def setUp(self):
        super().setUp()
        for layer in self.layers.values():
            layer.rollBack()
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)

    def tip(self, table):
        return self.toolbar.draw_actions[table].toolTip()

    def actions(self):
        return [self.toolbar.act_new, self.toolbar.act_open, self.toolbar.act_start, self.toolbar.act_stop,
                self.toolbar.act_info, self.toolbar.act_select, *self.toolbar.draw_actions.values(),
                self.toolbar.act_fill_use,
                self.toolbar.act_fill_property, self.toolbar.act_assign]

    def test_every_button_is_an_icon_and_the_text_lives_in_the_tooltip(self):
        self.assertEqual(self.toolbar.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonIconOnly)
        for action in self.actions():
            self.assertFalse(action.icon().isNull(), action.text())
            self.assertTrue(action.toolTip(), action.text())

    def test_the_icon_files_exist_and_are_valid_svg(self):
        import xml.etree.ElementTree as ET
        names = {"start.svg", "stop.svg", "assign.svg", "new.svg", "open.svg", "info.svg", "select.svg", "helper.svg", "fill_use.svg", "fill_property.svg", "../icon.svg", *(name for _, name, _ in DRAW_BUTTONS)}
        for name in names:
            root = ET.parse(ICONS / name).getroot()
            self.assertTrue(root.tag.endswith("svg"), name)

    def test_there_is_one_draw_button_per_geometry_and_no_point_button(self):
        self.assertEqual(list(self.toolbar.draw_actions), ["detaljplan", "anvandning_yta", "egenskap_yta",
                                                            "egenskap_yta_sekundar", "egenskap_linje", "hjalplinje"])

    def test_the_toolbar_has_no_palette_dropdown_or_status_label(self):
        from qgis.PyQt.QtWidgets import QComboBox, QLabel
        self.assertEqual(self.toolbar.findChildren(QComboBox), [])
        self.assertEqual(self.toolbar.findChildren(QLabel), [])

    def test_new_and_open_stay_available_without_a_plan(self):
        from qgis.core import QgsProject
        QgsProject.instance().clear()
        self.toolbar.refresh()
        self.assertTrue(self.toolbar.act_new.isEnabled())
        self.assertTrue(self.toolbar.act_open.isEnabled())
        for action in (self.toolbar.act_start, self.toolbar.act_info, self.toolbar.act_assign,
                       *self.toolbar.draw_actions.values()):
            self.assertFalse(action.isEnabled())

    def test_new_open_and_info_call_their_callbacks(self):
        calls = []
        toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog,
                              lambda: calls.append("ny"), lambda: calls.append("öppna"), lambda: calls.append("info"))
        self.addCleanup(toolbar.deleteLater)
        self.draw("detaljplan", PLAN)
        toolbar.act_new.trigger()
        toolbar.act_open.trigger()
        toolbar.act_info.trigger()
        self.assertEqual(calls, ["ny", "öppna", "info"])

    def test_settings_and_validation_buttons_have_moved_into_the_ngp_dialog(self):
        self.assertFalse(hasattr(self.toolbar, "act_settings"))
        self.assertFalse(hasattr(self.toolbar, "act_validate"))
        texts = [a.text() for a in self.toolbar.actions()]
        self.assertFalse(any("Kontrollera" in t or "Inställningar" in t for t in texts), texts)
        self.assertIn("Leverera till NGP", texts)

    def test_the_toolbar_is_named_after_the_plugin(self):
        self.assertEqual(self.toolbar.windowTitle(), "Rita Detaljplan")
        self.assertEqual(self.toolbar.toggleViewAction().text(), "Rita Detaljplan")

    def test_new_and_open_come_first(self):
        actions = [a for a in self.toolbar.actions() if not a.isSeparator()]
        self.assertEqual(actions[:2], [self.toolbar.act_new, self.toolbar.act_open])

    def test_dragging_selects_everything_the_rectangle_touches(self):
        from qgis.core import QgsRectangle
        self.toolbar.start()
        self.build_plan(uses=(LEFT, RIGHT))
        found = self.toolbar.select_tool.select_rect(QgsRectangle(-1, -1, 101, 101))
        self.assertEqual({c.table for c in found}, {"detaljplan", "anvandning_yta"})
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 2)
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 1)

    def test_a_rectangle_around_nothing_reports_it_and_a_second_one_replaces_the_selection(self):
        from qgis.core import QgsRectangle
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        found = self.toolbar.select_tool.select_rect(QgsRectangle(200, 200, 210, 210))
        self.assertEqual(found, [])
        self.assertTrue(any("Inget att markera" in m for m in self.messages()))
        self.toolbar.select_tool.select_rect(QgsRectangle(-1, -1, 60, 101))
        self.assertGreater(self.layers["anvandning_yta"].selectedFeatureCount(), 0)
        self.toolbar.select_tool.select_rect(QgsRectangle(1000, 1000, 1001, 1001))
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 0, "en ny (icke-add) rektangel ersätter")

    def test_an_add_rectangle_keeps_the_previous_selection(self):
        from qgis.core import QgsPointXY, QgsRectangle
        self.toolbar.start()
        self.build_plan(uses=(LEFT, RIGHT))
        self.toolbar.select_tool.choose = lambda candidates: next(c for c in candidates if c.table == "anvandning_yta")
        self.toolbar.select_tool.click(QgsPointXY(20, 50))
        self.toolbar.select_tool.select_rect(QgsRectangle(60, 0, 100, 100), add=True)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 2)

    def test_ctrl_or_shift_click_adds_to_the_selection_and_a_plain_click_replaces_it(self):
        from qgis.core import QgsPointXY
        from qgis.PyQt.QtCore import Qt
        self.toolbar.start()
        self.build_plan(uses=(LEFT, RIGHT))
        tool = self.toolbar.select_tool
        tool.choose = lambda candidates: next(c for c in candidates if c.table == "anvandning_yta")

        def click(point, modifiers=Qt.KeyboardModifier.NoModifier):
            press = mock.Mock(button=lambda: Qt.MouseButton.LeftButton, mapPoint=lambda: QgsPointXY(*point))
            tool.canvasPressEvent(press)
            release = mock.Mock(button=lambda: Qt.MouseButton.LeftButton, mapPoint=lambda: QgsPointXY(*point),
                                modifiers=lambda: modifiers)
            tool.canvasReleaseEvent(release)

        click((20, 50))
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1)
        click((80, 50), Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 2, "Ctrl lägger till")
        click((80, 50), Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 2, "Skift fungerar likadant")
        click((20, 50))
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1, "ett vanligt klick ersätter")

    def test_a_drag_past_the_threshold_selects_with_a_rectangle_not_a_click(self):
        from qgis.core import QgsPointXY
        from qgis.PyQt.QtCore import Qt
        self.toolbar.start()
        self.build_plan(uses=(LEFT, RIGHT))
        tool = self.toolbar.select_tool
        press = mock.Mock(button=lambda: Qt.MouseButton.LeftButton, mapPoint=lambda: QgsPointXY(-1, -1))
        tool.canvasPressEvent(press)
        release = mock.Mock(button=lambda: Qt.MouseButton.LeftButton, mapPoint=lambda: QgsPointXY(101, 101),
                            modifiers=lambda: Qt.KeyboardModifier.NoModifier)
        tool.canvasReleaseEvent(release)
        self.assertGreaterEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1)

    def test_right_click_clears_the_selection_and_the_deselect_button_is_gone(self):
        from qgis.core import QgsPointXY
        from qgis.PyQt.QtCore import Qt
        self.assertFalse(hasattr(self.toolbar, "act_deselect"))
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        self.toolbar.select_tool.choose = lambda candidates: candidates[0]  # plan och användning ligger på varandra
        self.toolbar.select_tool.click(QgsPointXY(20, 50))
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1)
        event = mock.Mock(button=lambda: Qt.MouseButton.RightButton)
        self.toolbar.select_tool.canvasReleaseEvent(event)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 0)

    def test_the_info_button_needs_a_plan_area(self):
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_info.isEnabled())
        self.assertIn("Rita planområdet", self.toolbar.act_info.toolTip())
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        self.assertTrue(self.toolbar.act_info.isEnabled())

    def test_the_save_question_lists_what_is_missing_before_delivery(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        with mock.patch.object(self.toolbar, "_ask_save", return_value=QMessageBox.StandardButton.Save) as ask:
            self.toolbar.stop()
        missing = ask.call_args.args[0]
        self.assertTrue(any("Namn" in t for t in missing), missing)
        self.assertTrue(any("nvändning" in t for t in missing), missing)

    def test_a_new_plan_shows_the_toolbar_with_start_enabled_and_everything_else_off(self):
        self.assertTrue(self.toolbar.act_start.isEnabled())
        self.assertFalse(self.toolbar.act_stop.isEnabled())
        for table, action in self.toolbar.draw_actions.items():
            self.assertFalse(action.isEnabled(), table)
            self.assertIn("Börja rita planbestämmelser", self.tip(table))
        self.assertFalse(self.toolbar.act_fill_use.isEnabled())
        self.assertFalse(self.toolbar.act_fill_property.isEnabled())
        self.assertFalse(self.toolbar.act_assign.isEnabled())

    def test_starting_enables_the_plan_area_button_only(self):
        self.toolbar.start()
        pump()
        self.assertFalse(self.toolbar.act_start.isEnabled())
        self.assertTrue(self.toolbar.act_stop.isEnabled())
        self.assertTrue(self.toolbar.draw_actions["detaljplan"].isEnabled())
        self.assertFalse(self.toolbar.draw_actions["anvandning_yta"].isEnabled())
        self.assertIn("Rita planområdet först", self.tip("anvandning_yta"))
        self.assertIn("Rita en användningsyta först", self.tip("egenskap_yta"))

    def test_the_hierarchy_unlocks_the_buttons_step_by_step(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        self.assertTrue(self.toolbar.draw_actions["anvandning_yta"].isEnabled())
        self.assertFalse(self.toolbar.draw_actions["egenskap_yta"].isEnabled())
        self.assertFalse(self.toolbar.act_assign.isEnabled(), "inget att tilldela förrän en användningsyta finns")
        self.draw("anvandning_yta", LEFT)
        for table in ("egenskap_yta", "egenskap_linje"):
            self.assertTrue(self.toolbar.draw_actions[table].isEnabled(), table)
        self.assertTrue(self.toolbar.act_assign.isEnabled())

    def test_the_secondary_property_button_draws_in_the_property_layer_and_marks_the_areas_as_secondary(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        self.assertFalse(self.toolbar.draw_actions["egenskap_yta_sekundar"].isEnabled(), "kräver en användningsyta")
        self.draw("anvandning_yta", LEFT)
        action = self.toolbar.draw_actions["egenskap_yta_sekundar"]
        self.assertTrue(action.isEnabled())
        self.assertIn("sekundär egenskapsgräns", action.toolTip())
        action.trigger()
        self.iface.setActiveLayer.assert_called_with(self.layers["egenskap_yta"])
        self.assertTrue(self.controller.secondary_mode)
        self.assertFalse(self.toolbar.draw_actions["egenskap_yta"].isChecked())
        secondary = self.draw("egenskap_yta", "MultiPolygon(((10 10, 20 10, 20 20, 10 20, 10 10)))")
        self.assertEqual(secondary["sekundar"], 1)
        self.toolbar.draw_actions["egenskap_yta"].trigger()
        self.assertFalse(self.controller.secondary_mode, "den vanliga knappen ritar vanliga egenskapsytor")
        normal = self.draw("egenskap_yta", "MultiPolygon(((30 10, 40 10, 40 20, 30 20, 30 10)))")
        self.assertEqual(normal["sekundar"], 0)
        self.toolbar.draw_actions["egenskap_yta_sekundar"].trigger()
        self.assertTrue(self.controller.secondary_mode)
        self.toolbar._uncheck_tools()
        self.assertFalse(self.controller.secondary_mode, "läget följer med när verktygen släpps")

    def test_helper_lines_only_need_an_edit_session_not_a_plan_area(self):
        self.toolbar.start()
        pump()
        self.assertTrue(self.toolbar.draw_actions["hjalplinje"].isEnabled())
        self.assertIn("inte följer med till NGP", self.tip("hjalplinje"))

    def test_the_fill_buttons_follow_the_hierarchy(self):
        self.toolbar.start()
        pump()
        self.assertFalse(self.toolbar.act_fill_use.isEnabled())
        self.assertIn("Rita planområdet först", self.toolbar.act_fill_use.toolTip())
        self.draw("detaljplan", PLAN)
        pump()
        self.assertTrue(self.toolbar.act_fill_use.isEnabled())
        self.assertFalse(self.toolbar.act_fill_property.isEnabled())
        self.draw("anvandning_yta", LEFT)
        pump()
        self.assertTrue(self.toolbar.act_fill_property.isEnabled())

    def test_the_fill_use_button_is_a_click_tool_that_deactivates_itself_once_used(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        self.toolbar.act_fill_use.trigger()
        self.assertTrue(self.toolbar.act_fill_use.isChecked())
        self.assertIs(self.canvas.mapTool(), self.toolbar.fill_use_tool)
        result = self.toolbar.fill_use_tool.click(QgsPointXY(80, 50))
        pump()
        self.assertTrue(result.ok)
        self.assertAlmostEqual(self.area("anvandning_yta"), 10000.0)
        self.assertTrue(any("Fyllde" in m for m in self.messages()), self.messages())
        self.assertFalse(self.toolbar.act_fill_use.isChecked(), "stänger av sig själv efter en lyckad fyllning")
        self.assertIsNot(self.canvas.mapTool(), self.toolbar.fill_use_tool)

    def test_only_the_bit_clicked_in_is_filled_not_necessarily_the_whole_plan(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        # en användning delar det som saknar användning i två skilda bitar
        self.draw("anvandning_yta", "MultiPolygon(((40 0, 60 0, 60 100, 40 100, 40 0)))")
        result = self.toolbar.fill_use_tool.click(QgsPointXY(20, 50))
        pump()
        self.assertTrue(result.ok)
        self.assertAlmostEqual(self.area("anvandning_yta"), 20 * 100 + 40 * 100, delta=0.5)
        self.assertLess(self.controller.missing_use_area(), 40 * 100 + 0.5)
        self.assertGreater(self.controller.missing_use_area(), 40 * 100 - 0.5, "den högra biten är fortfarande tom")

    def test_a_miss_leaves_the_fill_use_tool_active(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        self.toolbar.act_fill_use.trigger()
        outside = self.toolbar.fill_use_tool.click(QgsPointXY(20, 50))  # LEFT har redan användning där
        self.assertFalse(outside.ok)
        self.assertTrue(self.toolbar.act_fill_use.isChecked(), "man får försöka igen utan att knappen stängs av")

    def test_the_fill_property_and_assign_tools_also_deactivate_themselves(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        self.toolbar.act_fill_property.trigger()
        self.assertTrue(self.toolbar.fill_tool.click(QgsPointXY(20, 50)).ok)
        self.assertFalse(self.toolbar.act_fill_property.isChecked())
        self.toolbar.act_assign.trigger()
        with mock.patch("rita_detaljplan.gui.plan_toolbar.AssignDialog"):
            self.toolbar.assign_tool.click(QgsPointXY(20, 50))
        self.assertFalse(self.toolbar.act_assign.isChecked())

    def test_the_fill_property_button_is_a_click_tool_that_excludes_the_others(self):
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        self.toolbar.act_fill_property.trigger()
        self.assertTrue(self.toolbar.act_fill_property.isChecked())
        self.assertIs(self.canvas.mapTool(), self.toolbar.fill_tool)
        self.toolbar.act_assign.trigger()
        self.assertFalse(self.toolbar.act_fill_property.isChecked())
        self.toolbar.act_fill_property.trigger()
        self.assertFalse(self.toolbar.act_assign.isChecked())
        self.toolbar.draw_actions["anvandning_yta"].trigger()
        self.assertFalse(self.toolbar.act_fill_property.isChecked())

    def test_clicking_with_the_fill_tool_fills_the_use_under_the_click(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        result = self.toolbar.fill_tool.click(QgsPointXY(20, 50))
        pump()
        self.assertTrue(result.ok)
        self.assertAlmostEqual(self.area("egenskap_yta"), 5000.0)
        outside = self.toolbar.fill_tool.click(QgsPointXY(80, 50))
        self.assertFalse(outside.ok)
        self.assertIn("Klicka inne i ett användningsområde", outside.message)

    def test_the_select_button_is_a_click_tool_that_excludes_the_others(self):
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        pump()
        self.assertTrue(self.toolbar.act_select.isEnabled())
        self.toolbar.act_select.trigger()
        self.assertTrue(self.toolbar.act_select.isChecked())
        self.assertIs(self.canvas.mapTool(), self.toolbar.select_tool)
        self.toolbar.act_assign.trigger()
        self.assertFalse(self.toolbar.act_select.isChecked())
        self.toolbar.act_select.trigger()
        self.assertFalse(self.toolbar.act_assign.isChecked())
        self.toolbar.act_fill_property.trigger()
        self.assertFalse(self.toolbar.act_select.isChecked())
        self.toolbar.act_select.trigger()
        self.toolbar.draw_actions["anvandning_yta"].trigger()
        self.assertFalse(self.toolbar.act_select.isChecked())

    def test_selecting_works_without_an_edit_session_but_needs_a_plan(self):
        from qgis.core import QgsProject
        self.assertTrue(self.toolbar.act_select.isEnabled(), "planen är öppen")
        QgsProject.instance().clear()
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_select.isEnabled())

    def test_a_click_selects_the_one_area_there_and_makes_its_layer_active(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        chosen = self.toolbar.select_tool.click(QgsPointXY(20, 50))
        self.assertEqual(chosen.table, "detaljplan", "bara planområdet ligger här: inget val behövs")
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 1)
        self.iface.setActiveLayer.assert_called_with(self.layers["detaljplan"])

    def test_several_areas_ask_which_one_is_meant(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        asked = []
        self.toolbar.select_tool.choose = lambda candidates: asked.append([c.table for c in candidates]) or candidates[1]
        chosen = self.toolbar.select_tool.click(QgsPointXY(20, 50))
        self.assertEqual(asked, [["anvandning_yta", "detaljplan"]])
        self.assertEqual(chosen.table, "detaljplan")
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 1)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 0)

    def test_dismissing_the_choice_changes_nothing_and_a_miss_clears_the_selection(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        self.toolbar.select_tool.choose = lambda candidates: None
        self.assertIsNone(self.toolbar.select_tool.click(QgsPointXY(20, 50)))
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 0)
        self.toolbar.select_tool.choose = lambda candidates: candidates[0]
        self.toolbar.select_tool.click(QgsPointXY(20, 50))
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1)
        self.assertIsNone(self.toolbar.select_tool.click(QgsPointXY(900, 900)))
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 0)

    def test_shift_click_adds_to_the_selection(self):
        from qgis.core import QgsPointXY
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        self.toolbar.select_tool.choose = lambda candidates: candidates[0]
        self.toolbar.select_tool.click(QgsPointXY(20, 50))
        self.toolbar.select_tool.choose = lambda candidates: candidates[-1]
        self.toolbar.select_tool.click(QgsPointXY(20, 50), add=True)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1)
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 1)

    def test_the_status_goes_to_the_status_bar(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        self.assertIn("Användning: saknas", self.toolbar.status_text)
        self.draw("anvandning_yta", LEFT)
        text = self.toolbar.status_text
        self.assertIn("50% av planområdet", text)
        self.assertIn("1 saknar bestämmelse", text)
        self.assertIn("10 000 m²", text)
        self.iface.statusBarIface().showMessage.assert_called_with(text, 0)

    def test_a_draw_button_activates_the_layer_and_starts_the_add_feature_tool(self):
        self.toolbar.start()
        pump()  # knapparnas läge uppdateras i nästa varv av händelseslingan
        self.toolbar.draw_actions["detaljplan"].trigger()
        self.iface.setActiveLayer.assert_called_with(self.layers["detaljplan"])
        self.iface.actionAddFeature().trigger.assert_called_once()
        self.assertTrue(self.toolbar.draw_actions["detaljplan"].isChecked())

    def test_only_one_draw_button_is_checked_at_a_time(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        self.toolbar.draw_actions["detaljplan"].trigger()
        self.toolbar.draw_actions["anvandning_yta"].trigger()
        self.assertEqual([t for t, a in self.toolbar.draw_actions.items() if a.isChecked()], ["anvandning_yta"])

    def test_a_blocked_button_explains_why_instead_of_drawing(self):
        self.toolbar.start()
        self.toolbar.draw("anvandning_yta", True)
        self.iface.actionAddFeature().trigger.assert_not_called()
        self.assertTrue(any("Rita planområdet först" in m for m in self.messages()))
        self.assertFalse(self.toolbar.draw_actions["anvandning_yta"].isChecked())

    def test_stopping_with_changes_asks_and_saves(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        with mock.patch.object(self.toolbar, "_ask_save", return_value=QMessageBox.StandardButton.Save) as ask:
            self.toolbar.stop()
        ask.assert_called_once()
        self.assertFalse(self.controller.editing)
        self.assertTrue(any("Sparade planen" in m for m in self.messages()))
        self.assertEqual(self.controller.layer("detaljplan").featureCount(), 1)

    def test_stopping_can_discard_the_changes(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        with mock.patch.object(self.toolbar, "_ask_save", return_value=QMessageBox.StandardButton.Discard):
            self.toolbar.stop()
        self.assertFalse(self.controller.editing)
        self.assertEqual(self.controller.layer("detaljplan").featureCount(), 0)
        self.assertTrue(any("Kastade" in m for m in self.messages()))

    def test_cancelling_keeps_the_edit_session_open(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        with mock.patch.object(self.toolbar, "_ask_save", return_value=QMessageBox.StandardButton.Cancel):
            self.toolbar.stop()
        self.assertTrue(self.controller.editing)
        self.assertEqual(self.controller.layer("detaljplan").featureCount(), 1)

    def test_stopping_without_changes_does_not_ask(self):
        self.toolbar.start()
        with mock.patch.object(self.toolbar, "_ask_save") as ask:
            self.toolbar.stop()
        ask.assert_not_called()
        self.assertFalse(self.controller.editing)

    def test_the_assign_button_switches_the_map_tool_on_and_off(self):
        self.toolbar.start()
        self.build_plan()
        self.toolbar.act_assign.trigger()
        self.assertIs(self.canvas.mapTool(), self.toolbar.assign_tool)
        self.assertTrue(self.toolbar.act_assign.isChecked())
        self.toolbar.act_assign.trigger()
        self.assertIsNot(self.canvas.mapTool(), self.toolbar.assign_tool)

    def test_picking_another_tool_releases_the_buttons(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        self.toolbar.draw_actions["detaljplan"].trigger()
        other = mock.Mock()
        other.action.return_value = mock.sentinel.something_else
        self.toolbar._on_tool_set(other)
        self.assertFalse(self.toolbar.draw_actions["detaljplan"].isChecked())

    def test_stopping_the_session_releases_all_tools(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        self.toolbar.draw_actions["detaljplan"].trigger()
        with mock.patch.object(self.toolbar, "_ask_save", return_value=QMessageBox.StandardButton.Save):
            self.toolbar.stop()
        self.assertFalse(any(a.isChecked() for a in self.toolbar.draw_actions.values()))

    def test_clicking_with_the_assign_tool_opens_the_dialog_for_the_areas_under_the_click(self):
        self.toolbar.start()
        self.build_plan()
        with mock.patch("rita_detaljplan.gui.plan_toolbar.AssignDialog") as dialog_cls:
            found = self.toolbar.assign_tool.click(QgsPointXY(75, 50))
        self.assertEqual(len(found), 1)
        dialog_cls.assert_called_once()
        args = dialog_cls.call_args.args
        self.assertIs(args[0], self.controller)
        self.assertEqual(args[2], found)
        self.assertEqual(args[3], self.toolbar.assign_tool.highlight)
        dialog_cls.return_value.exec.assert_called_once()


class AssignToolTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.opened, self.reports = [], []
        self.tool = AssignTool(self.canvas, self.controller, lambda c, t: self.opened.append(c),
                               lambda text, warning: self.reports.append((text, warning)))
        self.use_a, self.use_b = self.build_plan()

    def test_a_click_on_an_area_opens_the_dialog_with_the_areas_there(self):
        found = self.tool.click(QgsPointXY(20, 50))
        self.assertEqual([(c.table, c.fid) for c in found], [("anvandning_yta", self.use_a.id())])
        self.assertEqual(self.opened, [found])

    def test_overlapping_areas_are_all_offered(self):
        self.draw("egenskap_yta", INSIDE)
        found = self.tool.click(QgsPointXY(20, 20))
        self.assertEqual([c.table for c in found], ["egenskap_yta", "anvandning_yta"])

    def test_a_click_on_nothing_says_so(self):
        self.assertEqual(self.tool.click(QgsPointXY(500, 500)), [])
        self.assertEqual(self.opened, [])
        self.assertIn("Ingen yta här", self.reports[-1][0])
        self.assertTrue(self.reports[-1][1])

    def test_clicking_before_editing_has_started_says_so(self):
        for layer in self.layers.values():
            layer.rollBack()
        self.assertEqual(self.tool.click(QgsPointXY(20, 50)), [])
        self.assertIn("Börja rita planbestämmelser", self.reports[-1][0])

    def test_the_chosen_area_is_highlighted_and_the_highlight_is_cleared_afterwards(self):
        seen = []

        def open_dialog(candidates, tool):
            tool.highlight(candidates[0])
            seen.append(tool._rubber.numberOfVertices())

        tool = AssignTool(self.canvas, self.controller, open_dialog, lambda *_: None)
        tool.click(QgsPointXY(20, 50))
        self.assertGreater(seen[0], 0, "ytan markeras medan dialogen är öppen")
        self.assertEqual(tool._rubber.numberOfVertices(), 0, "markeringen tas bort när dialogen stängts")

    def test_highlighting_nothing_or_a_missing_area_does_not_fail(self):
        self.tool.highlight(None)
        from rita_detaljplan.controller import Candidate
        self.tool.highlight(Candidate("anvandning_yta", 999999, "finns inte"))
        self.assertEqual(self.tool._rubber.numberOfVertices(), 0)


class DialogCase(GuiCase):
    def setUp(self):
        super().setUp()
        self.use_a, self.use_b = self.build_plan()
        self.selected = []

    def open(self, point=(20, 50)):
        candidates = self.controller.candidates_at(QgsPointXY(*point), 0.5)
        dialog = AssignDialog(self.controller, lambda: self.catalog, candidates, self.selected.append)
        self.addCleanup(dialog.deleteLater)
        return dialog

    @staticmethod
    def choose(dialog, entry):
        dialog.entry_combo.setCurrentIndex(dialog.combo_index(entry))

    def add_via(self, dialog, entry, number=None):
        self.choose(dialog, entry)
        if number is not None and dialog.variables._editors:
            dialog.variables._editors[0]["value"].setText(number)
        self.assertTrue(dialog.btn_add.isEnabled(), dialog.variables.problems())
        dialog.btn_add.click()


class AssignDialogTests(DialogCase):
    def test_one_area_hides_the_area_chooser_and_names_the_area_in_the_title(self):
        dialog = self.open((20, 50))
        self.assertTrue(dialog.area_combo.isHidden())
        self.assertIn("Användningsområde", dialog.windowTitle())
        self.assertEqual(self.selected[-1].table, "anvandning_yta")

    def test_several_areas_show_a_chooser_and_switching_changes_everything_below(self):
        self.draw("egenskap_yta", INSIDE)
        dialog = self.open((20, 20))
        self.assertFalse(dialog.area_combo.isHidden())
        self.assertEqual(dialog.area_combo.count(), 2)
        self.assertTrue(dialog.area_combo.itemText(0).startswith("Egenskapsområde"))
        self.assertEqual(dialog.candidate().table, "egenskap_yta")
        self.assertTrue(all(e.layer_name == "egenskap_yta" for e in dialog._entries))
        dialog.area_combo.setCurrentIndex(1)
        self.assertEqual(dialog.candidate().table, "anvandning_yta")
        self.assertTrue(all(e.layer_name == "anvandning_yta" for e in dialog._entries))
        self.assertEqual([c.table for c in self.selected], ["egenskap_yta", "anvandning_yta"],
                         "kartan ska följa den valda ytan")

    def test_the_dropdown_lists_the_provisions_for_the_area_and_is_searchable(self):
        dialog = self.open()
        self.assertGreaterEqual(dialog.entry_combo.count(), len(dialog._entries), "posterna plus rubrikerna")
        self.assertTrue(dialog.entry_combo.isEditable())
        self.assertEqual(dialog.entry_combo.lineEdit().text(), "")
        entry = pick(self.catalog, "DP_KM_J2")
        self.assertIn(entry_text(entry), [dialog.entry_combo.itemText(i) for i in range(dialog.entry_combo.count())])

    def test_searching_on_a_word_that_is_not_the_first_word_still_finds_the_provision(self):
        dialog = self.open()
        entry = pick(self.catalog, "DP_KM_J2")  # "J – Industri (Kvartersmark)": sökordet är inte första ordet
        dialog._search_filter.set_search_text("industri")
        texts = [dialog._search_filter.index(i, 0).data() for i in range(dialog._search_filter.rowCount())]
        self.assertIn(entry_text(entry), texts)

    def test_searching_several_words_in_any_order_finds_rows_containing_them_all(self):
        dialog = self.open()
        full = dialog.entry_combo.count()
        dialog._search_filter.set_search_text("kvartersmark industri")  # omvänd ordning mot texten
        self.assertGreater(dialog._search_filter.rowCount(), 0)
        self.assertLess(dialog._search_filter.rowCount(), full, "sökningen begränsar listan")
        texts = [dialog._search_filter.index(i, 0).data() for i in range(dialog._search_filter.rowCount())]
        self.assertTrue(all("industri" in t.lower() and "kvartersmark" in t.lower() for t in texts))

    def test_a_word_matching_nothing_gives_an_empty_result(self):
        dialog = self.open()
        dialog._search_filter.set_search_text("something that matches nothing at all xyz")
        self.assertEqual(dialog._search_filter.rowCount(), 0)

    def test_clearing_the_search_shows_everything_again(self):
        dialog = self.open()
        full = dialog._search_filter.rowCount()
        dialog._search_filter.set_search_text("industri")
        self.assertLess(dialog._search_filter.rowCount(), full)
        dialog._search_filter.set_search_text("")
        self.assertEqual(dialog._search_filter.rowCount(), full)

    def test_headings_never_show_up_as_search_results(self):
        dialog = self.open()
        dialog._search_filter.set_search_text("kvartersmark")  # ordet finns även i rubrikerna
        for row in range(dialog._search_filter.rowCount()):
            index = dialog._search_filter.index(row, 0)
            self.assertTrue(index.flags() & Qt.ItemFlag.ItemIsSelectable, index.data())

    def test_typing_drives_the_search_filter(self):
        dialog = self.open()
        dialog.entry_combo.lineEdit().setText("industri")
        dialog.entry_combo.lineEdit().textEdited.emit("industri")
        self.assertGreater(dialog._search_filter.rowCount(), 0)
        self.assertLess(dialog._search_filter.rowCount(), dialog.entry_combo.count())

    def test_the_search_popup_is_wide_enough_for_long_texts(self):
        from rita_detaljplan.gui.assign_dialog import POPUP_WIDTH
        dialog = self.open()
        self.assertGreaterEqual(dialog.entry_combo.view().minimumWidth(), POPUP_WIDTH)
        self.assertGreaterEqual(dialog.entry_combo.completer().popup().minimumWidth(), POPUP_WIDTH)
        self.assertGreaterEqual(dialog.entry_combo.maxVisibleItems(), 20)

    def test_the_assigned_rows_box_is_small_with_a_scrollbar_when_needed(self):
        dialog = self.open((20, 50))
        self.assertLessEqual(dialog.rows_list.maximumHeight(), 90)
        self.assertEqual(dialog.rows_list.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def test_add_is_disabled_until_a_provision_is_chosen_and_its_values_are_valid(self):
        dialog = self.open((20, 50))
        self.assertFalse(dialog.btn_add.isEnabled())
        entry = pick(self.catalog, "DP_KM_J2")
        self.choose(dialog, entry)
        self.assertTrue(dialog.btn_add.isEnabled())

        self.draw("egenskap_yta", INSIDE)
        prop_dialog = self.open((20, 20))
        self.choose(prop_dialog, pick(self.catalog, layer="egenskap_yta", contains="byggnadsarea"))
        self.assertFalse(prop_dialog.btn_add.isEnabled(), "värdet saknas")
        prop_dialog.variables._editors[0]["value"].setText("30")
        self.assertTrue(prop_dialog.btn_add.isEnabled())

    def test_adding_a_provision_lists_it_and_updates_the_area_title(self):
        dialog = self.open((20, 50))
        self.add_via(dialog, pick(self.catalog, "DP_KM_J2"))
        self.assertEqual(dialog.rows_list.count(), 1)
        self.assertIn("Industri", dialog.rows_list.item(0).text())
        self.assertIn("· J ·", dialog.area_combo.itemText(0))
        self.assertEqual(dialog.entry_combo.lineEdit().text(), "", "rullistan är redo för nästa bestämmelse")
        self.assertEqual(dialog.problems.text(), "")

    def test_an_area_can_get_several_provisions(self):
        dialog = self.open((20, 50))
        self.add_via(dialog, pick(self.catalog, "DP_KM_J2"))
        other = next(e for e in dialog._entries if e.label_base == "B")
        self.add_via(dialog, other)
        self.assertEqual(dialog.rows_list.count(), 2)
        self.assertEqual(self.layers["anvandning_yta"].getFeature(self.use_a.id())["beteckning"], "JB")

    def test_a_used_up_form_narrows_the_dropdown(self):
        dialog = self.open((20, 50))
        self.assertGreater(len({e.anvandningsform for e in dialog._entries}), 1)
        self.add_via(dialog, pick(self.catalog, "DP_KM_J2"))
        self.assertEqual({e.anvandningsform for e in dialog._entries}, {"Kvartersmark"},
                         "en användningsyta kan inte vara både kvartersmark och allmän plats")

    def test_adding_the_same_provision_twice_shows_the_reason(self):
        dialog = self.open((20, 50))
        entry = pick(self.catalog, "DP_KM_J2")
        self.add_via(dialog, entry)
        self.choose(dialog, entry)
        dialog.btn_add.click()
        self.assertIn("redan den bestämmelsen", dialog.problems.text())
        self.assertEqual(dialog.rows_list.count(), 1)

    def test_removing_a_provision(self):
        dialog = self.open((20, 50))
        self.add_via(dialog, pick(self.catalog, "DP_KM_J2"))
        self.assertFalse(dialog.btn_remove.isEnabled())
        dialog.rows_list.setCurrentRow(0)
        self.assertTrue(dialog.btn_remove.isEnabled())
        dialog.btn_remove.click()
        self.assertEqual(dialog.rows_list.count(), 0)
        self.assertIn("saknar bestämmelse", dialog.area_combo.itemText(0))

    def test_editing_a_provision_through_the_full_dialog(self):
        dialog = self.open((20, 50))
        self.add_via(dialog, pick(self.catalog, "DP_KM_J2"))
        new = pick(self.catalog, "DP_KM_R2_Motorsport")
        fake = mock.Mock()
        fake.exec.return_value = True
        fake.selected_entry.return_value = new
        fake.values.return_value = filled(new)
        fake.motive.return_value = "Ny motivering"
        fake.custom_formulation.return_value = None
        dialog.rows_list.setCurrentRow(0)
        with mock.patch("rita_detaljplan.gui.assign_dialog.BestammelseDialog", return_value=fake) as cls:
            dialog.btn_edit.click()
        self.assertEqual(cls.call_args.args[1], "anvandning_yta", "dialogen begränsas till ytans lager")
        self.assertEqual(cls.call_args.args[2].kod, "DP_KM_J2", "förifylld med nuvarande bestämmelse")
        self.assertEqual(dialog.rows_list.count(), 1)
        self.assertIn("Motorsportbana", dialog.rows_list.item(0).text())
        row = assignments.rows_of_area(self.controller.project, "anvandning_yta", self.use_a.id())[0]
        self.assertEqual(row["motiv"], "Ny motivering")

    def test_the_details_button_adds_with_a_custom_formulation_and_motive(self):
        self.draw("egenskap_yta", INSIDE)
        dialog = self.open((20, 20))
        entry = pick(self.catalog, layer="egenskap_yta", contains="byggnadsarea")
        self.choose(dialog, entry)
        dialog.variables._editors[0]["value"].setText("30")
        fake = mock.Mock()
        fake.exec.return_value = True
        fake.selected_entry.return_value = entry
        fake.values.return_value = filled(entry, "30")
        fake.motive.return_value = "Bevara innergården"
        fake.custom_formulation.return_value = "Byggnadsarean är högst [utnyttjandegrad:decimaltal] % av tomten."
        with mock.patch("rita_detaljplan.gui.assign_dialog.BestammelseDialog", return_value=fake) as cls:
            dialog.btn_details.click()
        self.assertEqual(cls.call_args.args[3][0].value, "30", "värdena förs över till den fullständiga dialogen")
        row = assignments.rows_of_area(self.controller.project, "egenskap_yta", self.controller.candidates_at(
            QgsPointXY(20, 20), 0.5)[0].fid)[0]
        self.assertEqual((row["motiv"], row["avviker"]), ("Bevara innergården", 1))

    def test_technical_installations_have_no_custom_formulation_button(self):
        dialog = self.open((20, 50))
        self.choose(dialog, pick(self.catalog, "DP_KM_E2"))
        self.assertFalse(dialog.btn_details.isEnabled())
        self.assertTrue(dialog.btn_add.isEnabled())

    def test_editing_a_provision_missing_from_the_catalog_explains_it(self):
        dialog = self.open((20, 50))
        self.add_via(dialog, pick(self.catalog, "DP_KM_J2"))
        dialog.catalog_provider = lambda: __import__("rita_detaljplan.core.catalog", fromlist=["x"]).Catalog(
            1, "x", "2020-01-01", [])
        dialog.rows_list.setCurrentRow(0)
        dialog.btn_edit.click()
        self.assertIn("Uppdatera katalogen", dialog.problems.text())

    def test_a_property_only_offers_provisions_matching_the_use_beneath(self):
        self.controller.add_bestammelse("anvandning_yta", self.use_a.id(), pick(self.catalog, "DP_KM_J2"),
                                        filled(pick(self.catalog, "DP_KM_J2")))
        self.draw("egenskap_yta", INSIDE)
        dialog = self.open((20, 20))
        self.assertLessEqual({e.anvandningsform for e in dialog._entries}, {"Kvartersmark", "Planområdet"})

    def test_a_line_only_offers_line_provisions(self):
        self.draw("egenskap_linje", LINE_INSIDE)
        dialog = self.open((20.1, 40))
        self.assertEqual(dialog.candidate().table, "egenskap_linje")
        self.assertTrue(all(e.layer_name == "egenskap_linje" for e in dialog._entries))

    def test_closing_the_dialog_keeps_the_changes(self):
        dialog = self.open((20, 50))
        self.add_via(dialog, pick(self.catalog, "DP_KM_J2"))
        dialog.buttons.rejected.emit()
        self.assertEqual(self.layers["anvandning_yta"].getFeature(self.use_a.id())["bestammelser"], 1)


class PluginTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.plugin = rita_detaljplan.classFactory(self.iface)
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)

    def test_menu_and_toolbar_are_created_and_there_is_no_dock(self):
        texts = [a.text() for a in self.plugin.actions]
        for expected in ("Ny detaljplan…", "Öppna detaljplan (GeoPackage)…", "Rita Detaljplan",
                         "Uppdatera planbestämmelsekatalogen…"):
            self.assertIn(expected, texts)
        self.assertFalse(any("palett" in t.lower() for t in texts))
        self.iface.addToolBar.assert_called_once()
        self.assertIs(self.iface.addToolBar.call_args.args[0], self.plugin.toolbar)
        self.iface.addDockWidget.assert_not_called()
        self.assertFalse(hasattr(self.plugin, "dock"))
        self.assertIs(self.plugin.toolbar.controller, self.plugin.controller)

    def test_the_menu_opens_the_ngp_settings_dialog(self):
        self.assertIn("Inställningar för leverans till NGP…", [a.text() for a in self.plugin.actions])
        with mock.patch("rita_detaljplan.plugin.SettingsDialog") as dialog_cls:  # inte den riktiga: den är modal
            self.plugin.open_settings()
        dialog_cls.assert_called_once()
        dialog_cls.return_value.exec.assert_called_once()

    def test_unload_removes_everything_and_stops_the_controller(self):
        self.plugin.unload()
        self.assertEqual(self.plugin.actions, [])
        self.assertIsNone(self.plugin.controller)
        self.assertIsNone(self.plugin.toolbar)
        self.assertEqual(self.iface.removePluginMenu.call_count, self.iface.addPluginToMenu.call_count)

    def test_the_first_plan_area_opens_the_form_for_the_plans_details(self):
        self.plugin.controller.start_editing()
        with mock.patch("rita_detaljplan.plugin.PlanInfoDialog") as dialog_cls:
            self.draw("detaljplan", PLAN)
        dialog_cls.assert_called_once()
        dialog_cls.return_value.exec.assert_called_once()

    def test_the_plan_details_need_a_plan_area(self):
        with mock.patch("rita_detaljplan.plugin.PlanInfoDialog") as dialog_cls:
            self.plugin.open_plan_info()
        dialog_cls.assert_not_called()
        self.assertTrue(any('Rita planområdet' in c.args[1] for c in self.iface.messageBar().pushMessage.call_args_list))

    def test_the_plugin_adds_no_separate_toolbar_icon_since_the_icon_lives_in_the_toolbar(self):
        self.iface.addToolBarIcon.assert_not_called()

    def test_new_plan_creates_the_project_and_points_the_user_to_the_pencil(self):
        from rita_detaljplan.gui.new_plan_dialog import NewPlanValues
        values = NewPlanValues(self.dir / "ny", "ny_plan", "Eskilstuna", "0482", 3006)
        with mock.patch("rita_detaljplan.plugin.NewPlanDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = True
            dialog_cls.return_value.values.return_value = values
            self.plugin.new_plan()
        self.iface.addProject.assert_called_once_with(str(self.dir / "ny" / "ny_plan.qgz"))
        self.assertTrue((self.dir / "ny" / "ny_plan.gpkg").exists())
        self.assertTrue(any("pennan" in c.args[1] for c in self.iface.messageBar().pushMessage.call_args_list))

    def test_new_plan_reports_an_existing_plan(self):
        from rita_detaljplan.gui.new_plan_dialog import NewPlanValues
        (self.dir / "ny").mkdir()
        (self.dir / "ny" / "dp.gpkg").write_bytes(b"")
        values = NewPlanValues(self.dir / "ny", "dp", "X", "0001", 3006)
        with mock.patch("rita_detaljplan.plugin.NewPlanDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = True
            dialog_cls.return_value.values.return_value = values
            self.plugin.new_plan()
        self.iface.messageBar().pushCritical.assert_called_once()
        self.iface.addProject.assert_not_called()

    def test_catalog_update_runs_in_the_background_and_reports(self):
        bundled = self.dir / "bundled.json"
        self.catalog.only_current().save(bundled)
        self.plugin.catalogs = CatalogService(self.dir / "profil", bundled, FakeApi())
        with mock.patch.object(self.plugin, "_catalog", return_value=self.catalog):
            self.plugin.update_catalog()
        deadline = time.time() + 15
        while self.plugin._tasks and time.time() < deadline:
            pump(0.05)
        self.assertEqual(self.plugin._tasks, [])
        texts = [c.args[1] for c in self.iface.messageBar().pushMessage.call_args_list]
        self.assertTrue(any("planbestämmelsekatalogen: release" in t for t in texts), texts)
        self.assertTrue((self.dir / "profil" / "planbestammelsekatalog.json").exists())

    def test_catalog_update_failure_is_reported_to_the_user(self):
        def offline(path):
            raise CatalogError("Ingen förbindelse")

        self.catalog.only_current().save(self.dir / "b.json")
        self.plugin.catalogs = CatalogService(self.dir / "p", self.dir / "b.json", offline)
        with mock.patch.object(self.plugin, "_catalog", return_value=self.catalog):
            self.plugin.update_catalog()
        deadline = time.time() + 15
        while self.plugin._tasks and time.time() < deadline:
            pump(0.05)
        self.iface.messageBar().pushCritical.assert_called_once()
        self.assertIn("Ingen förbindelse", self.iface.messageBar().pushCritical.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
