"""Taggar för planbeskrivningen: indelningen i BFS 2020:8, reglerna och XML-delen (ren Python, ingen QGIS)."""
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning as pb  # noqa: E402

XSD = ROOT / "spec" / "planbeskrivning-2.0.xsd"
XS = "{http://www.w3.org/2001/XMLSchema}"
PLAN = "12345678-cafe-cafe-cafe-123456789012"
RULE = "379b67a6-e396-4752-a021-0b92c8d17209"


def make(identitet="abc", tema="Genomförandefrågor", grupp="Fastighetsrättsliga frågor", undergrupp=None,
         lage=pb.PLANOMRADE, referens=None):
    return pb.Omfattning(identitet, tema, grupp, undergrupp, lage, referens)


def header(**kwargs):
    return pb.Header(PLAN, "11111111-2222-3333-4444-555555555555", programvara="Rita Detaljplan",
                     programvaruversion="0.1.47", **kwargs)


def check_against_xsd(testcase, xml_text):
    """Kontrollerar ordning, förekomst och mönster mot Lantmäteriets schema (en liten egen kontroll: ingen
    XSD-validerare finns i QGIS Python)."""
    schema = ET.parse(XSD).getroot()
    types = {t.get("name"): t for t in schema.findall(XS + "complexType")}
    patterns = {s.get("name"): re.compile(s.find(f"{XS}restriction/{XS}pattern").get("value") + r"\Z")
                for s in schema.findall(XS + "simpleType")}
    ns = "{" + schema.get("targetNamespace") + "}"

    def sequence(type_name):
        node = types[type_name.split(":")[-1]]
        extension = node.find(f"{XS}complexContent/{XS}extension")
        if extension is not None:
            return sequence(extension.get("base")) + [e for e in extension.find(XS + "sequence")]
        return list(node.find(XS + "sequence"))

    def check(element, type_name):
        declared = [e for e in sequence(type_name) if e.tag == XS + "element" and e.get("name")]
        wanted = [(e.get("name"), e.get("minOccurs", "1"), e.get("maxOccurs", "1"), e.get("type")) for e in declared]
        if type_name.split(":")[-1] == "LageType":  # choice: högst en av tre
            wanted = [("objektreferens", "0", "1", None), ("planbestammelsereferens", "0", "1", None),
                      ("planomrade", "0", "1", None)]
        children = [(c.tag.replace(ns, ""), c) for c in element]
        position = 0
        for name, low, high, child_type in wanted:
            matching = []
            while position < len(children) and children[position][0] == name:
                matching.append(children[position][1])
                position += 1
            testcase.assertGreaterEqual(len(matching), int(low), f"{element.tag}: {name} saknas")
            if high != "unbounded":
                testcase.assertLessEqual(len(matching), int(high), f"{element.tag}: för många {name}")
            for found in matching:
                kind = (child_type or "").split(":")[-1]
                if kind in patterns:
                    testcase.assertRegex(found.text or "", patterns[kind], f"{name}: {found.text!r}")
                elif kind in types:
                    check(found, kind)
        testcase.assertEqual(position, len(children), f"{element.tag}: oväntat eller felplacerat element "
                                                      f"{children[position][0] if position < len(children) else ''}")

    root = ET.fromstring(xml_text.encode("utf-8"))
    testcase.assertEqual(root.tag, ns + "Planbeskrivning")
    check(root, "app:PlanbeskrivningType")


class TableTests(unittest.TestCase):
    def test_the_table_follows_the_annex_to_bfs_2020_8(self):
        self.assertEqual(pb.temas(), ["Detaljplanens syfte", "Beskrivning av detaljplanen",
                                      "Motiv till detaljplanens regleringar", "Genomförandefrågor",
                                      "Planeringsunderlag", "Planeringsförutsättningar", "Konsekvenser"])
        self.assertEqual(pb.grupper("Genomförandefrågor"),
                         ["Mark- och utrymmesförvärv", "Fastighetsrättsliga frågor", "Tekniska frågor",
                          "Ekonomiska frågor", "Organisatoriska frågor", "Kulturvärden",
                          "Prövning enligt annan lagstiftning", "Upplysningar", "Annat"])
        self.assertEqual(pb.undergrupper("Beskrivning av detaljplanen", "Allmän plats"), ["Huvudmannaskap"])
        self.assertEqual(len(pb.undergrupper("Konsekvenser", "Riksintresse")), 22)
        self.assertEqual(pb.undergrupper("Planeringsförutsättningar", "Riksintressen"),
                         pb.undergrupper("Konsekvenser", "Riksintresse"))

    def test_the_planning_background_types_match_the_underlagstyp_codelist_of_the_detaljplan_specification(self):
        import json
        spec = json.loads((ROOT / "spec" / "detaljplan-4.1.json").read_text(encoding="utf-8"))
        enum = set(spec["definitions"]["underlagstyp"]["enum"]) - {"annat"}
        ours = {u.lower() for g in pb.INDELNING["Planeringsunderlag"].values() for u in g}
        self.assertEqual(enum - {"detaljplan"} - ours, set(), "underlagstyper som saknas i indelningen")

    def test_lookups_ignore_case_and_spacing(self):
        self.assertEqual(pb.canonical("genomförandefrågor  ", pb.temas()), "Genomförandefrågor")
        self.assertEqual(pb.grupper("GENOMFÖRANDEFRÅGOR")[1], "Fastighetsrättsliga frågor")
        self.assertEqual(pb.grupper("okänt"), [])
        self.assertEqual(pb.undergrupper("Genomförandefrågor", "Upplysningar"), [])

    def test_the_motive_theme_has_the_group_the_specification_names(self):
        self.assertEqual(pb.grupper(pb.MOTIV_TEMA), [pb.MOTIV_GRUPP])


class RuleTests(unittest.TestCase):
    def test_a_valid_tag_has_no_problems(self):
        self.assertEqual(pb.problems([make()]), [])
        self.assertEqual(pb.problems([make(lage=pb.PLANBESTAMMELSE, referens=RULE)]), [])
        self.assertEqual(pb.problems([make(lage=pb.OBJEKT, referens="ABC-1")]), [])

    def test_at_least_one_tag_is_needed(self):
        self.assertTrue(pb.problems([]))

    def test_the_identity_follows_planb_005(self):
        for bad in ("", "1abc", "med mellanslag", "a" * 41, "a-b", "ab.c"):
            self.assertTrue(pb.problems([make(identitet=bad)]), repr(bad))
        for good in ("a", "åäö_1", "A" + "b" * 39):
            self.assertEqual(pb.problems([make(identitet=good)]), [], repr(good))

    def test_the_identity_is_unique_ignoring_case(self):
        found = pb.problems([make("abc"), make("ABC")])
        self.assertTrue(any("flera gånger" in p for p in found))

    def test_the_theme_must_exist_but_groups_and_subgroups_may_be_your_own(self):
        self.assertTrue(pb.problems([make(tema="Eget tema")]))
        self.assertEqual(pb.problems([make(grupp="Egen grupp", undergrupp="Egen undergrupp")]), [])

    def test_a_group_is_required(self):
        self.assertTrue(pb.problems([make(grupp="")]))

    def test_the_location_needs_its_reference(self):
        self.assertTrue(pb.problems([make(lage=pb.PLANBESTAMMELSE, referens=None)]))
        self.assertTrue(pb.problems([make(lage=pb.PLANBESTAMMELSE, referens="inte-ett-uuid")]))
        self.assertTrue(pb.problems([make(lage=pb.OBJEKT, referens=" ")]))
        self.assertTrue(pb.problems([make(lage="annat")]))

    def test_motive_for_a_regulation_must_point_at_a_provision(self):
        motive = make(tema=pb.MOTIV_TEMA, grupp=pb.MOTIV_GRUPP)
        self.assertTrue(any("PLANB-002" in p for p in pb.problems([motive])))
        self.assertEqual(pb.problems([make(tema=pb.MOTIV_TEMA, grupp=pb.MOTIV_GRUPP, lage=pb.PLANBESTAMMELSE,
                                           referens=RULE)]), [])


class XmlTests(unittest.TestCase):
    def build(self, items, **kwargs):
        return pb.build_xml(header(**kwargs), items, valid_from="2026-10-05T12:00:00.000+02:00")

    def test_the_xml_follows_the_schema_from_lantmateriet(self):
        text = self.build([
            make("abc", lage=pb.PLANBESTAMMELSE, referens=RULE),
            make("def", "Planeringsunderlag", "Utredningar", "Bullerutredning"),
            make("ghi", "Beskrivning av detaljplanen", "Egen grupp", "Egen undergrupp", pb.OBJEKT, "ID-17"),
        ], arkividentitet="XYZ:789/OPQ2")
        check_against_xsd(self, text)

    def test_the_example_in_the_specification_is_reproduced(self):
        text = self.build([make("abc", lage=pb.PLANBESTAMMELSE, referens=RULE),
                           make("def", grupp="Tekniska frågor")])
        self.assertIn('<Planbeskrivning xmlns="' + pb.NAMESPACE + '">', text)
        self.assertIn("<detaljplansreferens>" + PLAN + "</detaljplansreferens>", text)
        self.assertIn("<planbestammelsereferens>" + RULE + "</planbestammelsereferens>", text)
        self.assertIn("<planomrade>true</planomrade>", text)
        self.assertIn("<tema>genomförandefrågor</tema>", text)
        self.assertIn("<grupp>fastighetsrättsliga frågor</grupp>", text)
        self.assertIn("<grupp>tekniska frågor</grupp>", text)
        self.assertNotIn("<undergrupp>", text)
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="utf-8"?>'))

    def test_a_subgroup_is_written_when_there_is_one(self):
        text = self.build([make(undergrupp="Rättigheter")])
        self.assertIn("<undergrupp>rättigheter</undergrupp>", text)

    def test_the_xml_can_be_read_back_exactly(self):
        items = [make("abc", lage=pb.PLANBESTAMMELSE, referens=RULE),
                 make("def", "Planeringsunderlag", "Utredningar", "Bullerutredning"),
                 make("ghi", "Konsekvenser", "egen grupp", "egen undergrupp", pb.OBJEKT, "ID-17"),  # egna värden skrivs med gemener
                 make("jkl")]
        head, read = pb.parse_xml(self.build(items, arkividentitet="X:1"))
        self.assertEqual(read, items)
        self.assertEqual((head.detaljplan, head.objektversion, head.arkividentitet), (PLAN, 1, "X:1"))
        self.assertEqual((head.programvara, head.programvaruversion), ("Rita Detaljplan", "0.1.47"))

    def test_the_example_from_the_specification_can_be_read(self):
        text = f"""<Planbeskrivning xmlns="{pb.NAMESPACE}" xmlns:lmg="http://namespace.lantmateriet.se/distribution/geometri/v2"
 xmlns:gml="http://www.opengis.net/gml/3.2">
 <objektidentitet>12345678-1234-1234-1234-123456789012</objektidentitet>
 <objektversion>1</objektversion>
 <versionGiltigFran>2022-11-17T14:24:34.123+01:00</versionGiltigFran>
 <detaljplansreferens>12345678-cafe-cafe-cafe-123456789012</detaljplansreferens>
 <Omfattning><identitet>abc</identitet>
  <Lage><planbestammelsereferens>{RULE}</planbestammelsereferens></Lage>
  <Indelning><tema>genomförandefrågor</tema><grupp>fastighetsrättsliga frågor</grupp></Indelning>
 </Omfattning>
</Planbeskrivning>"""
        head, items = pb.parse_xml(text)
        self.assertEqual(head.detaljplan, PLAN)
        self.assertEqual(items, [make("abc", lage=pb.PLANBESTAMMELSE, referens=RULE)])

    def test_xml_that_is_not_a_planbeskrivning_is_refused(self):
        with self.assertRaises(ValueError):
            pb.parse_xml("<a><b/></a>")
        with self.assertRaises(ValueError):
            pb.parse_xml("inte xml alls")

    def test_tags_that_break_the_rules_are_not_written(self):
        with self.assertRaises(ValueError) as caught:
            self.build([make("1fel")])
        self.assertIn("1fel", str(caught.exception))
        with self.assertRaises(ValueError):
            pb.build_xml(pb.Header("inte-ett-uuid"), [make()])

    def test_a_new_version_keeps_the_identity_and_raises_the_version(self):
        first = pb.next_header(None, PLAN, "Rita Detaljplan", "0.1.47")
        self.assertEqual(first.objektversion, 1)
        self.assertRegex(first.objektidentitet, pb.UUID_RE)
        second = pb.next_header(first, PLAN, "Rita Detaljplan", "0.1.48")
        self.assertEqual((second.objektidentitet, second.objektversion), (first.objektidentitet, 2))
        self.assertEqual(second.programvaruversion, "0.1.48")
        other = pb.next_header(first, "99999999-cafe-cafe-cafe-123456789012", "Rita Detaljplan", "0.1.48")
        self.assertNotEqual(other.objektidentitet, first.objektidentitet, "en annan detaljplan är en annan planbeskrivning")


if __name__ == "__main__":
    unittest.main()
