"""Dialogen "Topologikontroll": resultatet som en lista på samma sätt som Kontrollera planen. Föreslagna ändringar av
brytpunkter och små glapp (ikryssade, görs automatiskt) står bland avvikelserna: att planområdet saknar användning
(fel) och att kvartersmark saknar egenskapsområden (varning)."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                                 QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)

from ..core import topology, validation
from ..core.topology import Change
from ..core.validation import ERROR, WARNING, Issue
from .validation_dialog import COLORS, MARKS

CHANGE_KIND, FINDING_KIND = "change", "finding"


class TopologyDialog(QDialog):
    """``analyze(tolerance)`` ger förslagen, ``apply(changes)`` genomför de valda och returnerar (gjorda, hoppade över),
    ``show(item)`` visar en yta i kartan (item är en ``Change`` eller en ``Issue``). ``findings()`` (avvikelser som
    inte kan åtgärdas automatiskt, som ``Issue``) och ``fill_use()`` (fyller det som saknar användning med en ny
    användningsyta, se ``controller.fill_use``) är valfria."""

    def __init__(self, analyze: Callable[[float], list[Change]], apply: Callable[[list[Change]], tuple[int, int]],
                 show: Optional[Callable[[object], None]] = None, parent=None, *,
                 findings: Optional[Callable[[], list[Issue]]] = None, fill_use: Optional[Callable[[], object]] = None):
        super().__init__(parent)
        self.setWindowTitle("Topologikontroll")
        self.setMinimumSize(620, 460)
        self._analyze, self._apply, self._show = analyze, apply, show
        self._findings, self._fill_use = findings, fill_use
        self.changes: list[Change] = []
        self.findings: list[Issue] = []

        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold;")
        self.filters = {}
        filter_row = QHBoxLayout()
        for severity, label in ((ERROR, "Fel"), (WARNING, "Varningar")):
            box = QCheckBox(label)
            box.setChecked(True)
            box.toggled.connect(self._fill)
            self.filters[severity] = box
            filter_row.addWidget(box)
        filter_row.addStretch(1)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setDecimals(2)
        self.tolerance.setRange(0.01, 5.0)
        self.tolerance.setSingleStep(0.05)
        self.tolerance.setSuffix(" m")
        self.tolerance.setValue(topology.DEFAULT_TOLERANCE)
        self.tolerance.setToolTip("Största avstånd som räknas som ett glapp eller en avvikelse. Större avstånd ses "
                                  "som avsiktliga och lämnas orörda.")
        self.btn_again = QPushButton("Kontrollera igen")
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.btn_all = QPushButton("Markera alla")
        self.btn_none = QPushButton("Avmarkera alla")
        self.btn_show = QPushButton("Visa i kartan")
        self.btn_fill = QPushButton("Fyll återstoden med en användningsyta")
        self.btn_fill.setVisible(fill_use is not None)
        self.btn_apply = QPushButton("Gör valda ändringar")
        self.btn_apply.setDefault(True)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        close.rejected.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Tolerans:"))
        top_row.addWidget(self.tolerance)
        top_row.addWidget(self.btn_again)
        top_row.addSpacing(16)
        top_row.addLayout(filter_row)
        select_row = QHBoxLayout()
        for button in (self.btn_all, self.btn_none, self.btn_show, self.btn_fill):
            select_row.addWidget(button)
        select_row.addStretch(1)
        select_row.addWidget(self.btn_apply)
        select_row.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addLayout(top_row)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.result)
        layout.addLayout(select_row)

        self.btn_again.clicked.connect(self.reload)
        self.tolerance.editingFinished.connect(self.reload)
        self.btn_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        self.btn_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self.btn_show.clicked.connect(self.show_selected)
        self.btn_fill.clicked.connect(self._fill_clicked)
        self.btn_apply.clicked.connect(self.apply_checked)
        self.list.itemChanged.connect(self._update_buttons)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.list.itemDoubleClicked.connect(lambda *_: self.show_selected())
        self.reload()

    # -- listan ---------------------------------------------------------------------------
    def reload(self) -> None:
        self.changes = self._analyze(self.tolerance.value())
        self.findings = self._findings() if self._findings is not None else []
        self._fill()

    def _issues(self) -> list[Issue]:
        """Allt som listan visar som avvikelser (förslagen räknas som varningar)."""
        return [*self.findings, *(Issue(WARNING, "", change.text, change.table, change.fid) for change in self.changes)]

    def _fill(self, *_) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for issue in self.findings:
            if issue.severity == ERROR and self.filters[ERROR].isChecked():
                self._add_finding(issue)
        if self.filters[WARNING].isChecked():
            for index, change in enumerate(self.changes):
                item = QListWidgetItem(f"{MARKS[WARNING]}  {change.where}: {change.text}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setForeground(QBrush(COLORS[WARNING]))
                item.setData(Qt.ItemDataRole.UserRole, (CHANGE_KIND, index))
                item.setToolTip(f"{change.title}\nFrån {change.old} till {change.new}" if change.old
                                else f"{change.title}\nNy brytpunkt vid {change.new}")
                self.list.addItem(item)
            for issue in self.findings:
                if issue.severity == WARNING:
                    self._add_finding(issue)
        self.list.blockSignals(False)
        issues = self._issues()
        self.summary.setText(validation.summary(issues).replace("Inga avvikelser: planen klarar kontrollen.",
                                                                "Inga avvikelser: topologin stämmer."))
        self._update_buttons()

    def _add_finding(self, issue: Issue) -> None:
        code = f"[{issue.code}] " if issue.code else ""
        item = QListWidgetItem(f"{MARKS[issue.severity]}  {issue.where}: {code}{issue.text}")
        item.setForeground(QBrush(COLORS[issue.severity]))
        item.setData(Qt.ItemDataRole.UserRole, (FINDING_KIND, issue))
        self.list.addItem(item)

    def checked(self) -> list[Change]:
        """De valda (ikryssade) förslagen."""
        chosen = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            kind, value = item.data(Qt.ItemDataRole.UserRole)
            if kind == CHANGE_KIND and item.checkState() == Qt.CheckState.Checked:
                chosen.append(self.changes[value])
        return chosen

    def _change_items(self) -> list[QListWidgetItem]:
        return [self.list.item(i) for i in range(self.list.count())
                if self.list.item(i).data(Qt.ItemDataRole.UserRole)[0] == CHANGE_KIND]

    def _set_all(self, state) -> None:
        self.list.blockSignals(True)
        for item in self._change_items():
            item.setCheckState(state)
        self.list.blockSignals(False)
        self._update_buttons()

    def _selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _update_buttons(self, *_) -> None:
        chosen = len(self.checked())
        self.btn_apply.setEnabled(chosen > 0)
        self.btn_apply.setText(f"Gör valda ändringar ({chosen})" if chosen else "Gör valda ändringar")
        has_changes = bool(self._change_items())
        self.btn_all.setEnabled(has_changes)
        self.btn_none.setEnabled(has_changes)
        selected = self._selected()
        locatable = selected is not None and (selected[0] == CHANGE_KIND or selected[1].locatable)
        self.btn_show.setEnabled(locatable and self._show is not None)
        self.btn_fill.setEnabled(any(issue.code == "DP-0002" and issue.severity == ERROR for issue in self.findings))

    # -- åtgärder ---------------------------------------------------------------------------
    def show_selected(self) -> None:
        selected = self._selected()
        if selected is None or self._show is None:
            return
        kind, value = selected
        if kind == CHANGE_KIND:
            self._show(self.changes[value])
        elif value.locatable:
            self._show(value)

    def _fill_clicked(self) -> None:
        if self._fill_use is None:
            return
        result = self._fill_use()
        self.result.setText(result.message)
        self.reload()

    def apply_checked(self) -> tuple[int, int]:
        """Genomför de ikryssade förslagen och kontrollerar om. Returnerar (gjorda, hoppade över)."""
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
