"""Arkivpaket: filer, PREMIS-metadata enligt Boverkets mallar och kontroll av ett paket i efterhand (utan QGIS)."""
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# modulen importeras direkt så att testerna går utan QGIS
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("archive_under_test", ROOT / "rita_detaljplan" / "core" / "archive.py")
archive = importlib.util.module_from_spec(_spec)
sys.modules["archive_under_test"] = archive
_spec.loader.exec_module(archive)

NS = {"p": archive.PREMIS_NS}
APP = archive.App("Rita Detaljplan", "0.1.55", "https://github.com/ericalnemar/rita-detaljplan")
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
        """metadata/PREMIS.xml: filerna, händelserna och aktörerna."""
        return ET.parse(package.premis).getroot()

    def general_tree(self, package):
        """detaljplan.xml: planen som helhet."""
        return ET.parse(package.general).getroot()

    def file_objects(self, root):
        return [o for o in root.findall("p:object", NS) if o.findtext("p:objectCategory", namespaces=NS) == "file"]


class PackageTests(ArchiveCase):
    def test_the_package_follows_the_boverket_picture_general_metadata_in_the_root_files_in_content(self):
        package = self.build()
        self.assertEqual(package.folder, self.out / "Lärkan_1_1_arkivpaket_2026-10-15")
        found = sorted(p.relative_to(package.folder).as_posix() for p in package.folder.rglob("*") if p.is_file())
        self.assertEqual(found, ["content/plan.gpkg", "content/plan.json", "content/planbeskrivning.docx",
                                 "content/planbeskrivning.pdf", "content/plankarta.pdf", "detaljplan.xml",
                                 "metadata/PREMIS.xml"])
        self.assertEqual(package.premis, package.folder / "metadata" / "PREMIS.xml")
        self.assertEqual(package.general, package.folder / "detaljplan.xml")

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

    def test_the_file_is_premis_3_in_the_boverket_layout(self):
        self.assertEqual(self.root_el.tag, f"{{{archive.PREMIS_NS}}}premis")
        self.assertEqual(self.root_el.get("version"), "3.0")
        text = self.package.premis.read_text(encoding="utf-8")
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("premis-3-0-draft.xsd", text)

    def test_the_plan_is_one_representation_in_the_general_file_with_every_file_as_a_part(self):
        general = self.general_tree(self.package)
        self.assertEqual(general.get("version"), "3.0")
        reps = general.findall("p:object", NS)
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0].findtext("p:objectCategory", namespaces=NS), "representation")
        self.assertEqual([o for o in self.root_el.findall("p:object", NS)
                          if o.findtext("p:objectCategory", namespaces=NS) == "representation"], [],
                         "filerna beskrivs i metadata/PREMIS.xml, helheten i detaljplan.xml")
        relation = reps[0].find("p:relationship", NS)
        self.assertEqual(relation.findtext("p:relationshipType", namespaces=NS), "structural")
        self.assertEqual(relation.findtext("p:relationshipSubType", namespaces=NS), "has Part")
        parts = {v.text for v in relation.findall("p:relatedObjectIdentifier/p:relatedObjectIdentifierValue", NS)}
        self.assertEqual(parts, {r.id for r in self.package.records})

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

    def test_the_element_order_inside_a_file_is_the_same_as_in_the_boverket_template(self):
        box = self.file_objects(self.root_el)[0]
        order = [child.tag.split("}")[1] for child in box]
        self.assertEqual(order[:5], ["objectIdentifier", "objectCategory", "originalName", "storage",
                                     "objectCharacteristics"])
        characteristics = [c.tag.split("}")[1] for c in box.find("p:objectCharacteristics", NS)]
        self.assertEqual(characteristics, ["compositionLevel", "fixity", "size", "format", "creatingApplication"])

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
        general = self.general_tree(self.package)
        ids = [e.text for root in (self.root_el, general) for e in root.iter() if e.tag.endswith("IdentifierValue")]
        defined = [o.findtext("p:objectIdentifier/p:objectIdentifierValue", namespaces=NS)
                   for root in (self.root_el, general) for o in root.findall("p:object", NS)]
        defined += [e.findtext("p:eventIdentifier/p:eventIdentifierValue", namespaces=NS) for e in self.root_el.findall("p:event", NS)]
        defined += [a.findtext("p:agentIdentifier/p:agentIdentifierValue", namespaces=NS) for a in self.root_el.findall("p:agent", NS)]
        self.assertEqual(len(defined), len(set(defined)))
        for value in defined:
            self.assertRegex(value, r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        self.assertLessEqual(set(ids), set(defined), "en hänvisning pekar på något som inte finns")

    def test_object_and_event_point_at_each_other_in_both_directions(self):
        objects = self.root_el.findall("p:object", NS) + self.general_tree(self.package).findall("p:object", NS)
        events = {e.findtext("p:eventIdentifier/p:eventIdentifierValue", namespaces=NS): e
                  for e in self.root_el.findall("p:event", NS)}
        for box in objects:
            object_id = box.findtext("p:objectIdentifier/p:objectIdentifierValue", namespaces=NS)
            for link in box.findall("p:linkingEventIdentifier/p:linkingEventIdentifierValue", NS):
                back = [v.text for v in events[link.text].findall("p:linkingObjectIdentifier/p:linkingObjectIdentifierValue", NS)]
                self.assertIn(object_id, back)
        for event_id, event in events.items():
            for link in event.findall("p:linkingObjectIdentifier/p:linkingObjectIdentifierValue", NS):
                box = next(o for o in objects if o.findtext("p:objectIdentifier/p:objectIdentifierValue", namespaces=NS) == link.text)
                self.assertIn(event_id, [v.text for v in box.findall("p:linkingEventIdentifier/p:linkingEventIdentifierValue", NS)])

    def test_the_events_are_creation_checksums_and_export_with_valid_values_from_the_lists(self):
        events = self.root_el.findall("p:event", NS)
        self.assertEqual([e.findtext("p:eventType", namespaces=NS) for e in events],
                         ["information package creation", "message digest calculation", "exporting"])
        for event in events:
            self.assertEqual(event.findtext("p:eventDateTime", namespaces=NS), archive._iso(NOW))
            self.assertTrue(event.findtext("p:eventDetailInformation/p:eventDetail", namespaces=NS))
        export = events[2]
        exported = {v.text for v in export.findall("p:linkingObjectIdentifier/p:linkingObjectIdentifierValue", NS)}
        self.assertEqual(exported, {r.id for r in self.package.records if r.generated})
        roles = {v.text for e in events for v in e.findall("p:linkingObjectIdentifier/p:linkingObjectRole", NS)}
        self.assertLessEqual(roles, {"outcome", "source"})

    def test_there_is_no_export_event_when_nothing_was_exported(self):
        package = archive.build_package(self.out, "y", [archive.Item(self.beskrivning)], APP, now=NOW)
        types = [e.findtext("p:eventType", namespaces=NS) for e in self.tree(package).findall("p:event", NS)]
        self.assertNotIn("exporting", types)

    def test_the_program_is_an_agent_and_so_is_the_person_who_made_the_package(self):
        agents = self.root_el.findall("p:agent", NS)
        self.assertEqual([a.findtext("p:agentType", namespaces=NS) for a in agents], ["software", "person"])
        self.assertEqual(agents[0].findtext("p:agentName", namespaces=NS), "Rita Detaljplan 0.1.55")
        self.assertEqual(agents[1].findtext("p:agentName", namespaces=NS), "Eva Planarkitekt")
        roles = {v.text for e in self.root_el.findall("p:event", NS) for v in e.findall("p:linkingAgentIdentifier/p:linkingAgentRole", NS)}
        self.assertEqual(roles, {"executing program", "implementer"})

    def test_without_a_person_there_is_only_the_program(self):
        package = self.build()
        self.assertEqual([a.findtext("p:agentType", namespaces=NS) for a in self.tree(package).findall("p:agent", NS)],
                         ["software"])

    def test_the_program_keeps_the_same_agent_id_from_package_to_package(self):
        self.assertEqual(archive.plugin_agent_id(APP), archive.plugin_agent_id(archive.App("Rita Detaljplan", "9.9.9", APP.homepage)))


class GeneralMetadataTests(ArchiveCase):
    def details(self, package):
        return self.general_tree(package).find("p:object/p:objectCharacteristics/p:objectCharacteristicsExtension/detaljplan", NS)

    def test_the_general_file_carries_the_plans_own_attributes(self):
        package = self.build()
        details = self.details(package)
        self.assertEqual({child.tag: child.text for child in details}, PLAN)
        self.assertEqual([child.tag for child in details], list(PLAN), "i den ordning de gavs")

    def test_a_plan_without_attributes_gets_no_empty_extension(self):
        package = self.build(plan={})
        self.assertIsNone(self.details(package))
        self.assertIsNone(self.general_tree(package).find(".//p:objectCharacteristics", NS))

    def test_the_general_file_is_well_formed_utf8_with_the_swedish_letters_intact(self):
        package = self.build()
        text = package.general.read_text(encoding="utf-8")
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("<namn>Lärkan 1:1</namn>", text)

    def test_the_representation_is_linked_to_the_creation_event_that_lists_it_as_the_outcome(self):
        package = self.build()
        box = self.general_tree(package).find("p:object", NS)
        representation = box.findtext("p:objectIdentifier/p:objectIdentifierValue", namespaces=NS)
        event_id = box.findtext("p:linkingEventIdentifier/p:linkingEventIdentifierValue", namespaces=NS)
        events = {e.findtext("p:eventIdentifier/p:eventIdentifierValue", namespaces=NS): e
                  for e in self.tree(package).findall("p:event", NS)}
        event = events[event_id]
        self.assertEqual(event.findtext("p:eventType", namespaces=NS), "information package creation")
        outcome = [link.findtext("p:linkingObjectIdentifierValue", namespaces=NS)
                   for link in event.findall("p:linkingObjectIdentifier", NS)
                   if link.findtext("p:linkingObjectRole", namespaces=NS) == "outcome"]
        self.assertEqual(outcome, [representation])


class VerifyTests(ArchiveCase):
    def setUp(self):
        super().setUp()
        self.package = self.build()

    def test_an_untouched_package_is_clean(self):
        report = archive.verify_package(self.package.folder)
        self.assertTrue(report.clean, report.text())
        self.assertEqual(len(report.ok), 5)
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

    def test_a_missing_general_file_is_reported(self):
        self.package.general.unlink()
        self.assertEqual(archive.verify_package(self.package.folder).missing, ["detaljplan.xml"])

    def test_the_metadata_files_themselves_are_not_reported_as_extra(self):
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


if __name__ == "__main__":
    unittest.main()
