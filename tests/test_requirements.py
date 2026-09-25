"""Kommunlistan och kraven inför leverans. Kräver inte QGIS."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_detaljplan.core import kommuner, requirements  # noqa: E402

COMPLETE = {"kommun": "Eskilstuna", "namn": "Kv Väktaren", "syfte": "Bostäder", "status": "påbörjad", "typ": "detaljplan"}


def reqs(values=None, **kwargs):
    defaults = dict(has_plan_area=True, uses=2, coverage=1.0, unassigned=0, implementation_months=120,
                    datum_paborjat="2024-01-01")
    return requirements.plan_requirements(COMPLETE if values is None else values, **{**defaults, **kwargs})


def by_key(items):
    return {r.key: r for r in items}


class Kommuner(unittest.TestCase):
    def test_all_290_municipalities_with_four_digit_codes(self):
        all_ = kommuner.all_kommuner()
        self.assertEqual(len(all_), 290)
        self.assertTrue(all(len(k.kod) == 4 and k.kod.isdigit() for k in all_))
        self.assertEqual(len({k.kod for k in all_}), 290)
        self.assertEqual(len({k.namn for k in all_}), 290)

    def test_lookup_by_name_and_code_ignores_case_and_whitespace(self):
        self.assertEqual(kommuner.by_name(" eskilstuna "), kommuner.Kommun("0484", "Eskilstuna"))
        self.assertEqual(kommuner.by_code("0180").namn, "Stockholm")
        self.assertEqual(kommuner.by_code(" 1480 ").namn, "Göteborg")
        self.assertIsNone(kommuner.by_name("Atlantis"))
        self.assertIsNone(kommuner.by_name(None))
        self.assertIsNone(kommuner.by_code("9999"))

    def test_swedish_names_are_sorted_the_swedish_way(self):
        names = [k.namn for k in kommuner.all_kommuner()]
        self.assertEqual(names[0], "Ale")
        self.assertEqual(names[-1], "Övertorneå", "å, ä, ö kommer sist")
        self.assertLess(names.index("Åmål"), names.index("Örebro"))
        self.assertLess(names.index("Zzz") if "Zzz" in names else 0, names.index("Åmål"))


class PlanRequirements(unittest.TestCase):
    def test_a_complete_plan_meets_every_requirement(self):
        self.assertEqual(requirements.missing(reqs()), [])

    def test_the_always_required_fields_follow_the_specification(self):
        self.assertEqual([k for k, _ in requirements.REQUIRED_PLAN_FIELDS],
                         ["kommun", "namn", "syfte", "status", "typ"])

    def test_each_missing_field_is_reported_by_name(self):
        for key, label in requirements.REQUIRED_PLAN_FIELDS:
            values = {**COMPLETE, key: None}
            missing = requirements.missing(reqs(values))
            self.assertEqual([r.key for r in missing], [key], key)
            self.assertEqual(missing[0].field, key)
            self.assertIn(label, missing[0].text)

    def test_blank_text_counts_as_missing(self):
        self.assertEqual([r.key for r in requirements.missing(reqs({**COMPLETE, "syfte": "   "}))], ["syfte"])

    def test_an_unknown_municipality_is_not_accepted(self):
        missing = requirements.missing(reqs({**COMPLETE, "kommun": "Atlantis"}))
        self.assertEqual([r.key for r in missing], ["kommun"])
        self.assertIn("Atlantis", missing[0].text)

    def test_the_plan_area_must_be_drawn(self):
        items = by_key(reqs(has_plan_area=False, uses=0, coverage=0.0))
        self.assertFalse(items["planomrade"].ok)
        self.assertFalse(items["anvandning"].ok)
        self.assertFalse(items["bestammelser"].ok)

    def test_the_use_must_cover_the_whole_plan_area(self):
        half = by_key(reqs(coverage=0.5))["anvandning"]
        self.assertFalse(half.ok)
        self.assertIn("50%", half.text)
        self.assertTrue(by_key(reqs(coverage=0.9995))["anvandning"].ok, "avrundningsfel ska inte stoppa")
        self.assertFalse(by_key(reqs(uses=0, coverage=0.0))["anvandning"].ok)

    def test_every_area_needs_a_provision(self):
        item = by_key(reqs(unassigned=3))["bestammelser"]
        self.assertFalse(item.ok)
        self.assertIn("3 saknar", item.text)
        self.assertTrue(by_key(reqs(unassigned=0))["bestammelser"].ok)

    def test_the_requirements_come_in_the_order_they_are_usually_met(self):
        self.assertEqual([r.key for r in reqs()], ["planomrade", "kommun", "namn", "syfte", "status", "typ",
                                                   "genomforandetid", "datumPaborjat", "anvandning", "bestammelser"])

    def test_the_implementation_time_is_required(self):
        for months in (None, 0):
            missing = requirements.missing(reqs(implementation_months=months))
            self.assertEqual([r.key for r in missing], ["genomforandetid"])
            self.assertEqual(missing[0].field, "genomforandetid")
        self.assertEqual(requirements.missing(reqs(implementation_months=60)), [])

    def test_the_start_date_is_required_but_reported_separately(self):
        for value in (None, "", "   "):
            missing = requirements.missing(reqs(datum_paborjat=value))
            self.assertEqual([r.key for r in missing], ["datumPaborjat"])
            self.assertEqual(missing[0].field, "datumPaborjat")
        self.assertEqual(requirements.missing(reqs(datum_paborjat="2024-06-01")), [])


if __name__ == "__main__":
    unittest.main()
