"""Formulär för en bestämmelses variabler: ett fält per variabel, med värdetyp och enhet för tal."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QWidget

from ..core import bestammelse as bm
from ..core import catalog as cat
from ..core import codelists as cl
from ..core import rows


LABEL_TIP = ("Beteckningen som visas på plankartan. Katalogens beteckning är en mall ([beteckning:text]#): "
             "skriv bara bokstäverna (t.ex. dagvatten). Siffran läggs på automatiskt (dagvatten1, dagvatten2 …) "
             "så att varje bestämmelse får en egen beteckning i hela planen.")


LABEL_PLACEHOLDER = "bara bokstäver, t.ex. dagvatten (siffran läggs på automatiskt)"


class VariableForm(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QFormLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._editors: list[dict] = []
        self._label_edit: Optional[QLineEdit] = None
        self.entry: Optional[cat.CatalogEntry] = None

    def set_entry(self, entry: Optional[cat.CatalogEntry], values: Optional[list[bm.VariableValue]] = None,
                  label: Optional[str] = None) -> None:
        """Bygger fälten för en bestämmelse. ``values`` förifyller (annars värdetyp och enhet så gott det går).
        Har katalogens beteckning en variabel ("[beteckning:text]#") får man också ange beteckningen (``label``)."""
        while self._layout.rowCount():
            self._layout.removeRow(0)
        self._editors = []
        self._label_edit = None
        self.entry = entry
        if entry is None or not (entry.variables or entry.label_variables):
            self.setVisible(False)
            self.changed.emit()
            return
        self.setVisible(True)
        if entry.label_variables:
            self._label_edit = QLineEdit(label or "")
            self._label_edit.setPlaceholderText(LABEL_PLACEHOLDER if "#" in entry.beteckning else "obligatoriskt")
            self._label_edit.setToolTip(LABEL_TIP)
            self._label_edit.textChanged.connect(self.changed)
            self._layout.addRow("Beteckning på plankartan", self._label_edit)
        initial = values if values and len(values) == len(entry.variables) else bm.default_values(entry)
        for item in initial:
            editor = {"variable": item.variable, "value": QLineEdit(item.value)}
            editor["value"].setPlaceholderText("valfritt" if item.variable.optional else "obligatoriskt")
            editor["value"].textChanged.connect(self.changed)
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(editor["value"], 3)
            if item.variable.datatype == "decimaltal":
                editor["vardetyp"] = QComboBox()
                editor["vardetyp"].addItems(cl.VARDETYP)
                editor["vardetyp"].setToolTip("Är värdet ett minimum, ett maximum eller exakt?")
                editor["enhet"] = QComboBox()
                editor["enhet"].addItem("Välj enhet", None)
                for unit in cl.ENHET:
                    editor["enhet"].addItem(unit, unit)
                if item.vardetyp in cl.VARDETYP:
                    editor["vardetyp"].setCurrentText(item.vardetyp)
                if item.enhet in cl.ENHET:
                    editor["enhet"].setCurrentIndex(editor["enhet"].findData(item.enhet))
                for combo in (editor["vardetyp"], editor["enhet"]):
                    combo.currentIndexChanged.connect(self.changed)
                    row_layout.addWidget(combo, 1)
            unit_label = "tal" if item.variable.datatype == "decimaltal" else "text"
            self._layout.addRow(f"{item.variable.name} ({unit_label})", row)
            self._editors.append(editor)
        if self._label_edit is not None:
            self._label_edit.setFocus()
        elif self._editors:
            self._editors[0]["value"].setFocus()
        self.changed.emit()

    def label(self) -> Optional[str]:
        """Beteckningen planförfattaren skrivit (None om katalogens beteckning inte har någon variabel)."""
        return self._label_edit.text().strip() if self._label_edit is not None else None

    def values(self) -> list[bm.VariableValue]:
        collected = []
        for editor in self._editors:
            vardetyp = editor["vardetyp"].currentText() if "vardetyp" in editor else None
            enhet = editor["enhet"].currentData() if "enhet" in editor else None
            collected.append(bm.VariableValue(editor["variable"], editor["value"].text(), vardetyp, enhet))
        return collected

    def problems(self) -> list[str]:
        """Felmeddelanden för nuvarande värden (tom lista = går att lägga till)."""
        if self.entry is None:
            return ["Välj en bestämmelse."]
        return rows.label_problems(self.entry, self.label()) + bm.check(self.entry, self.values())
