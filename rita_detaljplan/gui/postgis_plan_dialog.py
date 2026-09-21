"""Dialogruta för att öppna en detaljplan som ligger i en PostGIS-databas."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QListWidget,
                                 QListWidgetItem, QVBoxLayout)

from ..core import storage


class PostgisPlanDialog(QDialog):
    def __init__(self, parent=None, connections: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Öppna detaljplan från PostGIS")
        self.setMinimumWidth(420)
        self._connections = connections if connections is not None else storage.postgis_connections()
        self.connection = QComboBox()
        for name in sorted(self._connections):
            self.connection.addItem(name, name)
        self.plans = QListWidget()
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #b3261e;")
        form = QFormLayout()
        form.addRow("Anslutning", self.connection)
        form.addRow("Detaljplaner", self.plans)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Öppna")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)
        self.connection.currentIndexChanged.connect(self.reload)
        self.plans.itemSelectionChanged.connect(self._update_ok)
        self.plans.itemDoubleClicked.connect(lambda *_: self.accept() if self.selection() else None)
        self.reload()

    def reload(self, *_) -> None:
        """Listar detaljplanerna (scheman med pluginets metadatatabell) i den valda databasen."""
        self.plans.clear()
        self.error.setText("")
        connection = self._connections.get(self.connection.currentData() or "")
        if connection is not None:
            try:
                for schema in storage.list_postgis_plans(connection):
                    item = QListWidgetItem(schema)
                    item.setData(Qt.ItemDataRole.UserRole, schema)
                    self.plans.addItem(item)
            except storage.PostgisError as exc:
                self.error.setText(str(exc))
            else:
                if not self.plans.count():
                    self.error.setText("Databasen innehåller inga detaljplaner skapade med pluginet.")
        self._update_ok()

    def selection(self) -> Optional[tuple[str, str]]:
        """(anslutning, schema) för den valda planen, eller None."""
        item = self.plans.currentItem()
        if item is None or not self.connection.currentData():
            return None
        return self.connection.currentData(), item.data(Qt.ItemDataRole.UserRole)

    def _update_ok(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.selection() is not None)
