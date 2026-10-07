"""Dialogerna Ny detaljplan och Planens uppgifter, samt kommunväljaren (kräver QGIS med offscreen-grafik)."""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, LEFT, PLAN, PlanCase, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsProject
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QLabel
    from rita_detaljplan.controller import PlanController
    from rita_detaljplan.core.project import find_plan_group
    from rita_detaljplan.gui.kommun_combo import KommunCombo
    from rita_detaljplan.gui.new_plan_dialog import NewPlanDialog, safe_filename
    from rita_detaljplan.gui.plan_info_dialog import SYFTE_MAX, PlanInfoDialog
    from rita_detaljplan.core import settings
    from rita_detaljplan.core.settings import parse_scale


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class LabelFieldTests(PlanCase):
    """Bestämmelser vars katalogbeteckning är en mall ("[beteckning:text]#") får ett fält för beteckningen."""

    def setUp(self):
        super().setUp()
        from rita_detaljplan.core import catalog as cat
        bundled = cat.Catalog.load(ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json")
        self.template = next(e for e in bundled.entries if e.kod == "DP_AP_Eg_UtformAP_Dagv_Annan")
        self.plain = next(e for e in bundled.entries if e.kod == "DP_KM_J2")
        self.bundled = bundled

    def test_the_form_asks_for_the_label_and_adding_needs_it(self):
        from rita_detaljplan.gui.variable_form import VariableForm
        form = VariableForm()
        form.set_entry(self.template)
        self.assertEqual(form.label(), "")
        self.assertTrue(any("beteckningen" in p for p in form.problems()))
        form._label_edit.setText("Dv")
        self.assertEqual(form.label(), "Dv")
        self.assertTrue(all("beteckningen" not in p for p in form.problems()))

    def test_the_form_remembers_the_label_when_it_is_rebuilt(self):
        from rita_detaljplan.gui.variable_form import VariableForm
        form = VariableForm()
        form.set_entry(self.template, label="Dagv")
        self.assertEqual(form.label(), "Dagv")

    def test_a_provision_with_a_fixed_label_has_no_label_field(self):
        from rita_detaljplan.gui.variable_form import VariableForm
        form = VariableForm()
        form.set_entry(self.plain)
        self.assertIsNone(form.label())
        self.assertFalse(form.isVisible() and bool(form._editors))

    def test_the_full_dialog_has_the_same_field_and_returns_the_label(self):
        from rita_detaljplan.gui.bestammelse_dialog import BestammelseDialog
        dialog = BestammelseDialog(self.bundled, "egenskap_yta", self.template, None, None, None, label="Dv")
        self.assertEqual(dialog.label(), "Dv")
        dialog._label_edit.setText("")
        dialog._update_state()
        self.assertFalse(dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled())
        self.assertIn("beteckningen", dialog.problems.text())
        dialog._label_edit.setText("Dagv")
        self.assertEqual(dialog.label(), "Dagv")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class KommunComboTests(PlanCase):
    def test_lists_every_municipality_and_starts_empty(self):
        combo = KommunCombo()
        self.assertEqual(combo.count(), 290)
        self.assertEqual(combo.currentText(), "")
        self.assertIsNone(combo.selected())

    def test_only_an_exact_municipality_counts_as_selected(self):
        combo = KommunCombo()
        combo.setEditText("Eskil")
        self.assertIsNone(combo.selected(), "en del av ett namn är inget val")
        combo.setEditText("eskilstuna")
        self.assertEqual(combo.selected().kod, "0484")

    def test_choosing_an_item_gives_the_municipality_and_its_code(self):
        combo = KommunCombo()
        combo.setCurrentIndex(combo.findText("Göteborg"))
        self.assertEqual((combo.selected().namn, combo.selected().kod), ("Göteborg", "1480"))

    def test_the_list_is_searchable_by_any_part_of_the_name(self):
        combo = KommunCombo()
        completer = combo.completer()
        self.assertEqual(completer.filterMode(), Qt.MatchFlag.MatchContains)
        completer.setCompletionPrefix("borg")
        self.assertGreater(completer.completionCount(), 3, "Göteborg, Strömstad… innehåller inte alla 'borg', men flera gör")

    def test_set_kommun_selects_a_known_name_and_keeps_an_unknown_one_as_text(self):
        combo = KommunCombo()
        combo.set_kommun("Malmö")
        self.assertEqual(combo.selected().kod, "1280")
        combo.set_kommun("Okänd")
        self.assertIsNone(combo.selected())
        self.assertEqual(combo.currentText(), "Okänd")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class NewPlanDialogTests(PlanCase):
    def test_the_digitising_mode_can_be_chosen_when_the_plan_is_created(self):
        dialog = NewPlanDialog()
        self.assertFalse(dialog.values().digitising if dialog.kommun.selected() else dialog.digitising.isChecked())
        dialog.kommun.set_kommun("Eskilstuna")
        dialog.planbeteckning.setText("DP 1957:1")
        dialog.folder.setFilePath("C:/planer")
        dialog.digitising.setChecked(True)
        self.assertTrue(dialog.values().digitising)

    def test_valid_only_when_a_municipality_a_name_and_a_folder_are_given(self):
        dialog = NewPlanDialog()
        self.assertFalse(dialog.is_valid())
        dialog.kommun.set_kommun("Eskilstuna")
        dialog.planbeteckning.setText("DP 2026:1")
        self.assertFalse(dialog.is_valid(), "mapp saknas")
        dialog.folder.setFilePath("C:/planer")
        self.assertTrue(dialog.is_valid())
        dialog.kommun.setEditText("Eskil")
        self.assertFalse(dialog.is_valid(), "kommunen måste väljas ur listan")

    def test_there_are_no_free_text_fields_for_municipality_or_code(self):
        dialog = NewPlanDialog()
        self.assertIsInstance(dialog.kommun, KommunCombo)
        self.assertFalse(hasattr(dialog, "kommunkod"))

    def test_the_municipality_code_follows_the_choice(self):
        dialog = NewPlanDialog()
        self.assertEqual(dialog.crs.count(), 13)
        dialog.crs.setCurrentIndex(4)
        dialog.kommun.set_kommun("Eskilstuna")
        dialog.planbeteckning.setText("DP 2026:1")
        dialog.folder.setFilePath("C:/planer")
        v = dialog.values()
        self.assertEqual((v.kommun, v.kommunkod, v.filnamn, v.epsg), ("Eskilstuna", "0484", "DP_2026_1", 3010))
        self.assertEqual(v.directory, Path("C:/planer"))

    def test_safe_filename_keeps_swedish_letters(self):
        self.assertEqual(safe_filename("Åkerö 1:2 / etapp 3"), "Åkerö_1_2_etapp_3")
        self.assertEqual(safe_filename("  ../..  "), "")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PlanInfoDialogTests(PlanCase):
    def setUp(self):
        super().setUp()
        self.controller = PlanController(lambda *_: None, lambda *_: None)
        self.addCleanup(self.controller.detach)
        self.add("detaljplan", PLAN)
        pump()

    def dialog(self):
        dialog = PlanInfoDialog(self.controller)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def marks(self, dialog):
        """Checklistans rader som (✔/✘, text)."""
        text = dialog.checklist_text().replace("<br>", "\n")
        import re
        return [(m.group(1), re.sub("<[^>]+>", "", m.group(2)).strip())
                for m in re.finditer(r"<b>(✔|✘)</b></span> ([^\n]+)", text)]

    def fill(self, dialog, **values):
        if "kommun" in values:
            dialog.kommun.set_kommun(values["kommun"])
        if "namn" in values:
            dialog.namn.setText(values["namn"])
        if "syfte" in values:
            dialog.syfte.setPlainText(values["syfte"])
        if "genomforandetid" in values:
            dialog.decision.impl_unit.setCurrentIndex(dialog.decision.impl_unit.findData("ar"))
            dialog.decision.impl_value.setValue(values["genomforandetid"])

    def test_no_plan_switcher_with_only_one_plan_loaded(self):
        dialog = self.dialog()
        self.assertIs(dialog.layout().itemAt(0).widget(), dialog.tabs, "ingen växlarrad när det bara finns en")

    def test_the_plan_switcher_closes_and_reopens_the_dialog_for_the_newly_active_plan(self):
        from unittest import mock
        from qgis.core import QgsProject
        from qgis.PyQt.QtWidgets import QComboBox, QDialog
        from rita_detaljplan.core.project import create_plan_project, find_plan_group, load_plan
        other_gpkg, _ = create_plan_project(self.dir, "annan_plan", "Eskilstuna", "0482", 3006)
        load_plan(other_gpkg, QgsProject.instance())  # blir aktiv
        dialog = self.dialog()
        combo = dialog.layout().itemAt(0).widget().findChild(QComboBox)
        with mock.patch("rita_detaljplan.gui.plan_info_dialog.PlanInfoDialog.exec",
                        return_value=QDialog.DialogCode.Rejected) as reopened:
            combo.setCurrentIndex(combo.findText("plan"))
            self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected, "den gamla dialogen stängdes")
            pump()
            reopened.assert_called_once()
        self.assertEqual(find_plan_group(QgsProject.instance()).name(), "plan")

    def test_the_dialog_starts_with_the_defaults_of_a_new_plan(self):
        dialog = self.dialog()
        self.assertEqual(dialog.kommun.selected().namn, "Eskilstuna", "kommunen från Ny detaljplan är förvald")
        self.assertEqual(dialog.status.currentText(), "påbörjad")
        self.assertEqual(dialog.typ.currentText(), "detaljplan")
        self.assertEqual(dialog.namn.text(), "")

    def test_the_status_and_type_lists_are_the_codelists_of_the_specification(self):
        dialog = self.dialog()
        self.assertEqual([dialog.status.itemText(i) for i in range(dialog.status.count())],
                         ["påbörjad", "samråd", "granskning", "antagen", "överklagad", "tillsyn", "laga kraft",
                          "upphävd", "avslutad"])
        self.assertEqual([dialog.typ.itemText(i) for i in range(dialog.typ.count())],
                         ["avstyckningsplan", "byggnadsplan", "detaljplan", "stadsplan"])

    def test_the_mandatory_fields_are_marked_with_a_red_asterisk(self):
        dialog = self.dialog()
        starred = [l.text() for l in dialog.findChildren(QLabel) if "*" in l.text() and "<span" in l.text()
                   and len(l.text()) < 80]
        for name in ("Kommun", "Namn", "Syfte", "Status", "Plantyp"):
            self.assertTrue(any(name in t for t in starred), name)
        self.assertFalse(any("Beteckning" in t for t in starred), "beteckning krävs först vid laga kraft")

    def test_the_start_date_is_marked_with_a_red_asterisk_on_the_beslut_tab(self):
        dialog = self.dialog()
        starred = [l.text() for l in dialog.findChildren(QLabel) if "*" in l.text() and "<span" in l.text()
                   and len(l.text()) < 80]
        self.assertTrue(any("Datum påbörjat" in t for t in starred))

    def test_empty_mandatory_fields_get_a_yellow_background_that_clears_when_filled(self):
        dialog = self.dialog()
        self.assertIn("fff3cd", dialog.namn.styleSheet().lower())
        self.assertIn("fff3cd", dialog.syfte.styleSheet().lower())
        self.assertIn("fff3cd", dialog.decision.impl_value.styleSheet().lower())
        self.assertNotIn("fff3cd", dialog.kommun.styleSheet().lower(), "kommunen är redan förvald")
        self.fill(dialog, namn="Kv Väktaren", syfte="Bostäder", genomforandetid=10)
        self.assertEqual(dialog.namn.styleSheet(), "")
        self.assertEqual(dialog.syfte.styleSheet(), "")
        self.assertEqual(dialog.decision.impl_value.styleSheet(), "")

    def test_the_start_date_field_is_yellow_when_empty_and_clears_when_filled(self):
        dialog = self.dialog()
        edit = dialog.decision.dates["datumPaborjat"]
        self.assertIn("fff3cd", edit.styleSheet().lower())
        edit.setText("2024-01-01")
        self.assertEqual(edit.styleSheet(), "")

    def test_an_invalid_start_date_is_flagged_red_instead_of_yellow(self):
        dialog = self.dialog()
        edit = dialog.decision.dates["datumPaborjat"]
        edit.setText("banan")
        self.assertIn("f8d7da", edit.styleSheet().lower())
        self.assertNotIn("fff3cd", edit.styleSheet().lower())

    def test_a_saved_start_date_is_shown_as_a_date_again_after_the_edits_are_committed(self):
        first = self.dialog()
        first.decision.dates["datumPaborjat"].setText("2024-05-06")
        first.accept()
        self.assertTrue(self.controller.layer("beslutsinformation").commitChanges())
        self.assertEqual(self.controller.decision_values()["datumPaborjat"], "2024-05-06")
        second = self.dialog()
        self.assertEqual(second.decision.dates["datumPaborjat"].text(), "2024-05-06")
        self.assertEqual(second.decision.problems(), [])
        self.assertTrue(second.buttons.buttons()[0].isEnabled())

    def test_a_saved_document_date_is_read_back_as_a_date(self):
        self.controller.set_documents([{"roll": "planbeskrivning", "namn": "Beskrivning", "datum": "2024-05-06",
                                        "handelse": "skapad"}])
        self.assertTrue(self.controller.layer("dokument").commitChanges())
        self.assertEqual(self.controller.documents()[0]["datum"], "2024-05-06")

    def test_the_dialog_fits_on_the_screen_so_the_save_button_is_always_visible(self):
        """Dialogen var så hög att Spara-knappen hamnade utanför skärmen."""
        from qgis.PyQt.QtCore import QPoint
        from qgis.PyQt.QtGui import QGuiApplication
        from qgis.PyQt.QtWidgets import QDialogButtonBox
        dialog = self.dialog()
        dialog.show()
        pump()
        screen = QGuiApplication.primaryScreen().availableGeometry().height()
        self.assertLessEqual(dialog.height(), int(screen * 0.9) + 1)
        save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.assertLessEqual(save.mapTo(dialog, QPoint(0, save.height())).y(), dialog.height())

    def test_the_checklist_is_split_in_two_columns(self):
        dialog = self.dialog()
        self.assertTrue(dialog.checklist.text() and dialog.checklist_right.text())
        left, right = dialog.checklist.text().count("<br>") + 1, dialog.checklist_right.text().count("<br>") + 1
        self.assertLessEqual(abs(left - right), 1, "kolumnerna är ungefär lika långa")
        self.assertEqual(len(self.marks(dialog)), left + right)

    def test_the_digitising_mode_is_set_in_the_dialog_and_removes_the_demand_for_motives(self):
        dialog = self.dialog()
        self.assertFalse(dialog.digitising.isChecked())
        self.assertTrue(any("motiv" in text.lower() for _, text in self.marks(dialog)))
        dialog.digitising.setChecked(True)
        self.assertFalse(any("motiv" in text.lower() for _, text in self.marks(dialog)), "raden om motiv tas bort direkt")
        self.fill(dialog, namn="Kv Väktaren", syfte="Bostäder")
        dialog.accept()
        self.assertTrue(self.controller.digitising)
        again = self.dialog()
        self.assertTrue(again.digitising.isChecked(), "valet sparas i projektet")
        again.digitising.setChecked(False)
        again.accept()
        self.assertFalse(self.controller.digitising)

    def test_missing_start_date_does_not_block_saving(self):
        dialog = self.dialog()
        self.fill(dialog, namn="Kv Väktaren", syfte="Bostäder")
        self.assertEqual(dialog.decision.dates["datumPaborjat"].text(), "")
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())
        dialog.accept()
        self.assertFalse(self.controller.decision_values()["datumPaborjat"])

    def test_the_checklist_says_what_is_missing_and_updates_while_typing(self):
        dialog = self.dialog()
        marks = dict((text, mark) for mark, text in self.marks(dialog))
        self.assertEqual(marks["Planområdet är ritat"], "✔")
        self.assertEqual(marks["Kommun är angivet"], "✔")
        self.assertEqual(marks["Namn är angivet"], "✘")
        self.assertEqual(marks["Syfte är angivet"], "✘")
        self.fill(dialog, namn="Kv Väktaren", syfte="Bostäder")
        marks = dict((text, mark) for mark, text in self.marks(dialog))
        self.assertEqual((marks["Namn är angivet"], marks["Syfte är angivet"]), ("✔", "✔"))

    def test_the_checklist_also_covers_the_drawing_before_any_use_exists(self):
        marks = dict((text.split(" (")[0], mark) for mark, text in self.marks(self.dialog()))
        self.assertEqual(marks["Användning täcker hela planområdet"], "✘")
        self.assertEqual(marks["Alla ytor har bestämmelse"], "✘")

    def test_the_checklist_turns_green_when_the_plan_is_ready(self):
        use = self.add("anvandning_yta", PLAN)
        pump()
        from rita_detaljplan.core import assignments
        from plan_case import filled, pick
        entry = pick(self.catalog, "DP_KM_J2")
        assignments.add(QgsProject.instance(), "anvandning_yta", use.id(), entry, filled(entry), "Ett motiv")
        dialog = self.dialog()
        self.assertEqual(dialog.quality.digitaliseringsniva.currentData(), "komplett", "förifyllt som standard")
        self.assertEqual(dialog.quality.anvandbarhet.currentData(), "god", "förifyllt som standard")
        self.fill(dialog, namn="Kv Väktaren", syfte="Bostäder")
        self.assertIn("✘", [m for m, _ in self.marks(dialog)], "genomförandetid saknas")
        self.fill(dialog, genomforandetid=10)
        dialog.decision.dates["datumPaborjat"].setText("2024-01-01")
        self.assertEqual([m for m, _ in self.marks(dialog)].count("✘"), 2, "planbeskrivning och beslutshandling saknas")
        dialog.decision.documents.extend([
            {"roll": "planbeskrivning", "namn": "Planbeskrivning"},
            {"roll": "beslutshandling", "innehall": "plankarta", "namn": "Plankarta"}])
        dialog.decision._reload_documents()
        self.assertEqual([m for m, _ in self.marks(dialog)], ["✔"] * 15)

    def test_the_quality_tab_is_saved_and_loaded_again(self):
        dialog = self.dialog()
        dialog.quality.digitaliseringsniva.setCurrentIndex(dialog.quality.digitaliseringsniva.findData("ej komplett"))
        dialog.quality.beskrivning_niva.setText("Byggnader saknas")
        dialog.quality.korrigerade_granser.setChecked(True)
        dialog.quality.anvandbarhet.setCurrentIndex(dialog.quality.anvandbarhet.findData("låg"))
        dialog.quality.beskrivning_anvandbarhet.setText("Gammalt underlag")
        dialog.accept()
        self.assertEqual(self.controller.quality_values(), {
            "digitaliseringsniva": "ej komplett", "beskrivningNiva": "Byggnader saknas",
            "korrigeradeGranser": True, "kontrolleratPlaneringsunderlag": False,
            "anvandbarhet": "låg", "beskrivningAnvandbarhet": "Gammalt underlag"})
        second = self.dialog()
        self.assertEqual(second.quality.digitaliseringsniva.currentData(), "ej komplett")
        self.assertEqual(second.quality.beskrivning_niva.text(), "Byggnader saknas")
        self.assertTrue(second.quality.korrigerade_granser.isChecked())
        self.assertEqual(second.quality.anvandbarhet.currentData(), "låg")

    def test_digitaliseringsniva_and_anvandbarhet_are_prefilled_and_turn_yellow_if_cleared(self):
        # komplett/god är förvalt (se model._kvalitet): det vanliga är att inte behöva ändra något här alls.
        dialog = self.dialog()
        self.assertEqual(dialog.quality.digitaliseringsniva.currentData(), "komplett")
        self.assertEqual(dialog.quality.anvandbarhet.currentData(), "god")
        self.assertEqual(dialog.quality.digitaliseringsniva.styleSheet(), "")
        self.assertEqual(dialog.quality.anvandbarhet.styleSheet(), "")
        dialog.quality.digitaliseringsniva.setCurrentIndex(dialog.quality.digitaliseringsniva.findData(None))
        self.assertIn("fff3cd", dialog.quality.digitaliseringsniva.styleSheet().lower())
        self.assertEqual(dialog.quality.anvandbarhet.styleSheet(), "", "användbarhet är orörd")

    def test_the_implementation_time_is_entered_in_years_or_months_and_stored_as_months(self):
        dialog = self.dialog()
        panel = dialog.decision
        self.assertIsNone(panel.months())
        self.fill(dialog, genomforandetid=10)
        self.assertEqual(panel.months(), 120)
        panel.impl_unit.setCurrentIndex(panel.impl_unit.findData("manader"))
        self.assertEqual(panel.months(), 10)
        panel._set_months(60)
        self.assertEqual((panel.impl_value.value(), panel.impl_unit.currentData()), (5, "ar"))
        panel._set_months(30)
        self.assertEqual((panel.impl_value.value(), panel.impl_unit.currentData()), (30, "manader"))
        panel._set_months(None)
        self.assertIsNone(panel.months())
        self.assertEqual(panel.values()["genomforandetid"], None)

    def test_the_implementation_time_cannot_be_longer_than_fifteen_years(self):
        panel = self.dialog().decision
        panel.impl_unit.setCurrentIndex(panel.impl_unit.findData("ar"))
        panel.impl_value.setValue(40)
        self.assertEqual((panel.impl_value.value(), panel.months()), (15, 180))
        panel.impl_unit.setCurrentIndex(panel.impl_unit.findData("manader"))
        panel.impl_value.setValue(500)
        self.assertEqual(panel.months(), 180, "180 månader är också 15 år")
        panel.impl_unit.setCurrentIndex(panel.impl_unit.findData("ar"))
        self.assertLessEqual(panel.months(), 180)
        panel._set_months(240)
        self.assertLessEqual(panel.months(), 180, "ett äldre för högt värde begränsas när det läses in")

    def test_an_unknown_municipality_is_flagged(self):
        dialog = self.dialog()
        dialog.kommun.setEditText("Atlantis")
        marks = self.marks(dialog)
        self.assertTrue(any(mark == "✘" and "Atlantis" in text for mark, text in marks), marks)

    def test_saving_writes_the_details_to_the_plan_and_names_the_layer_group(self):
        dialog = self.dialog()
        self.fill(dialog, kommun="Göteborg", namn="Kv Väktaren", syfte="Bostäder och service")
        dialog.beteckning.setText("DP 2026:1")
        dialog.status.setCurrentText("samråd")
        dialog.accept()
        plan = self.controller.plan_feature()
        self.assertEqual((plan["kommun"], plan["namn"], plan["syfte"], plan["beteckning"], plan["status"]),
                         ("Göteborg", "Kv Väktaren", "Bostäder och service", "DP 2026:1", "samråd"))
        self.assertEqual(find_plan_group(QgsProject.instance()).name(), "Kv Väktaren")
        self.assertEqual(QgsProject.instance().title(), "Kv Väktaren")

    def test_the_status_change_date_is_only_set_when_the_status_changes(self):
        dialog = self.dialog()
        dialog.accept()
        self.assertFalse(self.controller.plan_feature()["datumStatusforandring"], "inte första gången")
        dialog = self.dialog()
        dialog.status.setCurrentText("granskning")
        dialog.accept()
        self.assertEqual(str(self.controller.plan_feature()["datumStatusforandring"])[:10],
                         date.today().isoformat())

    def test_cancelling_changes_nothing(self):
        dialog = self.dialog()
        self.fill(dialog, namn="Ska inte sparas")
        dialog.reject()
        self.assertFalse(self.controller.plan_feature()["namn"])

    def test_the_purpose_is_counted_and_cut_at_the_length_of_the_specification(self):
        dialog = self.dialog()
        dialog.syfte.setPlainText("x" * (SYFTE_MAX + 50))
        self.assertIn(f"{SYFTE_MAX + 50} av {SYFTE_MAX}", dialog.syfte_count.text())
        self.assertEqual(len(dialog.values()["syfte"]), SYFTE_MAX)

    def test_saving_is_never_blocked_by_missing_details(self):
        dialog = self.dialog()
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())
        dialog.accept()  # kastar inget även om namn och syfte saknas
        self.assertFalse(self.controller.plan_feature()["namn"])

    def test_the_documents_tab_says_what_is_missing_for_the_delivery(self):
        dialog = self.dialog()
        note = dialog.decision.docs_note
        self.assertFalse(note.isHidden())
        self.assertIn("planbeskrivning", note.text())
        self.assertIn("beslutshandling", note.text())
        self.assertEqual(dialog.tabs.tabText(3), "Handlingar", "kryss först vid laga kraft")
        dialog.decision.documents.append({"roll": "planbeskrivning", "namn": "Planbeskrivning"})
        dialog.decision._reload_documents()
        self.assertNotIn("planbeskrivning", note.text())
        dialog.decision.documents.append({"roll": "beslutshandling", "innehall": "övrigt", "namn": "Protokoll"})
        dialog.decision._reload_documents()
        self.assertTrue(note.isHidden())

    def test_at_laga_kraft_the_documents_tab_is_marked_until_the_plan_map_is_added(self):
        dialog = self.dialog()
        dialog.status.setCurrentText("laga kraft")
        self.assertEqual(dialog.tabs.tabText(3), "Handlingar ✘")
        self.assertIn("planbeskrivning", dialog.decision.docs_note.text())
        self.assertIn("plankarta", dialog.decision.docs_note.text())
        dialog.decision.documents.extend([{"roll": "planbeskrivning", "namn": "Planbeskrivning"},
                                          {"roll": "beslutshandling", "innehall": "övrigt", "namn": "Protokoll"}])
        dialog.decision._reload_documents()
        self.assertEqual(dialog.tabs.tabText(3), "Handlingar ✘", "ett protokoll är inte plankartan")
        dialog.decision.documents.append({"roll": "beslutshandling", "innehall": "plankarta", "namn": "Plankarta"})
        dialog.decision._reload_documents()
        self.assertEqual(dialog.tabs.tabText(3), "Handlingar")
        self.assertTrue(dialog.decision.docs_note.isHidden())
        dialog.status.setCurrentText("samråd")
        self.assertEqual(dialog.decision.missing_documents(), [])

    def test_before_laga_kraft_the_note_only_says_what_will_be_required(self):
        dialog = self.dialog()
        self.assertTrue(dialog.decision.docs_note.text().startswith("Krävs vid laga kraft"))
        dialog.status.setCurrentText("laga kraft")
        self.assertTrue(dialog.decision.docs_note.text().startswith("Saknas (krävs vid laga kraft)"))

    def test_a_protocol_that_also_contains_the_plan_map_is_enough_at_laga_kraft(self):
        dialog = self.dialog()
        dialog.status.setCurrentText("laga kraft")
        dialog.decision.documents.extend([
            {"roll": "planbeskrivning", "namn": "Planbeskrivning"},
            {"roll": "beslutshandling", "innehall": "plankarta; beslutsprotokoll", "namn": "Beslut"}])
        dialog.decision._reload_documents()
        self.assertEqual(dialog.tabs.tabText(3), "Handlingar")
        self.assertEqual(dialog.decision.missing_documents(), [])

    def test_missing_documents_never_block_saving(self):
        dialog = self.dialog()
        dialog.status.setCurrentText("laga kraft")
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())

    def test_the_details_can_be_reopened_and_are_loaded_again(self):
        first = self.dialog()
        self.fill(first, namn="Kv Väktaren", syfte="Bostäder")
        first.accept()
        second = self.dialog()
        self.assertEqual((second.namn.text(), second.syfte.toPlainText()), ("Kv Väktaren", "Bostäder"))


    def test_the_reference_scale_is_set_in_the_plan_details(self):
        from qgis.core import QgsSettings
        self.addCleanup(lambda: QgsSettings().remove(settings.KEY_REFERENCE_SCALE))
        QgsSettings().remove(settings.KEY_REFERENCE_SCALE)
        dialog = self.dialog()
        self.assertEqual(dialog.scale_value(), 1000)
        self.assertEqual([dialog.scale.itemText(i) for i in range(dialog.scale.count())],
                         [f"1:{v}" for v in settings.SCALES])
        dialog.scale.setEditText("1:2000")
        dialog.accept()
        self.assertEqual(settings.reference_scale(), 2000)

    def test_saving_the_details_restyles_the_plan_for_the_new_scale(self):
        from qgis.core import QgsSettings
        self.addCleanup(lambda: QgsSettings().remove(settings.KEY_REFERENCE_SCALE))
        dialog = self.dialog()
        dialog.scale.setEditText("1:500")
        dialog.accept()
        self.assertEqual(self.controller.layer("anvandning_yta").renderer().referenceScale(), 500)

    def test_a_free_scale_can_be_typed_and_an_invalid_one_blocks_saving(self):
        from qgis.core import QgsSettings
        self.addCleanup(lambda: QgsSettings().remove(settings.KEY_REFERENCE_SCALE))
        QgsSettings().remove(settings.KEY_REFERENCE_SCALE)
        dialog = self.dialog()
        dialog.scale.setEditText("1:1500")
        self.assertEqual(dialog.scale_value(), 1500)
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())
        dialog.scale.setEditText("banan")
        self.assertIsNone(dialog.scale_value())
        self.assertFalse(dialog.buttons.buttons()[0].isEnabled())
        self.assertIn("1:1000", dialog.scale_error.text())
        dialog.accept()
        self.assertEqual(settings.reference_scale(), 1000, "ogiltigt värde sparas inte")

    def test_the_dialog_starts_at_the_saved_scale(self):
        from qgis.core import QgsSettings
        self.addCleanup(lambda: QgsSettings().remove(settings.KEY_REFERENCE_SCALE))
        settings.set_reference_scale(1500)
        self.assertEqual(self.dialog().scale_value(), 1500)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class MotiveTabTests(PlanCase):
    """Fliken Motiv till planbestämmelser i Planens uppgifter."""

    def setUp(self):
        super().setUp()
        from plan_case import filled, pick
        self.controller = PlanController(lambda *_: None, lambda *_: None)
        self.addCleanup(self.controller.detach)
        self.add("detaljplan", PLAN)
        self.left = self.add("anvandning_yta", LEFT)
        self.right = self.add("anvandning_yta", "MultiPolygon(((50 0, 100 0, 100 100, 50 100, 50 0)))")
        self.prop_a = self.add("egenskap_yta", "MultiPolygon(((5 5, 20 5, 20 20, 5 20, 5 5)))")
        self.prop_b = self.add("egenskap_yta", "MultiPolygon(((60 5, 80 5, 80 20, 60 20, 60 5)))")
        pump()
        self.use_entry = pick(self.catalog, "DP_KM_J2")
        self.prop_entry = pick(self.catalog, layer="egenskap_yta", form="Kvartersmark")
        self.tech_entry = pick(self.catalog, "DP_KM_E2")
        for feature in (self.left, self.right):
            self.controller.add_bestammelse("anvandning_yta", feature.id(), self.use_entry, filled(self.use_entry))
        for feature in (self.prop_a, self.prop_b):
            self.controller.add_bestammelse("egenskap_yta", feature.id(), self.prop_entry, filled(self.prop_entry))
        pump()

    def dialog(self):
        dialog = PlanInfoDialog(self.controller)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def tab_names(self, dialog):
        return [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]

    def test_there_is_a_tab_for_the_motives_of_the_provisions(self):
        dialog = self.dialog()
        self.assertEqual(self.tab_names(dialog)[:4], ["Plan", "Kvalitet", "Beslut", "Handlingar"])
        self.assertTrue(self.tab_names(dialog)[4].startswith("Motiv till planbestämmelser"))

    def test_every_used_provision_is_listed_once_however_many_areas_have_it(self):
        dialog = self.dialog()
        self.assertEqual(dialog.motives.list.count(), 2, "användningen (två ytor) och egenskapen (två ytor)")
        self.assertEqual([p["areas"] for p in dialog.motives.provisions], [2, 2])
        self.assertEqual(dialog.motives.summary.text(), "0 av 2 har motiv")

    def test_writing_a_motive_marks_the_provision_and_counts_it(self):
        dialog = self.dialog()
        tab = dialog.motives
        tab.list.setCurrentRow(0)
        self.assertTrue(tab.list.item(0).text().startswith("✘"))
        tab.editor.setPlainText("Bostäder behövs i området")
        self.assertTrue(tab.list.item(0).text().startswith("✔"))
        self.assertEqual(tab.summary.text(), "1 av 2 har motiv")
        tab.list.setCurrentRow(1)
        tab.list.setCurrentRow(0)
        self.assertEqual(tab.editor.toPlainText(), "Bostäder behövs i området", "texten finns kvar när man byter")

    def test_saving_writes_the_motive_on_every_area_with_the_provision(self):
        dialog = self.dialog()
        dialog.motives.list.setCurrentRow(0)
        dialog.motives.editor.setPlainText("Bostäder behövs")
        dialog.accept()
        from rita_detaljplan.core import assignments
        for feature in (self.left, self.right):
            (row,) = assignments.rows_of_area(self.controller.project, "anvandning_yta", feature.id())
            self.assertEqual(row["motiv"], "Bostäder behövs")
        for feature in (self.prop_a, self.prop_b):
            (row,) = assignments.rows_of_area(self.controller.project, "egenskap_yta", feature.id())
            self.assertIsNone(row["motiv"], "den andra bestämmelsen fick inget motiv")

    def test_cancelling_writes_nothing(self):
        dialog = self.dialog()
        dialog.motives.list.setCurrentRow(0)
        dialog.motives.editor.setPlainText("Ska inte sparas")
        dialog.reject()
        from rita_detaljplan.core import assignments
        self.assertTrue(all(r["motiv"] is None for r in assignments.read_rows(self.controller.project)))

    def test_the_motives_are_loaded_again_when_the_dialog_is_reopened(self):
        first = self.dialog()
        first.motives.list.setCurrentRow(0)
        first.motives.editor.setPlainText("Ett motiv")
        first.accept()
        second = self.dialog()
        self.assertEqual(second.motives.summary.text(), "1 av 2 har motiv")
        second.motives.list.setCurrentRow(0)
        self.assertEqual(second.motives.editor.toPlainText(), "Ett motiv")

    def test_missing_motives_never_block_saving_and_are_not_flagged_before_laga_kraft(self):
        dialog = self.dialog()
        self.assertTrue(dialog.buttons.buttons()[0].isEnabled())
        self.assertEqual(dialog.motives.editor.styleSheet(), "")
        self.assertNotIn("✘", dialog.tabs.tabText(4))
        dialog.accept()

    def test_at_laga_kraft_the_empty_motives_turn_yellow_and_the_tab_is_marked(self):
        dialog = self.dialog()
        dialog.motives.list.setCurrentRow(0)
        dialog.status.setCurrentText("laga kraft")
        self.assertIn("fff3cd", dialog.motives.editor.styleSheet().lower())
        self.assertIn("✘", dialog.tabs.tabText(4))
        dialog.motives.editor.setPlainText("Klart")
        self.assertEqual(dialog.motives.editor.styleSheet(), "")
        dialog.motives.list.setCurrentRow(1)
        dialog.motives.editor.setPlainText("Klart också")
        self.assertNotIn("✘", dialog.tabs.tabText(4))
        dialog.status.setCurrentText("samråd")
        self.assertEqual(dialog.motives.editor.styleSheet(), "")

    def test_technical_installations_show_their_fixed_motive_and_cannot_be_edited(self):
        from plan_case import filled
        self.controller.add_bestammelse("anvandning_yta", self.right.id(), self.tech_entry, filled(self.tech_entry))
        dialog = self.dialog()
        tab = dialog.motives
        index = next(i for i, p in enumerate(tab.provisions) if p["technical"])
        tab.list.setCurrentRow(index)
        self.assertEqual(tab.editor.toPlainText(), "Tekniska anläggningar")
        self.assertFalse(tab.editor.isEnabled())
        self.assertEqual(tab.summary.text(), "1 av 3 har motiv", "det fasta motivet räknas som ifyllt")

    def motive_row(self, dialog):
        """Raden om motiv i checklistan på fliken Plan, som (✔/✘, text)."""
        import re
        text = dialog.checklist_text().replace("<br>", "\n")
        found = [(m.group(1), re.sub("<[^>]+>", "", m.group(2)).strip())
                 for m in re.finditer(r"<b>(✔|✘)</b></span> ([^\n]+)", text)]
        return next(row for row in found if row[1].startswith("Alla planbestämmelser har ett motiv"))

    def write_motive(self, tab, row, text):
        tab.list.setCurrentRow(row)
        tab.editor.setPlainText(text)

    def test_the_checklist_has_a_row_about_every_provision_having_a_motive(self):
        dialog = self.dialog()
        self.assertEqual(self.motive_row(dialog),
                         ("✘", "Alla planbestämmelser har ett motiv (krävs vid laga kraft) (2 saknar)"))

    def test_the_row_follows_the_motive_tab_while_the_dialog_is_open(self):
        dialog = self.dialog()
        self.write_motive(dialog.motives, 0, "Första")
        self.assertTrue(self.motive_row(dialog)[1].endswith("(1 saknar)"))
        self.write_motive(dialog.motives, 1, "Andra")
        self.assertEqual(self.motive_row(dialog),
                         ("✔", "Alla planbestämmelser har ett motiv (krävs vid laga kraft)"))

    def test_a_fixed_motive_does_not_count_as_missing(self):
        from plan_case import filled
        self.controller.add_bestammelse("anvandning_yta", self.right.id(), self.tech_entry, filled(self.tech_entry))
        dialog = self.dialog()
        self.assertTrue(self.motive_row(dialog)[1].endswith("(2 saknar)"), "tekniska anläggningar räknas inte")

    def test_a_plan_without_provisions_says_so(self):
        for layer in (self.layers["bestammelse"],):
            layer.deleteFeatures(layer.allFeatureIds())
        pump()
        dialog = self.dialog()
        self.assertFalse(dialog.motives.empty.isHidden())
        self.assertTrue(dialog.motives.list.isHidden())


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class DateEditTests(PlanCase):
    """Datumrutor med kalenderknapp."""

    def setUp(self):
        super().setUp()
        from qgis.PyQt.QtCore import QDate
        self.QDate = QDate
        self.controller = PlanController(lambda *_: None, lambda *_: None)
        self.addCleanup(self.controller.detach)
        self.add("detaljplan", PLAN)
        pump()

    def date_fields(self, dialog):
        panel = dialog.decision
        return [*panel.dates.values(), panel.lagakraft]

    def test_every_date_field_has_a_calendar_button(self):
        from rita_detaljplan.gui.date_edit import DateLineEdit
        dialog = PlanInfoDialog(self.controller)
        self.addCleanup(dialog.deleteLater)
        fields = self.date_fields(dialog)
        self.assertEqual(len(fields), 4)
        for edit in fields:
            self.assertIsInstance(edit, DateLineEdit)
            self.assertFalse(edit.calendar_action.icon().isNull(), "kalenderikonen läses in")
            self.assertIn("kalender", edit.calendar_action.toolTip())

    def test_the_document_date_field_has_one_too(self):
        from rita_detaljplan.gui.date_edit import DateLineEdit
        from rita_detaljplan.gui.decision_dialog import DocumentDialog
        dialog = DocumentDialog()
        self.addCleanup(dialog.deleteLater)
        self.assertIsInstance(dialog.datum, DateLineEdit)

    def test_choosing_a_date_writes_it_and_the_field_validates_as_usual(self):
        from rita_detaljplan.gui.date_edit import DateLineEdit
        edit = DateLineEdit()
        edit.choose(self.QDate(2024, 5, 6))
        self.assertEqual(edit.text(), "2024-05-06")
        edit.choose(self.QDate(2025, 1, 2))
        self.assertEqual(edit.text(), "2025-01-02", "ett enkelt datumfält byts ut")

    def test_a_field_with_several_dates_adds_the_chosen_one_without_duplicates(self):
        from rita_detaljplan.gui.date_edit import DateLineEdit
        edit = DateLineEdit(multiple=True)
        edit.choose(self.QDate(2024, 5, 6))
        edit.choose(self.QDate(2024, 6, 7))
        edit.choose(self.QDate(2024, 5, 6))
        self.assertEqual(edit.text(), "2024-05-06; 2024-06-07")

    def test_the_calendar_opens_on_the_date_in_the_field_or_today(self):
        from rita_detaljplan.gui.date_edit import DateLineEdit
        edit = DateLineEdit(multiple=True)
        self.assertEqual(edit.start_date(), self.QDate.currentDate())
        edit.setText("banan")
        self.assertEqual(edit.start_date(), self.QDate.currentDate(), "ogiltigt datum: idag")
        edit.setText("2024-05-06; 2024-08-09")
        self.assertEqual(edit.start_date(), self.QDate(2024, 8, 9), "det sista datumet")
        self.assertEqual(edit.make_calendar().selectedDate(), self.QDate(2024, 8, 9))

    def test_clicking_a_day_in_the_calendar_picks_it(self):
        from rita_detaljplan.gui.date_edit import DateLineEdit
        edit = DateLineEdit()
        calendar = edit.make_calendar()
        self.addCleanup(calendar.deleteLater)
        calendar.clicked.emit(self.QDate(2023, 12, 24))
        self.assertEqual(edit.text(), "2023-12-24")

    def test_the_button_opens_a_small_calendar_window_without_blocking(self):
        from rita_detaljplan.gui.date_edit import DateLineEdit
        edit = DateLineEdit()
        self.addCleanup(edit.deleteLater)
        edit.show()
        edit.calendar_action.trigger()
        self.assertIsNotNone(edit.menu)
        edit.choose(self.QDate(2024, 1, 1))
        self.assertEqual(edit.text(), "2024-01-01")

    def test_a_date_picked_in_the_calendar_is_saved_with_the_plan(self):
        dialog = PlanInfoDialog(self.controller)
        self.addCleanup(dialog.deleteLater)
        dialog.decision.dates["datumPaborjat"].choose(self.QDate(2024, 5, 6))
        dialog.decision.lagakraft.choose(self.QDate(2025, 3, 1))
        dialog.accept()
        values = self.controller.decision_values()
        self.assertEqual((values["datumPaborjat"], values["datumLagakraft"]), ("2024-05-06", "2025-03-01"))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class SettingsTests(PlanCase):
    def setUp(self):
        super().setUp()
        from qgis.core import QgsSettings
        self.addCleanup(lambda: QgsSettings().remove(settings.KEY_REFERENCE_SCALE))
        QgsSettings().remove(settings.KEY_REFERENCE_SCALE)

    def test_the_default_reference_scale_is_1_1000(self):
        self.assertEqual(settings.reference_scale(), 1000)

    def test_a_chosen_scale_is_remembered_and_kept_within_sensible_limits(self):
        self.assertEqual(settings.set_reference_scale(2000), 2000)
        self.assertEqual(settings.reference_scale(), 2000)
        self.assertEqual(settings.clamp_scale(5), settings.MIN_SCALE)
        self.assertEqual(settings.clamp_scale(10 ** 9), settings.MAX_SCALE)
        self.assertEqual(settings.clamp_scale("skräp"), settings.DEFAULT_REFERENCE_SCALE)

    def test_scale_text_is_parsed_as_1_colon_n_or_a_plain_number(self):
        self.assertEqual(parse_scale("1:500"), 500)
        self.assertEqual(parse_scale(" 1 : 2000 "), 2000)
        self.assertEqual(parse_scale("4000"), 4000)
        for bad in ("", "1:", "abc", "2:500", "1:5"):
            self.assertIsNone(parse_scale(bad), bad)


if __name__ == "__main__":
    unittest.main()
