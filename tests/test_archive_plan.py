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


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class NgpArchiveBoxTests(unittest.TestCase):
    """Skapa arkivpaket som en egen ruta i dialogen Leverans och export, som leverans och JSON-fil."""

    @classmethod
    def setUpClass(cls):
        from qgis_app import get_app
        cls.app = get_app()

    def dialog(self, offer_archive=True, config=None):
        from rita_detaljplan.core import ngp_client as ngp
        from rita_detaljplan.gui.ngp_dialog import NgpDialog, NgpRequest
        holder = {"config": config or ngp.NgpConfig("ver", ngp.VER_BASE, ngp.VER_TOKEN, "cfg")}
        dialog = NgpDialog(NgpRequest("Kv Väktaren", "Eskilstuna", "0484", 0, 0, False), lambda: holder["config"],
                           offer_archive=offer_archive)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_box_exists_only_when_the_archive_can_be_made(self):
        self.assertFalse(self.dialog().archive_box.isHidden())
        self.assertTrue(self.dialog(offer_archive=False).archive_box.isHidden())

    def test_it_is_a_radio_button_with_an_explanation_like_the_other_two(self):
        dialog = self.dialog()
        self.assertEqual(dialog.archive.text(), "Skapa arkivpaket")
        self.assertIn("Inget levereras till NGP", dialog.archive_info.text())
        self.assertIn("arkivpaket", dialog.archive_info.text())
        self.assertIsNot(dialog.archive_box, dialog.file.parentWidget())

    def test_there_is_no_archive_button_next_to_the_validation_button(self):
        dialog = self.dialog()
        self.assertFalse(hasattr(dialog, "btn_archive"))
        self.assertEqual(dialog.btn_validate.text(), "Kontrollera planen…")

    def test_the_three_choices_exclude_each_other(self):
        dialog = self.dialog()
        dialog.archive.setChecked(True)
        self.assertFalse(dialog.upload.isChecked() or dialog.file.isChecked())
        dialog.file.setChecked(True)
        self.assertFalse(dialog.upload.isChecked() or dialog.archive.isChecked())
        dialog.upload.setChecked(True)
        self.assertFalse(dialog.file.isChecked() or dialog.archive.isChecked())

    def test_choosing_it_changes_the_ok_button_and_turns_off_the_production_confirmation(self):
        from rita_detaljplan.gui.ngp_dialog import ARCHIVE, UPLOAD
        dialog = self.dialog()
        self.assertEqual(dialog.choice(), UPLOAD, "standardvalet är oförändrat när leverans går")
        ok = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
        dialog.archive.setChecked(True)
        self.assertEqual(dialog.choice(), ARCHIVE)
        self.assertEqual(ok.text(), "Skapa arkivpaket…")
        self.assertTrue(ok.isEnabled())
        self.assertFalse(dialog.understand.isEnabled())

    def test_it_is_never_the_choice_when_the_dialog_does_not_offer_it(self):
        from rita_detaljplan.gui.ngp_dialog import ARCHIVE
        dialog = self.dialog(offer_archive=False)
        dialog.archive.setChecked(True)
        self.assertNotEqual(dialog.choice(), ARCHIVE)

    def test_a_chosen_archive_stays_chosen_when_the_dialog_refreshes_without_delivery_settings(self):
        from rita_detaljplan.core import ngp_client as ngp
        from rita_detaljplan.gui.ngp_dialog import ARCHIVE, FILE
        dialog = self.dialog(config=ngp.NgpConfig("", "", "", ""))
        self.assertFalse(dialog.upload.isEnabled())
        self.assertEqual(dialog.choice(), FILE, "utan inställningar väljs filen")
        dialog.archive.setChecked(True)
        dialog.refresh()
        self.assertEqual(dialog.choice(), ARCHIVE, "användarens val ändras inte av en omläsning")


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class NgpArchiveWiringTests(ArchivePlanCase):
    def test_the_toolbar_hands_the_archive_callback_to_the_ngp_dialog(self):
        from rita_detaljplan.gui.ngp_dialog import NgpRequest
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar

        def callback(parent):
            return None

        toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog, on_archive=callback)
        self.addCleanup(toolbar.deleteLater)
        with mock.patch("rita_detaljplan.gui.plan_toolbar.NgpDialog") as dialog_cls:
            toolbar._ask_ngp(NgpRequest("p", "k", "0484"))
        self.assertIs(dialog_cls.call_args.kwargs["offer_archive"], True)
        without = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(without.deleteLater)
        with mock.patch("rita_detaljplan.gui.plan_toolbar.NgpDialog") as dialog_cls:
            without._ask_ngp(NgpRequest("p", "k", "0484"))
        self.assertIs(dialog_cls.call_args.kwargs["offer_archive"], False)

    def test_choosing_the_archive_in_the_ngp_dialog_opens_the_archive_dialog_over_the_main_window(self):
        from rita_detaljplan.gui.ngp_dialog import ARCHIVE
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        seen = []
        toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog,
                              on_archive=lambda parent: seen.append(parent) or object())
        self.addCleanup(toolbar.deleteLater)
        with mock.patch.object(toolbar, "_ask_ngp", return_value=ARCHIVE), \
                mock.patch.object(toolbar, "save_json") as save, mock.patch.object(toolbar.controller, "export_ngp") as export:
            self.assertTrue(toolbar.deliver())
        self.assertEqual(seen, [self.iface.mainWindow()])
        save.assert_not_called()
        export.assert_not_called()

    def test_a_cancelled_archive_dialog_makes_deliver_return_false(self):
        from rita_detaljplan.gui.ngp_dialog import ARCHIVE
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog, on_archive=lambda parent: None)
        self.addCleanup(toolbar.deleteLater)
        with mock.patch.object(toolbar, "_ask_ngp", return_value=ARCHIVE):
            self.assertFalse(toolbar.deliver())

    def test_the_plugin_wires_its_own_archive_function_into_the_toolbar(self):
        plugin = rita_detaljplan.classFactory(self.iface)
        plugin.initGui()
        self.addCleanup(plugin.unload)
        self.assertEqual(plugin.toolbar._on_archive, plugin.open_archive)

    def test_the_archive_function_uses_the_given_window_and_returns_the_package(self):
        plugin = rita_detaljplan.classFactory(self.iface)
        plugin.initGui()
        self.addCleanup(plugin.unload)
        package = archive.Package(self.out / "p", self.out / "p" / "metadata" / "PREMIS.xml",
                                  self.out / "p" / "detaljplan.xml",
                                  [archive.Record("1", "a", "a.pdf", 1, "x", "PDF", None, "Q", None, "t", False)])
        parent = object()
        with mock.patch("rita_detaljplan.plugin.ArchiveDialog") as dialog_cls, \
                mock.patch("rita_detaljplan.plugin.build_archive", return_value=package):
            dialog_cls.return_value.exec.return_value = True
            result = plugin.open_archive(parent)
        self.assertIs(dialog_cls.call_args.args[1], parent)
        self.assertIs(result, package)

    def test_the_menu_entry_opens_it_over_the_main_window_and_a_cancelled_dialog_returns_nothing(self):
        plugin = rita_detaljplan.classFactory(self.iface)
        plugin.initGui()
        self.addCleanup(plugin.unload)
        with mock.patch("rita_detaljplan.plugin.ArchiveDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = False
            self.assertIsNone(plugin.open_archive())
        self.assertIs(dialog_cls.call_args.args[1], self.iface.mainWindow())
        entry = next(a for a in plugin.actions if a.text() == "Skapa arkivpaket…")
        with mock.patch("rita_detaljplan.plugin.ArchiveDialog") as dialog_cls:
            dialog_cls.return_value.exec.return_value = False
            entry.trigger()
        self.assertIs(dialog_cls.call_args.args[1], self.iface.mainWindow(), "inte True/False som fönster")


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
