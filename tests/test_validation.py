"""Validering av planen mot Lantmäteriets regler (kräver QGIS)."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, LEFT, PLAN, RIGHT, PlanCase, filled, pick, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsGeometry, QgsPointXY, QgsProject
    from qgis.PyQt.QtCore import Qt
    from rita_detaljplan.core import bestammelse as bm
    from rita_detaljplan.core import validation as v
    from rita_detaljplan.core.validation import Area, Issue, PlanData
    from rita_detaljplan.gui.validation_dialog import ValidationDialog
    from test_toolbar import GuiCase

GOOD_PLAN = {"kommun": "Eskilstuna", "namn": "Kv Väktaren", "syfte": "Bostäder", "status": "påbörjad",
             "typ": "detaljplan", "lagesmetodTyp": "lägesplacering", "tidpunktForLagesbestamning": "2026-01-01",
             "digitaliseringsniva": "komplett", "anvandbarhet": "god"}


def area(table, wkt, identity=None, fid=1, **attrs):
    return Area(table, fid, identity or f"{table}-{fid}", QgsGeometry.fromWkt(wkt), attrs)


def form_row(table, identity, form="Kvartersmark", **extra):
    return {"tabell": table, "yta": identity, "anvandningsform": form, "bestammelsekod": "X",
            "digitaliseringsniva": "komplett", "anvandbarhet": "god", **extra}


def plan_data(uses=(LEFT, RIGHT), plan=PLAN, plan_attrs=None, extra_areas=(), rows=None, beslut=(), dokument=(),
              meta_kommun="Eskilstuna"):
    data = PlanData(plan=area("detaljplan", plan, "plan", 1, **(plan_attrs or GOOD_PLAN)), meta_kommun=meta_kommun)
    for i, wkt in enumerate(uses, start=1):
        data.areas.append(area("anvandning_yta", wkt, f"use{i}", i))
    data.areas.extend(extra_areas)
    data.rows = rows if rows is not None else [form_row("anvandning_yta", a.identity) for a in data.areas]
    data.beslut, data.dokument = list(beslut), list(dokument)
    return data


def texts(issues, severity=None, code=None):
    return [i.text for i in issues if (severity is None or i.severity == severity) and (code is None or i.code == code)]


def sq(x0, y0, x1, y1):
    return f"MultiPolygon((({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0})))"


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class GeometryRules(unittest.TestCase):
    def test_a_complete_plan_has_no_geometry_issues(self):
        self.assertEqual(v.check_geometry(plan_data()), [])

    def test_a_plan_without_use_stops_on_dp_0002(self):
        issues = v.check_geometry(plan_data(uses=()))
        self.assertEqual([(i.severity, i.code) for i in issues], [("fel", "DP-0002")])

    def test_uncovered_plan_area_is_reported_with_its_size(self):
        issues = v.check_geometry(plan_data(uses=(LEFT,)))
        self.assertEqual([i.code for i in issues], ["DP-0002"])
        self.assertIn("5 000.0 m²", issues[0].text)
        self.assertEqual(issues[0].table, "detaljplan")

    def test_ten_centimetres_are_tolerated_but_half_a_metre_is_not(self):
        self.assertEqual(v.check_geometry(plan_data(uses=(sq(0, 0, 50, 100), sq(50, 0, 99.95, 100)))), [])
        short = v.check_geometry(plan_data(uses=(sq(0, 0, 50, 100), sq(50, 0, 99.5, 100))))
        self.assertEqual(len(texts(short, code="DP-0002")), 1)

    def test_use_outside_the_plan_stops_on_dp_0003(self):
        data = plan_data(uses=(sq(0, 0, 100, 100), sq(90, 90, 130, 130)))
        issues = [i for i in v.check_geometry(data) if i.code == "DP-0003"]
        self.assertEqual(len(issues), 1)
        self.assertEqual((issues[0].table, issues[0].fid), ("anvandning_yta", 2))

    def test_overlapping_uses_stop_unless_the_overlap_is_small(self):
        big = v.check_geometry(plan_data(uses=(sq(0, 0, 60, 100), sq(50, 0, 100, 100))))
        self.assertTrue(any(i.severity == "fel" and i.code == "DP-Krav-0013" for i in big), big)
        small = v.check_geometry(plan_data(uses=(sq(0, 0, 50.02, 100), sq(50, 0, 100, 100))))
        found = [i for i in small if i.code == "DP-Krav-0013"]
        self.assertEqual([i.severity for i in found], ["varning"])

    def test_small_gaps_between_uses_warn_with_the_limit_of_the_plans_age(self):
        gap = (sq(0, 0, 49.7, 100), sq(50, 0, 100, 100))  # 30 cm glapp
        issues = v.check_geometry(plan_data(uses=gap))
        self.assertIn("DP-Krav-0011", [i.code for i in issues if i.severity == "varning"])
        wide = (sq(0, 0, 48.5, 100), sq(50, 0, 100, 100))  # 1,5 m glapp
        self.assertNotIn("DP-Krav-0011", [i.code for i in v.check_geometry(plan_data(uses=wide))])
        old = plan_data(uses=wide, beslut=[{"datumPaborjat": "2019-05-01"}])
        self.assertIn("DP-Krav-0012", [i.code for i in v.check_geometry(old)])

    def test_touching_uses_are_not_a_gap(self):
        self.assertNotIn("DP-Krav-0011", [i.code for i in v.check_geometry(plan_data())])

    def test_an_abnormally_narrow_area_warns(self):
        narrow = area("egenskap_yta", sq(10, 10, 60, 10.3), "narrow", 5)
        issues = v.check_geometry(plan_data(extra_areas=[narrow]))
        self.assertIn(("varning", "DP-Krav-0014"), [(i.severity, i.code) for i in issues])
        wide = area("egenskap_yta", sq(10, 10, 60, 12), "wide", 5)
        self.assertNotIn("DP-Krav-0014", [i.code for i in v.check_geometry(plan_data(extra_areas=[wide]))])

    def test_a_self_crossing_boundary_stops_on_dp_krav_0018(self):
        bowtie = area("egenskap_yta", "MultiPolygon(((10 10, 50 50, 50 10, 10 50, 10 10)))", "bow", 5)
        issues = [i for i in v.check_geometry(plan_data(extra_areas=[bowtie])) if i.code == "DP-Krav-0018"]
        self.assertEqual([(i.severity, i.table) for i in issues], [("fel", "egenskap_yta")])
        loop = area("egenskap_linje", "MultiLineString((( 10 10, 50 50, 50 10, 10 50)))", "loop", 6)
        self.assertTrue([i for i in v.check_geometry(plan_data(extra_areas=[loop])) if i.code == "DP-Krav-0018"])
        fine = area("egenskap_linje", "MultiLineString((( 10 10, 50 50)))", "fine", 6)
        self.assertFalse([i for i in v.check_geometry(plan_data(extra_areas=[fine])) if i.code == "DP-Krav-0018"])

    def test_a_property_must_lie_within_the_uses(self):
        outside = area("egenskap_yta", sq(90, 90, 130, 130), "p", 5)
        issues = [i for i in v.check_geometry(plan_data(extra_areas=[outside])) if i.table == "egenskap_yta"]
        self.assertEqual([i.severity for i in issues], ["fel"])
        inside = area("egenskap_yta", INSIDE, "p", 5)
        self.assertEqual([i for i in v.check_geometry(plan_data(extra_areas=[inside])) if i.table == "egenskap_yta"], [])

    def test_a_property_line_must_lie_on_a_use(self):
        off = area("egenskap_linje", "MultiLineString((( 200 200, 300 300)))", "l", 6)
        self.assertEqual([i.severity for i in v.check_geometry(plan_data(extra_areas=[off])) if i.table == "egenskap_linje"],
                         ["fel"])
        on = area("egenskap_linje", "MultiLineString((( 20 20, 20 60)))", "l", 6)
        self.assertEqual([i for i in v.check_geometry(plan_data(extra_areas=[on])) if i.table == "egenskap_linje"], [])

    def test_small_property_overlaps_warn_but_large_ones_are_allowed(self):
        a = area("egenskap_yta", sq(10, 10, 30, 30), "a", 5)
        b = area("egenskap_yta", sq(29.9, 10, 50, 30), "b", 6)
        c = area("egenskap_yta", sq(20, 10, 50, 30), "c", 7)
        self.assertIn("DP-Krav-0013", [i.code for i in v.check_geometry(plan_data(extra_areas=[a, b]))])
        self.assertNotIn("DP-Krav-0013", [i.code for i in v.check_geometry(plan_data(extra_areas=[a, c]))])

    def test_an_empty_geometry_is_reported(self):
        empty = Area("egenskap_yta", 9, "e", QgsGeometry(), {})
        self.assertTrue([i for i in v.check_geometry(plan_data(extra_areas=[empty])) if "geometri" in i.text])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class HierarchyRules(unittest.TestCase):
    def test_areas_without_provisions_are_errors(self):
        data = plan_data(rows=[])
        issues = v.check_hierarchy(data)
        self.assertEqual(len(issues), 2)
        self.assertTrue(all(i.severity == "fel" and "Saknar bestämmelse" in i.text for i in issues))

    def test_a_use_cannot_have_two_forms(self):
        rows = [form_row("anvandning_yta", "use1", "Kvartersmark"), form_row("anvandning_yta", "use1", "Allmän plats"),
                form_row("anvandning_yta", "use2")]
        issues = v.check_hierarchy(plan_data(rows=rows))
        self.assertEqual(len(issues), 1)
        self.assertIn("allmän plats och kvartersmark", issues[0].text)

    def prop_data(self, form, use_forms=("Kvartersmark", "Allmän plats")):
        prop = area("egenskap_yta", sq(10, 10, 30, 30) if use_forms[0] else sq(60, 10, 80, 30), "prop", 5)
        rows = [form_row("anvandning_yta", "use1", use_forms[0]), form_row("anvandning_yta", "use2", use_forms[1]),
                form_row("egenskap_yta", "prop", form)]
        return plan_data(extra_areas=[prop], rows=rows)

    def test_a_property_must_match_the_form_of_the_use_it_lies_on(self):
        issues = v.check_hierarchy(self.prop_data("Allmän plats"))
        self.assertEqual(len(issues), 1)
        self.assertIn("allmän plats", issues[0].text)
        self.assertEqual(issues[0].table, "egenskap_yta")
        self.assertEqual(v.check_hierarchy(self.prop_data("Kvartersmark")), [])

    def test_plan_area_provisions_fit_any_use(self):
        self.assertEqual(v.check_hierarchy(self.prop_data("Planområdet")), [])

    def test_a_neighbour_that_only_shares_an_edge_does_not_count(self):
        prop = area("egenskap_yta", sq(10, 10, 50, 30), "prop", 5)  # i vänstra användningen, kant mot högra
        rows = [form_row("anvandning_yta", "use1", "Allmän plats"), form_row("anvandning_yta", "use2", "Kvartersmark"),
                form_row("egenskap_yta", "prop", "Allmän plats")]
        self.assertEqual(v.check_hierarchy(plan_data(extra_areas=[prop], rows=rows)), [])

    def test_a_property_over_a_use_without_form_is_not_judged(self):
        prop = area("egenskap_yta", sq(10, 10, 30, 30), "prop", 5)
        rows = [{"tabell": "anvandning_yta", "yta": "use1"}, form_row("anvandning_yta", "use2"),
                form_row("egenskap_yta", "prop", "Allmän plats")]
        self.assertEqual(v.check_hierarchy(plan_data(extra_areas=[prop], rows=rows)), [])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PlanRules(unittest.TestCase):
    def test_a_complete_plan_passes(self):
        issues = v.check_plan(plan_data(beslut=[{"datumPaborjat": "2023-02-01"}]))
        self.assertEqual(issues, [])

    def test_missing_plan_area(self):
        issues = v.check_plan(PlanData())
        self.assertEqual([(i.severity, i.code) for i in issues], [("fel", "DP-0002")])

    def test_every_required_field_is_reported_by_name(self):
        for name, label in (("kommun", "Kommun"), ("namn", "Namn"), ("syfte", "Syfte"), ("status", "Status"),
                            ("typ", "Plantyp")):
            data = plan_data(plan_attrs={**GOOD_PLAN, name: None}, beslut=[{"datumPaborjat": "2023-02-01"}])
            found = [i for i in v.check_plan(data) if i.severity == "fel"]
            self.assertTrue(any(label in i.text for i in found), (name, found))

    def test_the_municipality_must_exist_and_match_the_one_the_plan_was_made_for(self):
        data = plan_data(plan_attrs={**GOOD_PLAN, "kommun": "Atlantis"}, beslut=[{"datumPaborjat": "2023-02-01"}])
        self.assertTrue(any("finns inte" in i.text for i in v.check_plan(data)))
        other = plan_data(plan_attrs={**GOOD_PLAN, "kommun": "Göteborg"}, beslut=[{"datumPaborjat": "2023-02-01"}])
        self.assertTrue(any("stämmer inte" in i.text for i in v.check_plan(other)))
        same = plan_data(plan_attrs={**GOOD_PLAN, "kommun": "eskilstuna"}, beslut=[{"datumPaborjat": "2023-02-01"}])
        self.assertEqual(v.check_plan(same), [])

    def test_new_plans_need_a_start_date_position_method_and_time(self):
        data = plan_data(plan_attrs={**GOOD_PLAN, "lagesmetodTyp": None, "tidpunktForLagesbestamning": None})
        found = v.check_plan(data)
        self.assertEqual(sorted(i.severity for i in found), ["fel", "fel", "varning"])
        self.assertTrue(any("Datum påbörjat" in i.text for i in found))

    def test_a_plan_started_before_2022_needs_neither(self):
        data = plan_data(plan_attrs={**GOOD_PLAN, "lagesmetodTyp": None}, beslut=[{"datumPaborjat": "2019-05-01"}])
        self.assertEqual(v.check_plan(data), [])
        self.assertFalse(v.is_new_plan(data))
        self.assertTrue(v.is_new_plan(plan_data(beslut=[{"datumPaborjat": "2022-01-01"}])))

    def test_dates_from_the_layer_are_read_as_text(self):
        from qgis.PyQt.QtCore import QDate
        self.assertEqual(v._clean(QDate(2020, 5, 1)), "2020-05-01")
        self.assertIsNone(v._clean(QDate()))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PositionRules(unittest.TestCase):
    def test_uncertain_position_may_not_be_given(self):
        data = plan_data()
        data.areas[0].attrs["absolutLagesosakerhetPlan"] = 0.5
        issues = v.check_position_data(data)
        self.assertEqual([(i.severity, i.code, i.fid) for i in issues], [("fel", "DP-0010", data.areas[0].fid)])

    def test_vertical_limits_are_for_areas_only(self):
        line = area("egenskap_linje", "MultiLineString((( 20 20, 20 60)))", "line", 6)
        rows = [form_row("egenskap_linje", "line", vertikalAvgransning="över mark")]
        issues = v.check_position_data(plan_data(extra_areas=[line], rows=rows))
        self.assertEqual([(i.code, i.table) for i in issues], [("DP-0015", "egenskap_linje")])
        ok = [form_row("egenskap_yta", "x", vertikalAvgransning="över mark")]
        self.assertEqual(v.check_position_data(plan_data(rows=ok)), [])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ProvisionRules(PlanCase):
    def row(self, kod="DP_KM_J2", table="anvandning_yta", **kwargs):
        entry = pick(self.catalog, kod)
        attrs = bm.feature_attributes(entry, kwargs.pop("values", filled(entry)), kwargs.pop("motiv", "Motiv"),
                                      kwargs.pop("formulation", None))
        return entry, {**attrs, "tabell": table, "yta": "use1", "beteckning": entry.beteckning}

    def data(self, row):
        return plan_data(uses=(PLAN,), rows=[row])

    def issues(self, row):
        return v.check_rows(self.data(row), self.catalog)

    def test_a_correct_provision_has_no_issues(self):
        _, row = self.row()
        self.assertEqual(self.issues(row), [])

    def test_a_missing_value_stops_on_dp_0022(self):
        entry = next(e for e in self.catalog.search(layer="egenskap_yta") if e.variables
                     and all(x.datatype == "decimaltal" for x in e.variables))
        _, row = self.row(entry.kod, "egenskap_yta")
        stored = json.loads(row["bestammelsevarde"])
        stored[0]["variabelvarde"] = ""
        row["bestammelsevarde"] = json.dumps(stored)
        data = plan_data(uses=(PLAN,), extra_areas=[], rows=[{**row, "yta": "use1", "tabell": "egenskap_yta"}])
        data.areas.append(area("egenskap_yta", INSIDE, "use1", 9))
        found = v.check_rows(data, self.catalog)
        self.assertIn(("fel", "DP-0022"), [(i.severity, i.code) for i in found], found)

    def test_a_missing_value_type_stops_on_dp_0009(self):
        entry = next(e for e in self.catalog.search(layer="egenskap_yta") if e.variables
                     and all(x.datatype == "decimaltal" for x in e.variables))
        _, row = self.row(entry.kod, "egenskap_yta")
        stored = json.loads(row["bestammelsevarde"])
        stored[0]["vardetyp"] = None
        row["bestammelsevarde"] = json.dumps(stored)
        data = plan_data(uses=(PLAN,), rows=[row])
        data.areas.append(area("egenskap_yta", INSIDE, "use1", 9))
        self.assertIn("DP-0009", [i.code for i in v.check_rows(data, self.catalog)])

    def test_a_customised_formulation_warns_dp_krav_0017(self):
        entry = pick(self.catalog, "DP_KM_J2")
        custom = entry.formulering + " (särskilt)"
        _, row = self.row(formulation=custom)
        self.assertTrue(row["avviker"])
        found = self.issues(row)
        self.assertEqual([(i.severity, i.code) for i in found], [("varning", "DP-Krav-0017")])

    def test_a_provision_missing_from_the_loaded_catalog_warns(self):
        _, row = self.row()
        row["planbestammelsekatalogreferens"] = "00000000-0000-0000-0000-000000000000"
        found = self.issues(row)
        self.assertEqual([i.severity for i in found], ["varning"])
        self.assertIn("finns inte i den laddade katalogen", found[0].text)
        self.assertEqual(v.check_rows(self.data(row), None), [], "utan katalog kan detta inte kontrolleras")

    def test_a_provision_without_a_catalog_reference_is_an_error(self):
        _, row = self.row()
        row["planbestammelsekatalogreferens"] = None
        self.assertEqual([i.severity for i in self.issues(row)], ["fel"])

    def test_a_provision_of_the_wrong_kind_for_its_area_is_an_error(self):
        _, row = self.row(table="anvandning_yta")
        prop = next(e for e in self.catalog.search(layer="egenskap_yta"))
        row["planbestammelsekatalogreferens"] = prop.id
        self.assertTrue(any("annan typ" in i.text for i in self.issues(row)))

    def test_technical_installations_need_the_exact_text_in_formulation_and_motive(self):
        _, ok = self.row("DP_KM_E2", "egenskap_yta", motiv="Tekniska anläggningar")
        data = plan_data(uses=(PLAN,), rows=[{**ok}])
        data.areas.append(area("egenskap_yta", INSIDE, "use1", 9))
        self.assertEqual([i for i in v.check_rows(data, self.catalog) if i.code.startswith("DP-002")], [])
        bad = {**ok, "motiv": "Något annat", "bestammelseformulering": "Teknik"}
        data.rows = [bad]
        codes = [i.code for i in v.check_rows(data, self.catalog)]
        self.assertIn("DP-0019", codes)
        self.assertIn("DP-0020", codes)

    def test_a_provision_whose_area_is_gone_warns_it_will_be_removed(self):
        _, row = self.row()
        data = plan_data(uses=(), rows=[row])
        found = v.check_rows(data, self.catalog)
        self.assertEqual([(i.severity, i.table) for i in found], [("varning", "bestammelse")])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class DocumentRules(unittest.TestCase):
    """Till NGP ska alltid en planbeskrivning och en beslutshandling följa med."""
    DESCRIPTION = {"roll": "planbeskrivning", "namn": "Planbeskrivning"}
    MAP = {"roll": "beslutshandling", "innehall": "plankarta", "namn": "Plankarta"}
    PROTOCOL = {"roll": "beslutshandling", "innehall": "beslutsprotokoll", "namn": "Protokoll"}

    def found(self, documents, status="påbörjad"):
        data = plan_data(plan_attrs={**GOOD_PLAN, "status": status}, dokument=documents)
        return v.check_documents(data) + v.check_laga_kraft(data)

    def test_before_laga_kraft_missing_documents_only_warn(self):
        found = self.found([])
        self.assertEqual(len(found), 2)
        self.assertTrue(all(i.severity == "varning" for i in found), "valfria enligt specifikationen före laga kraft")
        text = " ".join(i.text for i in found)
        self.assertIn("Planbeskrivning saknas", text)
        self.assertIn("Beslutshandling saknas", text)
        self.assertIn("krävs vid laga kraft", text)
        self.assertTrue(all(i.table == "dokument" for i in found))

    def test_at_laga_kraft_missing_documents_are_errors_with_the_rule_codes(self):
        found = [i for i in self.found([], "laga kraft") if i.table == "dokument"]
        self.assertEqual({(i.severity, i.code) for i in found}, {("fel", "DP-0005"), ("fel", "DP-0014")})

    def test_a_protocol_that_also_contains_the_plan_map_satisfies_laga_kraft(self):
        both = {"roll": "beslutshandling", "innehall": "plankarta; beslutsprotokoll", "namn": "Beslut"}
        self.assertEqual([i for i in self.found([self.DESCRIPTION, both], "laga kraft") if i.table == "dokument"], [])

    def test_any_decision_document_will_do_before_laga_kraft(self):
        self.assertEqual(self.found([self.DESCRIPTION, self.PROTOCOL]), [])
        self.assertEqual(self.found([self.DESCRIPTION, self.MAP]), [])

    def test_only_the_description_missing_or_only_the_decision_document_missing(self):
        self.assertEqual([i.text[:12] for i in self.found([self.MAP])], ["Planbeskrivn"])
        self.assertEqual([i.text[:12] for i in self.found([self.DESCRIPTION])], ["Beslutshandl"])

    def test_at_laga_kraft_some_decision_document_must_contain_the_plan_map(self):
        issues = [i for i in self.found([self.DESCRIPTION, self.PROTOCOL], "laga kraft") if i.table == "dokument"]
        self.assertEqual([i.text[:16] for i in issues], ["Ingen beslutshan"])
        self.assertEqual(issues[0].code, "DP-0014")
        self.assertEqual([i for i in self.found([self.DESCRIPTION, self.MAP], "laga kraft") if i.table == "dokument"], [])

    def test_the_validation_reports_them_for_a_new_plan_without_documents(self):
        found = v.validate(plan_data())
        self.assertTrue(any("Planbeskrivning saknas" in i.text for i in found))
        self.assertTrue(any("Beslutshandling saknas" in i.text for i in found))

    def test_a_missing_plan_area_gives_no_document_errors_of_its_own(self):
        self.assertEqual(v.check_documents(PlanData()), [])


class LagaKraftRules(unittest.TestCase):
    complete = dict(
        plan_attrs={**GOOD_PLAN, "status": "laga kraft", "beteckning": "DP 1"},
        rows=[form_row("anvandning_yta", "use1", motiv="Motiv"), form_row("anvandning_yta", "use2", motiv="Motiv")],
        beslut=[{"datumPaborjat": "2023-01-01", "diarienummerKommun": "KS 1/23", "beslutstyp": "antagande",
                 "datumAntagande": "2024-01-01", "datumLagakraft": "2024-02-01", "genomforandetid": 5,
                 "genomforandetidStartar": "2024-02-01"}],
        dokument=[{"roll": "planbeskrivning"}, {"roll": "beslutshandling", "innehall": "plankarta"}])

    def test_only_plans_with_status_laga_kraft_are_checked(self):
        self.assertEqual(v.check_laga_kraft(plan_data()), [])

    def test_a_complete_plan_passes(self):
        self.assertEqual(v.check_laga_kraft(plan_data(**self.complete)), [])

    def test_an_empty_plan_reports_everything_that_is_missing(self):
        data = plan_data(plan_attrs={**GOOD_PLAN, "status": "laga kraft"}, rows=[])
        found = v.check_laga_kraft(data) + v.check_documents(data)
        text = " ".join(i.text for i in found)
        for expected in ("beteckning", "Planbeskrivning", "plankartan", "inga bestämmelser", "Beslutsinformation saknas"):
            self.assertIn(expected, text)
        self.assertTrue(all(i.severity == "fel" for i in found))
        self.assertEqual(sum("plankartan" in i.text for i in found), 1, "en enda text om plankartan, inte två")

    def test_each_decision_field_is_required(self):
        for name in ("diarienummerKommun", "beslutstyp", "datumAntagande", "datumLagakraft",
                     "genomforandetidStartar"):
            beslut = [{**self.complete["beslut"][0], name: None}]
            found = v.check_laga_kraft(plan_data(**{**self.complete, "beslut": beslut}))
            self.assertEqual([i.code for i in found], ["DP-0017"], name)

    def test_new_plans_need_a_motive_on_every_provision(self):
        rows = [form_row("anvandning_yta", "use1", motiv=""), form_row("anvandning_yta", "use2", motiv="Motiv")]
        found = v.check_laga_kraft(plan_data(**{**self.complete, "rows": rows}))
        self.assertEqual([(i.code, i.fid) for i in found], [("DP-0011", 1)])

    def test_old_plans_do_not_need_motives(self):
        rows = [form_row("anvandning_yta", "use1", motiv="")]
        old = [{**self.complete["beslut"][0], "datumPaborjat": "2019-01-01"}]
        self.assertEqual(v.check_laga_kraft(plan_data(**{**self.complete, "rows": rows, "beslut": old})), [])

    def test_a_missing_quality_description_on_the_plan_is_reported(self):
        for missing in ("digitaliseringsniva", "anvandbarhet"):
            plan_attrs = {**self.complete["plan_attrs"], missing: None}
            found = v.check_laga_kraft(plan_data(**{**self.complete, "plan_attrs": plan_attrs}))
            self.assertEqual([(i.code, i.table) for i in found], [("DP-0005", "detaljplan")], missing)
            self.assertIn("kvalitetsbeskrivning", found[0].text)

    def test_a_missing_quality_description_on_a_provision_is_reported(self):
        rows = [form_row("anvandning_yta", "use1", motiv="Motiv", digitaliseringsniva=None),
                form_row("anvandning_yta", "use2", motiv="Motiv")]
        found = v.check_laga_kraft(plan_data(**{**self.complete, "rows": rows}))
        self.assertEqual([(i.code, i.table, i.fid) for i in found], [("DP-0005", "anvandning_yta", 1)])
        self.assertIn("kvalitetsbeskrivning", found[0].text)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ResultTests(unittest.TestCase):
    def test_errors_come_first_and_the_same_issue_is_not_repeated(self):
        data = plan_data(uses=(LEFT,), rows=[])
        issues = v.validate(data)
        severities = [i.severity for i in issues]
        self.assertEqual(severities, sorted(severities, key=v.SEVERITIES.index))
        self.assertEqual(len(issues), len(set(issues)))
        self.assertEqual(v.validate(plan_data(uses=(LEFT,), rows=[])), issues, "samma resultat varje gång")

    def test_the_summary_counts_by_severity(self):
        self.assertEqual(v.summary([]), "Inga avvikelser: planen klarar kontrollen.")
        issues = [Issue("fel", "", "a"), Issue("fel", "", "b"), Issue("varning", "", "c")]
        self.assertEqual(v.summary(issues), "2 fel, 1 varning")
        self.assertEqual(v.summary(issues + [Issue("varning", "", "d"), Issue("info", "", "e")]),
                         "2 fel, 2 varningar, 1 att fylla i")

    def test_an_issue_can_be_shown_in_the_map_only_when_it_belongs_to_an_area(self):
        self.assertTrue(Issue("fel", "", "x", "anvandning_yta", 3).locatable)
        self.assertTrue(Issue("fel", "", "x", "detaljplan", 1).locatable)
        self.assertFalse(Issue("fel", "", "x", "beslutsinformation").locatable)
        self.assertFalse(Issue("fel", "", "x", "anvandning_yta", None).locatable)
        self.assertEqual(Issue("fel", "", "x", "egenskap_linje", 1).where, "Egenskapslinje")
        self.assertEqual(Issue("fel", "", "x").where, "Planen")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class LivePlanTests(GuiCase):
    """Valideringen mot en riktig plan i projektet (lager, bestämmelser och redigeringsbuffert)."""

    def setUp(self):
        super().setUp()
        self.controller.start_editing()
        self.uses = self.build_plan(uses=(LEFT,))
        self.entry = pick(self.catalog, "DP_KM_J2")
        self.controller.add_bestammelse("anvandning_yta", self.uses[0].id(), self.entry, filled(self.entry))

    def test_collect_reads_areas_rows_and_the_municipality_the_plan_was_made_for(self):
        data = v.collect(self.controller.project)
        self.assertEqual(data.meta_kommun, "Eskilstuna")
        self.assertEqual([(a.table, a.is_area) for a in data.areas], [("anvandning_yta", True)])
        self.assertEqual(len(data.rows), 1)
        self.assertIsNotNone(data.plan)
        self.assertAlmostEqual(data.plan.geometry.area(), 10000.0)

    def test_the_uncovered_half_and_the_missing_plan_details_are_found(self):
        issues = self.controller.validate(self.catalog)
        codes = [i.code for i in issues]
        self.assertIn("DP-0002", codes)
        self.assertTrue(any("Namn saknas" in i.text for i in issues))
        self.assertEqual(issues[0].severity, "fel")

    def test_filling_the_rest_and_assigning_removes_the_coverage_and_provision_errors(self):
        fill = self.controller.fill_use()
        pump()
        self.controller.add_bestammelse("anvandning_yta", fill.fid, self.entry, filled(self.entry))
        issues = self.controller.validate(self.catalog)
        self.assertNotIn("DP-0002", [i.code for i in issues])
        self.assertFalse([i for i in issues if "Saknar bestämmelse" in i.text])

    def test_a_changed_municipality_is_caught(self):
        self.controller.set_plan_values({"kommun": "Göteborg", "namn": "X", "syfte": "Y"})
        self.assertTrue(any("stämmer inte med kommunen planen skapades för" in i.text
                            for i in self.controller.validate(self.catalog)))

    def test_validation_does_not_change_the_plan(self):
        before = [(f.id(), f.geometry().asWkt(), f.attributes()) for f in self.layers["anvandning_yta"].getFeatures()]
        self.controller.validate(self.catalog)
        after = [(f.id(), f.geometry().asWkt(), f.attributes()) for f in self.layers["anvandning_yta"].getFeatures()]
        self.assertEqual(before, after)

    def test_show_issue_selects_the_area(self):
        issue = next(i for i in self.controller.validate(self.catalog) if i.table == "detaljplan" and i.locatable)
        self.controller.show_issue(issue)
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 1)
        self.controller.show_issue(Issue("fel", "", "x", "beslutsinformation"))  # inget att markera: ingen krasch


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class DialogTests(GuiCase):
    def make(self, issues, controller=None):
        self.calls, self.shown = [], []

        def run():
            self.calls.append(1)
            return list(issues)

        dialog = ValidationDialog(run, self.shown.append, controller=controller)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_no_plan_switcher_with_only_one_plan_loaded(self):
        dialog = self.make([], controller=self.controller)
        self.assertEqual(dialog.layout().itemAt(0).widget(), dialog.summary, "ingen växlarrad när det bara finns en")

    def test_switching_the_active_plan_reruns_the_check_for_the_new_one(self):
        from qgis.core import QgsProject
        from qgis.PyQt.QtWidgets import QComboBox
        from rita_detaljplan.core.project import create_plan_project, find_plan_group, load_plan
        other_gpkg, _ = create_plan_project(self.dir, "annan_plan", "Eskilstuna", "0482", 3006)
        load_plan(other_gpkg, QgsProject.instance())  # blir aktiv
        dialog = self.make(self.ISSUES, controller=self.controller)
        self.assertEqual(self.calls, [1])
        combo = dialog.layout().itemAt(0).widget().findChild(QComboBox)
        combo.setCurrentIndex(combo.findText("plan"))
        self.assertEqual(find_plan_group(QgsProject.instance()).name(), "plan")
        self.assertEqual(self.calls, [1, 1], "kontrollen kördes om efter bytet")

    ISSUES = [Issue("fel", "DP-0002", "Planområdet saknar användning.", "detaljplan", 1),
              Issue("varning", "DP-Krav-0014", "Ytan är smal.", "egenskap_yta", 2),
              Issue("fel", "", "Namn saknas.", "beslutsinformation"),
              Issue("info", "", "Fylls i senare.")]

    def rows(self, dialog):
        return [dialog.list.item(i).text() for i in range(dialog.list.count())]

    def test_every_issue_is_listed_with_its_mark_place_code_and_text(self):
        dialog = self.make(self.ISSUES)
        rows = self.rows(dialog)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0], "✘  Planområde: [DP-0002] Planområdet saknar användning.")
        self.assertTrue(rows[1].startswith("▲  Egenskapsområde: [DP-Krav-0014]"))
        self.assertIn("2 fel, 1 varning, 1 att fylla i", dialog.summary.text())

    def test_the_filters_hide_and_show_kinds_of_issues(self):
        dialog = self.make(self.ISSUES)
        dialog.filters["varning"].setChecked(False)
        dialog.filters["info"].setChecked(False)
        self.assertEqual(len(self.rows(dialog)), 2)
        dialog.filters["varning"].setChecked(True)
        self.assertEqual(len(self.rows(dialog)), 3)

    def test_show_is_only_possible_for_issues_with_a_place_in_the_map(self):
        dialog = self.make(self.ISSUES)
        self.assertFalse(dialog.btn_show.isEnabled())
        dialog.list.setCurrentRow(0)
        self.assertTrue(dialog.btn_show.isEnabled())
        dialog.btn_show.click()
        self.assertEqual(self.shown, [self.ISSUES[0]])
        dialog.list.setCurrentRow(2)
        self.assertFalse(dialog.btn_show.isEnabled())
        dialog.show_selected()
        self.assertEqual(len(self.shown), 1)

    def test_check_again_runs_the_validation_again(self):
        dialog = self.make(self.ISSUES)
        self.assertEqual(len(self.calls), 1)
        dialog.btn_again.click()
        self.assertEqual(len(self.calls), 2)

    def test_a_clean_plan_says_so(self):
        dialog = self.make([])
        self.assertEqual(dialog.summary.text(), "Inga avvikelser: planen klarar kontrollen.")
        self.assertEqual(dialog.list.count(), 0)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ToolBarValidationTests(GuiCase):
    def setUp(self):
        super().setUp()
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        for layer in self.layers.values():
            layer.rollBack()
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)

    def test_the_validation_is_opened_from_the_ngp_dialog_not_from_the_toolbar(self):
        self.assertFalse(hasattr(self.toolbar, "act_validate"))
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        pump()
        with mock.patch("rita_detaljplan.gui.plan_toolbar.NgpDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = False
            self.toolbar.deliver()
        self.assertEqual(dialog_cls.call_args.args[4], self.toolbar.validate)

    def test_validate_opens_the_dialog_with_the_result_of_the_check(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        pump()
        with mock.patch("rita_detaljplan.gui.plan_toolbar.ValidationDialog") as dialog_cls:
            self.toolbar.validate()
        run = dialog_cls.call_args.args[0]
        self.assertIn("DP-0002", [i.code for i in run()])
        dialog_cls.return_value.exec.assert_called_once()

    def test_showing_an_issue_selects_activates_and_zooms(self):
        self.toolbar.start()
        self.build_plan(uses=(LEFT,))
        issue = Issue("fel", "DP-0002", "x", "anvandning_yta", self.layers["anvandning_yta"].allFeatureIds()[0])
        self.toolbar._show_issue(issue)
        self.assertEqual(self.layers["anvandning_yta"].selectedFeatureCount(), 1)
        self.iface.setActiveLayer.assert_called_with(self.layers["anvandning_yta"])

    def test_showing_an_issue_with_an_exact_area_highlights_it_without_selecting_the_whole_plan_area(self):
        from qgis.core import QgsGeometry
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        gap = QgsGeometry.fromWkt("MultiPolygon(((0 0, 20 0, 20 20, 0 20, 0 0)))")
        issue = Issue("fel", "DP-0002", "20 m² av planområdet saknar användning.", "detaljplan",
                     self.layers["detaljplan"].allFeatureIds()[0], gap)
        self.toolbar._show_issue(issue)
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 0, "hela planområdet ska inte markeras")
        self.iface.setActiveLayer.assert_not_called()
        self.assertFalse(self.toolbar._issue_band.asGeometry().isEmpty())
        self.assertTrue(self.toolbar._issue_band.asGeometry().equals(gap))

    def test_a_second_call_replaces_the_highlight_instead_of_stacking(self):
        from qgis.core import QgsGeometry
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        first = QgsGeometry.fromWkt("MultiPolygon(((0 0, 10 0, 10 10, 0 10, 0 0)))")
        second = QgsGeometry.fromWkt("MultiPolygon(((50 50, 60 50, 60 60, 50 60, 50 50)))")
        fid = self.layers["detaljplan"].allFeatureIds()[0]
        self.toolbar._show_issue(Issue("fel", "DP-0002", "x", "detaljplan", fid, first))
        self.toolbar._show_issue(Issue("fel", "DP-0002", "x", "detaljplan", fid, second))
        self.assertTrue(self.toolbar._issue_band.asGeometry().equals(second))

    def test_an_issue_without_an_exact_area_still_selects_the_whole_feature_as_before(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        fid = self.layers["detaljplan"].allFeatureIds()[0]
        self.toolbar._show_issue(Issue("fel", "DP-0002", "x", "detaljplan", fid))
        self.assertEqual(self.layers["detaljplan"].selectedFeatureCount(), 1)
        self.assertTrue(self.toolbar._issue_band.asGeometry().isEmpty())

    def test_saving_reports_the_result_of_the_check(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        with mock.patch.object(self.toolbar, "_ask_save", return_value=__import__(
                "qgis.PyQt.QtWidgets", fromlist=["QMessageBox"]).QMessageBox.StandardButton.Save):
            self.toolbar.stop()
        message = [m for m in self.messages() if "Sparade planen" in m]
        self.assertTrue(message, self.messages())
        self.assertIn("Kontroll:", message[0])
        self.assertIn("fel", message[0])

    def test_discarding_does_not_run_the_check(self):
        self.toolbar.start()
        self.draw("detaljplan", PLAN)
        with mock.patch.object(self.toolbar, "_ask_save", return_value=__import__(
                "qgis.PyQt.QtWidgets", fromlist=["QMessageBox"]).QMessageBox.StandardButton.Discard), \
                mock.patch.object(self.controller, "validate") as validate:
            self.toolbar.stop()
        validate.assert_not_called()

class ImplementationTime(unittest.TestCase):
    def check(self, *months):
        beslut = [{"genomforandetid": m} for m in months]
        return v.check_implementation(plan_data(beslut=beslut))

    def test_a_plan_without_implementation_time_is_an_error(self):
        for missing in ((), (None,), (0,), ("x",)):
            (issue,) = self.check(*missing)
            self.assertEqual(issue.severity, "fel")
            self.assertIn("Genomförandetid saknas", issue.text)

    def test_five_to_fifteen_years_is_fine(self):
        for months in (60, 120, 180):
            self.assertEqual(self.check(months), [])

    def test_outside_five_to_fifteen_years_is_a_warning(self):
        for months in (12, 59, 181):
            (issue,) = self.check(months)
            self.assertEqual(issue.severity, "varning")

    def test_it_is_part_of_the_whole_validation(self):
        self.assertTrue(any("Genomförandetid saknas" in i.text for i in v.validate(plan_data())))


if __name__ == "__main__":
    unittest.main()
