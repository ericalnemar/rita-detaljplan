"""Tar man bort något högre i hierarkin försvinner allt som ligger under det (kräver QGIS)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, filled, pump  # noqa: E402

if HAVE_QGIS:
    from test_export import ExportCase

RIGHT_PROPERTY = "MultiPolygon(((60 10, 90 10, 90 40, 60 40, 60 10)))"
ACROSS = "MultiPolygon(((40 60, 60 60, 60 80, 40 80, 40 60)))"  # ligger till hälften på vardera användningen
RIGHT_LINE = "MultiLineString(((70 20, 70 60)))"
AREA_TABLES = ("anvandning_yta", "egenskap_yta", "egenskap_linje")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class CascadeCase(ExportCase):
    """Planen i ExportCase (två användningar, egenskap och linje på den vänstra) med fler egenskaper som tillägg."""

    def setUp(self):
        super().setUp()
        self.right_property = self.draw("egenskap_yta", RIGHT_PROPERTY)
        self.across = self.draw("egenskap_yta", ACROSS)
        self.right_line = self.draw("egenskap_linje", RIGHT_LINE)
        for table, feature, entry in (("egenskap_yta", self.right_property, self.prop_entry),
                                      ("egenskap_yta", self.across, self.prop_entry),
                                      ("egenskap_linje", self.right_line, self.line_entry)):
            self.controller.add_bestammelse(table, feature.id(), entry, filled(entry))
        pump()
        self.warnings.clear()

    def count(self, table):
        return self.layers[table].featureCount()

    def delete(self, table, fid):
        self.assertTrue(self.layers[table].deleteFeature(fid))
        pump()

    def ids(self, table):
        return {f.id() for f in self.layers[table].getFeatures()}

    def area_identities(self):
        return {f["objektidentitet"] for table in AREA_TABLES for f in self.layers[table].getFeatures()}

    def rows_on(self, identity):
        return [r for r in self.layers["bestammelse"].getFeatures() if r["yta"] == identity]

    def plan(self):
        (plan,) = list(self.layers["detaljplan"].getFeatures())
        return plan


class DeletingAUseTests(CascadeCase):
    def test_everything_that_lay_on_the_deleted_use_disappears(self):
        self.delete("anvandning_yta", self.left.id())
        self.assertEqual(self.count("anvandning_yta"), 1)
        self.assertNotIn(self.prop.id(), self.ids("egenskap_yta"))
        self.assertNotIn(self.line.id(), self.ids("egenskap_linje"))

    def test_what_lies_on_the_other_use_stays(self):
        self.delete("anvandning_yta", self.left.id())
        self.assertIn(self.right_property.id(), self.ids("egenskap_yta"))
        self.assertIn(self.right_line.id(), self.ids("egenskap_linje"))

    def test_a_property_across_two_uses_keeps_only_the_part_on_the_remaining_use(self):
        self.delete("anvandning_yta", self.left.id())
        kept = self.layers["egenskap_yta"].getFeature(self.across.id()).geometry()
        self.assertAlmostEqual(kept.area(), 10 * 20, delta=1.0, msg="halva ytan (x 50 till 60) återstår")
        self.assertGreaterEqual(kept.boundingBox().xMinimum(), 49.9)

    def test_no_provision_is_left_without_an_area(self):
        before = self.count("bestammelse")
        self.delete("anvandning_yta", self.left.id())
        self.assertLess(self.count("bestammelse"), before)
        identities = self.area_identities()
        self.assertTrue(all(r["yta"] in identities for r in self.layers["bestammelse"].getFeatures()))

    def test_the_use_that_is_left_keeps_its_provisions(self):
        identity = self.layers["anvandning_yta"].getFeature(self.right.id())["objektidentitet"]
        before = len(self.rows_on(identity))
        self.assertGreater(before, 0)
        self.delete("anvandning_yta", self.left.id())
        self.assertEqual(len(self.rows_on(identity)), before)

    def test_the_user_is_told_what_else_was_removed(self):
        self.delete("anvandning_yta", self.left.id())
        text = " ".join(self.warnings)
        self.assertIn("Tog bort även", text)
        self.assertIn("egenskap", text)
        self.assertIn("bestämmelse", text)
        self.assertIn("som hörde till det du tog bort", text)


class DeletingTheLowestLevelTests(CascadeCase):
    def test_deleting_a_property_removes_nothing_else_but_its_own_provisions(self):
        uses, plans, lines = self.count("anvandning_yta"), self.count("detaljplan"), self.count("egenskap_linje")
        identity = self.right_property["objektidentitet"]
        self.assertGreater(len(self.rows_on(identity)), 0)
        self.delete("egenskap_yta", self.right_property.id())
        self.assertEqual((self.count("anvandning_yta"), self.count("detaljplan"), self.count("egenskap_linje")),
                         (uses, plans, lines))
        self.assertEqual(self.rows_on(identity), [])
        self.assertFalse(any("Tog bort även" in w for w in self.warnings))

    def test_deleting_a_line_leaves_the_areas_alone(self):
        areas = self.count("egenskap_yta")
        self.delete("egenskap_linje", self.right_line.id())
        self.assertEqual(self.count("egenskap_yta"), areas)
        self.assertEqual(self.count("anvandning_yta"), 2)


class DeletingThePlanAreaTests(CascadeCase):
    def test_everything_below_the_plan_area_disappears(self):
        self.delete("detaljplan", self.plan().id())
        for table in AREA_TABLES:
            self.assertEqual(self.count(table), 0, table)

    def test_all_provisions_of_the_plan_disappear(self):
        self.assertGreater(self.count("bestammelse"), 0)
        self.delete("detaljplan", self.plan().id())
        self.assertEqual([r for r in self.layers["bestammelse"].getFeatures() if r["tabell"] in AREA_TABLES], [])

    def test_helper_lines_are_not_part_of_the_hierarchy_and_stay(self):
        self.draw("hjalplinje", "MultiLineString(((0 0, 100 100)))")
        self.delete("detaljplan", self.plan().id())
        self.assertEqual(self.count("hjalplinje"), 1)

    def test_the_message_counts_everything_that_went(self):
        self.delete("detaljplan", self.plan().id())
        text = " ".join(self.warnings)
        self.assertIn("2 användningsytor", text)
        self.assertIn(" och ", text)
        self.assertIn("bestämmelser", text)

    def test_deleting_the_plan_area_when_nothing_lies_below_it_is_quiet(self):
        for table in ("egenskap_yta", "egenskap_linje", "anvandning_yta"):
            layer = self.layers[table]
            layer.deleteFeatures([f.id() for f in layer.getFeatures()])
        pump()
        self.warnings.clear()
        self.delete("detaljplan", self.plan().id())
        self.assertEqual(self.warnings, [])

    def test_the_plan_can_be_started_again_afterwards(self):
        self.delete("detaljplan", self.plan().id())
        again = self.draw("detaljplan", "MultiPolygon(((0 0, 100 0, 100 100, 0 100, 0 0)))")
        use = self.draw("anvandning_yta", "MultiPolygon(((0 0, 50 0, 50 100, 0 100, 0 0)))")
        self.assertIsNotNone(again)
        self.assertIsNotNone(use)
        self.assertEqual(self.count("anvandning_yta"), 1)


class OtherDeletionsTests(CascadeCase):
    def test_deleting_selected_features_in_one_go_works_too(self):
        layer = self.layers["anvandning_yta"]
        layer.selectAll()
        layer.deleteSelectedFeatures()
        pump()
        for table in AREA_TABLES:
            self.assertEqual(self.count(table), 0, table)

    def test_a_controller_that_has_been_detached_ignores_its_pending_cleanup(self):
        self.assertTrue(self.layers["detaljplan"].deleteFeature(self.plan().id()))  # städningen väntar i händelseslingan
        self.controller.detach()
        pump()
        self.assertEqual(self.count("anvandning_yta"), 2, "en gammal styrenhet får inte ta bort ytor i projektet")

    def test_our_own_deletions_do_not_start_new_cascades(self):
        self.delete("anvandning_yta", self.left.id())
        pump()
        pump()
        self.assertEqual(self.count("anvandning_yta"), 1)
        self.assertEqual(len([w for w in self.warnings if "Tog bort även" in w]), 1)
        self.assertTrue(self.controller.editing)


if __name__ == "__main__":
    unittest.main()
