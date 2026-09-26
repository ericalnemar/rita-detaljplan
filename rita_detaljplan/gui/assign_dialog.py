"""Dialogen "Tilldela bestämmelser": välj yta, se dess bestämmelser och lägg till fler ur en sökbar rullista.

En yta kan ha flera bestämmelser: en användningsyta kan vara kombinerad (B + C) och en egenskapsyta har vanligen
flera egenskapsbestämmelser. Ändringarna görs direkt i planen (i redigeringssessionen) och kan ångras i QGIS.
"""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
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
from ..core import rows
from .bestammelse_dialog import BestammelseDialog
from .variable_form import VariableForm

_ERROR_STYLE = "color: #b00020;"


def entry_text(entry: cat.CatalogEntry) -> str:
    """Text i rullistan: "R – Motorsportbana (Kvartersmark)"."""
    label = entry.label_base or "–"
    return f"{label} – {entry.formulering}  ({entry.anvandningsform})"


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
        self.rows_list.setMinimumHeight(50)
        self.rows_list.setMaximumHeight(88)  # ~3-4 rader; en rullist dyker upp av sig själv om det behövs mer
        self.btn_edit = QPushButton("Ändra…")
        self.btn_remove = QPushButton("Ta bort")
        self.btn_up = QPushButton("▲")
        self.btn_up.setToolTip("Flytta upp: bestämmelsen kommer tidigare i beteckningen.")
        self.btn_down = QPushButton("▼")
        self.btn_down.setToolTip("Flytta ned: bestämmelsen kommer senare i beteckningen.")
        for button in (self.btn_up, self.btn_down):
            button.setFixedWidth(36)
        rows_buttons = QHBoxLayout()
        rows_buttons.addWidget(self.btn_up)
        rows_buttons.addWidget(self.btn_down)
        rows_buttons.addSpacing(12)
        rows_buttons.addWidget(self.btn_edit)
        rows_buttons.addWidget(self.btn_remove)
        rows_buttons.addStretch(1)
        assigned_box = QGroupBox("Ytans bestämmelser")
        assigned_layout = QVBoxLayout(assigned_box)
        assigned_layout.addWidget(self.rows_list)
        assigned_layout.addLayout(rows_buttons)

        # -- lägg till ----------------------------------------------------------------
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
        self.btn_details.setToolTip("Anpassa ordalydelsen för bestämmelsen. Motivet skrivs under Planens uppgifter, på fliken "
                                    "Motiv till planbestämmelser.")
        add_buttons = QHBoxLayout()
        add_buttons.addWidget(self.btn_details)
        add_buttons.addStretch(1)
        add_buttons.addWidget(self.btn_add)
        add_box = QGroupBox("Lägg till bestämmelse")
        add_layout = QVBoxLayout(add_box)
        add_layout.addWidget(self.entry_combo)
        add_layout.addWidget(self.filter_note)
        add_layout.addWidget(self.info)
        add_layout.addWidget(self.variables)
        add_layout.addLayout(add_buttons)

        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet(_ERROR_STYLE)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("Klar")
        self.buttons.rejected.connect(self.accept)

        layout = QVBoxLayout(self)
        self.area_label = QLabel("Yta:")
        layout.addWidget(self.area_label)
        layout.addWidget(self.area_combo)
        layout.addWidget(assigned_box)
        layout.addWidget(add_box)
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
        self.btn_details.clicked.connect(self.add_with_details)
        self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_up.clicked.connect(lambda: self.move_selected(-1))
        self.btn_down.clicked.connect(lambda: self.move_selected(1))
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
        self.problems.setText("")

    def _reload_entries(self):
        candidate = self.candidate()
        self._entries = self.controller.entries_for(self.catalog_provider(), candidate.table, candidate.fid) \
            if candidate else []
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
        self.entry_combo.setCurrentIndex(-1)
        self.entry_combo.clearEditText()
        self.entry_combo.blockSignals(False)
        self._search_filter.set_search_text("")
        self.variables.set_entry(None)
        self.info.setText("")
        self._update_state()

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
        self.btn_details.setEnabled(entry is not None and not entry.is_technical)
        selected = self.rows_list.currentItem() is not None
        self.btn_edit.setEnabled(selected)
        self.btn_remove.setEnabled(selected)
        row = self.rows_list.currentRow()
        self.btn_up.setEnabled(selected and row > 0)
        self.btn_down.setEnabled(selected and row < self.rows_list.count() - 1)

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
        if self._run(lambda: self.controller.add_bestammelse(candidate.table, candidate.fid, entry,
                                                             self.variables.values())):
            self._reload_entries()
            self._reload_rows()

    def add_with_details(self):
        """Öppnar den fullständiga dialogen för att anpassa formuleringen innan bestämmelsen läggs till."""
        candidate, entry = self.candidate(), self.current_entry()
        if candidate is None or entry is None:
            return
        dialog = BestammelseDialog(self.catalog_provider(), candidate.table, entry, self.variables.values(), None, self)
        if not dialog.exec():
            return
        if self._run(lambda: self.controller.add_bestammelse(candidate.table, candidate.fid, dialog.selected_entry(),
                                                             dialog.values(), None,
                                                             dialog.custom_formulation())):
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
        dialog = BestammelseDialog(catalog, row["tabell"], entry, values, formulation, self)
        if not dialog.exec():
            return
        if self._run(lambda: self.controller.update_bestammelse(row["_fid"], dialog.selected_entry(), dialog.values(),
                                                                None, dialog.custom_formulation())):
            self._reload_entries()
            self._reload_rows()

    def remove_selected(self):
        row = self._selected_row()
        if row is None:
            return
        if self._run(lambda: self.controller.remove_bestammelse(row["_fid"])):
            self._reload_entries()
            self._reload_rows()
