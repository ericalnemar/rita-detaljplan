"""Dialogen "Tilldela bestämmelser": välj yta, se dess bestämmelser och lägg till fler ur en sökbar rullista.

En yta kan ha flera bestämmelser: en användningsyta kan vara kombinerad (B + C) och en egenskapsyta har vanligen
flera egenskapsbestämmelser. Ändringarna görs direkt i planen (i redigeringssessionen) och kan ångras i QGIS.
"""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ..controller import Candidate, PlanController
from ..core import assignments
from ..core import bestammelse as bm
from ..core import catalog as cat
from ..core import rows, settings
from .bestammelse_dialog import BestammelseDialog
from .quality_panel import QualityDialog
from .regulates_dialog import RegulatesPlanDialog
from .variable_form import VariableForm

_ERROR_STYLE = "color: #b00020;"


def entry_text(entry: cat.CatalogEntry) -> str:
    """Text i rullistan: "R – Motorsportbana (Kvartersmark)"."""
    label = entry.label_base or "–"
    kind = "tolkning, " if entry.tolkning else ""
    return f"{label} – {entry.formulering}  ({kind}{entry.anvandningsform})"


POPUP_WIDTH = 720  # mm-oberoende pixelbredd: så att långa bestämmelsetexter inte klipps i rullistan


class WordSearchFilter(QSortFilterProxyModel):
    """Filtrerar rullistans rader: en rad visas om **varje** ord i söktexten finns någonstans i radens text, oavsett
    ordning eller var i texten (inte bara i det första ordet). Rubrikraderna filtreras alltid bort här; de hör bara
    hemma i själva rullistan, inte i sökförslagen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._words: list[str] = []
        self.setDynamicSortFilter(True)

    def set_search_text(self, text: str) -> None:
        self._words = [w for w in text.lower().split() if w]
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if not (model.flags(index) & Qt.ItemFlag.ItemIsSelectable):
            return False  # rubrik
        if not self._words:
            return True
        text = (index.data(Qt.ItemDataRole.DisplayRole) or "").lower()
        return all(word in text for word in self._words)


class AssignDialog(QDialog):
    def __init__(self, controller: PlanController, catalog_provider: Callable[[], cat.Catalog],
                 candidates: list[Candidate], on_select: Optional[Callable[[Optional[Candidate]], None]] = None,
                 parent=None):
        super().__init__(parent)
        self.controller = controller
        self.catalog_provider = catalog_provider
        self.candidates = candidates
        self.on_select = on_select
        self._entries: list[cat.CatalogEntry] = []
        self.setWindowTitle("Tilldela bestämmelser")
        self.setMinimumWidth(620)

        # -- vilken yta ---------------------------------------------------------------
        self.area_combo = QComboBox()
        self.area_combo.setToolTip("Flera ytor ligger här. Välj vilken yta bestämmelserna gäller.")

        # -- tilldelade bestämmelser --------------------------------------------------
        self.rows_list = QListWidget()
        self.rows_list.setMinimumHeight(70)  # växer med rutan; en rullist dyker upp av sig själv om det behövs
        self.btn_edit = QPushButton("Ändra…")
        self.btn_remove = QPushButton("Ta bort")
        self.btn_up = QPushButton("▲")
        self.btn_up.setToolTip("Flytta upp: bestämmelsen kommer tidigare i beteckningen.")
        self.btn_down = QPushButton("▼")
        self.btn_down.setToolTip("Flytta ned: bestämmelsen kommer senare i beteckningen.")
        for button in (self.btn_up, self.btn_down):
            button.setFixedWidth(36)
        self.btn_reindex = QPushButton("Indexera om")
        self.btn_reindex.setToolTip("Numrera om indexet i beteckningen (t.ex. F1/F2) så att det följer den här "
                                    "ordningen i stället för i vilken ordning bestämmelserna lades till.")
        self.btn_quality = QPushButton("Kvalitet…")
        self.btn_quality.setToolTip("Kvalitetsbeskrivning och användbarhet för den här bestämmelsen (krävs vid "
                                    "laga kraft).")
        self.btn_regulates = QPushButton("Reglerar annan plan…")
        self.btn_regulates.setToolTip("Anger att den här egenskapsbestämmelsen reglerar (hör ihop med) en annan "
                                      "detaljplan, t.ex. vid samordning mellan grannplaner. Valfritt.")
        rows_buttons = QHBoxLayout()
        rows_buttons.addWidget(self.btn_up)
        rows_buttons.addWidget(self.btn_down)
        rows_buttons.addWidget(self.btn_reindex)
        rows_buttons.addSpacing(12)
        rows_buttons.addWidget(self.btn_edit)
        rows_buttons.addWidget(self.btn_quality)
        rows_buttons.addWidget(self.btn_regulates)
        rows_buttons.addWidget(self.btn_remove)
        rows_buttons.addStretch(1)
        assigned_box = QGroupBox("Ytans bestämmelser")
        assigned_layout = QVBoxLayout(assigned_box)
        assigned_layout.addWidget(self.rows_list)
        assigned_layout.addLayout(rows_buttons)

        # -- redan använda bestämmelser -----------------------------------------------
        self.used_combo = QComboBox()
        self.used_combo.setToolTip("Bestämmelser som redan används någon annanstans i planen. Samma bestämmelse får "
                                   "samma beteckning överallt.")
        self.btn_add_used = QPushButton("Lägg till")
        used_box = QGroupBox("Använd en bestämmelse som redan finns i planen")
        used_layout = QHBoxLayout(used_box)
        used_layout.addWidget(self.used_combo, 1)
        used_layout.addWidget(self.btn_add_used)
        self._used_rows: list[dict] = []

        # -- lägg till ----------------------------------------------------------------
        self.chk_interpretation = QCheckBox("Visa tolkningsbestämmelser (för äldre planer)")
        self.chk_interpretation.setToolTip(
            "Tolkningsbestämmelserna är Boverkets sätt att återge en äldre plans bestämmelser i dagens katalog. Använd dem "
            "när du digitaliserar en plan som är upprättad enligt äldre regler. Valet kommer ihåg till nästa gång.")
        self.chk_interpretation.setChecked(settings.show_interpretation() or controller.digitising)
        self.entry_combo = QComboBox()
        self.entry_combo.setEditable(True)
        self.entry_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.entry_combo.setMaxVisibleItems(24)  # större ruta: fler rader syns utan att behöva rulla
        self.entry_combo.lineEdit().setPlaceholderText("Sök och välj bestämmelse …")
        self._search_filter = WordSearchFilter(self.entry_combo)
        self._search_filter.setSourceModel(self.entry_combo.model())
        completer = QCompleter(self._search_filter, self.entry_combo)
        # Filtreringen sköts helt av WordSearchFilter (ord var som helst, oavsett ordning); completerns egen
        # filtrering stängs av så att den inte dessutom kräver att hela söktexten står i följd i texten.
        completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.entry_combo.setCompleter(completer)
        self.entry_combo.lineEdit().textEdited.connect(self._search_filter.set_search_text)
        for view in (self.entry_combo.view(), completer.popup()):
            view.setMinimumWidth(POPUP_WIDTH)
        self.variables = VariableForm()
        self.filter_note = QLabel()
        self.filter_note.setWordWrap(True)
        self.filter_note.setEnabled(False)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setEnabled(False)
        self.btn_add = QPushButton("Lägg till")
        self.btn_add.setDefault(True)
        self.btn_details = QPushButton("Anpassa formulering…")
        self.btn_details.setToolTip("Öppnar den fullständiga dialogen där du kan bläddra bland alla bestämmelser och anpassa "
                                    "ordalydelsen. Har du valt en bestämmelse i rullistan öppnas den förvald. Motivet skrivs "
                                    "under Planens uppgifter, på fliken Motiv till planbestämmelser.")
        add_buttons = QHBoxLayout()
        add_buttons.addWidget(self.btn_details)
        add_buttons.addStretch(1)
        add_buttons.addWidget(self.btn_add)
        add_box = QGroupBox("Lägg till bestämmelse")
        add_layout = QVBoxLayout(add_box)
        add_layout.addWidget(self.entry_combo)
        add_layout.addWidget(self.chk_interpretation)
        add_layout.addWidget(self.filter_note)
        add_layout.addWidget(self.info)
        add_layout.addWidget(self.variables)
        self.chk_all = QCheckBox()
        self.chk_all.setToolTip("Du har markerat flera ytor av samma typ med Markera. Bestämmelsen läggs då på alla "
                                "markerade ytor på en gång, med samma beteckning.")
        self.chk_all.setVisible(False)
        add_layout.addWidget(self.chk_all)
        add_layout.addLayout(add_buttons)

        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet(_ERROR_STYLE)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setEnabled(False)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("Klar")
        self.buttons.rejected.connect(self.accept)

        layout = QVBoxLayout(self)
        self.area_label = QLabel("Yta:")
        layout.addWidget(self.area_label)
        layout.addWidget(self.area_combo)
        layout.addWidget(assigned_box, 1)  # tar den extra plats som finns när rutan görs större
        layout.addWidget(used_box)
        layout.addWidget(add_box)
        layout.addWidget(self.notice)
        layout.addWidget(self.problems)
        layout.addWidget(self.buttons)

        for index, candidate in enumerate(candidates):
            self.area_combo.addItem(candidate.title, index)
        self.area_combo.setVisible(len(candidates) > 1)
        self.area_label.setVisible(len(candidates) > 1)
        if len(candidates) == 1:
            self.setWindowTitle(f"Tilldela bestämmelser – {candidates[0].title}")

        self.area_combo.currentIndexChanged.connect(self._on_area)
        self.entry_combo.currentIndexChanged.connect(self._on_entry)
        self.variables.changed.connect(self._update_state)
        self.rows_list.itemSelectionChanged.connect(self._update_state)
        self.btn_add.clicked.connect(self.add_selected)
        self.chk_interpretation.toggled.connect(self._on_interpretation_toggled)
        self.used_combo.currentIndexChanged.connect(self._update_state)
        self.btn_add_used.clicked.connect(self.add_used)
        self.btn_details.clicked.connect(self.add_with_details)
        self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_quality.clicked.connect(self.edit_quality)
        self.btn_regulates.clicked.connect(self.edit_regulates)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_up.clicked.connect(lambda: self.move_selected(-1))
        self.btn_down.clicked.connect(lambda: self.move_selected(1))
        self.btn_reindex.clicked.connect(self.reindex_rows)
        self._on_area()

    # -- vald yta ---------------------------------------------------------------------
    def candidate(self) -> Optional[Candidate]:
        index = self.area_combo.currentData()
        return self.candidates[index] if index is not None and 0 <= index < len(self.candidates) else None

    def _on_area(self, *_):
        candidate = self.candidate()
        if self.on_select is not None:
            self.on_select(candidate)
        self._reload_entries()
        self._reload_rows()
        self._update_others()
        self.problems.setText("")
        self.notice.setText("")

    def _others(self) -> list[Candidate]:
        """De andra markerade ytorna av samma typ som den valda ytan, om den valda ytan själv är markerad (annars har
        man inte tänkt sig flera)."""
        candidate = self.candidate()
        if candidate is None:
            return []
        selected = self.controller.selected_candidates(candidate.table)
        if candidate.fid not in {c.fid for c in selected}:
            return []
        return [c for c in selected if c.fid != candidate.fid]

    def _update_others(self) -> None:
        """Visar valet att lägga bestämmelsen på alla markerade ytor när flera ytor av samma typ är markerade."""
        others = self._others()
        self.chk_all.setVisible(bool(others))
        if others:
            count = len(others)
            self.chk_all.setText(f"Lägg även på de {count} andra markerade ytorna" if count > 1
                                 else "Lägg även på den andra markerade ytan")
            self.chk_all.setChecked(True)

    def _targets(self) -> list[Candidate]:
        """Ytorna som en ny bestämmelse läggs på: den valda, och de andra markerade om valet är ibockat."""
        candidate = self.candidate()
        if candidate is None:
            return []
        return [candidate, *self._others()] if not self.chk_all.isHidden() and self.chk_all.isChecked() else [candidate]

    def _add_to_targets(self, entry, values, motiv, formulation, label) -> bool:
        """Lägger bestämmelsen på alla valda ytor. En yta där den inte passar hoppas över och förklaras; de andra får
        den ändå. Returnerar sant om den lades till på minst en yta."""
        targets = self._targets()
        done, failed, whole_use = 0, [], False
        for target in targets:
            try:
                if target.table == cat.USE_LAYER and entry.layer_name != cat.USE_LAYER:
                    # en egenskap för hela användningsområdet: läggs på en egenskapsyta med användningsytans form
                    self.controller.add_to_whole_use(target.fid, entry, values, motiv, formulation, label)
                    whole_use = True
                else:
                    self.controller.add_bestammelse(target.table, target.fid, entry, values, motiv, formulation, label)
                done += 1
            except assignments.AssignmentError as exc:
                failed.append((target, str(exc)))
        self.notice.setText("")
        if not failed:
            self.problems.setText("")
            if whole_use:
                self.notice.setText("Egenskapen lades på en egenskapsyta som täcker hela användningsområdet. Den visas "
                                    "bland egenskapsytorna, inte i listan över användningens bestämmelser.")
            elif len(targets) > 1:
                self.notice.setText(f"Bestämmelsen lades på {done} ytor.")
            return True
        if len(targets) == 1:
            self.problems.setText(failed[0][1])
            return False
        lines = [f"{target.title}: {reason}" for target, reason in failed[:3]]
        more = f" (och {len(failed) - 3} till)" if len(failed) > 3 else ""
        self.problems.setText(f"Bestämmelsen lades på {done} av {len(targets)} ytor. Inte på:\n"
                              + "\n".join(lines) + more)
        return done > 0

    def _reload_entries(self):
        candidate = self.candidate()
        self._entries = self.controller.entries_for(self.catalog_provider(), candidate.table, candidate.fid,
                                                    self.chk_interpretation.isChecked()) if candidate else []
        self.filter_note.setText(self._filter_text(candidate))
        self.entry_combo.blockSignals(True)
        self.entry_combo.clear()
        self._row_of_entry = {}
        heading = subheading = None
        for entry in self._entries:
            if (entry.typ_rubrik, entry.anvandningsform) != heading:
                heading, subheading = (entry.typ_rubrik, entry.anvandningsform), None
                self._add_heading(f"{entry.typ_rubrik} – {entry.anvandningsform}", level=0)
            if entry.kategori and entry.kategori != subheading:
                subheading = entry.kategori
                self._add_heading(entry.kategori, level=1)
            self.entry_combo.addItem(entry_text(entry), entry.id)
            index = self.entry_combo.count() - 1
            self.entry_combo.setItemData(index, entry.kod, Qt.ItemDataRole.ToolTipRole)
            self._row_of_entry[index] = entry
        if candidate is not None and candidate.table == cat.USE_LAYER:
            # egenskaper som uttryckligen gäller hela användningsområdet kan väljas direkt på en användningsyta
            whole = self.controller.whole_use_entries(self.catalog_provider(), candidate.fid)
            if whole:
                self._add_heading("Egenskap för hela användningsområdet", level=0)
            for entry in whole:
                self.entry_combo.addItem(entry_text(entry), entry.id)
                index = self.entry_combo.count() - 1
                self.entry_combo.setItemData(index, entry.kod, Qt.ItemDataRole.ToolTipRole)
                self._row_of_entry[index] = entry
            self._entries = [*self._entries, *whole]
        self.entry_combo.setCurrentIndex(-1)
        self.entry_combo.clearEditText()
        self.entry_combo.blockSignals(False)
        self._search_filter.set_search_text("")
        self.variables.set_entry(None)
        self.info.setText("")
        self._update_state()

    def _on_interpretation_toggled(self, checked: bool) -> None:
        settings.set_show_interpretation(checked)
        self._reload_entries()

    def _add_heading(self, text: str, level: int) -> None:
        """Rubrik i rullistan: syns men går inte att välja."""
        self.entry_combo.addItem(text)
        item = self.entry_combo.model().item(self.entry_combo.count() - 1)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # inte valbar
        font = item.font()
        font.setBold(level == 0)
        font.setItalic(level == 1)
        item.setFont(font)
        if level == 0:
            item.setBackground(QBrush(QColor(225, 232, 240)))
        item.setData(text, Qt.ItemDataRole.ToolTipRole)

    def combo_index(self, entry: cat.CatalogEntry) -> int:
        """Radnumret i rullistan för en bestämmelse (rubrikerna räknas med), eller -1."""
        return next((i for i, e in self._row_of_entry.items() if e.id == entry.id), -1)

    def _filter_text(self, candidate) -> str:
        """Förklarar urvalet i rullistan: bara bestämmelser för ytans användningsform visas."""
        if candidate is None or candidate.table == cat.USE_LAYER:
            return ""
        forms = self.controller.allowed_forms(candidate.table, candidate.fid)
        if forms:
            return "Visar bara bestämmelser för " + " och ".join(sorted(f.lower() for f in forms)) + "."
        return ("Användningen under ytan har ingen bestämmelse än, så alla egenskaper visas. Tilldela användningen "
                "en bestämmelse först för att bara få de som passar (kvartersmark eller allmän plats).")

    def _reload_rows(self):
        candidate = self.candidate()
        self.rows_list.clear()
        self._reload_used()
        if candidate is None:
            return
        for row in self.controller.rows_of(candidate.table, candidate.fid):
            item = QListWidgetItem(rows.describe(row))
            item.setData(Qt.ItemDataRole.UserRole, row["_fid"])
            item.setToolTip(row.get("bestammelsekod") or "")
            self.rows_list.addItem(item)
        if candidate is not None:  # rubrikerna i ytlistan visar antal och beteckning
            index = self.area_combo.currentIndex()
            self.area_combo.setItemText(index, self.controller.describe_area(candidate.table, candidate.fid))
        self._update_state()

    def _reload_used(self) -> None:
        """Fyller rullistan med bestämmelser som redan används i planen och som passar ytan."""
        candidate = self.candidate()
        allowed = {e.id for e in self.controller.entries_for(self.catalog_provider(), candidate.table, candidate.fid,
                                                             True)} if candidate else set()
        self._used_rows = [r for r in self.controller.plan_provisions(candidate.table, candidate.fid)
                           if r.get("planbestammelsekatalogreferens") in allowed] if candidate else []
        self.used_combo.blockSignals(True)
        self.used_combo.clear()
        self.used_combo.addItem("Välj en bestämmelse som redan används …" if self._used_rows
                                else "Inga andra bestämmelser av den här typen används i planen än")
        for row in self._used_rows:
            self.used_combo.addItem(rows.describe(row))
            self.used_combo.setItemData(self.used_combo.count() - 1, row.get("bestammelsekod") or "",
                                        Qt.ItemDataRole.ToolTipRole)
        self.used_combo.setEnabled(bool(self._used_rows))
        self.used_combo.blockSignals(False)

    def add_used(self) -> None:
        """Lägger den valda, redan använda bestämmelsen på ytan: samma text, värden och beteckning som den har
        på andra ytor i planen."""
        candidate, index = self.candidate(), self.used_combo.currentIndex() - 1
        if candidate is None or not 0 <= index < len(self._used_rows):
            return
        row, catalog = self._used_rows[index], self.catalog_provider()
        entry = catalog.get(row["planbestammelsekatalogreferens"])
        if entry is None:
            self.problems.setText("Bestämmelsen finns inte i den katalog som är laddad. Uppdatera katalogen först.")
            return
        values = bm.values_from_attributes(entry, row.get("bestammelsevarde"))
        formulation = row["bestammelseformulering"] if row.get("avviker") else None
        if self._add_to_targets(entry, values, None, formulation, rows.label_text(entry, row)):
            self._reload_entries()
            self._reload_rows()

    # -- vald bestämmelse i rullistan ---------------------------------------------------
    def current_entry(self) -> Optional[cat.CatalogEntry]:
        index = self.entry_combo.currentIndex()
        entry = self._row_of_entry.get(index)  # rubrikerna har ingen bestämmelse
        if entry is None or self.entry_combo.itemText(index) != self.entry_combo.currentText():
            return None  # rubrik, eller texten har ändrats efter valet
        return entry

    def _on_entry(self, *_):
        entry = self.current_entry()
        self.variables.set_entry(entry)
        self.info.setText(entry.allmanna_rad.strip().split("\n")[0] if entry and entry.allmanna_rad else "")
        self._update_state()

    def _update_state(self, *_):
        entry = self.current_entry()
        self.btn_add.setEnabled(entry is not None and not self.variables.problems())
        self.btn_add_used.setEnabled(self.used_combo.currentIndex() > 0)
        self.btn_details.setEnabled(entry is None or not entry.is_technical)
        selected = self.rows_list.currentItem() is not None
        self.btn_edit.setEnabled(selected)
        self.btn_quality.setEnabled(selected)
        selected_row = self._selected_row()
        self.btn_regulates.setEnabled(selected_row is not None and selected_row.get("tabell") in cat.PROPERTY_LAYERS)
        self.btn_remove.setEnabled(selected)
        row = self.rows_list.currentRow()
        self.btn_up.setEnabled(selected and row > 0)
        self.btn_down.setEnabled(selected and row < self.rows_list.count() - 1)
        self.btn_reindex.setEnabled(self.rows_list.count() > 1)

    # -- kommandon ----------------------------------------------------------------------
    def _run(self, action) -> bool:
        try:
            action()
        except assignments.AssignmentError as exc:
            self.problems.setText(str(exc))
            return False
        self.problems.setText("")
        return True

    def add_selected(self):
        candidate, entry = self.candidate(), self.current_entry()
        if candidate is None or entry is None:
            return
        if self._add_to_targets(entry, self.variables.values(), None, None, self.variables.label()):
            self._reload_entries()
            self._reload_rows()

    def add_with_details(self):
        """Öppnar den fullständiga dialogen för att välja och anpassa en bestämmelse innan den läggs till. Är en
        bestämmelse vald i rullistan öppnas den förvald, med de värden som redan fyllts i."""
        candidate, entry = self.candidate(), self.current_entry()
        if candidate is None:
            return
        dialog = BestammelseDialog(self.catalog_provider(), candidate.table, entry,
                                   self.variables.values() if entry is not None else None, None, self,
                                   label=self.variables.label() if entry is not None else None)
        if entry is None and self.chk_interpretation.isChecked():
            dialog.chk_interp.setChecked(True)
        if not dialog.exec():
            return
        if self._add_to_targets(dialog.selected_entry(), dialog.values(), None, dialog.custom_formulation(),
                                dialog.label()):
            self._reload_entries()
            self._reload_rows()

    def _selected_row(self) -> Optional[dict]:
        item = self.rows_list.currentItem()
        candidate = self.candidate()
        if item is None or candidate is None:
            return None
        fid = item.data(Qt.ItemDataRole.UserRole)
        return next((r for r in self.controller.rows_of(candidate.table, candidate.fid) if r["_fid"] == fid), None)

    def move_selected(self, steps: int) -> None:
        """Flyttar den markerade bestämmelsen upp (-1) eller ned (1) och behåller den markerad."""
        item = self.rows_list.currentItem()
        candidate = self.candidate()
        if item is None or candidate is None:
            return
        row_fid = item.data(Qt.ItemDataRole.UserRole)
        if self._run(lambda: self.controller.move_bestammelse(row_fid, steps)):
            self._reload_rows()
            for index in range(self.rows_list.count()):
                if self.rows_list.item(index).data(Qt.ItemDataRole.UserRole) == row_fid:
                    self.rows_list.setCurrentRow(index)
                    break

    def reindex_rows(self):
        """Numrerar om indexet (t.ex. F1/F2) i beteckningen efter listans nuvarande ordning."""
        candidate = self.candidate()
        if candidate is None:
            return
        if self._run(lambda: self.controller.reindex_bestammelser(candidate.table, candidate.fid)):
            self._reload_rows()

    def edit_selected(self):
        row = self._selected_row()
        catalog = self.catalog_provider()
        entry = catalog.get(row["planbestammelsekatalogreferens"]) if row else None
        if row is None:
            return
        if entry is None:
            self.problems.setText("Bestämmelsen finns inte i den katalog som är laddad. Uppdatera katalogen först.")
            return
        values = bm.values_from_attributes(entry, row.get("bestammelsevarde"))
        formulation = row["bestammelseformulering"] if row.get("avviker") else None
        dialog = BestammelseDialog(catalog, row["tabell"], entry, values, formulation, self,
                                   label=rows.label_text(entry, row))
        if not dialog.exec():
            return
        if self._run(lambda: self.controller.update_bestammelse(row["_fid"], dialog.selected_entry(), dialog.values(),
                                                                None, dialog.custom_formulation(), dialog.label())):
            self._reload_entries()
            self._reload_rows()

    def edit_quality(self):
        """Kvalitetsbeskrivning och användbarhet för den markerade bestämmelsen (se ``QualityDialog``) – fristående
        från ``edit_selected``, som bara ändrar bestämmelsens innehåll (kod, värden, formulering)."""
        row = self._selected_row()
        if row is None:
            return
        QualityDialog(row["_fid"], self.controller, self).exec()

    def edit_regulates(self):
        """Vilken annan detaljplan den markerade egenskapsbestämmelsen reglerar (se ``RegulatesPlanDialog``) –
        bara för egenskapsbestämmelser (se ``_update_state``, som styr när knappen är påslagen)."""
        row = self._selected_row()
        if row is None:
            return
        RegulatesPlanDialog(row["_fid"], self.controller, self).exec()

    def remove_selected(self):
        row = self._selected_row()
        if row is None:
            return
        if self._run(lambda: self.controller.remove_bestammelse(row["_fid"])):
            self._reload_entries()
            self._reload_rows()
