"""Vilken annan detaljplan en egenskapsbestämmelse reglerar (``reglerarDetaljplan``, NIS Detaljplan 4.1) – en
UUID-referens till en annan plan, t.ex. vid samordning mellan grannplaner. Finns bara för egenskapsbestämmelser
(se ``core.catalog.PROPERTY_LAYERS``); knappen för det ligger i tilldelningsdialogen (``AssignDialog``)."""
from __future__ import annotations

import re
from typing import Optional

from qgis.PyQt.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from ..controller import PlanController
from ..core.project import find_plan_group, plan_groups, plan_identity

UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
_MISSING = "#b00020"


class RegulatesPlanDialog(QDialog):
    def __init__(self, row_fid: int, controller: PlanController, parent=None):
        super().__init__(parent)
        self.row_fid = row_fid
        self.controller = controller
        self.setWindowTitle("Reglerar annan detaljplan")
        self.setMinimumWidth(480)

        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.addItem("", None)
        active = find_plan_group(controller.project)
        for group in plan_groups(controller.project):
            if group is active:
                continue  # en bestämmelse reglerar en ANNAN plan, inte sin egen
            identity = plan_identity(group)
            if identity:
                self.combo.addItem(group.name(), identity)

        current = controller.bestammelse_regulates_plan(row_fid)
        if current:
            index = self.combo.findData(current)
            if index >= 0:
                self.combo.setCurrentIndex(index)
            else:
                self.combo.setEditText(current)  # en identitet för en plan som inte är laddad här

        self.error = QLabel()
        self.error.setStyleSheet(f"color: {_MISSING};")
        self.error.setWordWrap(True)
        self.combo.editTextChanged.connect(self._validate)

        form = QFormLayout()
        form.addRow("Annan detaljplan", self.combo)
        hint = QLabel("Välj bland andra laddade planer, eller skriv in identiteten (UUID) direkt om planen inte "
                      "är laddad här. Lämna tomt för att ta bort kopplingen. Valfritt – gäller bara "
                      "egenskapsbestämmelser.")
        hint.setWordWrap(True)
        hint.setEnabled(False)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Spara")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)
        self._validate()

    def value(self) -> Optional[str]:
        """Den valda planens identitet (från listan), eller den fritt skrivna texten (en identitet för en plan
        som inte är laddad här) – tomt om inget är ifyllt."""
        data = self.combo.currentData()
        if data:
            return data
        return self.combo.currentText().strip() or None

    def _validate(self, *_) -> None:
        value = self.value()
        invalid = bool(value) and not UUID_RE.match(value)
        self.error.setText("Ska vara en identitet (UUID), t.ex. vald ur listan." if invalid else "")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(not invalid)

    def accept(self) -> None:
        self.controller.set_bestammelse_regulates_plan(self.row_fid, self.value())
        super().accept()
