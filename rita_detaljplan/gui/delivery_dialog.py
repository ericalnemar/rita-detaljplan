"""Dialogerna för leverans till NGP: bekräftelsen före leveransen och resultatet (status och valideringsrapport)."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                                 QPushButton, QVBoxLayout)

from ..core.ngp_client import Delivery, NgpConfig, NgpError

MARKS = {"FAILURE": "✘", "ERROR": "✘", "WARNING": "▲", "SKIPPED": "•", "OK": "✔"}
COLORS = {"FAILURE": QColor(179, 38, 30), "ERROR": QColor(179, 38, 30), "WARNING": QColor(176, 110, 0),
          "SKIPPED": QColor(90, 90, 90), "OK": QColor(27, 127, 59)}
STATUS_TEXT = {
    "registrerad": "Registrerad: planen väntar på att laddas upp.",
    "mottagen": "Mottagen: valideringen pågår.",
    "validerad": "Validerad: planen klarade valideringen och väntar på publicering.",
    "valideringsfel": "Valideringsfel: NGP godtog inte planen. Rätta felen nedan och leverera igen.",
    "publicerad": "Publicerad: planen finns i geodatakatalogen.",
    "fel": "Fel: NGP kunde inte behandla leveransen.",
}
GOOD = ("validerad", "publicerad")


def confirmation_text(config: NgpConfig, plan_name: str, kommun: str, kommunkod: str, errors: int,
                      resuming: bool) -> str:
    """Texten i frågan före leveransen: vart, för vem och vad som händer. Produktion varnas extra för."""
    lines = [f"Planen <b>{plan_name or 'utan namn'}</b> ({kommun}, kommunkod {kommunkod}) levereras till NGP.",
             f"Miljö: <b>{config.title}</b> ({config.base_url})."]
    if config.is_production:
        lines.append("<b>Detta är produktionsmiljön: en godkänd plan publiceras i geodatakatalogen.</b>")
    if errors:
        lines.append(f"Planen har {errors} fel som NGP stoppar. Leveransen kommer troligen att få valideringsfel.")
    if resuming:
        lines.append("Planen laddas upp igen på den tidigare mottagningen (den fick valideringsfel).")
    lines.append("Leveransen kan inte ångras härifrån. Vill du fortsätta?")
    return "<br><br>".join(lines)


class DeliveryDialog(QDialog):
    """Resultatet av en leverans: status, mottagningens id och de kontroller hos NGP som inte gick igenom."""

    def __init__(self, delivery: Delivery, environment: str, refresh: Optional[Callable[[], Delivery]] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Leverans till NGP")
        self.setMinimumSize(560, 420)
        self.delivery = delivery
        self._refresh = refresh
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-weight: bold;")
        self.info = QLabel(f"Miljö: {environment}. Mottagning: {delivery.mottagningsid}")
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info.setEnabled(False)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.btn_refresh = QPushButton("Uppdatera status")
        self.btn_refresh.setToolTip("Hämtar status och valideringsrapport igen (t.ex. för att se om planen publicerats).")
        self.btn_refresh.setVisible(refresh is not None)
        self.btn_refresh.clicked.connect(self.refresh)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        close.rejected.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_refresh)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.info)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self._show()

    def _show(self) -> None:
        delivery = self.delivery
        kind = delivery.status.typ
        text = STATUS_TEXT.get(kind, f"Status: {kind}")
        if delivery.status.felmeddelande:
            text += f" ({delivery.status.felmeddelande})"
        self.status.setText(text)
        self.status.setStyleSheet("font-weight: bold; color: " + ("#1b7f3b" if kind in GOOD else "#b3261e"
                                                                  if kind in ("valideringsfel", "fel") else "#444") + ";")
        self.list.clear()
        report = delivery.report
        self.summary.setText(report.summary if report else "Ingen valideringsrapport än.")
        if report is not None:
            for case in report.problems:
                item = QListWidgetItem(f"{MARKS.get(case.status, '•')}  [{case.id}] {case.label}"
                                       + "".join(f"\n      {m}" for m in case.messages))
                item.setForeground(QBrush(COLORS.get(case.status, QColor(0, 0, 0))))
                self.list.addItem(item)
        if not self.list.count() and report is not None:
            self.list.addItem(QListWidgetItem("✔  Alla kontroller gick igenom."))

    def refresh(self) -> None:
        if self._refresh is None:
            return
        try:
            self.delivery = self._refresh()
        except NgpError as exc:
            self.summary.setText(str(exc))
            return
        self._show()
