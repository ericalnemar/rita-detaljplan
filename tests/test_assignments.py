"""Tilldelning av bestämmelser till ytor (lägga till, ändra, ta bort, flera per yta) – kräver QGIS."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, LEFT, LINE_INSIDE, PLAN, RIGHT, PlanCase, filled, pick  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsProject, QgsVectorLayer
    from rita_detaljplan.core import assignments
    from rita_detaljplan.core import catalog as cat
    from rita_detaljplan.core.assignments import AssignmentError

UTNYTT = dict(layer="egenskap_yta", contains="byggnadsarea")


class AssignmentCase(PlanCase):
    def setUp(self):
        super().setUp()
        self.project = QgsProject.instance()

    def use(self, wkt=LEFT, form="Kvartersmark"):
        f = self.add("anvandning_yta", wkt)
        return self.layers["anvandning_yta"].getFeature(f.id())

    def prop(self, wkt=INSIDE, table="egenskap_yta"):
        f = self.add(table, wkt)
        return self.layers[table].getFeature(f.id())

    def assign(self, table, feature, entry, number="30", **kwargs):
        return assignments.add(self.project, table, feature.id(), entry, filled(entry, number), **kwargs)

    def area(self, table, feature):
        return self.layers[table].getFeature(feature.id())


class AddTests(AssignmentCase):
    def test_a_use_gets_its_label_colour_and_form_from_the_provision(self):
        use = self.use()
        entry = pick(self.catalog, "DP_KM_J2")
        row = self.assign("anvandning_yta", use, entry)
        area = self.area("anvandning_yta", use)
        self.assertEqual((area["beteckning"], area["farg"], area["anvandningsform"], area["bestammelser"]),
                         ("J", "Blågrå", "Kvartersmark", 1))
        self.assertEqual(row["yta"], use["objektidentitet"])
        stored = assignments.rows_of_area(self.project, "anvandning_yta", use.id())
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["planbestammelsekatalogreferens"], entry.id)
        self.assertEqual(stored[0]["tabell"], "anvandning_yta")

    def test_a_use_can_have_several_uses_and_writes_their_letters_together(self):
        use = self.use()
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        other = next(e for e in self.catalog.search(layer="anvandning_yta")
                     if e.anvandningsform == "Kvartersmark" and e.label_base == "B")
        self.assign("anvandning_yta", use, other)
        area = self.area("anvandning_yta", use)
        self.assertEqual(area["bestammelser"], 2)
        self.assertEqual(area["beteckning"], "JB")
        self.assertEqual(len(assignments.rows_of_area(self.project, "anvandning_yta", use.id())), 2)

    def test_a_property_area_can_have_several_properties_and_a_label_for_each(self):
        self.use()
        prop = self.prop()
        a = pick(self.catalog, **UTNYTT)
        b = pick(self.catalog, "DP_KM_Eg_VillkorLov_SkyddSakerhet_Bygglov")
        self.assign("egenskap_yta", prop, a)
        self.assign("egenskap_yta", prop, b)
        area = self.area("egenskap_yta", prop)
        self.assertEqual(area["bestammelser"], 2)
        self.assertEqual(area["beteckning"], "e1 a1")

    def test_the_same_provision_twice_on_one_area_is_refused(self):
        use = self.use()
        entry = pick(self.catalog, "DP_KM_J2")
        self.assign("anvandning_yta", use, entry)
        with self.assertRaises(AssignmentError) as caught:
            self.assign("anvandning_yta", use, entry)
        self.assertIn("redan den bestämmelsen", str(caught.exception))
        self.assertEqual(self.area("anvandning_yta", use)["bestammelser"], 1)

    def test_the_same_provision_on_two_areas_gets_the_same_label(self):
        a, b = self.use(LEFT), self.use(RIGHT)
        entry = pick(self.catalog, "DP_KM_R2_Motorsport")
        self.assign("anvandning_yta", a, entry)
        self.assign("anvandning_yta", b, entry)
        self.assertEqual(self.area("anvandning_yta", a)["beteckning"], self.area("anvandning_yta", b)["beteckning"])

    def test_a_provision_for_another_layer_is_refused(self):
        use = self.use()
        with self.assertRaises(AssignmentError):
            self.assign("anvandning_yta", use, pick(self.catalog, **UTNYTT))

    def test_a_use_cannot_be_two_different_forms_at_once(self):
        use = self.use()
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))  # kvartersmark
        street = pick(self.catalog, layer="anvandning_yta", form="Allmän plats", variables=False)
        with self.assertRaises(AssignmentError) as caught:
            self.assign("anvandning_yta", use, street)
        self.assertIn("kvartersmark", str(caught.exception))
        self.assertIn("allmän plats", str(caught.exception))

    def test_a_property_must_match_the_form_of_the_use_it_lies_on(self):
        use = self.use()
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))  # kvartersmark
        prop = self.prop()
        allman = pick(self.catalog, layer="egenskap_yta", form="Allmän plats", variables=False)
        with self.assertRaises(AssignmentError) as caught:
            self.assign("egenskap_yta", prop, allman)
        self.assertIn("allmän plats", str(caught.exception))
        self.assertEqual(self.area("egenskap_yta", prop)["bestammelser"], 0)

    def test_a_property_can_be_assigned_when_the_use_has_no_form_yet(self):
        self.use()
        prop = self.prop()
        self.assign("egenskap_yta", prop, pick(self.catalog, layer="egenskap_yta", form="Allmän plats", variables=False))
        self.assertEqual(self.area("egenskap_yta", prop)["bestammelser"], 1)

    def test_a_property_outside_the_uses_cannot_be_assigned(self):
        self.use(LEFT)
        prop = self.prop("MultiPolygon(((60 10, 90 10, 90 40, 60 40, 60 10)))")
        with self.assertRaises(AssignmentError) as caught:
            self.assign("egenskap_yta", prop, pick(self.catalog, **UTNYTT))
        self.assertIn("användningsyta", str(caught.exception))

    def test_a_line_gets_a_symbol_from_its_provision(self):
        self.use(LEFT)
        line = self.prop("MultiLineString(((0 50, 0 80)))", "egenskap_linje")
        entry = next(e for e in self.catalog.search(layer="egenskap_linje") if e.symbol.startswith("Utfart")
                     and not e.variables and e.anvandningsform == "Kvartersmark")
        self.assign("egenskap_linje", line, entry)
        area = self.area("egenskap_linje", line)
        self.assertEqual((area["symbol"], area["bestammelser"]), ("Utfart får inte finnas", 1))

    def test_rows_are_created_with_uuid_plan_link_and_version_time(self):
        use = self.use()
        self.add("detaljplan", PLAN)
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        row = assignments.rows_of_area(self.project, "anvandning_yta", use.id())[0]
        self.assertRegex(row["objektidentitet"], r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
        self.assertNotEqual(row["objektidentitet"], use["objektidentitet"], "bestämmelsen är ett eget objekt")
        self.assertTrue(row["versionGiltigFran"])

    def test_the_motive_and_a_custom_formulation_are_stored(self):
        use = self.use()
        prop = self.prop()
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        entry = pick(self.catalog, **UTNYTT)
        self.assign("egenskap_yta", prop, entry, motiv="Bevara innergården",
                    formulation="Byggnadsarean är högst [utnyttjandegrad:decimaltal] % av tomten.")
        row = assignments.rows_of_area(self.project, "egenskap_yta", prop.id())[0]
        self.assertEqual(row["motiv"], "Bevara innergården")
        self.assertTrue(row["avviker"])
        self.assertIn("av tomten", row["bestammelseformulering"])


class IdentityTests(AssignmentCase):
    def raw_area(self, table, wkt):
        """Ett objekt utan standardvärden, som när det läggs in utan ritverktyget (inklistrat, importerat, skript)."""
        from qgis.core import QgsFeature, QgsGeometry
        layer = self.layers[table]
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        layer.addFeature(feature)
        return layer.getFeature(feature.id())

    def test_areas_without_identity_get_one_and_do_not_share_provisions(self):
        a, b = self.raw_area("anvandning_yta", LEFT), self.raw_area("anvandning_yta", RIGHT)
        self.assertFalse(a["objektidentitet"] or b["objektidentitet"], "förutsättning: ingen identitet från början")
        self.assign("anvandning_yta", a, pick(self.catalog, "DP_KM_J2"))
        self.assign("anvandning_yta", b, pick(self.catalog, "DP_KM_R2_Motorsport"))
        self.assertEqual(self.area("anvandning_yta", a)["beteckning"], "J")
        self.assertEqual(self.area("anvandning_yta", b)["beteckning"], "R1")
        self.assertNotEqual(self.area("anvandning_yta", a)["objektidentitet"], self.area("anvandning_yta", b)["objektidentitet"])
        self.assertEqual(len(assignments.read_rows(self.project)), 2)

    def test_an_existing_identity_is_never_replaced(self):
        use = self.use()
        before = use["objektidentitet"]
        assignments.ensure_identity(self.layers["anvandning_yta"], use.id())
        self.assertEqual(self.area("anvandning_yta", use)["objektidentitet"], before)


class ChangeTests(AssignmentCase):
    def test_a_provision_can_be_replaced_and_the_label_follows(self):
        use = self.use()
        row = self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        new = pick(self.catalog, "DP_KM_R2_Motorsport")
        assignments.update(self.project, row["_fid"], new, filled(new))
        area = self.area("anvandning_yta", use)
        self.assertEqual((area["beteckning"], area["bestammelser"]), ("R1", 1))
        self.assertEqual(len(assignments.rows_of_area(self.project, "anvandning_yta", use.id())), 1)

    def test_changing_a_value_gives_a_new_number_only_if_it_is_a_different_provision(self):
        self.use()
        prop = self.prop()
        entry = pick(self.catalog, **UTNYTT)
        row = self.assign("egenskap_yta", prop, entry, number="30")
        assignments.update(self.project, row["_fid"], entry, filled(entry, "40"))
        self.assertEqual(self.area("egenskap_yta", prop)["beteckning"], "e1", "ingen annan yta har e1")

    def test_updating_to_the_same_provision_as_another_row_on_the_area_is_refused(self):
        use = self.use()
        a = self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        other = next(e for e in self.catalog.search(layer="anvandning_yta")
                     if e.anvandningsform == "Kvartersmark" and e.label_base == "B")
        b = self.assign("anvandning_yta", use, other)
        with self.assertRaises(AssignmentError):
            assignments.update(self.project, b["_fid"], pick(self.catalog, "DP_KM_J2"), [])
        self.assertEqual(self.area("anvandning_yta", use)["bestammelser"], 2)
        self.assertTrue(a["_fid"])

    def test_removing_a_provision_updates_the_area_and_removing_the_last_makes_it_unassigned(self):
        use = self.use()
        a = self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        b = self.assign("anvandning_yta", use, next(e for e in self.catalog.search(layer="anvandning_yta")
                                                    if e.anvandningsform == "Kvartersmark" and e.label_base == "B"))
        assignments.remove(self.project, a["_fid"])
        self.assertEqual(self.area("anvandning_yta", use)["beteckning"], "B")
        assignments.remove(self.project, b["_fid"])
        area = self.area("anvandning_yta", use)
        self.assertEqual(area["bestammelser"], 0)
        self.assertFalse(area["beteckning"])
        self.assertFalse(area["farg"])

    def test_removing_a_missing_row_does_nothing(self):
        assignments.remove(self.project, 999999)

    def test_rows_of_deleted_areas_are_removed(self):
        use = self.use()
        keep = self.use(RIGHT)
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        self.assign("anvandning_yta", keep, pick(self.catalog, "DP_KM_R2_Motorsport"))
        self.layers["anvandning_yta"].deleteFeature(use.id())
        self.assertEqual(assignments.remove_orphans(self.project), 1)
        remaining = assignments.read_rows(self.project)
        self.assertEqual([r["yta"] for r in remaining], [keep["objektidentitet"]])

    def test_refresh_all_repairs_the_summaries(self):
        use = self.use()
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        layer = self.layers["anvandning_yta"]
        layer.changeAttributeValue(use.id(), layer.fields().indexOf("beteckning"), "fel")
        assignments.refresh_all(self.project)
        self.assertEqual(layer.getFeature(use.id())["beteckning"], "J")


class ChoiceTests(AssignmentCase):
    def test_a_use_offers_all_uses_until_it_has_a_form(self):
        use = self.use()
        forms = {e.anvandningsform for e in assignments.entries_for(self.project, self.catalog, "anvandning_yta", use.id())}
        self.assertLessEqual({"Kvartersmark", "Allmän plats"}, forms)

    def test_a_use_with_a_provision_only_offers_the_same_form(self):
        use = self.use()
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        offered = assignments.entries_for(self.project, self.catalog, "anvandning_yta", use.id())
        self.assertTrue(offered)
        self.assertEqual({e.anvandningsform for e in offered}, {"Kvartersmark"})

    def test_a_property_only_offers_provisions_for_the_form_of_the_use_beneath(self):
        use = self.use()
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        prop = self.prop()
        offered = assignments.entries_for(self.project, self.catalog, "egenskap_yta", prop.id())
        self.assertTrue(offered)
        self.assertLessEqual({e.anvandningsform for e in offered}, {"Kvartersmark", "Planområdet"})
        self.assertTrue(all(e.layer_name == "egenskap_yta" for e in offered))

    def test_a_property_over_unassigned_uses_is_offered_everything(self):
        self.use()
        prop = self.prop()
        forms = {e.anvandningsform for e in assignments.entries_for(self.project, self.catalog, "egenskap_yta", prop.id())}
        self.assertLessEqual({"Kvartersmark", "Allmän plats"}, forms)

    def _street_and_block(self):
        street, block = self.use(LEFT), self.use(RIGHT)
        self.assign("anvandning_yta", street, pick(self.catalog, layer="anvandning_yta", form="Allmän plats",
                                                    variables=False))
        self.assign("anvandning_yta", block, pick(self.catalog, "DP_KM_J2"))

    def forms_offered(self, wkt):
        prop = self.prop(wkt)
        return {e.anvandningsform for e in assignments.entries_for(self.project, self.catalog, "egenskap_yta", prop.id())}

    def test_a_property_on_general_place_never_offers_provisions_for_private_land_and_vice_versa(self):
        self._street_and_block()
        on_street = self.forms_offered("MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))")
        on_block = self.forms_offered("MultiPolygon(((60 10, 90 10, 90 40, 60 40, 60 10)))")
        self.assertNotIn("Kvartersmark", on_street)
        self.assertIn("Allmän plats", on_street)
        self.assertNotIn("Allmän plats", on_block)
        self.assertIn("Kvartersmark", on_block)

    def test_a_neighbouring_use_that_only_shares_an_edge_does_not_widen_the_choice(self):
        self._street_and_block()
        forms = self.forms_offered("MultiPolygon(((10 10, 50 10, 50 40, 10 40, 10 10)))")  # i gatan, kant mot kvarteret
        self.assertNotIn("Kvartersmark", forms)

    def test_a_property_across_both_kinds_of_land_is_offered_both(self):
        self._street_and_block()
        forms = self.forms_offered("MultiPolygon(((40 10, 60 10, 60 40, 40 40, 40 10)))")
        self.assertLessEqual({"Kvartersmark", "Allmän plats"}, forms)

    def test_lines_only_offer_line_provisions(self):
        self.use()
        line = self.prop("MultiLineString(((20 20, 20 60)))", "egenskap_linje")
        offered = assignments.entries_for(self.project, self.catalog, "egenskap_linje", line.id())
        self.assertTrue(offered)
        self.assertTrue(all(e.layer_name == "egenskap_linje" for e in offered))


class PersistenceTests(AssignmentCase):
    def test_rows_and_area_summaries_survive_saving(self):
        use = self.use()
        self.add("detaljplan", PLAN)
        self.assign("anvandning_yta", use, pick(self.catalog, "DP_KM_J2"))
        for table in ("detaljplan", "anvandning_yta", "bestammelse"):
            layer = self.layers[table]
            self.assertTrue(layer.commitChanges(), layer.commitErrors())
        fresh_rows = QgsVectorLayer(f"{self.gpkg.as_posix()}|layername=bestammelse", "x", "ogr")
        fresh_use = QgsVectorLayer(f"{self.gpkg.as_posix()}|layername=anvandning_yta", "x", "ogr")
        self.assertEqual(fresh_rows.featureCount(), 1)
        self.assertEqual(next(fresh_use.getFeatures())["beteckning"], "J")
        row = next(fresh_rows.getFeatures())
        self.assertEqual(row["yta"], next(fresh_use.getFeatures())["objektidentitet"])


if __name__ == "__main__":
    unittest.main()
