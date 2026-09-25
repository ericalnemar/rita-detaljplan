"""Styrenheten: hierarki, redigeringssession, regler vid ritning och tilldelning (kräver QGIS)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import (FAR_AWAY, HAVE_QGIS, INSIDE, LEFT, LINE_FAR, LINE_INSIDE, LINE_ON_EDGE, PLAN,  # noqa: E402
                       RIGHT, PlanCase, filled, pick, pump)

if HAVE_QGIS:
    from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer
    from rita_detaljplan.controller import PlanController
    from rita_detaljplan.core import assignments
    from rita_detaljplan.core.assignments import AssignmentError
    from rita_detaljplan.core.project import create_plan_project, load_plan


class ControllerCase(PlanCase):
    def setUp(self):
        super().setUp()
        self.errors, self.warnings = [], []
        self.open_form = mock.Mock()
        self.controller = PlanController(self.errors.append, self.warnings.append, open_form=self.open_form)
        self.addCleanup(self.controller.detach)

    def draw(self, table, wkt):
        """Ritar ett objekt och låter styrenheten hantera det. Returnerar objektet, eller None om det togs bort."""
        feature = self.add(table, wkt)
        pump()
        result = self.layers[table].getFeature(feature.id())
        return result if result.isValid() else None

    def build_plan(self, uses=(LEFT, RIGHT)):
        """Planområde + användningsytor via styrenheten (som när man ritar)."""
        self.draw("detaljplan", PLAN)
        return [self.draw("anvandning_yta", wkt) for wkt in uses]

    def assign(self, table, feature, entry, number="30", **kwargs):
        return self.controller.add_bestammelse(table, feature.id(), entry, filled(entry, number), **kwargs)


class HierarchyTests(ControllerCase):
    def test_nothing_can_be_drawn_before_editing_has_started(self):
        for layer in self.layers.values():
            layer.rollBack()
        ok, reason = self.controller.can_draw("detaljplan")
        self.assertFalse(ok)
        self.assertIn("Börja rita planbestämmelser", reason)

    def test_the_plan_area_can_always_be_drawn_while_editing(self):
        self.assertEqual(self.controller.can_draw("detaljplan"), (True, ""))

    def test_a_use_cannot_be_drawn_before_the_plan_area_exists(self):
        ok, reason = self.controller.can_draw("anvandning_yta")
        self.assertFalse(ok)
        self.assertIn("Rita planområdet först", reason)
        self.draw("detaljplan", PLAN)
        self.assertEqual(self.controller.can_draw("anvandning_yta"), (True, ""))

    def test_a_property_cannot_be_drawn_before_a_use_exists(self):
        self.draw("detaljplan", PLAN)
        for table in ("egenskap_yta", "egenskap_linje"):
            ok, reason = self.controller.can_draw(table)
            self.assertFalse(ok, table)
            self.assertIn("Rita en användningsyta först", reason)
        self.draw("anvandning_yta", LEFT)
        for table in ("egenskap_yta", "egenskap_linje"):
            self.assertEqual(self.controller.can_draw(table), (True, ""), table)

    def test_the_summary_tells_what_is_drawn_and_what_is_missing(self):
        empty = self.controller.summary()
        self.assertEqual((empty.has_plan, empty.has_use, empty.coverage, empty.unassigned), (False, False, 0.0, 0))
        self.build_plan(uses=(LEFT,))
        self.draw("egenskap_yta", INSIDE)
        state = self.controller.summary()
        self.assertEqual((state.plans, state.uses, state.properties), (1, 1, 1))
        self.assertAlmostEqual(state.plan_area, 10000.0)
        self.assertAlmostEqual(state.coverage, 0.5)
        self.assertEqual(state.unassigned, 2, "användningen och egenskapen saknar bestämmelse")
        self.assertTrue(state.editing)

    def test_assigning_provisions_reduces_the_number_of_unassigned_areas(self):
        use, = self.build_plan(uses=(LEFT,))
        self.assertEqual(self.controller.summary().unassigned, 1)
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        self.assertEqual(self.controller.summary().unassigned, 0)

    def test_changes_are_announced_to_the_toolbar(self):
        seen = []
        self.controller.changed.connect(lambda: seen.append(1))
        pump()
        seen.clear()
        self.draw("detaljplan", PLAN)
        self.draw("anvandning_yta", LEFT)
        self.assertGreaterEqual(len(seen), 1)


class IdentityTests(ControllerCase):
    def test_objects_added_without_defaults_get_an_identity_from_the_controller(self):
        from qgis.core import QgsFeature
        self.draw("detaljplan", PLAN)
        layer = self.layers["anvandning_yta"]
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(LEFT))
        layer.addFeature(feature)
        pump()
        stored = layer.getFeature(feature.id())
        self.assertRegex(stored["objektidentitet"], r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")


class PlanAreaTests(ControllerCase):
    def test_the_first_plan_area_asks_for_the_details_of_the_plan(self):
        feature = self.draw("detaljplan", PLAN)
        self.open_form.assert_called_once()
        layer, opened = self.open_form.call_args.args
        self.assertIs(layer, self.layers["detaljplan"])
        self.assertEqual(opened.id(), feature.id())

    FIRST = "MultiPolygon(((0 0, 50 0, 50 50, 0 50, 0 0)))"
    SECOND = "MultiPolygon(((60 0, 100 0, 100 50, 60 50, 60 0)))"

    def two_areas(self):
        first = self.draw("detaljplan", self.FIRST)
        self.controller.set_plan_values({"kommun": "Eskilstuna", "namn": "Kv Väktaren", "syfte": "Bostäder",
                                         "status": "samråd", "typ": "detaljplan", "beteckning": "DP 1"})
        self.open_form.reset_mock()
        second = self.draw("detaljplan", self.SECOND)
        return first, second

    def test_a_second_area_is_a_plan_area_of_its_own_belonging_to_the_same_plan(self):
        first, second = self.two_areas()
        plans = self.features("detaljplan")
        self.assertEqual(len(plans), 2, "två planområden som kan markeras var för sig")
        self.assertNotEqual(first["objektidentitet"], second["objektidentitet"])
        self.assertEqual(sum(f.geometry().area() for f in plans), 50 * 50 + 40 * 50)
        self.open_form.assert_not_called()
        self.assertTrue(any("fler än ett planområde" in w for w in self.warnings))
        stored = self.layers["detaljplan"].getFeature(second.id())
        self.assertEqual((stored["namn"], stored["kommun"], stored["status"], stored["beteckning"]),
                         ("Kv Väktaren", "Eskilstuna", "samråd", "DP 1"), "uppgifterna gäller hela planen")

    def test_the_plan_details_are_saved_on_every_plan_area_and_read_from_the_first(self):
        first, second = self.two_areas()
        self.controller.set_plan_values({"namn": "Nytt namn", "status": "granskning"})
        for fid in (first.id(), second.id()):
            self.assertEqual(self.layers["detaljplan"].getFeature(fid)["namn"], "Nytt namn")
        self.assertEqual(self.controller.plan_feature().id(), first.id())
        self.assertEqual(self.controller.plan_values()["status"], "granskning")

    def test_the_delivery_is_one_plan_with_both_areas_as_its_geometry(self):
        from rita_detaljplan.core import validation
        first, _ = self.two_areas()
        data = validation.collect(self.controller.project)
        self.assertEqual(data.plan.fid, first.id())
        self.assertEqual(data.plan.identity, first["objektidentitet"])
        self.assertAlmostEqual(data.plan.geometry.area(), 50 * 50 + 40 * 50)
        self.assertEqual(len(data.plan.geometry.asGeometryCollection()), 2)

    def test_the_new_area_can_be_selected_and_deleted_without_touching_the_first(self):
        first, second = self.two_areas()
        candidates = self.controller.candidates_at(QgsPointXY(80, 25), 0.5, tables=("detaljplan",))
        self.assertEqual([c.fid for c in candidates], [second.id()], "bara den nya ytan markeras")
        self.assertTrue(self.layers["detaljplan"].deleteFeature(second.id()))
        pump()
        self.assertEqual([f.id() for f in self.features("detaljplan")], [first.id()])
        self.assertEqual(self.controller.plan_values()["namn"], "Kv Väktaren")

    def test_deleting_one_of_two_plan_areas_removes_or_trims_only_the_uses_on_it(self):
        first, second = self.two_areas()
        left = self.draw("anvandning_yta", "MultiPolygon(((0 0, 50 0, 50 50, 0 50, 0 0)))")
        right = self.draw("anvandning_yta", self.SECOND)
        self.assertTrue(self.layers["detaljplan"].deleteFeature(second.id()))
        pump()
        self.assertEqual([f.id() for f in self.features("anvandning_yta")], [left.id()])
        self.assertTrue(any("Tog bort även 1 användningsyta" in w for w in self.warnings), self.warnings)

    def test_a_second_area_overlapping_the_first_is_clipped_and_one_inside_it_is_refused(self):
        self.draw("detaljplan", self.FIRST)
        self.draw("detaljplan", "MultiPolygon(((40 0, 100 0, 100 50, 40 50, 40 0)))")
        plans = self.features("detaljplan")
        self.assertEqual(len(plans), 2)
        self.assertAlmostEqual(sum(f.geometry().area() for f in plans), 100 * 50, delta=0.01)
        self.draw("detaljplan", "MultiPolygon(((10 10, 20 10, 20 20, 10 20, 10 10)))")
        self.assertEqual(len(self.features("detaljplan")), 2)
        self.assertTrue(any("helt inom ett planområde" in e for e in self.errors), self.errors)

    def test_moving_the_plan_area_away_from_the_uses_warns(self):
        self.build_plan(uses=(LEFT,))
        layer = self.layers["detaljplan"]
        layer.changeGeometry(layer.allFeatureIds()[0], QgsGeometry.fromWkt(
            "MultiPolygon(((60 0, 100 0, 100 100, 60 100, 60 0)))"))
        self.assertTrue(any("användning ligger nu utanför planområdet" in w for w in self.warnings), self.warnings)


class UseTests(ControllerCase):
    def test_a_use_cannot_be_kept_without_a_plan_area(self):
        self.assertIsNone(self.draw("anvandning_yta", LEFT))
        self.assertIn("Rita planområdet först", self.errors[0])
        self.assertEqual(self.features("anvandning_yta"), [])

    def test_a_use_inside_the_plan_is_kept_and_starts_without_provisions(self):
        use = self.build_plan(uses=(LEFT,))[0]
        self.assertAlmostEqual(use.geometry().area(), 5000.0)
        self.assertEqual(use["bestammelser"], 0, "bestämmelser tilldelas i ett senare steg")
        self.assertFalse(use["beteckning"])
        self.assertEqual(use["detaljplan"], self.features("detaljplan")[0]["objektidentitet"])
        self.assertEqual(self.errors, [])

    def test_the_part_outside_the_plan_is_clipped_away_with_a_message(self):
        self.draw("detaljplan", PLAN)
        use = self.draw("anvandning_yta", "MultiPolygon(((80 80, 130 80, 130 130, 80 130, 80 80)))")
        self.assertAlmostEqual(use.geometry().area(), 20 * 20)
        self.assertTrue(any("beskars mot planområdet" in w for w in self.warnings))
        self.assertEqual(use.geometry().wkbType().name, "MultiPolygon")

    def test_a_use_entirely_outside_the_plan_is_removed(self):
        self.draw("detaljplan", PLAN)
        self.assertIsNone(self.draw("anvandning_yta", FAR_AWAY))
        self.assertIn("utanför planområdet", self.errors[0])
        self.assertEqual(self.features("anvandning_yta"), [])

    def test_overlap_between_uses_is_clipped_away(self):
        self.draw("detaljplan", PLAN)
        self.draw("anvandning_yta", LEFT)
        second = self.draw("anvandning_yta", "MultiPolygon(((30 0, 80 0, 80 100, 30 100, 30 0)))")
        self.assertAlmostEqual(second.geometry().area(), 30 * 100)
        self.assertTrue(any("Överlapp" in w for w in self.warnings))
        union = QgsGeometry.unaryUnion([f.geometry() for f in self.features("anvandning_yta")])
        self.assertAlmostEqual(union.area(), 80 * 100)

    def test_a_use_wholly_inside_another_is_removed(self):
        self.draw("detaljplan", PLAN)
        self.draw("anvandning_yta", LEFT)
        self.assertIsNone(self.draw("anvandning_yta", INSIDE))
        self.assertIn("får inte överlappa", self.errors[-1])

    def test_a_use_dragged_out_of_the_plan_is_clipped_back(self):
        self.build_plan(uses=(LEFT,))
        layer = self.layers["anvandning_yta"]
        fid = layer.allFeatureIds()[0]
        layer.changeGeometry(fid, QgsGeometry.fromWkt("MultiPolygon(((-30 0, 50 0, 50 100, -30 100, -30 0)))"))
        self.assertAlmostEqual(layer.getFeature(fid).geometry().area(), 5000.0)
        self.assertTrue(any("beskars mot planområdet" in w for w in self.warnings))

    def test_a_use_dragged_over_another_is_clipped_back(self):
        self.build_plan(uses=(LEFT, RIGHT))
        layer = self.layers["anvandning_yta"]
        left = next(f for f in self.features("anvandning_yta") if f.geometry().boundingBox().xMinimum() < 1)
        layer.changeGeometry(left.id(), QgsGeometry.fromWkt("MultiPolygon(((0 0, 70 0, 70 100, 0 100, 0 0)))"))
        self.assertAlmostEqual(layer.getFeature(left.id()).geometry().area(), 5000.0)


class PropertyTests(ControllerCase):
    def test_a_property_inside_a_use_is_kept_without_provisions(self):
        self.build_plan(uses=(LEFT,))
        prop = self.draw("egenskap_yta", INSIDE)
        self.assertIsNotNone(prop)
        self.assertEqual(prop["bestammelser"], 0)
        self.assertEqual(self.errors, [])

    def test_a_property_is_clipped_to_the_use(self):
        self.build_plan(uses=(LEFT,))
        prop = self.draw("egenskap_yta", "MultiPolygon(((30 10, 80 10, 80 40, 30 40, 30 10)))")
        self.assertAlmostEqual(prop.geometry().area(), 20 * 30)
        self.assertTrue(any("beskars mot användningen" in w for w in self.warnings))

    def test_a_property_outside_every_use_is_removed(self):
        self.build_plan(uses=(LEFT,))
        self.assertIsNone(self.draw("egenskap_yta", "MultiPolygon(((60 10, 90 10, 90 40, 60 40, 60 10)))"))
        self.assertIn("Egenskapen togs bort", self.errors[0])
        self.assertIn("inte inom någon användningsyta", self.errors[0])

    def test_a_property_without_any_use_is_removed(self):
        self.draw("detaljplan", PLAN)
        self.assertIsNone(self.draw("egenskap_yta", INSIDE))
        self.assertIn("användningen först", self.errors[0])

    def test_lines_must_lie_on_a_use(self):
        self.build_plan(uses=(LEFT,))
        self.assertIsNotNone(self.draw("egenskap_linje", LINE_ON_EDGE))
        self.assertIsNotNone(self.draw("egenskap_linje", LINE_INSIDE))
        self.assertIsNone(self.draw("egenskap_linje", LINE_FAR))
        self.assertEqual(len(self.errors), 1)
        self.assertIn("Egenskapslinjen", self.errors[0])

    def test_an_area_spanning_two_uses_is_kept_whole(self):
        self.build_plan(uses=(LEFT, RIGHT))
        prop = self.draw("egenskap_yta", "MultiPolygon(((30 10, 70 10, 70 40, 30 40, 30 10)))")
        self.assertAlmostEqual(prop.geometry().area(), 40 * 30)
        self.assertEqual(self.warnings, [])

    def test_properties_may_overlap_each_other(self):
        self.build_plan(uses=(LEFT,))
        first = self.draw("egenskap_yta", INSIDE)
        second = self.draw("egenskap_yta", "MultiPolygon(((20 20, 45 20, 45 50, 20 50, 20 20)))")
        self.assertTrue(first and second)
        self.assertEqual(len(self.features("egenskap_yta")), 2)
        self.assertEqual(self.errors, [])

    def test_moving_a_property_out_of_its_use_warns_and_within_it_stays_quiet(self):
        self.build_plan(uses=(LEFT, RIGHT))
        prop = self.draw("egenskap_yta", INSIDE)
        layer = self.layers["egenskap_yta"]
        layer.changeGeometry(prop.id(), QgsGeometry.fromWkt("MultiPolygon(((30 10, 70 10, 70 40, 30 40, 30 10)))"))
        self.assertEqual(self.warnings, [])
        layer.changeGeometry(prop.id(), QgsGeometry.fromWkt(FAR_AWAY))
        self.assertTrue(any("hör inte längre till en användning" in w for w in self.warnings))
        self.assertEqual(len(self.features("egenskap_yta")), 1, "flyttade objekt tas inte bort automatiskt")


class CandidateTests(ControllerCase):
    def setUp(self):
        super().setUp()
        self.use_a, self.use_b = self.build_plan(uses=(LEFT, RIGHT))
        self.prop = self.draw("egenskap_yta", INSIDE)
        self.big = self.draw("egenskap_yta", "MultiPolygon(((5 5, 45 5, 45 95, 5 95, 5 5)))")
        self.line = self.draw("egenskap_linje", LINE_INSIDE)

    def tables(self, point, tolerance=0.5):
        return [(c.table, c.fid) for c in self.controller.candidates_at(QgsPointXY(*point), tolerance)]

    def test_a_click_on_a_use_alone_finds_only_that_use(self):
        self.assertEqual(self.tables((75, 50)), [("anvandning_yta", self.use_b.id())])

    def test_overlapping_areas_are_listed_top_first_and_smallest_property_first(self):
        found = self.tables((30, 30))
        self.assertEqual(found, [("egenskap_yta", self.prop.id()), ("egenskap_yta", self.big.id()),
                                 ("anvandning_yta", self.use_a.id())])

    def test_a_line_is_found_within_the_tolerance_and_comes_first(self):
        found = self.tables((20.3, 40))
        self.assertEqual(found[0], ("egenskap_linje", self.line.id()))
        self.assertIn(("anvandning_yta", self.use_a.id()), found)
        self.assertNotIn(("egenskap_linje", self.line.id()), self.tables((25, 40)))

    def test_a_click_outside_every_area_finds_nothing(self):
        self.assertEqual(self.tables((500, 500)), [])

    def test_the_titles_tell_what_kind_of_area_it_is_and_whether_it_has_provisions(self):
        titles = [c.title for c in self.controller.candidates_at(QgsPointXY(30, 30), 0.5)]
        self.assertTrue(titles[0].startswith("Egenskapsområde · saknar bestämmelse · "))
        self.assertTrue(titles[-1].startswith("Användningsområde · saknar bestämmelse · "))
        self.assertIn("m²", titles[0])
        self.assertTrue(self.controller.candidates_at(QgsPointXY(20.3, 40), 0.5)[0].title.startswith("Egenskapslinje"))
        self.assertTrue(self.controller.candidates_at(QgsPointXY(20.3, 40), 0.5)[0].title.endswith(" m"))

    def test_the_title_shows_the_label_once_provisions_are_assigned(self):
        self.assign("anvandning_yta", self.use_b, pick(self.catalog, "DP_KM_J2"))
        candidate = self.controller.candidates_at(QgsPointXY(75, 50), 0.5)[0]
        self.assertIn("· J ·", candidate.title)


class AssignTests(ControllerCase):
    def test_a_use_can_get_several_uses(self):
        use, = self.build_plan(uses=(LEFT,))
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        other = next(e for e in self.catalog.search(layer="anvandning_yta")
                     if e.anvandningsform == "Kvartersmark" and e.label_base == "B")
        self.assign("anvandning_yta", use, other)
        self.assertEqual(self.layers["anvandning_yta"].getFeature(use.id())["beteckning"], "JB")
        self.assertEqual(len(self.controller.rows_of("anvandning_yta", use.id())), 2)

    def test_a_refused_assignment_explains_why_and_changes_nothing(self):
        use, = self.build_plan(uses=(LEFT,))
        with self.assertRaises(AssignmentError):
            self.assign("anvandning_yta", use, pick(self.catalog, layer="egenskap_yta", contains="byggnadsarea"))
        self.assertEqual(self.controller.rows_of("anvandning_yta", use.id()), [])

    def test_the_provisions_offered_depend_on_the_area(self):
        use, = self.build_plan(uses=(LEFT,))
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))  # kvartersmark
        prop = self.draw("egenskap_yta", INSIDE)
        offered = self.controller.entries_for(self.catalog, "egenskap_yta", prop.id())
        self.assertTrue(offered and {e.anvandningsform for e in offered} <= {"Kvartersmark", "Planområdet"})

    def test_assigning_a_use_that_conflicts_with_assigned_properties_warns(self):
        use, = self.build_plan(uses=(LEFT,))
        prop = self.draw("egenskap_yta", INSIDE)
        self.assign("egenskap_yta", prop, pick(self.catalog, layer="egenskap_yta", contains="byggnadsarea"))  # kvartersmark
        street = pick(self.catalog, layer="anvandning_yta", form="Allmän plats", variables=False)
        self.assign("anvandning_yta", use, street)
        self.assertTrue(any("egenskaper ligger nu på en användning med annan användningsform" in w
                            for w in self.warnings), self.warnings)
        self.assertEqual(self.controller.form_conflicts(), 1)

    def test_updating_and_removing_go_through_the_controller(self):
        use, = self.build_plan(uses=(LEFT,))
        row = self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        new = pick(self.catalog, "DP_KM_R2_Motorsport")
        self.controller.update_bestammelse(row["_fid"], new, filled(new))
        self.assertEqual(self.layers["anvandning_yta"].getFeature(use.id())["beteckning"], "R1")
        self.controller.remove_bestammelse(row["_fid"])
        self.assertEqual(self.layers["anvandning_yta"].getFeature(use.id())["bestammelser"], 0)

    def test_deleting_an_area_removes_its_provisions(self):
        use, other = self.build_plan(uses=(LEFT, RIGHT))
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        self.assign("anvandning_yta", other, pick(self.catalog, "DP_KM_R2_Motorsport"))
        self.layers["anvandning_yta"].deleteFeature(use.id())
        pump()
        rows = assignments.read_rows(self.controller.project)
        self.assertEqual([r["yta"] for r in rows], [other["objektidentitet"]])


class SessionTests(ControllerCase):
    def setUp(self):
        super().setUp()
        for layer in self.layers.values():
            layer.rollBack()

    def test_starting_opens_every_plan_layer_and_the_provision_table_for_editing(self):
        self.assertFalse(self.controller.editing)
        self.assertTrue(self.controller.start_editing())
        self.assertTrue(self.controller.editing)
        for table in ("detaljplan", "anvandning_yta", "egenskap_yta", "egenskap_linje", "bestammelse"):
            self.assertTrue(self.layers[table].isEditable(), table)

    def test_saving_commits_the_whole_plan_including_provisions(self):
        self.controller.start_editing()
        use, = self.build_plan(uses=(LEFT,))
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        self.assertTrue(self.controller.has_edits())
        self.assertEqual(self.controller.stop_editing(save=True), [])
        self.assertFalse(self.controller.editing)
        self.assertFalse(self.controller.has_edits())
        for table, expected in (("detaljplan", 1), ("anvandning_yta", 1), ("bestammelse", 1)):
            fresh = QgsVectorLayer(f"{self.gpkg.as_posix()}|layername={table}", "x", "ogr")
            self.assertEqual(fresh.featureCount(), expected, table)

    def test_saving_first_removes_provisions_of_deleted_areas(self):
        self.controller.start_editing()
        use, = self.build_plan(uses=(LEFT,))
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        self.layers["anvandning_yta"].deleteFeature(use.id())
        self.assertEqual(self.controller.stop_editing(save=True), [])
        fresh = QgsVectorLayer(f"{self.gpkg.as_posix()}|layername=bestammelse", "x", "ogr")
        self.assertEqual(fresh.featureCount(), 0)

    def test_discarding_throws_the_changes_away(self):
        self.controller.start_editing()
        use, = self.build_plan(uses=(LEFT,))
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        self.assertEqual(self.controller.stop_editing(save=False), [])
        self.assertFalse(self.controller.editing)
        for table in ("detaljplan", "anvandning_yta", "bestammelse"):
            fresh = QgsVectorLayer(f"{self.gpkg.as_posix()}|layername={table}", "x", "ogr")
            self.assertEqual(fresh.featureCount(), 0, table)

    def test_layers_loaded_after_the_controller_are_attached(self):
        from qgis.core import QgsProject
        QgsProject.instance().clear()
        late = PlanController(self.errors.append, self.warnings.append)
        self.addCleanup(late.detach)
        gpkg, _ = create_plan_project(self.dir, "plan2", "Eskilstuna", "0482", 3006)
        self.layers = load_plan(gpkg, QgsProject.instance())
        late.start_editing()
        self.add("detaljplan", PLAN)
        pump()
        self.assertEqual(late.summary().plans, 1)
        self.assertEqual(late.can_draw("anvandning_yta"), (True, ""))


if __name__ == "__main__":
    unittest.main()


class SavingTests(ControllerCase):
    def test_one_save_saves_everything_and_nothing_starts_editing_again(self):
        from rita_detaljplan.core.project import apply_attributes
        left, _ = self.build_plan()
        entry = pick(self.catalog, "DP_KM_J2")
        self.assign("anvandning_yta", left, entry)
        apply_attributes(self.layers["anvandning_yta"], [left.id()], {"label_x": 12.5, "label_y": 34.5})
        self.controller.set_decision({"datumPaborjat": "2024-05-06"})
        pump()
        self.assertEqual(self.controller.stop_editing(True), [])
        pump()
        self.assertFalse(self.controller.editing, "inget lager ska ha öppnats för redigering igen efter sparandet")
        self.assertFalse(self.controller.has_edits())
        saved = next(f for f in self.layers["anvandning_yta"].getFeatures() if f.geometry().centroid().asPoint().x() < 50)
        self.assertEqual((saved["label_x"], saved["label_y"]), (12.5, 34.5), "textens läge nollställs inte av sparandet")
        self.assertEqual(saved["bestammelser"], 1)
        self.assertEqual(self.layers["bestammelse"].featureCount(), 1)


class FillTests(ControllerCase):
    def start(self):
        self.controller.start_editing()

    def test_fill_use_covers_the_rest_of_the_plan(self):
        self.start()
        self.build_plan(uses=(LEFT,))
        result = self.controller.fill_use()
        pump()
        self.assertTrue(result.ok, result.message)
        self.assertAlmostEqual(self.area("anvandning_yta"), 10000.0)
        uses = self.features("anvandning_yta")
        self.assertEqual(len(uses), 2)
        new = next(f for f in uses if f.geometry().centroid().asPoint().x() > 50)
        self.assertAlmostEqual(new.geometry().area(), 5000.0)
        self.assertTrue(new["objektidentitet"])
        self.assertEqual(new["bestammelser"], 0, "ytan får en bestämmelse i nästa steg")
        self.assertEqual(new.geometry().wkbType().name, "MultiPolygon")

    def test_fill_use_fills_every_hole_at_once(self):
        self.start()
        self.draw("detaljplan", PLAN)
        self.draw("anvandning_yta", "MultiPolygon(((40 0, 60 0, 60 100, 40 100, 40 0)))")
        self.assertTrue(self.controller.fill_use().ok)
        pump()
        self.assertAlmostEqual(self.area("anvandning_yta"), 10000.0)

    def test_fill_use_with_nothing_left_says_so_and_adds_nothing(self):
        self.start()
        self.build_plan(uses=(LEFT, RIGHT))
        result = self.controller.fill_use()
        self.assertFalse(result.ok)
        self.assertIn("inget att fylla", result.message)
        self.assertEqual(len(self.features("anvandning_yta")), 2)

    def test_a_deleted_use_can_be_filled_again_and_given_a_provision_in_the_same_session(self):
        self.start()
        left, _ = self.build_plan(uses=(LEFT, RIGHT))
        entry = pick(self.catalog, "DP_KM_J2")
        self.assign("anvandning_yta", left, entry)
        pump()
        for _ in range(2):  # även när den nya ytan i sin tur tas bort
            use = next(f for f in self.features("anvandning_yta") if f.geometry().centroid().asPoint().x() < 50)
            self.assertTrue(self.layers["anvandning_yta"].deleteFeature(use.id()))
            pump()
            result = self.controller.fill_use_at(QgsPointXY(20, 50))
            self.assertTrue(result.ok, result.message)
            pump()
            self.assign("anvandning_yta", self.layers["anvandning_yta"].getFeature(result.fid), entry)
            pump()
            self.assertEqual(len(self.features("anvandning_yta")), 2)
            self.assertAlmostEqual(self.area("anvandning_yta"), 10000.0)

    def test_fill_use_needs_a_plan_area_and_an_edit_session(self):
        for layer in self.layers.values():
            layer.rollBack()
        self.assertIn("Börja rita", self.controller.fill_use().message)
        self.start()
        self.assertIn("Rita planområdet först", self.controller.fill_use().message)

    def test_fill_use_at_fills_only_the_connected_part_under_the_point(self):
        self.start()
        self.draw("detaljplan", PLAN)
        self.draw("anvandning_yta", "MultiPolygon(((40 0, 60 0, 60 100, 40 100, 40 0)))")
        left = self.controller.fill_use_at(QgsPointXY(20, 50))
        pump()
        self.assertTrue(left.ok, left.message)
        self.assertAlmostEqual(self.area("anvandning_yta"), 40 * 100 + 20 * 100, delta=0.5)
        self.assertGreater(self.controller.missing_use_area(), 40 * 100 - 0.5, "högra biten är fortfarande tom")
        right = self.controller.fill_use_at(QgsPointXY(80, 50))
        pump()
        self.assertTrue(right.ok, right.message)
        self.assertEqual(self.controller.missing_use_area(), 0.0)

    def test_fill_use_at_a_point_with_no_gap_says_so(self):
        self.start()
        self.build_plan(uses=(LEFT,))  # högra halvan (RIGHT) saknar fortfarande användning
        result = self.controller.fill_use_at(QgsPointXY(20, 50))  # men just här, i LEFT, finns redan en
        self.assertFalse(result.ok)
        self.assertIn("Klicka i den del", result.message)

    def test_fill_use_at_needs_a_plan_area_and_an_edit_session(self):
        for layer in self.layers.values():
            layer.rollBack()
        result = self.controller.fill_use_at(QgsPointXY(20, 50))
        self.assertIn("Börja rita", result.message)
        self.start()
        result = self.controller.fill_use_at(QgsPointXY(20, 50))
        self.assertIn("Rita planområdet först", result.message)

    def test_fill_property_fills_only_the_use_under_the_click(self):
        self.start()
        self.build_plan(uses=(LEFT, RIGHT))
        self.draw("egenskap_yta", INSIDE)
        result = self.controller.fill_property(QgsPointXY(20, 80))
        pump()
        self.assertTrue(result.ok, result.message)
        props = self.features("egenskap_yta")
        self.assertEqual(len(props), 2)
        big = [f for f in props if f.geometry().area() > 4000]
        self.assertEqual(len(big), 1)
        self.assertAlmostEqual(big[0].geometry().area(), 5000.0 - 900.0)  # användningen minus INSIDE (30 x 30)
        self.assertTrue(all(f.geometry().centroid().asPoint().x() < 50 for f in props), "högra användningen orörd")

    def test_fill_property_outside_any_use_or_when_full_reports_it(self):
        self.start()
        self.build_plan(uses=(LEFT,))
        miss = self.controller.fill_property(QgsPointXY(80, 50))
        self.assertFalse(miss.ok)
        self.assertIn("inne i ett användningsområde", miss.message)
        self.assertTrue(self.controller.fill_property(QgsPointXY(20, 50)).ok)
        pump()
        again = self.controller.fill_property(QgsPointXY(20, 50))
        self.assertFalse(again.ok)
        self.assertIn("inget att fylla", again.message)

    def test_fill_property_needs_a_use(self):
        self.start()
        self.draw("detaljplan", PLAN)
        self.assertIn("användningsyta först", self.controller.fill_property(QgsPointXY(20, 50)).message)


class HelperLineTests(ControllerCase):
    def test_helper_lines_can_be_drawn_without_a_plan_and_are_left_alone(self):
        self.controller.start_editing()
        self.assertTrue(self.controller.can_draw("hjalplinje")[0])
        f = self.add("hjalplinje", "MultiLineString(((500 500, 900 900)))")
        pump()
        self.assertTrue(self.layers["hjalplinje"].getFeature(f.id()).isValid(), "hjälplinjer beskärs inte")
        self.assertEqual(self.errors + self.warnings, [])
        self.assertEqual(self.controller.summary().unassigned, 0)

    def test_helper_lines_are_part_of_the_edit_session(self):
        for layer in self.layers.values():
            layer.rollBack()
        self.controller.start_editing()
        self.assertTrue(self.layers["hjalplinje"].isEditable())


class SelectionTests(ControllerCase):
    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.build_plan(uses=(LEFT,))
        self.prop = self.draw("egenskap_yta", INSIDE)
        self.helper = self.add("hjalplinje", "MultiLineString(((0 50, 100 50)))")

    def at(self, x, y, tables=None):
        args = (QgsPointXY(x, y), 0.5) + ((tables,) if tables else ())
        return self.controller.candidates_at(*args)

    def test_assigning_still_only_sees_use_and_property_areas(self):
        tables = [c.table for c in self.at(20, 20)]
        self.assertEqual(tables, ["egenskap_yta", "anvandning_yta"])

    def test_selecting_also_finds_the_plan_area_and_helper_lines_topmost_first(self):
        tables = [c.table for c in self.at(20, 50, self.controller.SELECTABLE)]
        self.assertEqual(tables, ["hjalplinje", "anvandning_yta", "detaljplan"])
        tables = [c.table for c in self.at(20, 20, self.controller.SELECTABLE)]
        self.assertEqual(tables, ["egenskap_yta", "anvandning_yta", "detaljplan"])

    def test_the_plan_area_is_selectable_where_no_use_covers_it(self):
        self.assertEqual([c.table for c in self.at(80, 20, self.controller.SELECTABLE)], ["detaljplan"])

    def test_the_choices_are_described_in_words(self):
        titles = [c.title for c in self.at(20, 50, self.controller.SELECTABLE)]
        self.assertTrue(titles[0].startswith("Hjälplinje · "), titles)
        self.assertTrue(titles[2].startswith("Planområde · "), titles)
        self.assertIn("m²", titles[2])

    def test_select_marks_exactly_that_area_in_its_layer(self):
        use = self.at(20, 60)[0]
        self.controller.select(use)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureIds(), [use.fid])
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 0)

    def test_a_new_selection_replaces_the_old_one_across_layers(self):
        self.controller.select(self.at(20, 60)[0])
        plan = self.at(80, 20, self.controller.SELECTABLE)[0]
        self.controller.select(plan)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 0)
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 1)

    def test_adding_keeps_the_earlier_selection(self):
        self.controller.select(self.at(20, 60)[0])
        self.controller.select(self.at(80, 20, self.controller.SELECTABLE)[0], add=True)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1)
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 1)

    def test_select_in_rect_finds_everything_it_touches_topmost_first(self):
        from qgis.core import QgsRectangle
        use_id = self.layers["anvandning_yta"].allFeatureIds()[0]
        plan_id = self.layers["detaljplan"].allFeatureIds()[0]
        found = self.controller.select_in_rect(QgsRectangle(-1, -1, 101, 101))
        self.assertEqual({(c.table, c.fid) for c in found},
                         {("hjalplinje", self.helper.id()), ("anvandning_yta", use_id),
                          ("egenskap_yta", self.prop.id()), ("detaljplan", plan_id)})
        self.assertEqual(self.layers["egenskap_yta"].selectedFeatureCount(), 1)
        self.assertEqual(self.layers["hjalplinje"].selectedFeatureCount(), 1)

    def test_select_in_rect_replaces_by_default_and_can_add_instead(self):
        from qgis.core import QgsRectangle
        self.controller.select_in_rect(QgsRectangle(0, 55, 100, 100))  # bara det som ligger norr om hjälplinjen
        self.assertEqual(self.layers["hjalplinje"].selectedFeatureCount(), 0)
        before = self.layers["anvandning_yta"].selectedFeatureCount()
        self.assertGreater(before, 0)
        self.controller.select_in_rect(QgsRectangle(0, 45, 100, 55), add=True)
        self.assertEqual(self.layers["hjalplinje"].selectedFeatureCount(), 1)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), before, "det som redan var markerat är kvar")
        self.controller.select_in_rect(QgsRectangle(60, 45, 100, 55))  # bara hjälplinjen ligger här (LEFT slutar vid x=50)
        self.assertEqual(self.layers["hjalplinje"].selectedFeatureCount(), 1)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 0, "utan add ersätts markeringen")

    def test_select_in_rect_with_nothing_there_returns_nothing_and_selects_nothing(self):
        from qgis.core import QgsRectangle
        self.assertEqual(self.controller.select_in_rect(QgsRectangle(900, 900, 910, 910)), [])
        self.assertEqual(sum(l.selectedFeatureCount() for l in self.layers.values() if l.isSpatial()), 0)

    def test_clear_selection_clears_every_plan_layer(self):
        self.controller.select(self.at(20, 60)[0])
        self.controller.select(self.at(80, 20, self.controller.SELECTABLE)[0], add=True)
        self.controller.clear_selection()
        self.assertEqual(sum(layer.selectedFeatureCount() for layer in self.layers.values() if layer.isSpatial()), 0)
