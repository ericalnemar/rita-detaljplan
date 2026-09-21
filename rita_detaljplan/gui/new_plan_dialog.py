"""Dialogruta för att skapa en ny detaljplan."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from qgis.core import QgsCoordinateReferenceSystem
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                                 QRadioButton, QVBoxLayout, QWidget)

from ..core import geopackage, storage
from .kommun_combo import KommunCombo


@dataclass(frozen=True)
class NewPlanValues:
    directory: Path
    filnamn: str
    kommun: str
    kommunkod: str
    epsg: int
    kind: str = "geopackage"  # "geopackage" (lokal fil) eller "postgis" (schema i en databas)
    connection: str = ""  # PostGIS: namnet på QGIS-anslutningen
    schema: str = ""  # PostGIS: schemat som planen får


def safe_filename(name: str) -> str:
    """Gör ett plannamn/beteckning till ett filnamn (behåller å, ä, ö)."""
    return re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE).strip("_")


class NewPlanDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ny detaljplan")
        self.setMinimumWidth(460)

        self.kommun = KommunCombo()
        self.kommun.setToolTip("Kommunen planen ligger i. Kommunkoden används som producent vid leverans till NGP.")
        self.planbeteckning = QLineEdit()
        self.planbeteckning.setPlaceholderText("Kommunens beteckning eller ett arbetsnamn")
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self.crs = QComboBox()
        for epsg in geopackage.epsg_codes():
            self.crs.addItem(f"EPSG:{epsg} – {QgsCoordinateReferenceSystem(f'EPSG:{epsg}').description()}", epsg)
        self.crs.setCurrentIndex(0)

        # -- var planen ska lagras ---------------------------------------------------------
        self.use_file = QRadioButton("Lokal fil (GeoPackage)")
        self.use_postgis = QRadioButton("PostGIS-databas")
        self.use_file.setChecked(True)
        self.connection = QComboBox()
        self.schema = QLineEdit()
        self.schema.setPlaceholderText("schemanamn, t.ex. dp_2026_1")
        self.schema.setToolTip("Planen får ett eget schema i databasen. Gemener a–z, siffror och understreck.")
        self._schema_edited = False
        self.postgis_note = QLabel()
        self.postgis_note.setWordWrap(True)
        self.postgis_note.setEnabled(False)
        names = sorted(storage.postgis_connections())
        for name in names:
            self.connection.addItem(name, name)
        if not names:
            self.use_postgis.setEnabled(False)
            self.use_postgis.setToolTip("Det finns inga PostgreSQL-anslutningar i QGIS. Lägg till en under "
                                        "Lager → Lägg till lager → Lägg till PostgreSQL-lager → Ny.")
        self.postgis_box = QWidget()
        postgis_form = QFormLayout(self.postgis_box)
        postgis_form.setContentsMargins(0, 0, 0, 0)
        postgis_form.addRow("Anslutning", self.connection)
        postgis_form.addRow("Schema", self.schema)
        self.postgis_box.setVisible(False)
        where = QHBoxLayout()
        where.addWidget(self.use_file)
        where.addWidget(self.use_postgis)
        where.addStretch(1)

        form = QFormLayout()
        form.addRow("Kommun", self.kommun)
        form.addRow("Planbeteckning / filnamn", self.planbeteckning)
        form.addRow("Lagras i", where)
        form.addRow("", self.postgis_box)
        form.addRow("Projektfil i mapp", self.folder)
        form.addRow("Koordinatsystem", self.crs)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Skapa")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

        self.kommun.currentTextChanged.connect(self._update_ok)
        self.planbeteckning.textChanged.connect(self._update_ok)
        self.folder.fileChanged.connect(self._update_ok)
        self.use_postgis.toggled.connect(self._on_storage_changed)
        self.connection.currentIndexChanged.connect(self._update_ok)
        self.schema.textEdited.connect(self._on_schema_edited)
        self.schema.textChanged.connect(self._update_ok)
        self.planbeteckning.textChanged.connect(self._suggest_schema)
        self._update_ok()

    def is_postgis(self) -> bool:
        return self.use_postgis.isChecked()

    def _on_storage_changed(self, *_):
        self.postgis_box.setVisible(self.is_postgis())
        self._suggest_schema()
        self._update_ok()

    def _on_schema_edited(self, *_):
        self._schema_edited = True  # användaren har valt schemanamn själv: föreslå inte över det

    def _suggest_schema(self, *_):
        if not self._schema_edited:
            self.schema.setText(storage.schema_name(self.planbeteckning.text()))

    def _update_ok(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.is_valid())

    def is_valid(self) -> bool:
        if self.is_postgis() and not (self.connection.currentData() and storage.is_valid_schema(self.schema.text())):
            return False
        return bool(
            self.kommun.selected() is not None
            and safe_filename(self.planbeteckning.text())
            and self.folder.filePath().strip()
        )

    def values(self) -> NewPlanValues:
        kommun = self.kommun.selected()
        return NewPlanValues(
            directory=Path(self.folder.filePath()),
            filnamn=safe_filename(self.planbeteckning.text()),
            kommun=kommun.namn,
            kommunkod=kommun.kod,
            epsg=int(self.crs.currentData(Qt.ItemDataRole.UserRole)),
            kind="postgis" if self.is_postgis() else "geopackage",
            connection=self.connection.currentData() or "" if self.is_postgis() else "",
            schema=self.schema.text().strip() if self.is_postgis() else "",
        )
