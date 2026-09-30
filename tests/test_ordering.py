"""Rubriker i rullistan över bestämmelser och ordningen på en ytas bestämmelser (kräver QGIS)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, pick  # noqa: E402

if HAVE_QGIS:
    from qgis.PyQt.QtCore import Qt
    from rita_detaljplan.core import assignments
    from test_toolbar import DialogCase


def two_uses(catalog):
    """Två användningsbestämmelser för kvartersmark med olika bokstav."""
    first = pick(catalog, "DP_KM_J2")
    second = next(e for e in catalog.search(layer="anvandning_yta")
                  if e.anvandningsform == "Kvartersmark" and not e.variables and e.label_base not in ("J", ""))
    return first, second


class HeadingTests(DialogCase):
    def items(self, dialog):
        combo = dialog.entry_combo
        return [(combo.itemText(i), bool(combo.model().item(i).flags() & Qt.ItemFlag.ItemIsSelectable))
                for i in range(combo.count())]

    def test_the_list_has_headings_that_cannot_be_chosen(self):
        dialog = self.open((20, 50))
        items = self.items(dialog)
        headings = [text for text, selectable in items if not selectable]
        self.assertTrue(headings)
        self.assertTrue(any(text.startswith("Användningsbestämmelser – ") for text in headings), headings)
        self.assertEqual(len(items) - len(headings), len(dialog._entries))

    def test_property_areas_get_property_headings(self):
        self.use_a = self.use_a
        self.controller.add_bestammelse("anvandning_yta", self.use_a.id(), pick(self.catalog, "DP_KM_J2"),
                                        [])
        prop = self.draw("egenskap_yta", INSIDE)
        candidates = [c for c in self.controller.candidates_at(__import__("qgis.core", fromlist=["QgsPointXY"]).QgsPointXY(20, 20), 0.5)
                      if c.table == "egenskap_yta"]
        from rita_detaljplan.gui.assign_dialog import AssignDialog
        dialog = AssignDialog(self.controller, lambda: self.catalog, candidates)
        self.addCleanup(dialog.deleteLater)
        headings = [text for text, selectable in self.items(dialog) if not selectable]
        self.assertTrue(any(text.startswith("Egenskapsbestämmelser – Kvartersmark") for text in headings), headings)
        self.assertFalse(any(text.startswith("Användningsbestämmelser") for text in headings), headings)

    def test_every_form_gets_its_own_heading_before_its_entries(self):
        dialog = self.open((20, 50))
        items = self.items(dialog)
        forms = []
        for text, selectable in items:
            if not selectable and " – " in text and text.split(" – ")[0].endswith("bestämmelser"):
                forms.append(text.split(" – ")[1])
        self.assertEqual(forms, sorted(set(forms), key=forms.index), "varje form bara en gång")
        self.assertIn("Kvartersmark", forms)
        self.assertIn("Allmän plats", forms)
        self.assertFalse(items[0][1], "listan börjar med en rubrik")

    def test_a_heading_cannot_be_added_as_a_provision(self):
        dialog = self.open((20, 50))
        dialog.entry_combo.setCurrentIndex(0)
        self.assertIsNone(dialog.current_entry())
        self.assertFalse(dialog.btn_add.isEnabled())

    def test_choosing_a_real_entry_still_works_with_headings_present(self):
        dialog = self.open((20, 50))
        entry = pick(self.catalog, "DP_KM_J2")
        self.choose(dialog, entry)
        self.assertEqual(dialog.current_entry().id, entry.id)
        self.assertTrue(dialog.btn_add.isEnabled())


class OrderTests(DialogCase):
    def setUp(self):
        super().setUp()
        self.first, self.second = two_uses(self.catalog)
        self.dialog = self.open((20, 50))
        for entry in (self.first, self.second):
            self.add_via(self.dialog, entry)

    def letters(self, entry):
        row = next(r for r in self.controller.rows_of("anvandning_yta", self.use_a.id()) if r["bestammelsekod"] == entry.kod)
        return row["beteckning"]

    def expected(self, *entries):
        return "".join(self.letters(e) for e in entries)

    def label(self):
        return self.layers["anvandning_yta"].getFeature(self.use_a.id())["beteckning"]

    def texts(self):
        return [self.dialog.rows_list.item(i).text() for i in range(self.dialog.rows_list.count())]

    def test_new_provisions_are_added_last(self):
        self.assertEqual(self.label(), self.expected(self.first, self.second))
        rows = self.controller.rows_of("anvandning_yta", self.use_a.id())
        self.assertEqual([r["ordning"] for r in rows], [1, 2])

    def test_moving_down_changes_the_order_in_the_label(self):
        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()
        self.assertEqual(self.label(), self.expected(self.second, self.first))
        self.assertEqual(self.dialog.rows_list.currentRow(), 1, "den flyttade bestämmelsen förblir markerad")

    def test_moving_up_swaps_back(self):
        self.dialog.rows_list.setCurrentRow(1)
        self.dialog.btn_up.click()
        self.assertEqual(self.label(), self.expected(self.second, self.first))
        self.dialog.btn_down.click()
        self.assertEqual(self.label(), self.expected(self.first, self.second))

    def test_the_list_shows_the_new_order(self):
        before = self.texts()
        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()
        self.assertEqual(self.texts(), list(reversed(before)))

    def test_the_buttons_are_disabled_at_the_ends_and_without_a_selection(self):
        self.dialog.rows_list.setCurrentRow(-1)
        self.assertFalse(self.dialog.btn_up.isEnabled())
        self.assertFalse(self.dialog.btn_down.isEnabled())
        self.dialog.rows_list.setCurrentRow(0)
        self.assertFalse(self.dialog.btn_up.isEnabled())
        self.assertTrue(self.dialog.btn_down.isEnabled())
        self.dialog.rows_list.setCurrentRow(1)
        self.assertTrue(self.dialog.btn_up.isEnabled())
        self.assertFalse(self.dialog.btn_down.isEnabled())

    def test_the_first_provision_decides_colour_and_symbol(self):
        feature = self.layers["anvandning_yta"].getFeature(self.use_a.id())
        first_colour = feature["farg"]
        self.assertEqual(first_colour, self.first.farg if hasattr(self.first, "farg") else first_colour)
        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()
        rows = self.controller.rows_of("anvandning_yta", self.use_a.id())
        self.assertEqual(self.layers["anvandning_yta"].getFeature(self.use_a.id())["farg"],
                         next(r["farg"] for r in rows if r.get("farg")))

    def test_moving_beyond_the_ends_does_nothing(self):
        row = self.controller.rows_of("anvandning_yta", self.use_a.id())[0]
        self.assertFalse(self.controller.move_bestammelse(row["_fid"], -1))
        self.assertEqual(self.label(), self.expected(self.first, self.second))

    def test_the_order_of_other_areas_is_untouched(self):
        other = self.open((80, 50))
        self.add_via(other, self.first)
        self.add_via(other, self.second)
        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()
        rows = self.controller.rows_of("anvandning_yta", self.use_b.id())
        self.assertEqual([r["ordning"] for r in rows], [1, 2])
        self.assertEqual(self.layers["anvandning_yta"].getFeature(self.use_b.id())["beteckning"],
                         self.expected(self.first, self.second))

    def test_rows_without_an_order_from_an_older_plan_keep_their_creation_order(self):
        layer = self.layers["anvandning_yta"]
        identity = layer.getFeature(self.use_a.id())["objektidentitet"]
        self.assertEqual(self.controller.stop_editing(save=True), [])  # som en plan från en äldre version: sparad
        self.controller.start_editing()
        rows_layer = assignments.rows_layer(self.controller.project)
        for row in assignments.read_rows(self.controller.project):
            rows_layer.changeAttributeValue(row["_fid"], rows_layer.fields().indexOf("ordning"), None)
        fid = next(f.id() for f in layer.getFeatures() if f["objektidentitet"] == identity)
        rows = self.controller.rows_of("anvandning_yta", fid)
        self.assertEqual([r["bestammelsekod"] for r in rows], [self.first.kod, self.second.kod])
        self.assertTrue(self.controller.move_bestammelse(rows[0]["_fid"], 1))
        rows = self.controller.rows_of("anvandning_yta", fid)
        self.assertEqual([r["bestammelsekod"] for r in rows], [self.second.kod, self.first.kod])

    def test_the_order_survives_saving(self):
        identity = self.layers["anvandning_yta"].getFeature(self.use_a.id())["objektidentitet"]
        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()
        self.assertEqual(self.controller.stop_editing(save=True), [])
        layer = self.layers["anvandning_yta"]
        fid = next(f.id() for f in layer.getFeatures() if f["objektidentitet"] == identity)
        rows = self.controller.rows_of("anvandning_yta", fid)
        self.assertEqual([r["bestammelsekod"] for r in rows], [self.second.kod, self.first.kod])


# egenskap_yta strax innanför RIGHT (se plan_case.PLAN/RIGHT): samma sorts yta som INSIDE, men på andra sidan.
INSIDE_B = "MultiPolygon(((60 10, 90 10, 90 40, 60 40, 60 10)))"


class ReindexTests(DialogCase):
    """Indexsiffran i beteckningen (t.ex. e1/e2) styrs INTE av ``ordning`` (se OrderTests): flyttar man om bland
    bestämmelser med samma bokstav i listan följer inte siffran med av sig själv. "Indexera om"-knappen numrerar
    om siffran efter listans nuvarande ordning."""

    UTNYTT = "DP_KM_Eg_Utnytt_StorstaAreaProc_ByggnadsEgen"  # indexerad beteckning ("e#"), olika värde ger olika index

    def setUp(self):
        super().setUp()
        self.property = self.draw("egenskap_yta", INSIDE)
        self.entry = pick(self.catalog, self.UTNYTT)
        self.dialog = self.open((20, 20))  # egenskapsytan ligger här, se test_several_areas_show_a_chooser...
        self.add_via(self.dialog, self.entry, "30")  # blir e1
        self.add_via(self.dialog, self.entry, "40")  # samma bestämmelse, annat värde: blir e2

    def labels(self):
        return [item.text().split(" – ")[0] for item in
               (self.dialog.rows_list.item(i) for i in range(self.dialog.rows_list.count()))]

    def test_swapping_the_order_keeps_the_old_index_until_reindexed(self):
        self.assertEqual(self.labels(), ["e1", "e2"])
        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()
        self.assertEqual(self.labels(), ["e2", "e1"], "index-siffran följer inte listans ordning av sig själv")

    def test_reindex_renumbers_to_match_the_list_order(self):
        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()
        self.assertTrue(self.dialog.btn_reindex.isEnabled())
        self.dialog.btn_reindex.click()
        self.assertEqual(self.labels(), ["e1", "e2"], "efter omindexering matchar siffrorna listans ordning")

    def test_reindex_updates_the_areas_own_label_too(self):
        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()
        self.dialog.btn_reindex.click()
        feature = self.layers["egenskap_yta"].getFeature(self.property.id())
        self.assertEqual(feature["beteckning"], "e1 e2")

    def test_reindex_propagates_to_other_areas_sharing_the_same_provisions(self):
        # samma bestämmelse (samma katalogreferens, formulering och värde) ska ha samma beteckning överallt i
        # planen (se rows.identity) – omindexeringen måste alltså räkna om den överallt, inte bara på den här ytan.
        other = self.draw("egenskap_yta", INSIDE_B)
        other_dialog = self.open((70, 20))
        self.add_via(other_dialog, self.entry, "30")  # samma bestämmelse som e1 ovan: återanvänder samma index
        self.add_via(other_dialog, self.entry, "40")
        other_rows_before = {r["bestammelsevarde"]: r["beteckning"]
                             for r in self.controller.rows_of("egenskap_yta", other.id())}
        self.assertEqual(set(other_rows_before.values()), {"e1", "e2"})

        self.dialog.rows_list.setCurrentRow(0)
        self.dialog.btn_down.click()  # e2 (värde 40) före e1 (värde 30) på den här ytan
        self.dialog.btn_reindex.click()  # byter plats: 40-värdet blir e1, 30-värdet blir e2 – överallt

        other_rows_after = {r["bestammelsevarde"]: r["beteckning"]
                            for r in self.controller.rows_of("egenskap_yta", other.id())}
        self.assertEqual(set(other_rows_after.values()), {"e1", "e2"})
        for value, label_before in other_rows_before.items():
            self.assertNotEqual(other_rows_after[value], label_before, "index-siffran ska ha bytt plats även här")

    def test_reindex_is_disabled_with_fewer_than_two_indexed_provisions(self):
        other = self.draw("egenskap_yta", INSIDE_B)
        other_dialog = self.open((70, 20))
        self.assertFalse(other_dialog.btn_reindex.isEnabled(), "inga bestämmelser alls")
        self.add_via(other_dialog, self.entry, "50")
        self.assertFalse(other_dialog.btn_reindex.isEnabled(), "bara en bestämmelse")


if __name__ == "__main__":
    unittest.main()
