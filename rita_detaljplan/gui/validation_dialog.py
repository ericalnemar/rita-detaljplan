"""Dialogen "Kontrollera planen": avvikelser mot Lantmäteriets regler, med val att visa dem i kartan."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
                                 QListWidgetItem, QPushButton, QVBoxLayout)

from ..core import validation
from ..core.validation import ERROR, INFO, WARNING, Issue

MARKS = {ERROR: "✘", WARNING: "▲", INFO: "•"}
COLORS = {ERROR: QColor(179, 38, 30), WARNING: QColor(176, 110, 0), INFO: QColor(90, 90, 90)}
NOTE = ("Fel stoppar leveransen till NGP. Varningar ger en varning hos NGP eller bör ses över. "
        "Dubbelklicka på en rad för att visa ytan i kartan.")


class ValidationDialog(QDialog):
    def __init__(self, run: Callable[[], list[Issue]], show: Callable[[Issue], None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kontrollera planen")
        self.setMinimumSize(560, 420)
        self._run = run
        self._show = show
        self.issues: list[Issue] = []

        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold;")
        note = QLabel(NOTE)
        note.setWordWrap(True)
        note.setEnabled(False)
        self.filters = {}
        filter_row = QHBoxLayout()
        for severity, label in ((ERROR, "Fel"), (WARNING, "Varningar"), (INFO, "Att fylla i")):
            box = QCheckBox(label)
            box.setChecked(True)
            box.toggled.connect(self._fill)
            self.filters[severity] = box
            filter_row.addWidget(box)
        filter_row.addStretch(1)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda *_: self.show_selected())
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.btn_show = QPushButton("Visa i kartan")
        self.btn_show.clicked.connect(self.show_selected)
        self.btn_again = QPushButton("Kontrollera igen")
        self.btn_again.clicked.connect(self.reload)
        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_show)
        buttons.addWidget(self.btn_again)
        buttons.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        close.rejected.connect(self.reject)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(note)
        layout.addLayout(filter_row)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self.reload()

    def reload(self) -> None:
        self.issues = self._run()
        self._fill()

    def _fill(self, *_) -> None:
        self.list.clear()
        self.summary.setText(validation.summary(self.issues))
        for issue in self.issues:
            if not self.filters[issue.severity].isChecked():
                continue
            code = f"[{issue.code}] " if issue.code else ""
            item = QListWidgetItem(f"{MARKS[issue.severity]}  {issue.where}: {code}{issue.text}")
            item.setForeground(QBrush(COLORS[issue.severity]))
            item.setData(Qt.ItemDataRole.UserRole, issue)
            self.list.addItem(item)
        self._update_buttons()

    def selected_issue(self) -> Optional[Issue]:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _update_buttons(self) -> None:
        issue = self.selected_issue()
        self.btn_show.setEnabled(issue is not None and issue.locatable)

    def show_selected(self) -> None:
        issue = self.selected_issue()
        if issue is not None and issue.locatable:
            self._show(issue)
