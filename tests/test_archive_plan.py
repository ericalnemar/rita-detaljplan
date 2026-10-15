"""Arkivpaketet ur en riktig plan: dialogen, exporten av GeoPackage, leveransfil och layout, och menyvalen (QGIS)."""
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS  # noqa: E402

if HAVE_QGIS:
    import rita_detaljplan
    from rita_detaljplan.core import archive
    from rita_detaljplan.gui import archive_dialog
    from rita_detaljplan.gui.archive_dialog import ArchiveDialog, ArchiveOptions, build_archive
    from test_archive import make_docx, make_pdf
    from test_toolbar import GuiCase
else:  # pragma: no cover
    GuiCase = unittest.TestCase


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class ArchivePlanCase(GuiCase):
    def setUp(self):
        super().setUp()
        self.build_plan()
        self.out = self.dir / "arkiv"
        self.out.mkdir()
        self.docs = self.dir / "handlingar"
        self.docs.mkdir()
        self.beskrivning = make_pdf(self.docs / "planbeskrivning.pdf", pdfa="2B", info="/Producer (Microsoft Word)")
        self.word = make_docx(self.docs / "planbeskrivning.docx")

    def finish_editing(self):
        for layer in self.layers.values():
            layer.commitChanges()
        self.assertFalse(self.controller.editing)


class BuildArchiveTests(ArchivePlanCase):
    def test_the_plan_file_is_found_and_a_plan_without_layers_has_none(self):
        self.assertEqual(self.controller.plan_file().resolve(), self.gpkg.resolve())
        with mock.patch.object(self.controller, "layer", return_value=None):
            self.assertIsNone(self.controller.plan_file())

    def test_a_copy_of_the_plan_the_delivery_file_and_the_documents_end_up_in_the_package(self):
        self.finish_editing()
        package = build_archive(self.controller, ArchiveOptions(self.out, documents=[self.beskrivning, self.word]),
                                archive.App("Rita Detaljplan", "0.1.55", "https://example.org"))
        paths = sorted(r.path for r in package.records)
        self.assertEqual(paths, ["content/detaljplan.gpkg", "content/detaljplan.json", "content/planbeskrivning.docx",
                                 "content/planbeskrivning.pdf"])
        records = {r.path: r for r in package.records}
        self.assertEqual(records["content/detaljplan.gpkg"].format_name, "GeoPackage")
        self.assertEqual(records["content/detaljplan.json"].app_name, "Rita Detaljplan")
        self.assertTrue(records["content/detaljplan.json"].generated)
        self.assertEqual(records["content/planbeskrivning.pdf"].format_name, "PDF/A")
        self.assertFalse(records["content/planbeskrivning.pdf"].generated)
        self.assertTrue(archive.verify_package(package.folder).clean)

    def test_there_is_no_automatic_export_of_a_layout_as_pdf(self):
        self.assertFalse(hasattr(archive_dialog, "export_layout_pdf"))
        self.assertNotIn("layout", ArchiveOptions.__dataclass_fields__)

    def test_the_geopackage_copy_holds_the_saved_plan_and_the_original_is_untouched(self):
        self.finish_editing()
        before = self.gpkg.stat().st_mtime_ns
        package = build_archive(self.controller, ArchiveOptions(self.out, delivery_file=False))
        copy = package.folder / "content" / "detaljplan.gpkg"
        con = sqlite3.connect(copy)
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM detaljplan").fetchone()[0], 1)
            self.assertEqual(con.execute("PRAGMA application_id").fetchone()[0], 1196444487)
        finally:
            con.close()
        self.assertEqual(self.gpkg.stat().st_mtime_ns, before)

    def test_the_delivery_file_is_the_plans_export(self):
        self.finish_editing()
        package = build_archive(self.controller, ArchiveOptions(self.out, geopackage=False))
        data = json.loads((package.folder / "content" / "detaljplan.json").read_text(encoding="utf-8"))
        self.assertEqual(data, self.controller.export_ngp())

    def test_the_file_names_follow_the_plan_name(self):
        self.finish_editing()
        self.controller.set_plan_values({"namn": "Lärkan 1:1"})
        self.controller.layer("detaljplan").commitChanges()
        package = build_archive(self.controller, ArchiveOptions(self.out, geopackage=False))
        self.assertEqual(package.folder.name.split("_arkivpaket")[0], "Lärkan_1_1")
        self.assertTrue((package.folder / "content" / "Lärkan_1_1.json").exists())

    def test_the_plans_own_attributes_go_into_the_general_file(self):
        self.controller.set_plan_values({"namn": "Lärkan 1:1", "beteckning": "DP 123", "status": "Laga kraft",
                                         "typ": "Detaljplan", "kommun": "Eskilstuna"})
        self.finish_editing()
        package = build_archive(self.controller, ArchiveOptions(self.out, geopackage=False))
        from xml.etree import ElementTree as ET
        ns = {"p": archive.PREMIS_NS}
        details = ET.parse(package.general).getroot().find(
            "p:object/p:objectCharacteristics/p:objectCharacteristicsExtension/detaljplan", ns)
        found = {child.tag: child.text for child in details}
        self.assertEqual(found["namn"], "Lärkan 1:1")
        self.assertEqual((found["beteckning"], found["status"], found["typ"]), ("DP 123", "Laga kraft", "Detaljplan"))
        from rita_detaljplan.core import kommuner
        self.assertEqual((found["kommun"], found["kommunkod"]), ("Eskilstuna", kommuner.by_name("Eskilstuna").kod))
        self.assertNotIn("syfte", found, "bara de sökbara attributen, inte syftet")
        self.assertNotIn("datumLagakraft", found, "ifyllt först när planen vunnit laga kraft")

    def test_the_plan_attributes_leave_out_what_is_empty_and_work_without_a_plan_area(self):
        self.finish_editing()
        self.assertNotIn("namn", archive_dialog.plan_metadata(self.controller))
        with mock.patch.object(self.controller, "plan_feature", return_value=None):
            self.assertEqual(archive_dialog.plan_metadata(self.controller), {})

    def test_a_plan_in_a_database_cannot_be_copied_as_a_file_but_the_delivery_file_has_it_all(self):
        self.finish_editing()
        with mock.patch.object(self.controller, "plan_file", return_value=None):
            with self.assertRaisesRegex(archive.ArchiveError, "databas"):
                build_archive(self.controller, ArchiveOptions(self.out))
            package = build_archive(self.controller, ArchiveOptions(self.out, geopackage=False))
        self.assertEqual([r.path for r in package.records], ["content/detaljplan.json"])

    def test_progress_is_reported_step_by_step(self):
        self.finish_editing()
        steps = []
        build_archive(self.controller, ArchiveOptions(self.out), progress=steps.append)
        self.assertTrue(any("GeoPackage" in s for s in steps))
        self.assertIn("Skriver bevarandemetadata", steps)


class ArchiveDialogTests(ArchivePlanCase):
    def dialog(self):
        dialog = ArchiveDialog(self.controller)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_dialog_starts_with_the_plan_and_the_delivery_file_chosen(self):
        dialog = self.dialog()
        self.assertEqual(dialog.windowTitle(), "Skapa arkivpaket")
        self.assertTrue(dialog.chk_gpkg.isChecked() and dialog.chk_json.isChecked())
        self.assertEqual(dialog.ok.text(), "Skapa paket")

    def test_it_refuses_while_the_plan_is_being_edited(self):
        dialog = self.dialog()
        dialog.folder.setText(str(self.out))
        self.assertFalse(dialog.ok.isEnabled())
        self.assertIn("redigeras", dialog.hint.text())
        self.finish_editing()
        dialog._update()
        self.assertTrue(dialog.ok.isEnabled())
        self.assertEqual(dialog.hint.text(), "")

    def test_it_needs_a_folder_that_exists_and_something_to_put_in_it(self):
        self.finish_editing()
        dialog = self.dialog()
        dialog.folder.setText(str(self.out / "finns_inte"))
        self.assertFalse(dialog.ok.isEnabled())
        self.assertIn("mapp som finns", dialog.hint.text())
        dialog.folder.setText(str(self.out))
        dialog.chk_gpkg.setChecked(False)
        dialog.chk_json.setChecked(False)
        self.assertFalse(dialog.ok.isEnabled())
        self.assertIn("minst en fil", dialog.hint.text())
        dialog.add_documents([self.beskrivning])
        self.assertTrue(dialog.ok.isEnabled())

    def test_the_dialog_does_not_offer_to_export_a_layout_only_files_the_user_adds(self):
        self.finish_editing()
        dialog = self.dialog()
        self.assertFalse(hasattr(dialog, "chk_map"))
        self.assertFalse(hasattr(dialog, "layouts"))
        self.assertFalse(hasattr(dialog.options(), "layout"))

    def test_the_dialog_says_that_pdfa_is_up_to_the_user_and_points_to_verapdf(self):
        from qgis.PyQt.QtWidgets import QLabel
        texts = " ".join(label.text() for label in self.dialog().findChildren(QLabel))
        self.assertIn("inga filer till PDF/A", texts)
        self.assertIn("PDF/A-validerare", texts)
        self.assertNotIn("veraPDF", texts, "dialogen pekar inte ut en enskild produkt")

    def test_documents_can_be_added_and_removed_and_a_pdf_that_is_not_pdfa_is_pointed_out(self):
        self.finish_editing()
        plain = make_pdf(self.docs / "plankarta.pdf")
        dialog = self.dialog()
        dialog.folder.setText(str(self.out))
        dialog.add_documents([plain, self.beskrivning, plain])
        self.assertEqual(dialog.list.count(), 2, "samma fil läggs inte till två gånger")
        self.assertEqual(dialog.documents, [plain, self.beskrivning])
        self.assertIn("plankarta.pdf: Filen är inte PDF/A", dialog.hint.text())
        self.assertNotIn("planbeskrivning.pdf", dialog.hint.text())
        dialog.list.setCurrentRow(0)
        dialog.btn_remove.click()
        self.assertEqual(dialog.documents, [self.beskrivning])
        self.assertEqual(dialog.hint.text(), "")

    def test_the_chosen_files_are_added_through_the_file_dialog(self):
        dialog = self.dialog()
        with mock.patch.object(archive_dialog.QFileDialog, "getOpenFileNames",
                               return_value=([str(self.beskrivning), str(self.word)], "")):
            dialog.btn_add.click()
        self.assertEqual([p.name for p in dialog.documents], ["planbeskrivning.pdf", "planbeskrivning.docx"])

    def test_the_options_carry_everything_chosen(self):
        dialog = self.dialog()
        dialog.folder.setText(str(self.out))
        dialog.chk_gpkg.setChecked(False)
        dialog.performer.setText("  Eva  ")
        dialog.add_documents([self.beskrivning])
        options = dialog.options()
        self.assertEqual((options.folder, options.geopackage, options.delivery_file, options.performer),
                         (self.out, False, True, "Eva"))
        self.assertEqual(options.documents, [self.beskrivning])

    def test_a_plan_in_a_database_cannot_choose_the_geopackage(self):
        with mock.patch.object(self.controller, "plan_file", return_value=None):
            dialog = self.dialog()
        self.assertFalse(dialog.chk_gpkg.isEnabled())
        self.assertFalse(dialog.chk_gpkg.isChecked())


class PluginArchiveTests(ArchivePlanCase):
    def setUp(self):
        super().setUp()
        self.plugin = rita_detaljplan.classFactory(self.iface)
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)

    def test_the_menu_has_the_two_entries(self):
        texts = [a.text() for a in self.plugin.actions]
        self.assertIn("Skapa arkivpaket…", texts)
        self.assertIn("Kontrollera arkivpaket…", texts)

    def test_without_a_plan_area_it_says_so(self):
        self.plugin.controller.layer("detaljplan").selectAll()
        for feature in list(self.plugin.controller.layer("detaljplan").getFeatures()):
            self.plugin.controller.layer("detaljplan").deleteFeature(feature.id())
        with mock.patch("rita_detaljplan.plugin.ArchiveDialog") as dialog_cls:
            self.plugin.open_archive()
        dialog_cls.assert_not_called()
        self.assertTrue(any("Rita planområdet först" in m for m in self.messages()))

    def test_creating_a_package_reports_what_was_made_and_what_to_think_about(self):
        package = archive.Package(self.out / "p", self.out / "p" / "metadata" / "PREMIS.xml",
                                  self.out / "p" / "detaljplan.xml", [
            archive.Record("1", "a", "a.pdf", 1, "x", "PDF", None, "Q", None, "t", False, ["Filen är inte PDF/A."])])
        with mock.patch("rita_detaljplan.plugin.ArchiveDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.build_archive", return_value=package) as build:
            dialog_cls.return_value.exec.return_value = True
            self.plugin.open_archive()
        build.assert_called_once()
        messages = self.messages()
        self.assertTrue(any("är skapat med 1 filer" in m for m in messages), messages)
        self.assertTrue(any("inte PDF/A" in m for m in messages), messages)

    def test_a_cancelled_dialog_makes_nothing(self):
        with mock.patch("rita_detaljplan.plugin.ArchiveDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.build_archive") as build:
            dialog_cls.return_value.exec.return_value = False
            self.plugin.open_archive()
        build.assert_not_called()

    def test_a_failure_is_shown_as_an_error_message(self):
        with mock.patch("rita_detaljplan.plugin.ArchiveDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.build_archive", side_effect=archive.ArchiveError("Disken är full")):
            dialog_cls.return_value.exec.return_value = True
            self.plugin.open_archive()
        self.assertEqual(len(self.criticals()), 1)

    def test_verifying_shows_the_result_in_a_dialog(self):
        self.finish_editing()
        package = build_archive(self.controller, ArchiveOptions(self.out))
        (package.folder / "content" / "detaljplan.json").write_text("ändrad", encoding="utf-8")
        with mock.patch("rita_detaljplan.plugin.QFileDialog.getExistingDirectory", return_value=str(package.folder)), \
                mock.patch("rita_detaljplan.plugin.QMessageBox") as box_cls:
            self.plugin.verify_archive()
        box = box_cls.return_value
        self.assertIn("skiljer sig", box.setText.call_args.args[0])
        self.assertIn("content/detaljplan.json", box.setInformativeText.call_args.args[0])
        box.exec.assert_called_once()

    def test_verifying_a_folder_that_is_not_a_package_is_explained(self):
        with mock.patch("rita_detaljplan.plugin.QFileDialog.getExistingDirectory", return_value=str(self.out)), \
                mock.patch("rita_detaljplan.plugin.QMessageBox") as box_cls:
            self.plugin.verify_archive()
        box_cls.assert_not_called()
        self.assertTrue(any("Hittar ingen metadata/PREMIS.xml" in m for m in self.messages()))

    def test_cancelling_the_folder_choice_does_nothing(self):
        with mock.patch("rita_detaljplan.plugin.QFileDialog.getExistingDirectory", return_value=""), \
                mock.patch("rita_detaljplan.plugin.QMessageBox") as box_cls:
            self.plugin.verify_archive()
        box_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
