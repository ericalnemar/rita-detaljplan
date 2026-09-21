"""Dialogruta för att välja en planbestämmelse ur Boverkets katalog och fylla i dess värden."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..core import bestammelse as bm
from ..core import catalog as cat
from ..core import codelists as cl
from ..core import model

COLUMNS = ("Kod", "Bestämmelse", "Typ", "Användningsform", "Kategori")
ALL = "Alla"
_ERROR_STYLE = "color: #b00020;"
_WARNING_STYLE = "color: #9a5b00;"
DEVIATION_TEXT = ("Formuleringen avviker från Boverkets katalog. NGP ger en varning vid leverans "
                  "och bestämmelsen blir inte sökbar nationellt.")


class BestammelseDialog(QDialog):
    def __init__(self, catalog: cat.Catalog, layer: Optional[str] = None,
                 entry: Optional[cat.CatalogEntry] = None, values: Optional[list[bm.VariableValue]] = None,
                 motiv: Optional[str] = None, formulation: Optional[str] = None, parent=None):
        """``layer`` begränsar listan till bestämmelser för ett lager (t.ex. "egenskap_linje").
        ``entry``/``values``/``motiv``/``formulation`` förifyller dialogen när en bestämmelse ändras."""
        super().__init__(parent)
        self.catalog = catalog
        self.layer = layer
        self.entry: Optional[cat.CatalogEntry] = None
        self._editors: list[dict] = []
        self.setWindowTitle("Välj planbestämmelse")
        self.resize(980, 760)

        # -- filter -------------------------------------------------------------------
        self.search = QLineEdit()
        self.search.setPlaceholderText("Sök på text, kod eller kategori …")
        self.search.setClearButtonEnabled(True)
        self.form_combo = QComboBox()
        self.form_combo.addItem(ALL)
        self.form_combo.addItems(catalog.forms())
        self.type_combo = QComboBox()
        self.type_combo.addItem(ALL)
        self.type_combo.addItems(sorted({typ for typ, _ in cat.LAYER_FOR}))
        if layer:  # lagret avgör redan typen
            self.type_combo.setEnabled(False)
        self.chk_interp = QCheckBox("Tolkningsbestämmelser (äldre planer)")
        self.chk_historic = QCheckBox("Upphörda bestämmelser")
        self.chk_historic.setEnabled(catalog.has_historic)
        if not catalog.has_historic:
            self.chk_historic.setToolTip("Uppdatera katalogen (Rita Detaljplan → Uppdatera planbestämmelsekatalogen) "
                                         "för att få med upphörda bestämmelser.")

        filters = QHBoxLayout()
        filters.addWidget(self.search, 3)
        filters.addWidget(QLabel("Användningsform:"))
        filters.addWidget(self.form_combo, 1)
        filters.addWidget(QLabel("Typ:"))
        filters.addWidget(self.type_combo, 1)
        options = QHBoxLayout()
        options.addWidget(self.chk_interp)
        options.addWidget(self.chk_historic)
        options.addStretch(1)

        # -- lista --------------------------------------------------------------------
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 150)
        self.count_label = QLabel()

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(filters)
        top_layout.addLayout(options)
        top_layout.addWidget(self.table, 1)
        top_layout.addWidget(self.count_label)

        # -- detaljer, värden och motiv -----------------------------------------------
        self.info = QTextBrowser()
        self.info.setMinimumHeight(110)
        self.values_box = QGroupBox("Värden")
        self.values_layout = QFormLayout(self.values_box)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.chk_custom = QCheckBox("Anpassa formuleringen")
        self.chk_custom.setToolTip("Ändra ordalydelsen kring variablerna. Variablerna ([namn:typ]) måste vara kvar.")
        self.formulation_edit = QPlainTextEdit()
        self.formulation_edit.setMaximumHeight(60)
        self.formulation_edit.setVisible(False)
        self.deviation = QLabel()
        self.deviation.setWordWrap(True)
        self.deviation.setStyleSheet(_WARNING_STYLE)
        self.motiv = QPlainTextEdit()
        self.motiv.setPlaceholderText("Motiv: varför regleringen finns och hur den stödjer planens syfte "
                                      "(planbestämmelsebeskrivning)")
        self.motiv.setMaximumHeight(70)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet(_ERROR_STYLE)
        source = QLabel(f"{cat.ATTRIBUTION}, release {catalog.release_name}")
        source.setEnabled(False)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self.info)
        bottom_layout.addWidget(self.values_box)
        bottom_layout.addWidget(QLabel("Så här visas bestämmelsen:"))
        bottom_layout.addWidget(self.preview)
        bottom_layout.addWidget(self.chk_custom)
        bottom_layout.addWidget(self.formulation_edit)
        bottom_layout.addWidget(self.deviation)
        bottom_layout.addWidget(self.motiv)
        bottom_layout.addWidget(self.problems)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Välj")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(source)
        layout.addWidget(self.buttons)

        # -- koppla -------------------------------------------------------------------
        self.search.textChanged.connect(self._refresh_table)
        self.form_combo.currentIndexChanged.connect(self._refresh_table)
        self.type_combo.currentIndexChanged.connect(self._refresh_table)
        self.chk_interp.toggled.connect(self._refresh_table)
        self.chk_historic.toggled.connect(self._refresh_table)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.motiv.textChanged.connect(self._update_state)
        self.chk_custom.toggled.connect(self._on_custom_toggled)
        self.formulation_edit.textChanged.connect(self._update_state)

        # Förvalt läge (vid ändring av en befintlig bestämmelse); måste sättas innan filtren ändras nedan.
        self._pending_entry, self._pending_values, self._pending_motiv = entry, values, motiv
        self._pending_formulation = formulation
        if entry is not None:
            if entry.tolkning:
                self.chk_interp.setChecked(True)
            if not entry.is_current and catalog.has_historic:
                self.chk_historic.setChecked(True)
        self._refresh_table()
        self._update_state()

    # -- tabell ---------------------------------------------------------------------
    def _filtered(self) -> list[cat.CatalogEntry]:
        results = self.catalog.search(
            self.search.text(),
            layer=self.layer,
            anvandningsform=None if self.form_combo.currentText() == ALL else self.form_combo.currentText(),
            typ=None if self.type_combo.currentText() == ALL else self.type_combo.currentText(),
            include_historic=self.chk_historic.isChecked(),
            include_interpretation=self.chk_interp.isChecked(),
        )
        return sorted(results, key=lambda e: (e.anvandningsform, e.kategori, e.kod))

    def _refresh_table(self, *_):
        keep = self.entry.id if self.entry else (self._pending_entry.id if self._pending_entry else None)
        results = self._filtered()
        self.table.blockSignals(True)
        self.table.setRowCount(len(results))
        select_row = -1
        for row, entry in enumerate(results):
            cells = (entry.kod, entry.formulering, entry.typ, entry.anvandningsform, entry.kategori)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry.id)
                self.table.setItem(row, column, item)
            if entry.id == keep:
                select_row = row
        self.table.blockSignals(False)
        self.count_label.setText(f"{len(results)} bestämmelse" + ("" if len(results) == 1 else "r"))
        if select_row >= 0:
            self.table.selectRow(select_row)
        else:
            self.table.clearSelection()
            self._on_selection()

    def _on_selection(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        entry = None
        if rows:
            entry_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
            entry = self.catalog.get(entry_id)
        self._show_entry(entry)

    # -- detaljer och värden --------------------------------------------------------
    def _show_entry(self, entry: Optional[cat.CatalogEntry]):
        pending = self._pending_entry is not None and entry is not None and entry.id == self._pending_entry.id
        values = self._pending_values if pending else None
        motiv = self._pending_motiv if pending else None
        formulation = self._pending_formulation if pending else None
        if pending:
            self._pending_entry = self._pending_values = self._pending_motiv = self._pending_formulation = None
        self.entry = entry
        self._rebuild_editors(entry, values)
        self._show_info(entry)
        technical = bool(entry and entry.is_technical)
        self.chk_custom.blockSignals(True)
        self.chk_custom.setChecked(formulation is not None)
        self.chk_custom.setEnabled(entry is not None and not technical)
        self.formulation_edit.setPlainText(formulation if formulation is not None else (entry.formulering if entry else ""))
        self.formulation_edit.setVisible(formulation is not None)
        self.chk_custom.blockSignals(False)
        self.motiv.blockSignals(True)
        if technical:
            self.motiv.setPlainText(cat.TECHNICAL_FORMULATION)
        elif entry is None or motiv is not None or self.motiv.toPlainText() == cat.TECHNICAL_FORMULATION:
            self.motiv.setPlainText(motiv or "")
        self.motiv.blockSignals(False)
        self.motiv.setEnabled(entry is not None and not technical)
        self._update_state()

    def _show_info(self, entry: Optional[cat.CatalogEntry]):
        if entry is None:
            self.info.setHtml("<i>Välj en bestämmelse i listan.</i>")
            return
        target = model.layer_by_name(entry.layer_name).alias if entry.layer_name else "–"
        rows = [("Kod", entry.kod), ("Typ", entry.typ), ("Användningsform", entry.anvandningsform),
                ("Kategori", " › ".join(p for p in (entry.kategori, entry.underkategori) if p)),
                ("Betecknas på plankartan", entry.beteckning), ("Sparas i", target)]
        if not entry.is_current:
            rows.append(("Upphörde att gälla", entry.slutar_galla))
        if entry.tolkning:
            rows.append(("Obs", "Tolkningsbestämmelse för äldre planer"))
        html = "".join(f"<b>{key}:</b> {value}<br>" for key, value in rows if value)
        if entry.allmanna_rad:
            html += "<hr>" + entry.allmanna_rad.strip().replace("\n", "<br>")
        self.info.setHtml(html)

    def _rebuild_editors(self, entry: Optional[cat.CatalogEntry], values: Optional[list[bm.VariableValue]]):
        while self.values_layout.rowCount():
            self.values_layout.removeRow(0)
        self._editors = []
        if entry is None or not entry.variables:
            self.values_box.setVisible(False)
            return
        self.values_box.setVisible(True)
        initial = values if values and len(values) == len(entry.variables) else bm.default_values(entry)
        for item in initial:
            editor = {"variable": item.variable, "value": QLineEdit(item.value)}
            editor["value"].setPlaceholderText("valfritt" if item.variable.optional else "obligatoriskt")
            editor["value"].textChanged.connect(self._update_state)
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(editor["value"], 3)
            if item.variable.datatype == "decimaltal":
                editor["vardetyp"] = QComboBox()
                editor["vardetyp"].addItems(cl.VARDETYP)
                editor["enhet"] = QComboBox()
                editor["enhet"].addItem("Välj enhet", None)
                for unit in cl.ENHET:
                    editor["enhet"].addItem(unit, unit)
                if item.vardetyp in cl.VARDETYP:
                    editor["vardetyp"].setCurrentText(item.vardetyp)
                if item.enhet in cl.ENHET:
                    editor["enhet"].setCurrentIndex(editor["enhet"].findData(item.enhet))
                editor["vardetyp"].setToolTip("Är värdet ett minimum, ett maximum eller exakt?")
                for combo in (editor["vardetyp"], editor["enhet"]):
                    combo.currentIndexChanged.connect(self._update_state)
                    row_layout.addWidget(combo, 1)
            label = f"{item.variable.name} ({'tal' if item.variable.datatype == 'decimaltal' else 'text'})"
            self.values_layout.addRow(label, row)
            self._editors.append(editor)
        if self._editors:
            self._editors[0]["value"].setFocus()

    # -- läge -----------------------------------------------------------------------
    def _collect_values(self) -> list[bm.VariableValue]:
        collected = []
        for editor in self._editors:
            vardetyp = editor["vardetyp"].currentText() if "vardetyp" in editor else None
            enhet = editor["enhet"].currentData() if "enhet" in editor else None
            collected.append(bm.VariableValue(editor["variable"], editor["value"].text(), vardetyp, enhet))
        return collected

    def _on_custom_toggled(self, checked: bool):
        self.formulation_edit.setVisible(checked)
        if checked and self.entry is not None:
            self.formulation_edit.blockSignals(True)
            self.formulation_edit.setPlainText(bm.delivered_formulation(self.entry, self._collect_values()))
            self.formulation_edit.blockSignals(False)
        self._update_state()

    def custom_formulation(self) -> Optional[str]:
        """Den anpassade formuleringen, eller None om katalogens används."""
        return self.formulation_edit.toPlainText() if self.chk_custom.isChecked() else None

    def _update_state(self, *_):
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self.entry is None:
            self.preview.setText("")
            self.problems.setText("")
            self.deviation.setText("")
            ok.setEnabled(False)
            return
        values = self._collect_values()
        formulation = self.custom_formulation()
        problems = bm.check(self.entry, values, formulation)
        self.preview.setText(bm.display_text(self.entry, values, formulation) if not problems or formulation is None
                             else bm.display_text(self.entry, values))
        self.problems.setText("\n".join(problems))
        self.deviation.setText(DEVIATION_TEXT if not problems and bm.deviates(self.entry, values, formulation) else "")
        ok.setEnabled(not problems)

    # -- resultat -------------------------------------------------------------------
    def selected_entry(self) -> Optional[cat.CatalogEntry]:
        return self.entry

    def values(self) -> list[bm.VariableValue]:
        return self._collect_values()

    def motive(self) -> str:
        return self.motiv.toPlainText().strip()

    def attributes(self) -> dict:
        """Attribut som beskriver bestämmelsen (se bestammelse.feature_attributes)."""
        if self.entry is None:
            raise ValueError("Ingen bestämmelse vald")
        return bm.feature_attributes(self.entry, self.values(), self.motive(), self.custom_formulation())
