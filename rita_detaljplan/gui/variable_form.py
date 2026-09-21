"""Formulär för en bestämmelses variabler: ett fält per variabel, med värdetyp och enhet för tal."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QWidget

from ..core import bestammelse as bm
from ..core import catalog as cat
from ..core import codelists as cl


class VariableForm(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QFormLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._editors: list[dict] = []
        self.entry: Optional[cat.CatalogEntry] = None

    def set_entry(self, entry: Optional[cat.CatalogEntry], values: Optional[list[bm.VariableValue]] = None) -> None:
        """Bygger fälten för en bestämmelse. ``values`` förifyller (annars värdetyp och enhet så gott det går)."""
        while self._layout.rowCount():
            self._layout.removeRow(0)
        self._editors = []
        self.entry = entry
        if entry is None or not entry.variables:
            self.setVisible(False)
            self.changed.emit()
            return
        self.setVisible(True)
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
        if self._editors:
            self._editors[0]["value"].setFocus()
        self.changed.emit()

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
        return bm.check(self.entry, self.values())
