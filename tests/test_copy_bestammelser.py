"""Kopiera bestämmelser: alla bestämmelser från en egenskapsyta till en annan, med kartverktyget och knappen (QGIS)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, filled, pick, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsPointXY
    from rita_detaljplan.core import assignments, rows
    from rita_detaljplan.core.assignments import AssignmentError
    from rita_detaljplan.gui.copy_tool import CopyTool, summary
    from rita_detaljplan.gui.plan_toolbar import ICONS, PlanToolBar
    from test_toolbar import GuiCase
else:  # pragma: no cover
    GuiCase = unittest.TestCase

LEFT_UPPER = "MultiPolygon(((10 60, 40 60, 40 90, 10 90, 10 60)))"
RIGHT_PROPERTY = "MultiPolygon(((60 10, 90 10, 90 40, 60 40, 60 10)))"


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class CopyCase(GuiCase):
    def setUp(self):
        super().setUp()
        self.use_a, self.use_b = self.build_plan()
        self.prop_a = self.draw("egenskap_yta", INSIDE)  # på vänster användning
        self.prop_c = self.draw("egenskap_yta", LEFT_UPPER)  # också på vänster användning
        self.prop_b = self.draw("egenskap_yta", RIGHT_PROPERTY)  # på höger användning
        self.entries = [e for e in self.catalog.entries
                        if e.layer_name == "egenskap_yta" and e.anvandningsform == "Kvartersmark" and e.deliverable
                        and not e.tolkning and e.is_current][:3]
        self.e1, self.e2, self.e3 = self.entries
        for entry in (self.e1, self.e2):
            self.controller.add_bestammelse("egenskap_yta", self.prop_a.id(), entry, filled(entry))

    def identities(self, feature):
        return [rows.identity(r) for r in self.controller.rows_of("egenskap_yta", feature.id())]


class CopyProvisionsTests(CopyCase):
    def test_all_provisions_are_copied_to_the_other_area(self):
        report = self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), self.prop_c.id())
        self.assertEqual((report.copied, report.already, report.skipped), (2, 0, []))
        self.assertEqual(self.identities(self.prop_c), self.identities(self.prop_a))
        copied = self.controller.rows_of("egenskap_yta", self.prop_c.id())
        original = self.controller.rows_of("egenskap_yta", self.prop_a.id())
        self.assertEqual([r["beteckning"] for r in copied], [r["beteckning"] for r in original],
                         "samma bestämmelse har samma beteckning överallt")
        self.assertEqual(len(self.controller.rows_of("egenskap_yta", self.prop_a.id())), 2, "källan är orörd")

    def test_the_target_keeps_its_own_provisions_and_the_copies_come_last(self):
        self.controller.add_bestammelse("egenskap_yta", self.prop_c.id(), self.e3, filled(self.e3))
        own = self.identities(self.prop_c)
        self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), self.prop_c.id())
        self.assertEqual(self.identities(self.prop_c), own + self.identities(self.prop_a))

    def test_the_area_summary_shows_the_copied_provisions(self):
        self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), self.prop_c.id())
        feature = self.layers["egenskap_yta"].getFeature(self.prop_c.id())
        self.assertEqual(feature["bestammelser"], 2)
        self.assertEqual(feature["beteckning"], self.layers["egenskap_yta"].getFeature(self.prop_a.id())["beteckning"])

    def test_provisions_the_target_already_has_are_not_copied_twice(self):
        self.controller.add_bestammelse("egenskap_yta", self.prop_c.id(), self.e1, filled(self.e1))
        report = self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), self.prop_c.id())
        self.assertEqual((report.copied, report.already), (1, 1))
        again = self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), self.prop_c.id())
        self.assertEqual((again.copied, again.already), (0, 2))
        self.assertEqual(len(self.identities(self.prop_c)), 2)

    def test_provisions_for_another_land_use_form_are_skipped_with_the_reason(self):
        other = pick(self.catalog, layer="anvandning_yta", form="Allmän plats")
        self.controller.add_bestammelse("anvandning_yta", self.use_b.id(), other, filled(other))
        report = self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), self.prop_b.id())
        self.assertEqual(report.copied, 0)
        self.assertEqual(len(report.skipped), 2)
        self.assertIn("kvartersmark", report.skipped[0].lower())
        self.assertEqual(self.controller.rows_of("egenskap_yta", self.prop_b.id()), [])

    def test_the_copies_are_made_in_the_edit_buffer_like_other_changes(self):
        self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), self.prop_c.id())
        self.assertTrue(assignments.rows_layer(self.controller.project).isModified())

    def test_it_explains_what_cannot_be_copied(self):
        with self.assertRaisesRegex(AssignmentError, "samma yta"):
            self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), self.prop_a.id())
        with self.assertRaisesRegex(AssignmentError, "inga bestämmelser"):
            self.controller.copy_bestammelser("egenskap_yta", self.prop_c.id(), self.prop_a.id())
        with self.assertRaisesRegex(AssignmentError, "egenskapsbestämmelser"):
            self.controller.copy_bestammelser("anvandning_yta", self.use_a.id(), self.use_b.id())
        with self.assertRaisesRegex(AssignmentError, "finns inte"):
            self.controller.copy_bestammelser("egenskap_yta", self.prop_a.id(), 999999)


class CopyToolTests(CopyCase):
    def setUp(self):
        super().setUp()
        self.reports = []
        self.tool = CopyTool(self.canvas, self.controller, lambda candidates: candidates[0],
                             lambda text, warning: self.reports.append((text, warning)))
        self.addCleanup(self.tool.reset_source)

    def last(self):
        return self.reports[-1]

    def test_the_first_click_picks_the_source_and_the_second_copies_to_the_clicked_area(self):
        first = self.tool.click(QgsPointXY(20, 20))
        self.assertEqual((first.table, first.fid), ("egenskap_yta", self.prop_a.id()))
        self.assertIn("Kopierar från", self.last()[0])
        self.assertFalse(self.last()[1])
        self.assertGreater(self.tool._rubber.numberOfVertices(), 0, "källan markeras i kartan")
        second = self.tool.click(QgsPointXY(20, 70))
        self.assertEqual(second.fid, self.prop_c.id())
        self.assertEqual(self.identities(self.prop_c), self.identities(self.prop_a))
        self.assertIn("Kopierade 2 bestämmelser", self.last()[0])
        self.assertFalse(self.last()[1])

    def test_the_tool_stays_on_the_source_so_more_areas_can_follow(self):
        self.tool.click(QgsPointXY(20, 20))
        self.tool.click(QgsPointXY(20, 70))
        self.assertEqual(self.tool.source.fid, self.prop_a.id())
        again = self.tool.click(QgsPointXY(20, 70))
        self.assertEqual(again.fid, self.prop_c.id())
        self.assertIn("redan alla bestämmelserna", self.last()[0])

    def test_clicking_the_source_again_does_not_copy_it_onto_itself(self):
        self.tool.click(QgsPointXY(20, 20))
        self.assertIsNone(self.tool.click(QgsPointXY(20, 20)))
        self.assertTrue(self.last()[1])
        self.assertEqual(len(self.identities(self.prop_a)), 2)

    def test_a_source_without_provisions_is_refused(self):
        self.assertIsNotNone(self.tool.click(QgsPointXY(20, 70)))
        self.assertIsNone(self.tool.source)
        self.assertIn("inga bestämmelser", self.last()[0])
        self.assertTrue(self.last()[1])

    def test_a_line_cannot_be_the_target_for_an_area_source(self):
        self.draw("egenskap_linje", "MultiLineString(((20 45, 20 55)))")
        self.tool.click(QgsPointXY(20, 20))
        self.assertIsNone(self.tool.click(QgsPointXY(20, 50)))
        self.assertIn("egenskapsyta", self.last()[0])
        self.assertTrue(self.last()[1])

    def test_a_click_on_nothing_or_a_use_area_says_so(self):
        self.assertIsNone(self.tool.click(QgsPointXY(500, 500)))
        self.assertIn("Ingen egenskapsyta", self.last()[0])
        self.assertIsNone(self.tool.click(QgsPointXY(45, 50)))  # bara användningen ligger här
        self.assertIn("Ingen egenskapsyta", self.last()[0])
        self.assertIsNone(self.tool.source)

    def test_skipped_provisions_are_reported_as_a_warning(self):
        other = pick(self.catalog, layer="anvandning_yta", form="Allmän plats")
        self.controller.add_bestammelse("anvandning_yta", self.use_b.id(), other, filled(other))
        self.tool.click(QgsPointXY(20, 20))
        self.tool.click(QgsPointXY(70, 20))
        self.assertIn("passade inte", self.last()[0])
        self.assertTrue(self.last()[1])

    def test_resetting_the_source_lets_the_next_click_pick_a_new_one(self):
        self.tool.click(QgsPointXY(20, 20))
        self.tool.reset_source(announce=True)
        self.assertIsNone(self.tool.source)
        self.assertEqual(self.tool._rubber.numberOfVertices(), 0)
        self.assertIn("kopiera från", self.last()[0])
        self.tool.click(QgsPointXY(20, 20))
        self.assertEqual(self.tool.source.fid, self.prop_a.id())

    def test_a_source_that_has_been_deleted_is_forgotten(self):
        self.tool.click(QgsPointXY(20, 20))
        self.layers["egenskap_yta"].deleteFeature(self.prop_a.id())
        self.tool.click(QgsPointXY(20, 70))
        self.assertIsNone(self.tool.source, "klicket blev ett nytt källval, som saknar bestämmelser")

    def test_clicking_before_editing_has_started_says_so(self):
        for layer in self.layers.values():
            layer.rollBack()
        self.assertIsNone(self.tool.click(QgsPointXY(20, 20)))
        self.assertIn("Börja rita planbestämmelser", self.last()[0])

    def test_the_message_names_the_provisions_and_what_was_left_out(self):
        class Fake:
            copied, already, skipped = 1, 2, ["a: fel form"]
        text = summary(Fake, "Egenskapsområde · e1")
        self.assertEqual(text, "Kopierade 1 bestämmelse till Egenskapsområde · e1. 2 bestämmelser fanns redan på ytan. "
                               "1 bestämmelse passade inte och hoppades över: a: fel form")


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class CopyButtonTests(CopyCase):
    def setUp(self):
        super().setUp()
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)
        self.toolbar.refresh()

    def test_the_button_has_an_icon_a_tooltip_and_the_icon_file_is_valid_svg(self):
        import xml.etree.ElementTree as ET
        action = self.toolbar.act_copy
        self.assertFalse(action.icon().isNull())
        self.assertTrue(action.isCheckable())
        self.assertIn("Kopiera bestämmelser", action.toolTip())
        self.assertTrue(ET.parse(ICONS / "copy.svg").getroot().tag.endswith("svg"))

    def test_it_sits_next_to_the_assign_button_and_is_available_when_assigning_is(self):
        actions = self.toolbar.actions()
        self.assertEqual(actions.index(self.toolbar.act_copy), actions.index(self.toolbar.act_assign) + 1)
        self.assertTrue(self.toolbar.act_assign.isEnabled())
        self.assertTrue(self.toolbar.act_copy.isEnabled())

    def test_it_is_unavailable_without_a_plan_or_when_editing_has_not_started(self):
        for layer in self.layers.values():
            layer.rollBack()
        self.toolbar.refresh()
        self.assertFalse(self.toolbar.act_copy.isEnabled())
        self.assertIn("Börja rita planbestämmelser", self.toolbar.act_copy.toolTip())

    def test_pressing_it_makes_the_copy_tool_active_and_it_lets_go_of_the_other_tools(self):
        self.toolbar.act_assign.trigger()
        self.assertTrue(self.toolbar.act_assign.isChecked())
        self.toolbar.act_copy.trigger()
        pump()
        self.assertTrue(self.toolbar.act_copy.isChecked())
        self.assertFalse(self.toolbar.act_assign.isChecked())
        self.assertIs(self.canvas.mapTool(), self.toolbar.copy_tool)
        self.toolbar.act_select.trigger()
        pump()
        self.assertFalse(self.toolbar.act_copy.isChecked())
        self.assertIsNot(self.canvas.mapTool(), self.toolbar.copy_tool)

    def test_pressing_the_assign_button_while_copying_switches_over(self):
        self.toolbar.act_copy.trigger()
        pump()
        self.toolbar.act_assign.trigger()
        pump()
        self.assertFalse(self.toolbar.act_copy.isChecked())
        self.assertTrue(self.toolbar.act_assign.isChecked())


if __name__ == "__main__":
    unittest.main()
