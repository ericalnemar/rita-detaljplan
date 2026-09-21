"""Reglerna för hierarkin planområde → användning → egenskap (ren geometri, ingen styrenhet)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import (FAR_AWAY, HAVE_QGIS, INSIDE, LEFT, LINE_FAR, LINE_INSIDE, LINE_ON_EDGE, PLAN, POINT_FAR,  # noqa: E402
                       POINT_ON_EDGE, RIGHT, PlanCase)

if HAVE_QGIS:
    from qgis.core import QgsGeometry
    from rita_detaljplan.core import rules


def geom(wkt):
    return QgsGeometry.fromWkt(wkt)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ConstrainUse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qgis_app import get_app
        get_app()
        cls.plan = geom(PLAN)

    def test_a_use_needs_a_plan_area(self):
        result = rules.constrain_use(geom(INSIDE), None, None)
        self.assertFalse(result.ok)
        self.assertIn("Rita planområdet först", result.problems[0])

    def test_a_use_inside_the_plan_is_left_alone(self):
        result = rules.constrain_use(geom(INSIDE), self.plan, None)
        self.assertTrue(result.ok)
        self.assertFalse(result.changed)
        self.assertEqual(result.notes, [])

    def test_the_part_outside_the_plan_is_clipped_away(self):
        result = rules.constrain_use(geom("MultiPolygon(((80 80, 120 80, 120 120, 80 120, 80 80)))"), self.plan, None)
        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertAlmostEqual(result.geometry.area(), 400.0)
        self.assertIn("beskars mot planområdet", result.notes[0])
        self.assertEqual(result.geometry.wkbType().name, "MultiPolygon")

    def test_a_use_entirely_outside_the_plan_is_refused(self):
        result = rules.constrain_use(geom(FAR_AWAY), self.plan, None)
        self.assertFalse(result.ok)
        self.assertIn("utanför planområdet", result.problems[0])

    def test_five_centimetres_outside_is_within_the_tolerance_and_kept_as_drawn(self):
        drawn = geom("MultiPolygon(((10 10, 100.05 10, 100.05 40, 10 40, 10 10)))")
        result = rules.constrain_use(drawn, self.plan, None)
        self.assertTrue(result.ok and not result.changed)

    def test_overlap_with_another_use_is_clipped_away(self):
        result = rules.constrain_use(geom("MultiPolygon(((30 0, 80 0, 80 100, 30 100, 30 0)))"), self.plan, geom(LEFT))
        self.assertTrue(result.ok)
        self.assertAlmostEqual(result.geometry.area(), 30 * 100)
        self.assertIn("Överlapp", result.notes[0])

    def test_a_use_entirely_inside_another_is_refused(self):
        result = rules.constrain_use(geom(INSIDE), self.plan, geom(LEFT))
        self.assertFalse(result.ok)
        self.assertIn("får inte överlappa", result.problems[0])

    def test_clipping_never_leaves_stray_lines_or_slivers(self):
        # ytan gränsar exakt mot planområdets kant: beskärningen får inte ge kvar linjer eller splitter
        result = rules.constrain_use(geom("MultiPolygon(((100 0, 150 0, 150 50, 100 50, 100 0)))"), self.plan, None)
        self.assertFalse(result.ok)

    def test_touching_uses_share_their_edge(self):
        result = rules.constrain_use(geom(RIGHT), self.plan, geom(LEFT))
        self.assertTrue(result.ok and not result.changed)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ConstrainProperty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qgis_app import get_app
        get_app()
        cls.uses = geom(LEFT)

    def test_a_property_needs_a_use(self):
        result = rules.constrain_property(geom(INSIDE), None)
        self.assertIn("användningen först", result.problems[0])

    def test_an_area_inside_a_use_is_left_alone(self):
        result = rules.constrain_property(geom(INSIDE), self.uses)
        self.assertTrue(result.ok and not result.changed)

    def test_an_area_is_clipped_to_the_use(self):
        result = rules.constrain_property(geom("MultiPolygon(((30 10, 70 10, 70 40, 30 40, 30 10)))"), self.uses)
        self.assertTrue(result.ok and result.changed)
        self.assertAlmostEqual(result.geometry.area(), 20 * 30)
        self.assertIn("beskars mot användningen", result.notes[0])

    def test_an_area_outside_every_use_is_refused(self):
        result = rules.constrain_property(geom(FAR_AWAY), self.uses)
        self.assertIn("inte inom någon användningsyta", result.problems[0])

    def test_a_line_is_clipped_and_a_far_line_refused(self):
        clipped = rules.constrain_property(geom("MultiLineString(((20 20, 80 20)))"), self.uses)
        self.assertTrue(clipped.ok and clipped.changed)
        self.assertAlmostEqual(clipped.geometry.length(), 30.1, delta=0.2)
        self.assertIn("linjen", rules.constrain_property(geom(LINE_FAR), self.uses).problems[0])
        self.assertTrue(rules.constrain_property(geom(LINE_INSIDE), self.uses).ok)
        self.assertTrue(rules.constrain_property(geom(LINE_ON_EDGE), self.uses).ok)

    def test_a_point_must_lie_on_or_in_a_use(self):
        self.assertTrue(rules.constrain_property(geom(POINT_ON_EDGE), self.uses).ok)
        self.assertIn("punkten", rules.constrain_property(geom(POINT_FAR), self.uses).problems[0])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class Measures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qgis_app import get_app
        get_app()

    def test_coverage_is_the_share_of_the_plan_that_has_a_use(self):
        self.assertAlmostEqual(rules.coverage(geom(LEFT), geom(PLAN)), 0.5)
        self.assertEqual(rules.coverage(None, geom(PLAN)), 0.0)
        self.assertEqual(rules.coverage(geom(LEFT), None), 0.0)
        self.assertEqual(rules.coverage(geom("MultiPolygon(((-50 -50, 200 -50, 200 200, -50 200, -50 -50)))"), geom(PLAN)), 1.0)

    def test_area_of_use_outside_the_plan(self):
        self.assertAlmostEqual(rules.outside_plan(geom("MultiPolygon(((80 0, 120 0, 120 100, 80 100, 80 0)))"), geom(PLAN)),
                               20 * 100, delta=20 * 0.1 * 100 / 2 + 1, msg="10 cm tolerans längs kanten dras av")
        self.assertEqual(rules.outside_plan(None, geom(PLAN)), 0.0)


class LinkRules(PlanCase):
    def link(self, wkt, form="Kvartersmark"):
        return rules.link_property(QgsGeometry.fromWkt(wkt), self.layers["anvandning_yta"], form)

    def use(self, wkt=PLAN, form="Kvartersmark"):
        return self.add("anvandning_yta", wkt, anvandningsform=form)

    def test_without_any_use_the_user_is_told_to_draw_it_first(self):
        result = self.link(INSIDE)
        self.assertFalse(result.ok)
        self.assertIn("användningen först", result.problems[0])

    def test_area_inside_a_use_is_linked_to_it(self):
        use = self.use()
        result = self.link(INSIDE)
        self.assertTrue(result.ok, result.problems)
        self.assertEqual(result.use_ids, [use["objektidentitet"]])

    def test_area_spanning_two_uses_is_linked_to_both(self):
        left, right = self.use(LEFT), self.use(RIGHT)
        result = self.link("MultiPolygon(((30 10, 70 10, 70 40, 30 40, 30 10)))")
        self.assertTrue(result.ok, result.problems)
        self.assertEqual(set(result.use_ids), {left["objektidentitet"], right["objektidentitet"]})

    def test_area_over_a_gap_between_uses_is_refused(self):
        self.use("MultiPolygon(((0 0, 40 0, 40 100, 0 100, 0 0)))")
        self.use("MultiPolygon(((60 0, 100 0, 100 100, 60 100, 60 0)))")
        self.assertFalse(self.link("MultiPolygon(((30 10, 70 10, 70 40, 30 40, 30 10)))").ok)

    def test_the_form_of_the_property_must_match_the_use(self):
        self.use(form="Kvartersmark")
        result = self.link(INSIDE, form="Allmän plats")
        self.assertFalse(result.ok)
        self.assertIn("allmän plats", result.problems[0])
        self.assertIn("kvartersmark", result.problems[0])

    def test_an_area_crossing_two_forms_is_refused_when_one_does_not_match(self):
        self.use(LEFT, "Kvartersmark")
        self.use(RIGHT, "Allmän plats")
        self.assertFalse(self.link("MultiPolygon(((30 10, 70 10, 70 40, 30 40, 30 10)))", form="Kvartersmark").ok)

    def test_unassigned_uses_and_plan_wide_properties_are_not_form_checked(self):
        self.add("anvandning_yta", PLAN)  # ingen bestämmelse än, alltså ingen användningsform
        self.assertTrue(self.link(INSIDE, form="Allmän plats").ok)
        self.assertTrue(self.link(INSIDE, form="Planområdet").ok)
        self.assertTrue(self.link(INSIDE, form=None).ok)

    def test_lines_and_points_are_linked_to_the_use_they_lie_on(self):
        use = self.use(LEFT)
        for wkt in (LINE_INSIDE, LINE_ON_EDGE, POINT_ON_EDGE):
            result = self.link(wkt)
            self.assertTrue(result.ok, f"{wkt}: {result.problems}")
            self.assertEqual(result.use_ids, [use["objektidentitet"]])

    def test_a_line_between_two_forms_only_needs_one_matching_side(self):
        self.use(LEFT, "Kvartersmark")
        self.use(RIGHT, "Allmän plats")
        border = "MultiLineString(((50 20, 50 60)))"
        self.assertTrue(self.link(border, form="Allmän plats").ok)
        self.assertTrue(self.link(border, form="Kvartersmark").ok)
        self.assertFalse(self.link(border, form="Vattenområde").ok)

    def test_empty_geometry_is_refused(self):
        self.use()
        self.assertIn("saknar geometri", rules.link_property(QgsGeometry(), self.layers["anvandning_yta"]).problems[0])

    def test_links_are_stored_as_semicolon_separated_uuids(self):
        self.assertEqual(rules.format_links(["a", "b"]), "a;b")
        self.assertEqual(rules.parse_links("a;b;"), ["a", "b"])
        self.assertEqual(rules.parse_links(None), [])


if __name__ == "__main__":
    unittest.main()
