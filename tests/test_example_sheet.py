"""Exempellayouterna för plankartan (ärende 2): mallarna för A1–A4 liggande och stående, titelrutan (ren Python) och
layouten i QGIS."""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, LEFT, PLAN, RIGHT, filled, pick  # noqa: E402
from rita_detaljplan.core import example_sheet as es  # noqa: E402

if HAVE_QGIS:
    import rita_detaljplan
    from qgis.core import QgsLayoutItemMap, QgsLayoutItemPicture, QgsLayoutItemScaleBar
    from rita_detaljplan.core import example_sheet_layout as esl
    from rita_detaljplan.core import legend_layout as ll
    from test_toolbar import GuiCase
else:  # pragma: no cover
    GuiCase = unittest.TestCase

PAGE_TYPE = "65638"


def template(paper, orientation):
    """(sidans storlek, {id: (x, y, bredd, höjd)}) ur mallfilen, utan QGIS."""
    root = ET.parse(es.template_path(paper, orientation)).getroot()
    page, items = None, {}
    for element in root.iter("LayoutItem"):
        size = [float(v) for v in element.get("size").split(",")[:2]]
        if element.get("type") == PAGE_TYPE:
            page = tuple(size)
            continue
        position = [float(v) for v in element.get("position").split(",")[:2]]
        items[element.get("id")] = (*position, *size)
    return page, items, root


class FormatTests(unittest.TestCase):
    def test_there_are_eight_formats_a1_to_a4_landscape_and_portrait(self):
        self.assertEqual(len(es.formats()), 8)
        self.assertEqual(es.formats()[:2], [("A1", "liggande"), ("A1", "stående")])
        self.assertEqual(es.format_label("A3", "stående"), "A3 stående")
        self.assertEqual(es.page_size("A2", "liggande"), (594, 420))
        self.assertEqual(es.page_size("A2", "stående"), (420, 594))
        self.assertAlmostEqual(es.factor("A1"), 841 / 594)
        self.assertEqual(es.template_path("A3", "stående").name, "plankarta-a3-staende.qpt")
        with self.assertRaises(ValueError):
            es.template_path("A0", "liggande")

    def test_the_map_and_the_legend_lie_inside_the_page_without_overlapping(self):
        for paper, orientation in es.formats():
            width, height = es.page_size(paper, orientation)
            map_box, legend = es.map_box(paper, orientation), es.legend_box(paper, orientation)
            for box in (map_box, legend):
                self.assertTrue(0 < box.x and box.right < width and 0 < box.y and box.bottom < height,
                                (paper, orientation, box))
            separate = map_box.right < legend.x if orientation == "liggande" else map_box.bottom < legend.y
            self.assertTrue(separate, (paper, orientation))

    def test_the_map_extent_shows_the_plan_in_the_middle_at_the_scale(self):
        box = es.Box(0, 0, 400, 300)
        xmin, ymin, xmax, ymax = es.map_extent((100, 200, 300, 400), box, 1000)
        self.assertEqual(((xmin + xmax) / 2, (ymin + ymax) / 2), (200, 300))
        self.assertAlmostEqual(xmax - xmin, 400.0)  # 400 mm i 1:1000 = 400 m
        self.assertAlmostEqual(ymax - ymin, 300.0)

    def test_a_plan_that_is_too_large_for_the_map_does_not_fit(self):
        box = es.Box(0, 0, 400, 300)
        self.assertTrue(es.fits((0, 0, 400, 300), box, 1000))
        self.assertFalse(es.fits((0, 0, 401, 10), box, 1000))
        self.assertTrue(es.fits((0, 0, 401, 10), box, 2000))

    def test_a2_landscape_is_suggested_and_a1_when_the_plan_is_too_large_for_a2(self):
        self.assertEqual(es.suggested_format((0, 0, 300, 200), 1000), ("A2", "liggande"))
        self.assertEqual(es.suggested_format((0, 0, 500, 200), 1000), ("A1", "liggande"))


class TemplateFileTests(unittest.TestCase):
    """Mallfilerna i data/layouts (byggda av tools/build_layouts.py) stämmer med example_sheet."""

    def test_every_template_has_the_right_page_and_the_items_the_plugin_fills_in(self):
        wanted = {es.MAP_ID, es.LEGEND_ID, es.PAPER_ID, es.STAGE_ID, es.PLAN_TYPE_ID, es.NAME_ID, es.KOMMUN_ID,
                  es.ADOPTION_ID, es.LAGAKRAFT_ID, "Norrpil", "Skala", "Skalstock"}
        for paper, orientation in es.formats():
            page, items, root = template(paper, orientation)
            self.assertEqual(page, es.page_size(paper, orientation), (paper, orientation))
            self.assertLessEqual(wanted, set(items), (paper, orientation))
            self.assertEqual(root.get("name"), f"Plankarta {paper} {orientation}")
            labels = {e.get("id"): e.get("labelText") for e in root.iter("LayoutItem") if e.get("labelText")}
            self.assertEqual(labels[es.PAPER_ID], f"({paper})")

    def test_the_map_and_the_legend_box_are_where_example_sheet_says(self):
        for paper, orientation in es.formats():
            _, items, _ = template(paper, orientation)
            for item_id, box in ((es.MAP_ID, es.map_box(paper, orientation)),
                                 (es.LEGEND_ID, es.legend_box(paper, orientation))):
                for got, expected in zip(items[item_id], (box.x, box.y, box.width, box.height)):
                    self.assertAlmostEqual(got, expected, delta=0.05, msg=(paper, orientation, item_id))

    def test_every_item_lies_on_the_page(self):
        for paper, orientation in es.formats():
            (width, height), items, _ = template(paper, orientation)
            for item_id, (x, y, w, h) in items.items():
                if item_id in ("Skalstock",):  # förankrad i höger kant och växer åt vänster med skalan
                    continue
                self.assertTrue(-0.01 <= x and x + w <= width + 0.01 and -0.01 <= y and y + h <= height + 0.01,
                                (paper, orientation, item_id))

    def test_the_landscape_formats_are_the_a2_page_in_another_scale(self):
        _, a2, _ = template("A2", "liggande")
        for paper in ("A1", "A3", "A4"):
            _, items, _ = template(paper, "liggande")
            k = es.factor(paper)
            for item_id in (es.NAME_ID, "Norrpil", es.STAGE_ID):
                for got, source in zip(items[item_id], a2[item_id]):
                    self.assertAlmostEqual(got, source * k, delta=0.05, msg=(paper, item_id))

    def test_the_coordinate_system_in_the_notes_follows_the_project(self):
        _, _, root = template("A2", "liggande")
        notes = next(e.get("labelText") for e in root.iter("LayoutItem") if e.get("id") == "Upplysningar")
        self.assertIn("[% @project_crs_description %]", notes)


class TitleBlockTests(unittest.TestCase):
    def test_the_stage_comes_from_the_status(self):
        self.assertEqual(es.stage({"status": "samråd"}), "SAMRÅDSHANDLING")
        self.assertEqual(es.stage({"status": "granskning"}), "GRANSKNINGSHANDLING")
        self.assertEqual(es.stage({}), "ARBETSHANDLING")

    def test_the_name_and_the_kommun(self):
        self.assertEqual(es.plan_name({"namn": "Kv Väktaren"}), "Kv Väktaren")
        self.assertEqual(es.plan_name({"namn": "Detaljplan för Väster"}), "Väster")
        self.assertEqual(es.kommun_text({"kommun": "Eskilstuna"}), "i Eskilstuna kommun")
        self.assertEqual(es.kommun_text({"kommun": "Lunds kommun"}), "i Lunds kommun")

    def test_the_decision_dates_or_blanks_to_fill_in(self):
        self.assertEqual(es.decision_dates({"datumAntagande": "2024-03-01",
                                            "datumLagakraft": "2024-04-01; 2024-04-15"}),
                         ("2024-03-01", "2024-04-01"))
        self.assertEqual(es.decision_dates({}), ("202x-xx-xx", "202x-xx-xx"))

    def test_the_layout_gets_a_name_that_is_not_taken(self):
        self.assertEqual(es.layout_name({"namn": "Kv"}, "A2", "liggande", []), "Plankarta A2 liggande – Kv")
        taken = ["Plankarta A3 stående – Kv", "Plankarta A3 stående – Kv (2)"]
        self.assertEqual(es.layout_name({"namn": "Kv"}, "A3", "stående", taken), "Plankarta A3 stående – Kv (3)")


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class SheetLayoutTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.draw("detaljplan", PLAN)
        self.draw("anvandning_yta", LEFT)
        self.draw("anvandning_yta", RIGHT)
        entry = pick(self.catalog, "DP_KM_J2")
        for feature in self.layers["anvandning_yta"].getFeatures():
            self.controller.add_bestammelse("anvandning_yta", feature.id(), entry, filled(entry))
        self.controller.set_plan_values({"kommun": "Eskilstuna", "namn": "Kv Väktaren", "syfte": "Industri",
                                         "status": "samråd", "typ": "detaljplan", "beteckning": "DP 1"})

    def create(self, paper="A2", orientation="liggande"):
        result = esl.create(self.controller.project, catalog=self.catalog, paper=paper, orientation=orientation,
                            **self.controller.sheet_data())
        self.addCleanup(lambda: self.controller.project.layoutManager().removeLayout(result.layout))
        return result

    def items(self, layout, kind):
        return [item for item in layout.items() if isinstance(item, kind)]

    def test_the_layout_is_the_a2_template_in_the_project(self):
        layout = self.create().layout
        page = layout.pageCollection().page(0).pageSize()
        self.assertEqual((round(page.width()), round(page.height())), (594, 420))
        self.assertIs(self.controller.project.layoutManager().layoutByName(layout.name()), layout)
        self.assertEqual(layout.name(), "Plankarta A2 liggande – Kv Väktaren")

    def test_the_map_shows_the_plan_at_its_reference_scale(self):
        layout = self.create().layout
        maps = self.items(layout, QgsLayoutItemMap)
        self.assertEqual(len(maps), 1)
        self.assertAlmostEqual(maps[0].scale(), self.controller.sheet_data()["scale"], delta=1)
        self.assertTrue(maps[0].extent().contains(self.layers["detaljplan"].extent()))

    def test_the_legend_replaces_its_box_and_the_arrow_and_scale_bars_follow_the_map(self):
        layout = self.create().layout
        self.assertEqual(len(ll.existing_legends(layout)), 1)
        self.assertIsNone(layout.itemById(es.LEGEND_ID), "rutan för teckenförklaringen är borta")
        legend = ll.existing_legends(layout)[0].sceneBoundingRect()
        box = es.legend_box("A2", "liggande")
        self.assertAlmostEqual(legend.left(), box.x, delta=1)
        self.assertLessEqual(legend.bottom(), box.bottom + 1)
        self.assertEqual(len(self.items(layout, QgsLayoutItemPicture)), 1)
        bars = self.items(layout, QgsLayoutItemScaleBar)
        self.assertEqual(len(bars), 2)
        self.assertTrue(all(bar.linkedMap() is self.items(layout, QgsLayoutItemMap)[0] for bar in bars))

    def test_the_title_block_has_the_stage_the_name_and_the_kommun(self):
        layout = self.create().layout
        texts = {item_id: layout.itemById(item_id).text()
                 for item_id in (es.STAGE_ID, es.PLAN_TYPE_ID, es.NAME_ID, es.KOMMUN_ID, es.ADOPTION_ID, es.PAPER_ID)}
        self.assertEqual(texts[es.STAGE_ID], "SAMRÅDSHANDLING")
        self.assertEqual(texts[es.PLAN_TYPE_ID], "Detaljplan för")
        self.assertEqual(texts[es.NAME_ID], "Kv Väktaren")
        self.assertEqual(texts[es.KOMMUN_ID], "i Eskilstuna kommun")
        self.assertIn("202x-xx-xx", texts[es.ADOPTION_ID])
        self.assertEqual(texts[es.PAPER_ID], "(A2)")

    def test_every_format_can_be_created(self):
        for paper, orientation in es.formats():
            layout = self.create(paper, orientation).layout
            page = layout.pageCollection().page(0).pageSize()
            self.assertEqual((round(page.width()), round(page.height())),
                             tuple(round(v) for v in es.page_size(paper, orientation)))
            legend = ll.existing_legends(layout)[0].sceneBoundingRect()
            self.assertLessEqual(legend.right(), page.width() + 0.01, (paper, orientation))
            self.assertLessEqual(legend.bottom(), page.height() + 0.01, (paper, orientation))
            self.assertEqual(layout.itemById(es.PAPER_ID).text(), f"({paper})")

    def test_two_layouts_get_different_names(self):
        first, second = self.create().layout, self.create().layout
        self.assertNotEqual(first.name(), second.name())


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class SheetPluginTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.plugin = rita_detaljplan.classFactory(self.iface)
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)
        patcher = mock.patch("rita_detaljplan.plugin.PlanInfoDialog")  # formuläret öppnas annars modalt vid planområdet
        patcher.start()
        self.addCleanup(patcher.stop)
        self.plugin.controller.start_editing()
        self.draw("detaljplan", PLAN)

    def test_the_chosen_format_is_created_and_a2_landscape_is_suggested(self):
        with mock.patch.object(self.plugin, "choose_sheet_format", return_value=("A3", "stående")) as choose:
            result = self.plugin.create_example_sheet()
        self.addCleanup(lambda: self.plugin.controller.project.layoutManager().removeLayout(result.layout))
        choose.assert_called_once_with(("A2", "liggande"))
        page = result.layout.pageCollection().page(0).pageSize()
        self.assertEqual((round(page.width()), round(page.height())), (297, 420))

    def test_nothing_is_created_when_the_choice_is_cancelled(self):
        before = len(self.plugin.controller.project.layoutManager().printLayouts())
        with mock.patch.object(self.plugin, "choose_sheet_format", return_value=None):
            self.assertIsNone(self.plugin.create_example_sheet())
        self.assertEqual(len(self.plugin.controller.project.layoutManager().printLayouts()), before)


if __name__ == "__main__":
    unittest.main()
