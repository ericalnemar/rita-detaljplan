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
        text = dialog.checklist.text().replace("<br>", "\n")
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
        assignments.add(QgsProject.instance(), "anvandning_yta", use.id(), entry, filled(entry))
        dialog = self.dialog()
        self.fill(dialog, namn="Kv Väktaren", syfte="Bostäder")
        self.assertIn("✘", [m for m, _ in self.marks(dialog)], "genomförandetid saknas")
        self.fill(dialog, genomforandetid=10)
        dialog.decision.dates["datumPaborjat"].setText("2024-01-01")
        self.assertEqual([m for m, _ in self.marks(dialog)], ["✔"] * 10)

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
