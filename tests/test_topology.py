"""Topologikontroll: analys, genomförande, styrenhet, dialog och knapp (kräver QGIS)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, PLAN, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsGeometry, QgsPointXY, QgsProject
    from qgis.PyQt.QtCore import Qt
    from rita_detaljplan.core import topology as t
    from rita_detaljplan.gui.topology_dialog import TopologyDialog
    from qgis_app import get_app
    from test_toolbar import GuiCase


def geom(wkt):
    return QgsGeometry.fromWkt(wkt)


def poly(*points):
    ring = ", ".join(f"{x} {y}" for x, y in [*points, points[0]])
    return geom(f"MultiPolygon((({ring})))")


PLAN_G = poly((0, 0), (100, 0), (100, 100), (0, 100))


def kinds(changes):
    return [(c.kind, c.table, c.fid, c.old, c.new) for c in changes]


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def test_exact_geometries_need_no_changes(self):
        uses = [(1, poly((0, 0), (50, 0), (50, 100), (0, 100))), (2, poly((50, 0), (100, 0), (100, 100), (50, 100)))]
        self.assertEqual(t.analyze(PLAN_G, uses, []), [])

    def test_a_use_corner_near_a_plan_corner_is_moved_onto_it(self):
        use = poly((0.2, 0.15), (100, 0), (100, 100), (0, 100))
        (change,) = t.analyze(PLAN_G, [(1, use)], [])
        self.assertEqual((change.kind, change.old, change.new, change.reference), (t.SNAP_VERTEX, (0.2, 0.15), (0.0, 0.0),
                                                                                    "detaljplan"))
        self.assertAlmostEqual(change.distance, 0.25)
        self.assertIn("25 cm", change.text)

    def test_a_vertex_near_the_plan_boundary_but_not_a_plan_vertex_is_moved_onto_the_boundary(self):
        use = poly((0, 0), (100, 0), (100, 100), (0, 100), (0, 60), (0.3, 50))
        found = [c for c in t.analyze(PLAN_G, [(1, use)], []) if c.old == (0.3, 50)]
        self.assertEqual([(c.kind, c.new) for c in found], [(t.SNAP_EDGE, (0.0, 50.0))])
        self.assertIn("Stäng glapp", found[0].text)

    def test_differences_larger_than_the_tolerance_are_left_alone(self):
        use = poly((1.5, 1.5), (100, 0), (100, 100), (0, 100))
        self.assertEqual(t.analyze(PLAN_G, [(1, use)], []), [])
        self.assertEqual(len(t.analyze(PLAN_G, [(1, use)], [], tolerance=2.5)), 1)

    def test_the_plan_is_never_changed_and_never_a_target(self):
        for change in t.analyze(PLAN_G, [(1, poly((0.2, 0.15), (100, 0), (100, 100), (0, 100)))], []):
            self.assertIn(change.table, ("anvandning_yta", "egenskap_yta"))

    def test_a_plan_vertex_missing_from_the_use_is_added(self):
        plan = poly((0, 0), (100, 0), (100, 100), (50, 100.0), (0, 100))  # brytpunkt i mitten av överkanten
        use = poly((0, 0), (100, 0), (100, 100), (0, 100))
        added = [c for c in t.analyze(plan, [(1, use)], []) if c.kind == t.ADD_VERTEX]
        self.assertEqual([(c.new, c.old) for c in added], [((50.0, 100.0), None)])
        self.assertIn("Lägg till", added[0].text)

    def test_no_vertex_is_added_where_the_use_already_has_one_nearby(self):
        plan = poly((0, 0), (100, 0), (100, 100), (50, 100), (0, 100))
        use = poly((0, 0), (100, 0), (100, 100), (50.2, 100), (0, 100))
        kinds_found = [c.kind for c in t.analyze(plan, [(1, use)], [])]
        self.assertEqual(kinds_found, [t.SNAP_VERTEX], "flyttas i stället för att få en ny")

    def test_a_gap_between_two_uses_is_closed_by_moving_the_later_one_only(self):
        first = poly((0, 0), (50, 0), (50, 100), (0, 100))
        second = poly((50.3, 0), (100, 0), (100, 100), (50.3, 100))
        found = t.analyze(PLAN_G, [(1, first), (2, second)], [])
        self.assertEqual({(c.fid, c.reference) for c in found}, {(2, "anvandning_yta")})
        self.assertEqual({c.new for c in found}, {(50.0, 0.0), (50.0, 100.0)})
        self.assertTrue(all(c.table == "anvandning_yta" for c in found))

    def test_a_property_corner_near_a_use_corner_snaps_to_the_use(self):
        use = poly((0, 0), (100, 0), (100, 100), (0, 100))
        prop = poly((0.2, 10), (40, 10), (40, 40), (0.2, 40))
        found = [c for c in t.analyze(PLAN_G, [(1, use)], [(7, prop)]) if c.table == "egenskap_yta"]
        self.assertEqual({(c.fid, c.new) for c in found}, {(7, (0.0, 10.0)), (7, (0.0, 40.0))})
        self.assertTrue(all(c.kind == t.SNAP_EDGE for c in found))

    def test_holes_are_checked_too(self):
        use = geom("MultiPolygon(((0 0, 100 0, 100 100, 0 100, 0 0), (20 20, 20 80, 80 80, 80 20, 20 20)))")
        plan = geom("MultiPolygon(((0 0, 100 0, 100 100, 0 100, 0 0), (20.2 20, 20.2 80, 80 80, 80 20, 20.2 20)))")
        found = t.analyze(plan, [(1, use)], [])
        self.assertTrue(found)
        self.assertTrue(all(c.reference == "detaljplan" for c in found))

    def test_everything_works_without_a_plan_or_without_uses(self):
        self.assertEqual(t.analyze(None, [(1, PLAN_G)], []), [])
        self.assertEqual(t.analyze(PLAN_G, [], []), [])
        self.assertEqual(t.analyze(PLAN_G, [(1, QgsGeometry())], []), [])

    def test_a_tiny_plan_uses_the_given_tolerance(self):
        plan = poly((0, 0), (1, 0), (1, 1), (0, 1))
        use = poly((0.02, 0.01), (1, 0), (1, 1), (0, 1))
        self.assertEqual(t.analyze(plan, [(1, use)], [], tolerance=0.05)[0].new, (0.0, 0.0))
        self.assertEqual(t.analyze(plan, [(1, use)], [], tolerance=0.005), [])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def test_moves_and_insertions_are_carried_out(self):
        use = poly((0.2, 0.15), (100, 0), (100, 100), (0, 100))
        changes = t.analyze(PLAN_G, [(1, use)], [])
        result, done, skipped = t.apply_to_geometry(use, changes)
        self.assertEqual((done, skipped), (1, 0))
        self.assertTrue(result.equals(PLAN_G) or abs(result.area() - 10000.0) < 1e-6)

    def test_a_vertex_is_added_on_the_right_segment(self):
        plan = poly((0, 0), (100, 0), (100, 100), (50, 100), (0, 100))
        use = poly((0, 0), (100, 0), (100, 100), (0, 100))
        added = [c for c in t.analyze(plan, [(1, use)], []) if c.kind == t.ADD_VERTEX]
        result, done, _ = t.apply_to_geometry(use, added)
        self.assertEqual(done, 1)
        self.assertIn((50.0, 100.0), [(round(p.x(), 6), round(p.y(), 6)) for p in t.vertices(result)])
        self.assertAlmostEqual(result.area(), 10000.0)

    def test_the_order_of_the_changes_does_not_matter(self):
        use = poly((0.2, 0.15), (100.1, 0), (100, 100.2), (0.1, 99.8))
        changes = t.analyze(PLAN_G, [(1, use)], [])
        forward, _, _ = t.apply_to_geometry(use, changes)
        backward, _, _ = t.apply_to_geometry(use, list(reversed(changes)))
        self.assertTrue(forward.equals(backward))
        self.assertAlmostEqual(forward.area(), 10000.0)

    def test_a_change_that_would_make_the_boundary_cross_itself_is_skipped(self):
        square = poly((0, 0), (10, 0), (10, 10), (0, 10))
        bad = t.Change(t.SNAP_VERTEX, "anvandning_yta", 1, (10.0, 10.0), (0.0, -1.0), 1.0, "detaljplan")
        result, done, skipped = t.apply_to_geometry(square, [bad])
        self.assertEqual((done, skipped), (0, 1))
        self.assertTrue(result.equals(square), "geometrin är oförändrad")

    def test_a_change_for_a_vertex_that_is_gone_is_skipped(self):
        square = poly((0, 0), (10, 0), (10, 10), (0, 10))
        gone = t.Change(t.SNAP_VERTEX, "anvandning_yta", 1, (33.0, 33.0), (0.0, 0.0), 0.1, "detaljplan")
        self.assertEqual(t.apply_to_geometry(square, [gone])[1:], (0, 1))

    def test_the_input_geometry_is_not_changed(self):
        use = poly((0.2, 0.15), (100, 0), (100, 100), (0, 100))
        before = use.asWkt()
        t.apply_to_geometry(use, t.analyze(PLAN_G, [(1, use)], []))
        self.assertEqual(use.asWkt(), before)


class TopologyCase(GuiCase):
    """En plan där användningsytorna ligger några decimeter fel: brytpunkter och ett glapp vid mitten."""

    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.draw("detaljplan", PLAN)
        # ritas via lagret direkt: styrenheten skulle annars beskära dem mot planområdet
        self.left = self.draw("anvandning_yta", "MultiPolygon(((0.2 0.15, 50 0, 50 100, 0.1 99.8, 0.2 0.15)))")
        self.right = self.draw("anvandning_yta", "MultiPolygon(((50.3 0, 99.9 0, 99.9 99.9, 50.25 100, 50.3 0)))")

    def area(self, table="anvandning_yta"):
        return sum(f.geometry().area() for f in self.layers[table].getFeatures())


class ControllerTests(TopologyCase):
    def test_the_controller_analyses_the_real_layers(self):
        changes = self.controller.topology_changes()
        self.assertTrue(changes)
        self.assertEqual({c.table for c in changes}, {"anvandning_yta"})
        self.assertEqual(self.controller.topology_changes(tolerance=0.01), [])

    def test_analysing_changes_nothing(self):
        before = [f.geometry().asWkt() for f in self.layers["anvandning_yta"].getFeatures()]
        self.controller.topology_changes()
        self.assertEqual([f.geometry().asWkt() for f in self.layers["anvandning_yta"].getFeatures()], before)

    def test_applying_all_changes_makes_the_uses_match_the_plan_and_each_other(self):
        changes = self.controller.topology_changes()
        done, skipped = self.controller.apply_topology(changes)
        self.assertEqual((done, skipped), (len(changes), 0))
        pump()
        self.assertEqual(self.controller.topology_changes(), [], "inga fler förslag efteråt")
        self.assertAlmostEqual(self.area(), 10000.0, delta=0.5)
        left = next(f for f in self.layers["anvandning_yta"].getFeatures() if f["objektidentitet"] == self.left["objektidentitet"])
        self.assertIn((0.0, 0.0), [(p.x(), p.y()) for p in t.vertices(left.geometry())])

    def test_only_the_chosen_changes_are_made(self):
        changes = self.controller.topology_changes()
        chosen = [changes[0]]
        done, _ = self.controller.apply_topology(chosen)
        self.assertEqual(done, 1)
        self.assertEqual(len(self.controller.topology_changes()), len(changes) - 1)

    def test_the_changes_can_be_undone_in_one_step_per_layer(self):
        wkts = [f.geometry().asWkt() for f in self.layers["anvandning_yta"].getFeatures()]
        self.controller.apply_topology(self.controller.topology_changes())
        self.layers["anvandning_yta"].undoStack().undo()
        self.assertEqual(sorted(f.geometry().asWkt() for f in self.layers["anvandning_yta"].getFeatures()), sorted(wkts))

    def test_applying_starts_editing_of_the_layer_when_needed(self):
        self.controller.stop_editing(save=True)
        self.assertFalse(self.layers["anvandning_yta"].isEditable())
        changes = self.controller.topology_changes()
        self.assertTrue(changes)
        done, _ = self.controller.apply_topology(changes)
        self.assertGreater(done, 0)
        self.assertTrue(self.layers["anvandning_yta"].isEditable())

    def test_changes_for_areas_that_no_longer_exist_are_skipped(self):
        ghost = t.Change(t.SNAP_VERTEX, "anvandning_yta", 987654, (0.2, 0.15), (0.0, 0.0), 0.25, "detaljplan")
        self.assertEqual(self.controller.apply_topology([ghost]), (0, 1))

    def test_the_areas_keep_their_provisions_and_identity(self):
        from plan_case import filled, pick
        entry = pick(self.catalog, "DP_KM_J2")
        self.controller.add_bestammelse("anvandning_yta", self.left.id(), entry, filled(entry))
        identity = self.layers["anvandning_yta"].getFeature(self.left.id())["objektidentitet"]
        self.controller.apply_topology(self.controller.topology_changes())
        kept = next(f for f in self.layers["anvandning_yta"].getFeatures() if f["objektidentitet"] == identity)
        self.assertEqual(kept["bestammelser"], 1)


X0, Y0 = 140000.0, 6580000.0  # riktiga SWEREF-koordinater: stora tal ska inte ge avrundningsproblem


def big(*points):
    ring = ", ".join(f"{X0 + x:.4f} {Y0 + y:.4f}" for x, y in [*points, points[0]])
    return f"MultiPolygon((({ring})))"


class RealisticTests(GuiCase):
    """Ytor som ritats i verkliga koordinater med några centimeters fel, både osparade och sparade."""

    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.draw("detaljplan", big((0, 0), (100, 0), (100, 100), (0, 100)))
        self.first = self.draw("anvandning_yta", big((0, 0), (50, 0), (50, 100), (0, 100)))
        self.second = self.draw("anvandning_yta", big((50.15, 0.04), (100, 0), (100, 100), (50.2, 99.9)))
        self.third = self.draw("egenskap_yta", big((10.2, 10), (40, 10), (40, 40), (10.2, 40)))

    def wkt(self, fid, table="anvandning_yta"):
        return self.layers[table].getFeature(fid).geometry().asWkt(3)

    def test_the_first_drawn_area_is_the_one_the_others_adapt_to(self):
        changes = self.controller.topology_changes()
        self.assertEqual({c.fid for c in changes if c.table == "anvandning_yta"}, {self.second.id()},
                         "bara den senast ritade användningsytan flyttas")
        self.assertTrue(all(c.reference in ("detaljplan", "anvandning_yta") for c in changes))

    def test_the_gap_is_closed_towards_the_first_area(self):
        before = self.wkt(self.first.id())
        self.controller.apply_topology([c for c in self.controller.topology_changes() if c.table == "anvandning_yta"])
        self.assertEqual(self.wkt(self.first.id()), before, "den först ritade ytan är oförändrad")
        second = self.layers["anvandning_yta"].getFeature(self.second.id()).geometry()
        points = {(round(p.x() - X0, 3), round(p.y() - Y0, 3)) for p in t.vertices(second)}
        self.assertLessEqual({(50.0, 0.0), (50.0, 100.0)}, points)

    def test_after_applying_everything_no_more_suggestions_remain(self):
        changes = self.controller.topology_changes()
        self.assertGreater(len(changes), 0)
        self.controller.apply_topology(changes)
        self.assertEqual(self.controller.topology_changes(), [], "kontrollen är stabil: ingen fram och tillbaka")

    def test_the_result_is_the_same_before_and_after_saving(self):
        unsaved = [(c.kind, c.table, c.old, c.new) for c in self.controller.topology_changes()]
        self.assertEqual(self.controller.stop_editing(save=True), [])
        saved = [(c.kind, c.table, c.old, c.new) for c in self.controller.topology_changes()]
        self.assertEqual(sorted(saved), sorted(unsaved))
        self.controller.apply_topology(self.controller.topology_changes())
        self.assertEqual(self.controller.topology_changes(), [])

    def test_the_uses_share_their_edge_without_gap_or_overlap_afterwards(self):
        self.controller.apply_topology(self.controller.topology_changes())
        uses = [f.geometry() for f in self.layers["anvandning_yta"].getFeatures()]
        union = QgsGeometry.unaryUnion(uses)
        self.assertAlmostEqual(union.area(), 10000.0, delta=0.5)
        self.assertLess(uses[0].intersection(uses[1]).area(), 0.5)

    def test_three_areas_in_a_row_all_end_up_consistent(self):
        self.layers["anvandning_yta"].selectAll()
        self.layers["anvandning_yta"].deleteSelectedFeatures()
        self.layers["egenskap_yta"].selectAll()
        self.layers["egenskap_yta"].deleteSelectedFeatures()
        self.draw("anvandning_yta", big((0, 0), (33, 0), (33, 100), (0, 100)))
        self.draw("anvandning_yta", big((33.1, 0.1), (66, 0), (66.2, 100), (33.05, 100)))
        self.draw("anvandning_yta", big((66.3, 0), (100, 0.2), (99.9, 100), (66.1, 99.95)))
        self.assertTrue(self.controller.topology_changes())
        done, skipped = self.controller.apply_topology(self.controller.topology_changes())
        self.assertGreater(done, 0)
        self.assertEqual(skipped, 0)
        self.assertEqual(self.controller.topology_changes(), [])
        self.assertAlmostEqual(sum(f.geometry().area() for f in self.layers["anvandning_yta"].getFeatures()), 10000.0,
                               delta=1.0)


class DialogTests(TopologyCase):
    def make(self, changes=None, apply=None, show=None):
        provided = changes if changes is not None else self.controller.topology_changes()
        self.analyses = []

        def analyze(tolerance):
            self.analyses.append(tolerance)
            return list(provided)

        dialog = TopologyDialog(analyze, apply or self.controller.apply_topology, show)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_every_suggestion_is_listed_and_ticked_by_default(self):
        dialog = self.make()
        self.assertEqual(dialog.list.count(), len(dialog.changes))
        self.assertTrue(dialog.list.count() >= 5)
        self.assertTrue(all(dialog.list.item(i).checkState() == Qt.CheckState.Checked for i in range(dialog.list.count())))
        self.assertIn("förslag", dialog.summary.text())
        self.assertIn("Användningsområde: ", dialog.list.item(0).text())
        self.assertIn(f"({dialog.list.count()})", dialog.btn_apply.text())

    def test_unticked_suggestions_are_not_made(self):
        dialog = self.make()
        dialog.list.item(0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(len(dialog.checked()), dialog.list.count() - 1)
        self.assertNotIn(dialog.changes[0], dialog.checked())
        applied = []
        dialog._apply = lambda changes: applied.append(changes) or (len(changes), 0)
        dialog.apply_checked()
        self.assertEqual(len(applied[0]), len(dialog.changes) - 1)

    def test_select_all_and_none(self):
        dialog = self.make()
        dialog.btn_none.click()
        self.assertEqual(dialog.checked(), [])
        self.assertFalse(dialog.btn_apply.isEnabled())
        dialog.btn_all.click()
        self.assertEqual(len(dialog.checked()), dialog.list.count())
        self.assertTrue(dialog.btn_apply.isEnabled())

    def test_applying_changes_the_layer_and_re_analyses(self):
        analyses = []
        real = self.controller.topology_changes
        dialog = TopologyDialog(lambda tol: analyses.append(tol) or real(tol), self.controller.apply_topology)
        self.addCleanup(dialog.deleteLater)
        self.assertGreater(dialog.list.count(), 0)
        done, skipped = dialog.apply_checked()
        self.assertGreater(done, 0)
        self.assertEqual(skipped, 0)
        self.assertEqual(dialog.list.count(), 0)
        self.assertIn("Inga förslag", dialog.summary.text())
        self.assertIn(f"{done} ändringar gjordes", dialog.result.text())
        self.assertEqual(len(analyses), 2, "analyserades om efteråt")
        self.assertFalse(dialog.btn_apply.isEnabled())

    def test_skipped_changes_are_explained(self):
        dialog = self.make(apply=lambda changes: (2, 3))
        dialog.apply_checked()
        self.assertIn("3 hoppades över", dialog.result.text())

    def test_nothing_ticked_means_nothing_is_done(self):
        dialog = self.make(apply=mock.Mock(side_effect=AssertionError("ska inte anropas")))
        dialog.btn_none.click()
        self.assertEqual(dialog.apply_checked(), (0, 0))

    def test_the_tolerance_is_passed_on_and_changing_it_re_analyses(self):
        dialog = self.make()
        self.assertEqual(self.analyses, [t.DEFAULT_TOLERANCE])
        dialog.tolerance.setValue(1.25)
        dialog.btn_again.click()
        self.assertEqual(self.analyses[-1], 1.25)

    def test_show_calls_back_with_the_selected_suggestion(self):
        shown = []
        dialog = self.make(show=shown.append)
        self.assertFalse(dialog.btn_show.isEnabled())
        dialog.list.setCurrentRow(1)
        self.assertTrue(dialog.btn_show.isEnabled())
        dialog.btn_show.click()
        self.assertEqual(shown, [dialog.changes[1]])

    def test_an_empty_result_says_the_boundaries_agree(self):
        dialog = self.make(changes=[])
        self.assertEqual(dialog.summary.text(), "Inga förslag: gränserna stämmer överens.")
        self.assertEqual(dialog.list.count(), 0)
        self.assertFalse(dialog.btn_all.isEnabled())


class ToolBarTests(TopologyCase):
    def setUp(self):
        super().setUp()
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)

    def test_there_is_no_topology_button_for_now(self):
        self.assertFalse(hasattr(self.toolbar, "act_topology"))
        self.assertFalse(any("opolog" in a.text() or "opolog" in a.toolTip() for a in self.toolbar.actions()))

    def test_the_check_can_still_be_opened_from_code_with_the_controllers_analysis_and_apply(self):
        with mock.patch("rita_detaljplan.gui.plan_toolbar.TopologyDialog") as dialog_cls:
            self.toolbar.check_topology()
        analyze, apply, show = dialog_cls.call_args.args[:3]
        self.assertTrue(analyze(0.5))
        dialog_cls.return_value.exec.assert_called_once()
        self.assertEqual(self.controller.stop_editing(save=True), [])
        done, _ = apply(analyze(0.5))
        self.assertGreater(done, 0)
        self.assertTrue(self.controller.editing, "redigeringen startades av ändringen")

    def test_showing_a_suggestion_selects_and_zooms_to_the_area(self):
        change = self.controller.topology_changes()[0]
        self.toolbar._show_change(change)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1)
        self.iface.setActiveLayer.assert_called_with(self.layers["anvandning_yta"])


if __name__ == "__main__":
    unittest.main()
