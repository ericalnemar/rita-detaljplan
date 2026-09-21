"""Dialogen "Topologikontroll": föreslagna ändringar av brytpunkter och små glapp, där man väljer vilka som ska göras."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout, QLabel, QListWidget,
                                 QListWidgetItem, QPushButton, QVBoxLayout)

from ..core import topology
from ..core.topology import Change

NOTE = ("Brytpunkter i användningsytorna ska sammanfalla med planområdets, och små glapp mellan gränser ska stängas. "
        "Planområdet ändras aldrig. Välj vilka förslag som ska göras: de valda ändringarna görs automatiskt.")


class TopologyDialog(QDialog):
    """``analyze(tolerance)`` ger förslagen, ``apply(changes)`` genomför de valda och returnerar (gjorda, hoppade över),
    ``show(change)`` visar en yta i kartan."""

    def __init__(self, analyze: Callable[[float], list[Change]], apply: Callable[[list[Change]], tuple[int, int]],
                 show: Optional[Callable[[Change], None]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Topologikontroll")
        self.setMinimumSize(620, 460)
        self._analyze, self._apply, self._show = analyze, apply, show
        self.changes: list[Change] = []

        note = QLabel(NOTE)
        note.setWordWrap(True)
        note.setEnabled(False)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setDecimals(2)
        self.tolerance.setRange(0.01, 5.0)
        self.tolerance.setSingleStep(0.05)
        self.tolerance.setSuffix(" m")
        self.tolerance.setValue(topology.DEFAULT_TOLERANCE)
        self.tolerance.setToolTip("Största avstånd som räknas som ett glapp eller en avvikelse. Större avstånd ses "
                                  "som avsiktliga och lämnas orörda.")
        self.btn_again = QPushButton("Analysera igen")
        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold;")
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.btn_all = QPushButton("Markera alla")
        self.btn_none = QPushButton("Avmarkera alla")
        self.btn_show = QPushButton("Visa i kartan")
        self.btn_apply = QPushButton("Gör valda ändringar")
        self.btn_apply.setDefault(True)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        close.rejected.connect(self.reject)

        settings_row = QHBoxLayout()
        settings_row.addWidget(QLabel("Tolerans:"))
        settings_row.addWidget(self.tolerance)
        settings_row.addWidget(self.btn_again)
        settings_row.addStretch(1)
        select_row = QHBoxLayout()
        for button in (self.btn_all, self.btn_none, self.btn_show):
            select_row.addWidget(button)
        select_row.addStretch(1)
        select_row.addWidget(self.btn_apply)
        select_row.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addLayout(settings_row)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.result)
        layout.addLayout(select_row)

        self.btn_again.clicked.connect(self.reload)
        self.tolerance.editingFinished.connect(self.reload)
        self.btn_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        self.btn_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self.btn_show.clicked.connect(self.show_selected)
        self.btn_apply.clicked.connect(self.apply_checked)
        self.list.itemChanged.connect(self._update_buttons)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.reload()

    # -- listan ---------------------------------------------------------------------------
    def reload(self) -> None:
        self.changes = self._analyze(self.tolerance.value())
        self.list.blockSignals(True)
        self.list.clear()
        for index, change in enumerate(self.changes):
            item = QListWidgetItem(f"{change.where}: {change.text}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(f"{change.title}\nFrån {change.old} till {change.new}" if change.old
                            else f"{change.title}\nNy brytpunkt vid {change.new}")
            self.list.addItem(item)
        self.list.blockSignals(False)
        count = len(self.changes)
        self.summary.setText("Inga förslag: gränserna stämmer överens." if not count
                             else f"{count} förslag på ändringar.")
        self._update_buttons()

    def checked(self) -> list[Change]:
        """De valda (ikryssade) förslagen."""
        return [self.changes[self.list.item(i).data(Qt.ItemDataRole.UserRole)] for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def _set_all(self, state) -> None:
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)
        self.list.blockSignals(False)
        self._update_buttons()

    def _update_buttons(self, *_) -> None:
        chosen = len(self.checked())
        self.btn_apply.setEnabled(chosen > 0)
        self.btn_apply.setText(f"Gör valda ändringar ({chosen})" if chosen else "Gör valda ändringar")
        has_rows = self.list.count() > 0
        self.btn_all.setEnabled(has_rows)
        self.btn_none.setEnabled(has_rows)
        self.btn_show.setEnabled(self.list.currentItem() is not None and self._show is not None)

    # -- åtgärder ---------------------------------------------------------------------------
    def show_selected(self) -> None:
        item = self.list.currentItem()
        if item is not None and self._show is not None:
            self._show(self.changes[item.data(Qt.ItemDataRole.UserRole)])

    def apply_checked(self) -> tuple[int, int]:
        """Genomför de ikryssade förslagen och analyserar om. Returnerar (gjorda, hoppade över)."""
        chosen = self.checked()
        if not chosen:
            return 0, 0
        done, skipped = self._apply(chosen)
        self.reload()
        text = f"{done} ändringar gjordes."
        if skipped:
            text += f" {skipped} hoppades över eftersom de hade gett en ogiltig gräns."
        self.result.setText(text + " Spara genom att avsluta redigeringen.")
        return done, skipped
