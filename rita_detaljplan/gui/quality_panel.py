"""Kvalitetsbeskrivning och användbarhet (NIS Detaljplan 4.1): samma sex fält (se ``core.model.QUALITY_FIELDS``)
används både för planen som helhet (fliken Kvalitet i Planens uppgifter) och för en enskild bestämmelse (knappen
Kvalitet… i tilldelningsdialogen) – krävs vid laga kraft, se docs/ngp-regler.md och
``core.validation.check_laga_kraft``."""
from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..controller import PlanController
from ..core import codelists as cl

_MISSING = "#b00020"
_STAR = f" <span style='color:{_MISSING}'>*</span>"


def _combo(values: tuple[str, ...]) -> QComboBox:
    combo = QComboBox()
    combo.addItem("", None)
    for value in values:
        combo.addItem(value, value)
    return combo


class QualityPanel(QWidget):
    """``load(values)``/``values()`` läser och skriver fälten som ett vanligt formulär. Digitaliseringsnivå och
    användbarhet krävs vid laga kraft (markerade med *); övriga är valfria."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.digitaliseringsniva = _combo(cl.DIGITALISERINGSNIVA)
        self.beskrivning_niva = QLineEdit()
        self.beskrivning_niva.setPlaceholderText("Fritext, t.ex. vad som inte är fullständigt digitaliserat")
        self.korrigerade_granser = QCheckBox("Gränserna är korrigerade mot ett bättre underlag")
        self.kontrollerat = QCheckBox("Planeringsunderlaget är kontrollerat")
        self.anvandbarhet = _combo(cl.TILLFORLITLIGHET)
        self.beskrivning_anvandbarhet = QLineEdit()
        self.beskrivning_anvandbarhet.setPlaceholderText("Fritext, t.ex. varför tillförlitligheten är låg")

        form = QFormLayout()
        form.addRow("Digitaliseringsnivå" + _STAR, self.digitaliseringsniva)
        form.addRow("Beskrivning av nivå", self.beskrivning_niva)
        form.addRow("", self.korrigerade_granser)
        form.addRow("", self.kontrollerat)
        form.addRow("Användbarhet" + _STAR, self.anvandbarhet)
        form.addRow("Beskrivning av användbarhet", self.beskrivning_anvandbarhet)
        hint = QLabel(f"Fält markerade med <span style='color:{_MISSING}'>*</span> krävs vid laga kraft "
                      "(kvalitetsbeskrivning och användbarhet enligt Nationell informationsspecifikation "
                      "Detaljplan 4.1).")
        hint.setWordWrap(True)
        hint.setEnabled(False)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addStretch(1)

    def load(self, values: dict) -> None:
        self.digitaliseringsniva.setCurrentIndex(max(self.digitaliseringsniva.findData(
            values.get("digitaliseringsniva")), 0))
        self.beskrivning_niva.setText(values.get("beskrivningNiva") or "")
        self.korrigerade_granser.setChecked(bool(values.get("korrigeradeGranser")))
        self.kontrollerat.setChecked(bool(values.get("kontrolleratPlaneringsunderlag")))
        self.anvandbarhet.setCurrentIndex(max(self.anvandbarhet.findData(values.get("anvandbarhet")), 0))
        self.beskrivning_anvandbarhet.setText(values.get("beskrivningAnvandbarhet") or "")

    def values(self) -> dict:
        return {
            "digitaliseringsniva": self.digitaliseringsniva.currentData(),
            "beskrivningNiva": self.beskrivning_niva.text().strip() or None,
            "korrigeradeGranser": self.korrigerade_granser.isChecked(),
            "kontrolleratPlaneringsunderlag": self.kontrollerat.isChecked(),
            "anvandbarhet": self.anvandbarhet.currentData(),
            "beskrivningAnvandbarhet": self.beskrivning_anvandbarhet.text().strip() or None,
        }


class QualityDialog(QDialog):
    """En bestämmelses kvalitetsbeskrivning och användbarhet (se ``AssignDialog.edit_quality``): samma
    ``QualityPanel`` som planens egen flik i Planens uppgifter, men för en enskild rad i tabellen ``bestammelse``."""

    def __init__(self, row_fid: int, controller: PlanController, parent=None):
        super().__init__(parent)
        self.row_fid = row_fid
        self.controller = controller
        self.setWindowTitle("Kvalitetsbeskrivning för bestämmelsen")
        self.setMinimumWidth(480)
        self.panel = QualityPanel(self)
        self.panel.load(controller.bestammelse_quality(row_fid))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Spara")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self.controller.set_bestammelse_quality(self.row_fid, self.panel.values())
        super().accept()
