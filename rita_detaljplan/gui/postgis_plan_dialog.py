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
        self.schema = QComboBox()
        self.plans = QListWidget()
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #b3261e;")
        form = QFormLayout()
        form.addRow("Anslutning", self.connection)
        form.addRow("Schema", self.schema)
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
        self.connection.currentIndexChanged.connect(self.reload_schemas)
        self.schema.currentIndexChanged.connect(self.reload_plans)
        self.plans.itemSelectionChanged.connect(self._update_ok)
        self.plans.itemDoubleClicked.connect(lambda *_: self.accept() if self.selection() else None)
        self.reload_schemas()

    def reload_schemas(self, *_) -> None:
        """Listar scheman som delas mellan planer (har pluginets tabeller) i den valda databasen."""
        self.schema.clear()
        self.error.setText("")
        connection = self._connections.get(self.connection.currentData() or "")
        if connection is not None:
            try:
                for schema in storage.list_plugin_schemas(connection):
                    self.schema.addItem(schema, schema)
            except storage.PostgisError as exc:
                self.error.setText(str(exc))
            else:
                if not self.schema.count():
                    self.error.setText("Databasen innehåller inga scheman skapade med pluginet.")
        self.reload_plans()

    def reload_plans(self, *_) -> None:
        """Listar planerna i det valda schemat."""
        self.plans.clear()
        connection = self._connections.get(self.connection.currentData() or "")
        schema = self.schema.currentData()
        if connection is not None and schema:
            try:
                for plan_id in storage.list_plans_in_schema(connection, schema):
                    item = QListWidgetItem(plan_id)
                    item.setData(Qt.ItemDataRole.UserRole, plan_id)
                    self.plans.addItem(item)
            except storage.PostgisError as exc:
                self.error.setText(str(exc))
            else:
                if not self.plans.count() and not self.error.text():
                    self.error.setText("Schemat innehåller inga planer.")
        self._update_ok()

    def selection(self) -> Optional[tuple[str, str, str]]:
        """(anslutning, schema, plan-id) för den valda planen, eller None."""
        item = self.plans.currentItem()
        if item is None or not self.connection.currentData() or not self.schema.currentData():
            return None
        return self.connection.currentData(), self.schema.currentData(), item.data(Qt.ItemDataRole.UserRole)

    def _update_ok(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.selection() is not None)
