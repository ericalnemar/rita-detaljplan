"""Rullista för att välja kommun (sökbar). Kommunkoden följer med valet."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QCompleter

from ..core import kommuner


class KommunCombo(QComboBox):
    """Alla Sveriges kommuner i en sökbar rullista. ``selected()`` ger vald kommun (med kod), annars None."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for kommun in kommuner.all_kommuner():
            self.addItem(kommun.namn, kommun.kod)
        completer = QCompleter(self.model(), self)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(completer)
        self.lineEdit().setPlaceholderText("Välj kommun …")
        self.setCurrentIndex(-1)
        self.clearEditText()

    def selected(self) -> Optional[kommuner.Kommun]:
        """Vald kommun, eller None om texten inte är exakt en kommun i listan."""
        return kommuner.by_name(self.currentText())

    def set_kommun(self, name: Optional[str]) -> None:
        kommun = kommuner.by_name(name)
        if kommun is None:
            self.setCurrentIndex(-1)
            self.setEditText(name or "")
        else:
            self.setCurrentIndex(self.findData(kommun.kod))
