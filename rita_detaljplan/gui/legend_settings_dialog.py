"""Inställningar för teckenförklaringen: teckensnitt, teckenstorlekar, storlek på rutor och avstånd mellan element.

Standardvärdena ger den teckenförklaring som skapas utan att något ändrats (se ``LegendStyle``). Inställningarna sparas i
QGIS-profilen och gäller alla teckenförklaringar tills de ändras igen."""
from __future__ import annotations

from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFontComboBox, QFormLayout,
                                 QGroupBox, QLabel, QPushButton, QVBoxLayout)

from ..core.legend_layout import LegendStyle

# (fält, etikett, enhet, steg)
TEXT_FIELDS = (
    ("heading_size", "Rubrik (PLANBESTÄMMELSER)", "pt", 1.0),
    ("title_size", "Rubriker (ANVÄNDNING AV …)", "pt", 0.5),
    ("group_size", "Underrubriker (kategorier)", "pt", 0.5),
    ("text_size", "Bestämmelsetexter", "pt", 0.5),
)
BOX_FIELDS = (
    ("swatch_width", "Rutornas bredd", "mm", 0.5),
    ("swatch_height", "Rutornas höjd", "mm", 0.2),
    ("line_length", "Linjesymbolernas längd", "mm", 0.5),
)
SPACING_FIELDS = (
    ("text_gap", "Mellan ruta och text", "mm", 0.5),
    ("entry_gap", "Mellan rader", "mm", 0.2),
    ("group_gap", "Före underrubrik", "mm", 0.5),
    ("section_gap", "Före rubrik", "mm", 0.5),
    ("column_gap", "Mellan kolumner", "mm", 0.5),
)


class LegendSettingsDialog(QDialog):
    def __init__(self, style: LegendStyle | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inställningar för teckenförklaring")
        self.setMinimumWidth(420)
        self.fields: dict[str, QDoubleSpinBox] = {}
        self.font_box = QFontComboBox()
        self.intro = QCheckBox("Med inledande text under PLANBESTÄMMELSER")
        self.scale_with_page = QCheckBox("Skala storlekar och avstånd efter sidans bredd (måtten gäller A1)")

        layout = QVBoxLayout(self)
        note = QLabel("Ändringarna gäller nästa teckenförklaring du skapar, och en teckenförklaring som redan finns "
                      "i layouten görs om direkt. Standardvärdena ger den teckenförklaring som skapas utan ändringar.")
        note.setWordWrap(True)
        layout.addWidget(note)
        text_form = QFormLayout()
        text_form.addRow("Teckensnitt", self.font_box)
        layout.addWidget(self._group("Text", text_form, TEXT_FIELDS))
        layout.addWidget(self._group("Rutor och linjer", QFormLayout(), BOX_FIELDS))
        layout.addWidget(self._group("Avstånd", QFormLayout(), SPACING_FIELDS))
        layout.addWidget(self.intro)
        layout.addWidget(self.scale_with_page)
        self.reset = QPushButton("Återställ standardvärden")
        self.reset.clicked.connect(lambda _checked=False: self.set_style(LegendStyle()))
        layout.addWidget(self.reset)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Spara")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.set_style(style if style is not None else LegendStyle.load())

    def _group(self, title: str, form: QFormLayout, fields) -> QGroupBox:
        for name, label, unit, step in fields:
            box = QDoubleSpinBox()
            box.setDecimals(1)
            box.setSingleStep(step)
            box.setSuffix(f" {unit}")
            low, high = self._range(name)
            box.setRange(low, high)
            self.fields[name] = box
            form.addRow(label, box)
        group = QGroupBox(title)
        group.setLayout(form)
        return group

    @staticmethod
    def _range(name: str) -> tuple:
        """Gränserna som ``LegendStyle.clamped`` använder, så att dialogen inte släpper igenom något som ändras efteråt."""
        probe_low = LegendStyle(**{name: -1e9}).clamped()
        probe_high = LegendStyle(**{name: 1e9}).clamped()
        return getattr(probe_low, name), getattr(probe_high, name)

    def set_style(self, style: LegendStyle) -> None:
        self.font_box.setCurrentFont(QFont(style.font))
        for name, box in self.fields.items():
            box.setValue(getattr(style, name))
        self.intro.setChecked(style.intro)
        self.scale_with_page.setChecked(style.scale_with_page)

    def style(self) -> LegendStyle:
        values = {name: box.value() for name, box in self.fields.items()}
        return LegendStyle(font=self.font_box.currentFont().family(), intro=self.intro.isChecked(),
                           scale_with_page=self.scale_with_page.isChecked(), **values).clamped()

    def accept(self) -> None:
        self.style().save()
        super().accept()
