"""Exempellayouten för plankartan (ärende 2): sidans indelning, skalstock och titelruta (ren Python), och layouten i QGIS."""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, LEFT, PLAN, RIGHT, filled, pick  # noqa: E402
from rita_detaljplan.core import example_sheet as es  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsLayoutItemMap, QgsLayoutItemPicture, QgsLayoutItemScaleBar, QgsLayoutItemLabel
    from rita_detaljplan.core import example_sheet_layout as esl
    from rita_detaljplan.core import legend_layout as ll
    from test_toolbar import GuiCase
else:  # pragma: no cover
    GuiCase = unittest.TestCase


class SheetTests(unittest.TestCase):
    def test_the_map_and_the_column_fill_an_a2_page_inside_the_margins(self):
        sheet = es.sheet()
        self.assertEqual((sheet.map.x, sheet.map.y), (es.MARGIN, es.MARGIN))
        self.assertEqual(sheet.map.bottom, es.PAGE_HEIGHT - es.MARGIN)
        self.assertAlmostEqual(sheet.legend.right, es.PAGE_WIDTH - es.MARGIN)
        self.assertAlmostEqual(sheet.title_block.bottom, es.PAGE_HEIGHT - es.MARGIN)
        self.assertLess(sheet.map.right, sheet.legend.x, "kartan och kolumnen överlappar inte")
        self.assertLess(sheet.legend.bottom, sheet.scale_row.y)
        self.assertLess(sheet.scale_row.bottom, sheet.title_block.y)
        self.assertGreater(sheet.title_block.height, 100)

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

    def test_the_scale_bar_has_even_segments_of_about_two_centimetres(self):
        self.assertEqual([es.segment_length(s) for s in (500, 1000, 2000, 4000)], [10, 20, 50, 100])
        self.assertEqual(es.scale_text(1000), "Skala 1:1 000 (A2)")

    def test_the_title_block_shows_the_plan_and_blanks_for_what_is_missing(self):
        kommun, name, stage = es.heading({"kommun": "Eskilstuna", "namn": "Kv Väktaren", "status": "granskning"})
        self.assertEqual((kommun, name, stage), ("Eskilstuna kommun", "Detaljplan för Kv Väktaren", "Granskningshandling"))
        self.assertEqual(es.heading({"kommun": "Lunds kommun", "namn": "Detaljplan för Väster"})[:2],
                         ("Lunds kommun", "Detaljplan för Väster"))
        rows = dict(es.title_rows({"beteckning": "DP 1"},
                                  {"datumAntagande": "2024-03-01", "datumLagakraft": "2024-04-01; 2024-04-15"},
                                  date(2026, 10, 30)))
        self.assertEqual((rows["Planbeteckning"], rows["Upprättad"], rows["Antagen"], rows["Laga kraft"]),
                         ("DP 1", "2026-10-30", "2024-03-01", "2024-04-01"))
        self.assertEqual((rows["Diarienummer"], rows["Handläggare"]), (es.BLANK, es.BLANK))

    def test_the_layout_gets_a_name_that_is_not_taken(self):
        self.assertEqual(es.layout_name({"namn": "Kv"}, []), "Plankarta – Kv")
        self.assertEqual(es.layout_name({"namn": "Kv"}, ["Plankarta – Kv", "Plankarta – Kv (2)"]), "Plankarta – Kv (3)")


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class SheetLayoutTests(GuiCase):
    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.draw("detaljplan", PLAN)
        use = self.draw("anvandning_yta", LEFT)
        self.draw("anvandning_yta", RIGHT)
        entry = pick(self.catalog, "DP_KM_J2")
        for feature in self.layers["anvandning_yta"].getFeatures():
            self.controller.add_bestammelse("anvandning_yta", feature.id(), entry, filled(entry))
        self.controller.set_plan_values({"kommun": "Eskilstuna", "namn": "Kv Väktaren", "syfte": "Industri",
                                         "status": "samråd", "typ": "detaljplan", "beteckning": "DP 1"})
        self.use = use

    def create(self):
        result = esl.create(self.controller.project, catalog=self.catalog, **self.controller.sheet_data())
        self.addCleanup(lambda: self.controller.project.layoutManager().removeLayout(result.layout))
        return result

    def items(self, layout, kind):
        return [item for item in layout.items() if isinstance(item, kind)]

    def test_the_layout_is_an_a2_page_in_the_project(self):
        layout = self.create().layout
        page = layout.pageCollection().page(0).pageSize()
        self.assertEqual((round(page.width()), round(page.height())), (594, 420))
        self.assertIs(self.controller.project.layoutManager().layoutByName(layout.name()), layout)
        self.assertEqual(layout.name(), "Plankarta – Kv Väktaren")

    def test_the_map_shows_the_plan_at_its_reference_scale(self):
        layout = self.create().layout
        maps = self.items(layout, QgsLayoutItemMap)
        self.assertEqual(len(maps), 1)
        self.assertAlmostEqual(maps[0].scale(), self.controller.sheet_data()["scale"], delta=1)
        self.assertTrue(maps[0].extent().contains(self.layers["detaljplan"].extent()))

    def test_there_is_a_legend_a_north_arrow_and_a_scale_bar_linked_to_the_map(self):
        layout = self.create().layout
        self.assertEqual(len(ll.existing_legends(layout)), 1)
        self.assertEqual(len(self.items(layout, QgsLayoutItemPicture)), 1)
        bars = self.items(layout, QgsLayoutItemScaleBar)
        self.assertEqual(len(bars), 1)
        self.assertIs(bars[0].linkedMap(), self.items(layout, QgsLayoutItemMap)[0])

    def test_the_title_block_has_the_plans_name_stage_and_scale(self):
        texts = [item.text() for item in self.items(self.create().layout, QgsLayoutItemLabel)]
        for wanted in ("ESKILSTUNA KOMMUN", "Detaljplan för Kv Väktaren", "Samrådshandling", "DP 1"):
            self.assertIn(wanted, texts)
        self.assertTrue(any(text.startswith("Skala 1:") for text in texts))

    def test_two_layouts_get_different_names(self):
        first, second = self.create().layout, self.create().layout
        self.assertNotEqual(first.name(), second.name())


if __name__ == "__main__":
    unittest.main()
