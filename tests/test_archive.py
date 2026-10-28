"""Arkivpaket: filer, PREMIS-metadata (giltig mot LoC:s schema) och kontroll av ett paket i efterhand (utan QGIS)."""
import hashlib
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

try:  # finns i QGIS Python; saknas den hoppas schematesterna över
    from lxml import etree as LXML
except ImportError:  # pragma: no cover
    LXML = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# modulen importeras direkt så att testerna går utan QGIS
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("archive_under_test", ROOT / "rita_detaljplan" / "core" / "archive.py")
archive = importlib.util.module_from_spec(_spec)
sys.modules["archive_under_test"] = archive
_spec.loader.exec_module(archive)

NS = {"p": archive.PREMIS_NS, "dp": archive.DETALJPLAN_NS}
XSI_TYPE = f"{{{archive.XSI_NS}}}type"
SCHEMAS = ROOT / "rita_detaljplan" / "data" / "schemas"
XSD = SCHEMAS / "premis-v3-0.xsd"  # Library of Congress PREMIS 3.0, oförändrad
DP_XSD = SCHEMAS / "detaljplan-1.xsd"  # schemat för planens uppgifter (vårt eget)
APP = archive.App("Rita Detaljplan", "0.1.55", "https://github.com/ritaplan/rita-detaljplan")
NOW = datetime(2026, 10, 15, 14, 3, 22)
PLAN = {"beteckning": "DP 123", "namn": "Lärkan 1:1", "status": "Laga kraft", "typ": "Detaljplan",
        "datumLagakraft": "2026-09-01", "kommun": "Eskilstuna", "kommunkod": "0482"}


def make_pdf(path: Path, version: str = "1.7", pdfa: str = "", info: str = "") -> Path:
    xmp = f"<pdfaid:part>{pdfa[0]}</pdfaid:part><pdfaid:conformance>{pdfa[1]}</pdfaid:conformance>" if pdfa else ""
    body = f"%PDF-{version}\n1 0 obj << {info} >> endobj\n{xmp}\n%%EOF\n"
    path.write_bytes(body.encode("latin-1"))
    return path


def make_docx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w/>")
        z.writestr("docProps/app.xml", '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'extended-properties"><Application>Microsoft Office Word</Application><AppVersion>16.0000</AppVersion>'
                   "</Properties>")
        z.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
                   'metadata/core-properties" xmlns:dcterms="http://purl.org/dc/terms/">'
                   "<dcterms:created>2026-03-04T10:11:00Z</dcterms:created></cp:coreProperties>")
    return path


def make_gpkg(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.execute("PRAGMA application_id = 1196444487")
    con.execute("PRAGMA user_version = 10300")
    con.execute("CREATE TABLE t (a)")
    con.commit()
    con.close()
    return path


class ArchiveCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / "källor"
        self.out = self.root / "ut"
        self.src.mkdir()
        self.out.mkdir()
        self.gpkg = make_gpkg(self.src / "plan.gpkg")
        self.json = self.src / "plan.json"
        self.json.write_text('{"type": "FeatureCollection"}', encoding="utf-8")
        self.karta = make_pdf(self.src / "plankarta.pdf", info="/Creator (QGIS 4.2) /CreationDate (D:20261015120000+02'00')")
        self.beskrivning = make_pdf(self.src / "planbeskrivning.pdf", version="1.6", pdfa="2B", info="/Producer (Microsoft Word)")
        self.docx = make_docx(self.src / "planbeskrivning.docx")

    def items(self):
        return [archive.Item(self.gpkg, creator=("Rita Detaljplan", "0.1.55")),
                archive.Item(self.json, creator=("Rita Detaljplan", "0.1.55")),
                archive.Item(self.karta, "plankarta.pdf"),
                archive.Item(self.beskrivning), archive.Item(self.docx)]

    def build(self, **kwargs):
        kwargs.setdefault("plan", PLAN)
        return archive.build_package(self.out, "Lärkan 1:1", self.items(), APP, now=NOW, **kwargs)

    def tree(self, package):
        """metadata/PREMIS.xml: planen, filerna, händelserna och aktörerna."""
        return ET.parse(package.premis).getroot()

    def file_objects(self, root):
        return [o for o in root.findall("p:object", NS) if o.get(XSI_TYPE) == "premis:file"]

    def entities(self, root):
        return [o for o in root.findall("p:object", NS) if o.get(XSI_TYPE) == "premis:intellectualEntity"]


class PackageTests(ArchiveCase):
    def test_the_package_is_a_metadata_folder_with_one_premis_file_and_a_content_folder(self):
        package = self.build()
        self.assertEqual(package.folder, self.out / "Lärkan_1_1_arkivpaket_2026-10-15")
        found = sorted(p.relative_to(package.folder).as_posix() for p in package.folder.rglob("*") if p.is_file())
        self.assertEqual(found, ["content/plan.gpkg", "content/plan.json", "content/planbeskrivning.docx",
                                 "content/planbeskrivning.pdf", "content/plankarta.pdf", "metadata/PREMIS.xml",
                                 "schemas/detaljplan-1.xsd", "schemas/premis-v3-0.xsd"])
        self.assertEqual(package.premis, package.folder / "metadata" / "PREMIS.xml")

    def test_the_originals_are_left_alone(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.src.iterdir()}
        self.build()
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.src.iterdir()}, before)

    def test_an_existing_package_folder_is_never_overwritten(self):
        first, second = self.build(), self.build()
        self.assertNotEqual(first.folder, second.folder)
        self.assertTrue(second.folder.name.endswith("_2"))
        self.assertTrue(first.premis.exists() and second.premis.exists())

    def test_two_files_with_the_same_name_in_a_folder_are_kept_apart(self):
        other = self.root / "annan"
        other.mkdir()
        twin = make_pdf(other / "planbeskrivning.pdf")
        package = archive.build_package(self.out, "x", [archive.Item(self.beskrivning), archive.Item(twin)], APP, now=NOW)
        self.assertEqual(sorted(r.path for r in package.records),
                         ["content/planbeskrivning.pdf", "content/planbeskrivning_2.pdf"])

    def test_characters_windows_does_not_allow_are_replaced_in_names(self):
        self.assertEqual(archive.clean_filename('a:b*c?.pdf'), "a_b_c_.pdf")
        self.assertEqual(archive.clean_filename("  . "), "fil")

    def test_a_package_needs_files_that_exist_and_a_folder_to_put_them_in(self):
        with self.assertRaisesRegex(archive.ArchiveError, "Inga filer"):
            archive.build_package(self.out, "x", [], APP)
        with self.assertRaisesRegex(archive.ArchiveError, "finns inte"):
            archive.build_package(self.out, "x", [archive.Item(self.src / "saknas.pdf")], APP)
        with self.assertRaisesRegex(archive.ArchiveError, "Mappen finns inte"):
            archive.build_package(self.out / "nej", "x", self.items(), APP)

    def test_a_failure_halfway_leaves_no_half_finished_folder(self):
        real, calls = archive.shutil.copy2, []

        def copy_then_fail(source, target):
            if calls:
                raise OSError("disken är full")
            calls.append(source)
            return real(source, target)

        with mock.patch.object(archive.shutil, "copy2", side_effect=copy_then_fail):
            with self.assertRaisesRegex(archive.ArchiveError, "disken är full"):
                self.build()
        self.assertEqual(len(calls), 1, "första filen hann kopieras innan felet")
        self.assertEqual(list(self.out.iterdir()), [])


class DescribeTests(ArchiveCase):
    def records(self):
        return {r.path.split("/")[-1]: r for r in self.build().records}

    def test_checksum_size_and_format_are_read_from_each_file(self):
        records = self.records()
        for name, record in records.items():
            target = self.out / "Lärkan_1_1_arkivpaket_2026-10-15" / record.path
            self.assertEqual(record.digest, hashlib.sha256(target.read_bytes()).hexdigest(), name)
            self.assertEqual(record.size, target.stat().st_size, name)
        self.assertEqual((records["plan.gpkg"].format_name, records["plan.gpkg"].format_version), ("GeoPackage", "1.3"))
        self.assertEqual(records["plan.json"].format_name, "JSON")
        self.assertEqual((records["plankarta.pdf"].format_name, records["plankarta.pdf"].format_version), ("PDF", "1.7"))
        self.assertEqual((records["planbeskrivning.pdf"].format_name, records["planbeskrivning.pdf"].format_version),
                         ("PDF/A", "2B"))
        self.assertEqual(records["planbeskrivning.docx"].format_name, "DOCX")

    def test_files_the_plugin_made_name_the_plugin_as_creator_and_the_others_are_read_from_the_file(self):
        records = self.records()
        self.assertEqual((records["plan.json"].app_name, records["plan.json"].app_version), ("Rita Detaljplan", "0.1.55"))
        self.assertTrue(records["plan.json"].generated)
        self.assertEqual(records["plankarta.pdf"].app_name, "QGIS 4.2")
        self.assertTrue(records["plankarta.pdf"].created.startswith("2026-10-15T12:00:00"))
        self.assertEqual(records["planbeskrivning.pdf"].app_name, "Microsoft Word")
        self.assertEqual((records["planbeskrivning.docx"].app_name, records["planbeskrivning.docx"].app_version),
                         ("Microsoft Office Word", "16.0000"))
        self.assertTrue(records["planbeskrivning.docx"].created.startswith("2026-03-04T10:11:00"))
        self.assertFalse(records["plankarta.pdf"].generated)

    def test_an_unknown_creating_program_is_stated_as_unknown_with_a_note(self):
        bare = make_pdf(self.src / "bar.pdf")
        package = archive.build_package(self.out, "x", [archive.Item(bare)], APP, now=NOW)
        record = package.records[0]
        self.assertEqual(record.app_name, archive.UNKNOWN_APPLICATION)
        self.assertTrue(any("kunde inte läsas" in note for note in record.notes))
        self.assertTrue(record.created)

    def test_files_that_are_not_pdfa_or_not_archive_formats_get_a_note(self):
        package = self.build()
        notes = {r.path.split("/")[-1]: r.notes for r in package.records}
        self.assertTrue(any("inte PDF/A" in n for n in notes["plankarta.pdf"]))
        self.assertTrue(any("PDF/A" in n for n in notes["planbeskrivning.docx"]))
        self.assertFalse([n for n in notes["planbeskrivning.pdf"] if "inte PDF/A" in n], "den är PDF/A")
        self.assertTrue(package.notes)

    def test_pdf_dates_are_read_with_and_without_time(self):
        self.assertTrue(archive._pdf_date("D:20260401103250+02'00'").startswith("2026-04-01T10:32:50"))
        self.assertTrue(archive._pdf_date("D:2026").startswith("2026-01-01T00:00:00"))
        self.assertIsNone(archive._pdf_date("inget datum"))


class PremisTests(ArchiveCase):
    def setUp(self):
        super().setUp()
        self.package = self.build(performer="Eva Planarkitekt")
        self.root_el = self.tree(self.package)

    def test_the_file_is_premis_3_and_points_at_the_final_schema_not_the_draft(self):
        self.assertEqual(self.root_el.tag, f"{{{archive.PREMIS_NS}}}premis")
        self.assertEqual(self.root_el.get("version"), "3.0")
        text = self.package.premis.read_text(encoding="utf-8")
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("premis-v3-0.xsd", text)
        self.assertNotIn("draft", text)

    def test_everything_is_in_one_file_there_is_no_separate_general_file(self):
        self.assertFalse((self.package.folder / "detaljplan.xml").exists())
        self.assertEqual(len(self.root_el.findall("p:object", NS)), 1 + 5, "planen och fem filer")

    def test_the_category_is_given_by_xsi_type_and_there_is_no_objectcategory_element(self):
        types = [o.get(XSI_TYPE) for o in self.root_el.findall("p:object", NS)]
        self.assertEqual(types, ["premis:intellectualEntity"] + ["premis:file"] * 5)
        self.assertEqual(self.root_el.findall(".//p:objectCategory", NS), [], "finns inte i XML-schemat")

    def test_the_plan_is_one_intellectual_entity_with_every_file_as_a_part(self):
        reps = self.entities(self.root_el)
        self.assertEqual(len(reps), 1)
        self.assertEqual([o for o in self.root_el.findall("p:object", NS) if o.get(XSI_TYPE) == "premis:representation"], [],
                         "ingen mellannivå: planen och filerna")
        relation = reps[0].find("p:relationship", NS)
        self.assertEqual(relation.findtext("p:relationshipType", namespaces=NS), "structural")
        self.assertEqual(relation.findtext("p:relationshipSubType", namespaces=NS), "has Part")
        parts = {v.text for v in relation.findall("p:relatedObjectIdentifier/p:relatedObjectIdentifierValue", NS)}
        self.assertEqual(parts, {r.id for r in self.package.records})
        self.assertEqual(reps[0].findtext("p:originalName", namespaces=NS), "Lärkan 1:1")
        self.assertIsNone(reps[0].find("p:objectCharacteristics", NS), "en entitet har inga filegenskaper")

    def test_every_file_points_back_at_the_plan_with_is_part_of(self):
        plan_id = self.entities(self.root_el)[0].findtext("p:objectIdentifier/p:objectIdentifierValue", namespaces=NS)
        for box in self.file_objects(self.root_el):
            relation = box.find("p:relationship", NS)
            self.assertEqual(relation.findtext("p:relationshipType", namespaces=NS), "structural")
            self.assertEqual(relation.findtext("p:relationshipSubType", namespaces=NS), "is Part Of")
            self.assertEqual([v.text for v in relation.findall("p:relatedObjectIdentifier/p:relatedObjectIdentifierValue", NS)],
                             [plan_id])

    def test_every_file_has_everything_the_catalogue_makes_mandatory(self):
        files = self.file_objects(self.root_el)
        self.assertEqual(len(files), 5)
        for box in files:
            for path in ("p:objectIdentifier/p:objectIdentifierValue", "p:originalName",
                         "p:storage/p:contentLocation/p:contentLocationType",
                         "p:storage/p:contentLocation/p:contentLocationValue",
                         "p:objectCharacteristics/p:fixity/p:messageDigestAlgorithm",
                         "p:objectCharacteristics/p:fixity/p:messageDigest", "p:objectCharacteristics/p:size",
                         "p:objectCharacteristics/p:format/p:formatDesignation/p:formatName",
                         "p:objectCharacteristics/p:creatingApplication/p:creatingApplicationName",
                         "p:objectCharacteristics/p:creatingApplication/p:dateCreatedByApplication"):
                self.assertTrue(box.findtext(path, namespaces=NS), path)
            self.assertEqual(box.findtext("p:objectCharacteristics/p:fixity/p:messageDigestAlgorithm", namespaces=NS),
                             "SHA-256")

    def test_the_element_order_is_the_one_the_schema_requires(self):
        def names(box):
            return [child.tag.split("}")[1] for child in box]

        box = self.file_objects(self.root_el)[0]
        self.assertEqual(names(box)[:5], ["objectIdentifier", "objectCharacteristics", "originalName", "storage",
                                          "relationship"])
        self.assertEqual(names(box.find("p:objectCharacteristics", NS)),
                         ["compositionLevel", "fixity", "size", "format", "creatingApplication"])
        event = self.root_el.find("p:event", NS)
        order = names(event)
        self.assertEqual(order[:5], ["eventIdentifier", "eventType", "eventDateTime", "eventDetailInformation",
                                     "eventOutcomeInformation"])
        self.assertLess(order.index("linkingAgentIdentifier"), order.index("linkingObjectIdentifier"),
                        "agenterna före objekten")
        self.assertEqual(names(self.root_el.find("p:agent", NS))[:5],
                         ["agentIdentifier", "agentName", "agentType", "agentVersion", "agentNote"])

    def test_objects_never_link_agents_directly_only_events_do(self):
        for box in self.root_el.findall("p:object", NS):
            self.assertEqual(box.findall("p:linkingAgentIdentifier", NS), [])

    def test_the_location_is_a_relative_uri_inside_the_package(self):
        values = {o.findtext("p:storage/p:contentLocation/p:contentLocationValue", namespaces=NS)
                  for o in self.file_objects(self.root_el)}
        self.assertEqual(values, {"content/plan.gpkg", "content/plan.json", "content/plankarta.pdf",
                                  "content/planbeskrivning.pdf", "content/planbeskrivning.docx"})

    def test_names_with_spaces_are_written_as_uri_escapes_and_checked_the_same_way(self):
        spaced = make_pdf(self.src / "Plan beskrivning åäö.pdf")
        package = archive.build_package(self.out, "x", [archive.Item(spaced)], APP, now=NOW)
        value = self.tree(package).find(".//p:contentLocationValue", NS).text
        self.assertIn("%20", value)
        self.assertTrue(archive.verify_package(package.folder).clean)

    def test_all_identifiers_are_unique_uuids_and_every_reference_points_at_something(self):
        defined = [o.findtext("p:objectIdentifier/p:objectIdentifierValue", namespaces=NS) for o in self.root_el.findall("p:object", NS)]
        defined += [e.findtext("p:eventIdentifier/p:eventIdentifierValue", namespaces=NS) for e in self.root_el.findall("p:event", NS)]
        defined += [a.findtext("p:agentIdentifier/p:agentIdentifierValue", namespaces=NS) for a in self.root_el.findall("p:agent", NS)]
        self.assertEqual(len(defined), len(set(defined)))
        for value in defined:
            self.assertRegex(value, r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        referenced = [e.text for e in self.root_el.iter() if e.tag.endswith("IdentifierValue")]
        self.assertLessEqual(set(referenced), set(defined), "en hänvisning pekar på något som inte finns")

    def test_every_link_exists_in_both_directions(self):
        self.assertEqual(archive.link_problems(self.root_el), [])

    def test_the_events_are_creation_checksums_and_export_with_valid_values_from_the_lists(self):
        events = self.root_el.findall("p:event", NS)
        self.assertEqual([e.findtext("p:eventType", namespaces=NS) for e in events],
                         ["information package creation", "message digest calculation", "exporting"])
        for event in events:
            self.assertEqual(event.findtext("p:eventDateTime", namespaces=NS), archive._iso(NOW))
            self.assertTrue(event.findtext("p:eventDetailInformation/p:eventDetail", namespaces=NS))
            self.assertEqual(event.findtext("p:eventOutcomeInformation/p:eventOutcome", namespaces=NS), "success")
        export = events[2]
        exported = {v.text for v in export.findall("p:linkingObjectIdentifier/p:linkingObjectIdentifierValue", NS)}
        self.assertEqual(exported, {r.id for r in self.package.records if r.generated})
        roles = {v.text for e in events for v in e.findall("p:linkingObjectIdentifier/p:linkingObjectRole", NS)}
        self.assertLessEqual(roles, {"outcome", "source"})

    def test_there_is_no_export_event_when_nothing_was_exported(self):
        package = archive.build_package(self.out, "y", [archive.Item(self.beskrivning)], APP, now=NOW)
        types = [e.findtext("p:eventType", namespaces=NS) for e in self.tree(package).findall("p:event", NS)]
        self.assertNotIn("exporting", types)
        self.assertEqual(archive.link_problems(self.tree(package)), [])

    def test_the_program_is_an_agent_with_its_version_in_its_own_element_and_so_is_the_person(self):
        agents = self.root_el.findall("p:agent", NS)
        self.assertEqual([a.findtext("p:agentType", namespaces=NS) for a in agents], ["software", "person"])
        self.assertEqual(agents[0].findtext("p:agentName", namespaces=NS), "Rita Detaljplan")
        self.assertEqual(agents[0].findtext("p:agentVersion", namespaces=NS), "0.1.55")
        self.assertEqual(agents[1].findtext("p:agentName", namespaces=NS), "Eva Planarkitekt")
        roles = {v.text for e in self.root_el.findall("p:event", NS) for v in e.findall("p:linkingAgentIdentifier/p:linkingAgentRole", NS)}
        self.assertEqual(roles, {"executing program", "implementer"})

    def test_agents_link_back_at_every_event_they_took_part_in(self):
        event_ids = {e.findtext("p:eventIdentifier/p:eventIdentifierValue", namespaces=NS) for e in self.root_el.findall("p:event", NS)}
        for agent in self.root_el.findall("p:agent", NS):
            self.assertEqual({v.text for v in agent.findall("p:linkingEventIdentifier/p:linkingEventIdentifierValue", NS)}, event_ids)

    def test_without_a_person_there_is_only_the_program(self):
        package = self.build()
        root = self.tree(package)
        self.assertEqual([a.findtext("p:agentType", namespaces=NS) for a in root.findall("p:agent", NS)], ["software"])
        self.assertEqual(archive.link_problems(root), [])

    def test_the_program_keeps_the_same_agent_id_from_package_to_package(self):
        self.assertEqual(archive.plugin_agent_id(APP), archive.plugin_agent_id(archive.App("Rita Detaljplan", "9.9.9", APP.homepage)))

    def test_the_agent_id_is_locked_to_the_old_address_so_the_move_to_ritaplan_changes_nothing(self):
        new = archive.App("Rita Detaljplan", "9.9.9", "https://github.com/ritaplan/rita-detaljplan")
        self.assertEqual(archive.plugin_agent_id(new), "c5f7cc2e-961f-5951-8c60-dd4e9e3edd9a")
        self.assertEqual(archive.plugin_agent_id(new), archive.plugin_agent_id(
            archive.App("Rita Detaljplan", "0.0.1", "https://github.com/ericalnemar/rita-detaljplan")), "samma id oavsett vilken adress som anges")

    def test_another_program_gets_an_id_from_its_own_address(self):
        other = archive.App("Annat program", "1", "https://example.org/a")
        self.assertEqual(archive.plugin_agent_id(other), str(archive.uuid.uuid5(archive.uuid.NAMESPACE_URL, "https://example.org/a")))


class PlanDetailsTests(ArchiveCase):
    """Planens uppgifter ligger i ``significantProperties`` på planen (en intellektuell entitet har inga ``objectCharacteristics``)."""

    def details(self, package):
        return self.tree(package).find(
            "p:object/p:significantProperties/p:significantPropertiesExtension/dp:detaljplan", NS)

    def test_the_plans_own_attributes_are_kept_in_their_own_namespace(self):
        package = self.build()
        details = self.details(package)
        self.assertEqual({child.tag.split("}")[1]: child.text for child in details}, PLAN)
        self.assertEqual([child.tag.split("}")[1] for child in details], list(PLAN), "i den ordning de gavs")
        self.assertTrue(all(child.tag.startswith(f"{{{archive.DETALJPLAN_NS}}}") for child in details))
        self.assertEqual(self.tree(package).findtext("p:object/p:significantProperties/p:significantPropertiesType", namespaces=NS),
                         "detaljplan")

    def test_a_plan_without_attributes_gets_no_empty_significant_properties(self):
        package = self.build(plan={})
        self.assertIsNone(self.details(package))
        self.assertIsNone(self.tree(package).find(".//p:significantProperties", NS))

    def test_the_file_is_well_formed_utf8_with_the_swedish_letters_intact(self):
        package = self.build()
        text = package.premis.read_text(encoding="utf-8")
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("Lärkan 1:1</dp:namn>", text)

    def test_the_entity_is_linked_to_the_creation_event_that_lists_it_as_the_outcome(self):
        package = self.build()
        root = self.tree(package)
        box = self.entities(root)[0]
        entity = box.findtext("p:objectIdentifier/p:objectIdentifierValue", namespaces=NS)
        event_id = box.findtext("p:linkingEventIdentifier/p:linkingEventIdentifierValue", namespaces=NS)
        events = {e.findtext("p:eventIdentifier/p:eventIdentifierValue", namespaces=NS): e for e in root.findall("p:event", NS)}
        event = events[event_id]
        self.assertEqual(event.findtext("p:eventType", namespaces=NS), "information package creation")
        outcome = [link.findtext("p:linkingObjectIdentifierValue", namespaces=NS)
                   for link in event.findall("p:linkingObjectIdentifier", NS)
                   if link.findtext("p:linkingObjectRole", namespaces=NS) == "outcome"]
        self.assertEqual(outcome, [entity])


class LinkProblemTests(ArchiveCase):
    """``link_problems`` hittar det som inte hänger ihop, så att kontrollen i sig prövas."""

    def setUp(self):
        super().setUp()
        self.root_el = self.tree(self.build(performer="Eva"))

    def test_a_missing_link_back_from_an_agent_is_found(self):
        agent = self.root_el.find("p:agent", NS)
        agent.remove(agent.find("p:linkingEventIdentifier", NS))
        self.assertTrue(any("Agenten" in p and "saknar länk tillbaka" in p for p in archive.link_problems(self.root_el)))

    def test_a_file_without_is_part_of_is_found(self):
        box = self.file_objects(self.root_el)[0]
        box.remove(box.find("p:relationship", NS))
        self.assertTrue(any("is Part Of" in p for p in archive.link_problems(self.root_el)))

    def test_a_link_to_something_that_does_not_exist_is_found(self):
        event = self.root_el.find("p:event", NS)
        event.find("p:linkingAgentIdentifier/p:linkingAgentIdentifierValue", NS).text = "00000000-0000-0000-0000-000000000000"
        self.assertTrue(any("agent som inte finns" in p for p in archive.link_problems(self.root_el)))

    def test_the_same_id_used_twice_is_found(self):
        ids = self.root_el.findall("p:object/p:objectIdentifier/p:objectIdentifierValue", NS)
        ids[1].text = ids[0].text
        self.assertTrue(any("Samma id" in p for p in archive.link_problems(self.root_el)))


@unittest.skipUnless(LXML is not None and XSD.is_file(), "kräver lxml och LoC:s schema i tests/data")
class SchemaTests(ArchiveCase):
    """Dokumentet ska vara giltigt mot Library of Congress PREMIS 3.0-schema, den fil Boverkets exempel hänvisar till."""

    @classmethod
    def schema(cls):
        if not hasattr(cls, "_schema"):
            cls._schema = LXML.XMLSchema(LXML.parse(str(XSD)))
        return cls._schema

    def errors(self, path):
        schema = self.schema()
        schema.validate(LXML.parse(str(path)))
        return [e.message.replace(f"{{{archive.PREMIS_NS}}}", "") for e in schema.error_log]

    def test_a_package_with_everything_is_valid(self):
        self.assertEqual(self.errors(self.build(performer="Eva Planarkitekt").premis), [])

    def test_a_package_without_a_person_a_plan_or_exported_files_is_valid(self):
        self.assertEqual(self.errors(self.build().premis), [])
        self.assertEqual(self.errors(self.build(plan={}).premis), [])
        only = archive.build_package(self.out, "y", [archive.Item(self.beskrivning)], APP, now=NOW)
        self.assertEqual(self.errors(only.premis), [])

    def test_unknown_creating_program_and_swedish_letters_in_names_are_valid_too(self):
        spaced = make_pdf(self.src / "Plan beskrivning åäö.pdf")
        package = archive.build_package(self.out, "Å Ä Ö", [archive.Item(spaced)], APP, "Ö Ä", NOW, plan=PLAN)
        self.assertEqual(self.errors(package.premis), [])

    def test_the_check_really_checks_an_objectcategory_element_makes_it_invalid(self):
        package = self.build()
        text = package.premis.read_text(encoding="utf-8")
        broken = text.replace("</premis:objectIdentifier>", "</premis:objectIdentifier><premis:objectCategory>file"
                              "</premis:objectCategory>", 1)
        package.premis.write_text(broken, encoding="utf-8")
        self.assertTrue(self.errors(package.premis))

    def test_a_missing_xsi_type_makes_it_invalid(self):
        package = self.build()
        text = package.premis.read_text(encoding="utf-8").replace(' xsi:type="premis:intellectualEntity"', "", 1)
        package.premis.write_text(text, encoding="utf-8")
        self.assertTrue(any("abstract" in e for e in self.errors(package.premis)))


class SchemasFolderTests(ArchiveCase):
    """Schemana som följer med i paketet (``schemas/``), så att det går att validera utan internet."""

    def test_the_premis_schema_and_the_schema_for_the_plans_details_are_in_the_package(self):
        package = self.build()
        found = sorted(p.name for p in (package.folder / "schemas").iterdir())
        self.assertEqual(found, ["detaljplan-1.xsd", "premis-v3-0.xsd"])
        for name in found:
            self.assertEqual((package.folder / "schemas" / name).read_bytes(), (SCHEMAS / name).read_bytes(),
                             "oförändrade kopior av pluginets scheman")

    def test_without_plan_details_only_the_premis_schema_follows(self):
        package = self.build(plan={})
        self.assertEqual(sorted(p.name for p in (package.folder / "schemas").iterdir()), ["premis-v3-0.xsd"])

    def test_the_schema_location_names_the_final_premis_schema_and_our_own_schema_by_a_path_inside_the_package(self):
        package = self.build()
        location = self.tree(package).get(f"{{{archive.XSI_NS}}}schemaLocation").split()
        self.assertEqual(location[:2], [archive.PREMIS_NS, "http://www.loc.gov/standards/premis/v3/premis-v3-0.xsd"])
        self.assertEqual(location[2], archive.DETALJPLAN_NS)
        self.assertTrue((package.premis.parent / location[3]).resolve().is_file(), "sökvägen leder till schemat i paketet")

    def test_no_schema_for_the_details_is_named_when_there_are_none(self):
        package = self.build(plan={})
        self.assertEqual(len(self.tree(package).get(f"{{{archive.XSI_NS}}}schemaLocation").split()), 2)

    def test_the_schemas_folder_is_not_reported_as_extra_but_other_extra_files_still_are(self):
        package = self.build()
        (package.folder / "content" / "ny.txt").write_text("hej", encoding="utf-8")
        self.assertEqual(archive.verify_package(package.folder).extra, ["content/ny.txt"])

    def test_a_package_without_the_schemas_folder_from_an_earlier_version_is_still_clean(self):
        package = self.build()
        archive.shutil.rmtree(package.folder / "schemas")
        self.assertTrue(archive.verify_package(package.folder).clean)


@unittest.skipUnless(LXML is not None and DP_XSD.is_file(), "kräver lxml och schemat för planens uppgifter")
class DetaljplanSchemaTests(ArchiveCase):
    """Schemat för planens uppgifter (``detaljplan-1.xsd``) och att det stämmer med det pluginet skriver."""

    @classmethod
    def schema(cls):
        if not hasattr(cls, "_schema"):
            cls._schema = LXML.XMLSchema(LXML.parse(str(DP_XSD)))
        return cls._schema

    def details(self, package):
        tree = LXML.parse(str(package.premis))
        found = tree.xpath("//dp:detaljplan", namespaces={"dp": archive.DETALJPLAN_NS})
        self.assertEqual(len(found), 1)
        return found[0]

    def test_the_plan_details_the_plugin_writes_are_valid_against_the_schema(self):
        package = self.build()
        self.assertTrue(self.schema().validate(self.details(package)), self.schema().error_log)

    def test_every_field_with_a_date_as_an_iso_date_and_all_the_codes_are_valid(self):
        plan = dict(PLAN, datumStatusforandring="2026-08-15", anvandbarhet="god")
        package = self.build(plan=plan)
        self.assertTrue(self.schema().validate(self.details(package)), self.schema().error_log)

    def test_the_elements_come_in_the_schemas_order_whatever_order_they_were_given_in(self):
        scrambled = {"kommunkod": "0482", "kommun": "Eskilstuna", "anvandbarhet": "god", "typ": "Detaljplan",
                     "datumStatusforandring": "2026-08-15", "namn": "Lärkan 1:1", "beteckning": "DP 123"}
        package = self.build(plan=scrambled)
        names = [child.tag.split("}")[1] for child in self.details(package)]
        self.assertEqual(names, ["beteckning", "namn", "datumStatusforandring", "typ", "anvandbarhet", "kommun", "kommunkod"])
        self.assertTrue(self.schema().validate(self.details(package)), self.schema().error_log)

    def test_a_date_that_is_not_an_iso_date_is_refused(self):
        package = self.build(plan=dict(PLAN, datumStatusforandring="PyQt6.QtCore.QDate(2026, 9, 1)"))
        self.assertFalse(self.schema().validate(self.details(package)))
        self.assertIn("datumStatusforandring", str(self.schema().error_log))

    def test_a_municipality_code_must_have_four_digits(self):
        package = self.build(plan=dict(PLAN, kommunkod="12"))
        self.assertFalse(self.schema().validate(self.details(package)))

    def test_an_element_the_schema_does_not_know_is_refused(self):
        package = self.build(plan=dict(PLAN, okant="x"))
        self.assertFalse(self.schema().validate(self.details(package)))

    def test_a_plan_with_only_a_name_is_valid_since_every_element_is_optional(self):
        package = self.build(plan={"namn": "Bara namn"})
        self.assertTrue(self.schema().validate(self.details(package)), self.schema().error_log)


class VerifyTests(ArchiveCase):
    def setUp(self):
        super().setUp()
        self.package = self.build()

    def make_legacy(self):
        """Gör paketet till ett från 0.1.55-0.1.59: objectCategory i stället för xsi:type, och en egen detaljplan.xml."""
        root = ET.parse(self.package.premis).getroot()
        for box in root.findall("p:object", NS):
            kind = box.attrib.pop(XSI_TYPE).split(":")[1]
            category = ET.Element(f"{{{archive.PREMIS_NS}}}objectCategory")
            category.text = kind
            box.insert(1, category)
        self.package.premis.write_text(archive.to_xml(root), encoding="utf-8")
        (self.package.folder / "detaljplan.xml").write_text("<premis/>", encoding="utf-8")

    def test_an_untouched_package_is_clean(self):
        report = archive.verify_package(self.package.folder)
        self.assertTrue(report.clean, report.text())
        self.assertEqual(len(report.ok), 5)
        self.assertEqual(report.notes, [])
        self.assertIn("5 filer är oförändrade", report.text())

    def test_a_changed_file_is_found(self):
        (self.package.folder / "content" / "plan.json").write_text("ändrad", encoding="utf-8")
        report = archive.verify_package(self.package.folder)
        self.assertEqual(report.changed, ["content/plan.json"])
        self.assertFalse(report.clean)
        self.assertIn("Ändrade", report.text())

    def test_a_missing_file_is_found(self):
        (self.package.folder / "content" / "plankarta.pdf").unlink()
        self.assertEqual(archive.verify_package(self.package.folder).missing, ["content/plankarta.pdf"])

    def test_the_metadata_file_itself_is_not_reported_as_extra(self):
        self.assertEqual(archive.verify_package(self.package.folder).extra, [])

    def test_a_file_added_afterwards_is_reported_as_extra(self):
        (self.package.folder / "content" / "ny.txt").write_text("hej", encoding="utf-8")
        self.assertEqual(archive.verify_package(self.package.folder).extra, ["content/ny.txt"])

    def test_a_path_that_leaves_the_package_is_not_followed(self):
        text = self.package.premis.read_text(encoding="utf-8").replace("content/plan.json", "../ut/hemlig.txt")
        self.package.premis.write_text(text, encoding="utf-8")
        report = archive.verify_package(self.package.folder)
        self.assertTrue(any("ogiltig sökväg" in u for u in report.unchecked))

    def test_an_unknown_checksum_algorithm_is_reported_as_unchecked(self):
        text = self.package.premis.read_text(encoding="utf-8").replace("<premis:messageDigestAlgorithm>SHA-256", "<premis:messageDigestAlgorithm>Tiger", 1)
        self.package.premis.write_text(text, encoding="utf-8")
        self.assertEqual(len(archive.verify_package(self.package.folder).unchecked), 1)

    def test_a_folder_that_is_not_a_package_and_a_broken_file_are_explained(self):
        with self.assertRaisesRegex(archive.ArchiveError, "Hittar ingen metadata/PREMIS.xml"):
            archive.verify_package(self.src)
        self.package.premis.write_text("<inte xml", encoding="utf-8")
        with self.assertRaisesRegex(archive.ArchiveError, "går inte att läsa"):
            archive.verify_package(self.package.folder)

    def test_broken_links_in_the_metadata_are_reported_as_notes_without_making_the_files_count_as_changed(self):
        root = ET.parse(self.package.premis).getroot()
        agent = root.find("p:agent", NS)
        agent.remove(agent.find("p:linkingEventIdentifier", NS))
        self.package.premis.write_text(archive.to_xml(root), encoding="utf-8")
        report = archive.verify_package(self.package.folder)
        self.assertTrue(report.clean, "filerna är oförändrade")
        self.assertTrue(any("saknar länk tillbaka" in note for note in report.notes), report.notes)
        self.assertIn("saknar länk tillbaka", report.text())

    def test_a_package_from_before_0_1_60_is_still_checked_and_the_old_metadata_is_pointed_out(self):
        self.make_legacy()
        report = archive.verify_package(self.package.folder)
        self.assertTrue(report.clean, report.text())
        self.assertEqual(len(report.ok), 5)
        self.assertEqual(report.extra, [], "den gamla detaljplan.xml hör till paketet")
        self.assertTrue(any("äldre version" in note for note in report.notes), report.notes)

    def test_an_old_package_missing_its_general_file_is_reported(self):
        self.make_legacy()
        (self.package.folder / "detaljplan.xml").unlink()
        self.assertEqual(archive.verify_package(self.package.folder).missing, ["detaljplan.xml"])


if __name__ == "__main__":
    unittest.main()
