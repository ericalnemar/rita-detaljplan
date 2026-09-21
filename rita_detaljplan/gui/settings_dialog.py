"""Inställningar för leverans till NGP: miljö, adresser och autentisering. (Referensskalan ställs in i Planens uppgifter,
teckenförklaringen i layoutläget.)"""
from __future__ import annotations

from qgis.PyQt.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel,
                                 QLineEdit, QPushButton, QVBoxLayout)
from qgis.PyQt.QtCore import Qt

from ..core import ngp_client as ngp
from ..core import settings


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inställningar för leverans till NGP")
        self.setMinimumWidth(520)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Spara")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._build_ngp()
        layout = QVBoxLayout(self)
        layout.addWidget(self.ngp_box)
        layout.addWidget(self.buttons)

    # -- leverans till NGP ---------------------------------------------------------------------
    def _build_ngp(self) -> None:
        config = settings.ngp_config()
        self.ngp_env = QComboBox()
        for key, env in ngp.ENVIRONMENTS.items():
            self.ngp_env.addItem(env.title, key)
        self.ngp_env.addItem("Egen adress", "egen")
        self.ngp_base = QLineEdit(config.base_url)
        self.ngp_token = QLineEdit(config.token_url)
        self.ngp_token.setPlaceholderText("tomt = ingen inloggning")
        self.ngp_auth = QComboBox()
        self.ngp_auth.addItem("(ingen vald)", "")
        for cid, name in settings.auth_configs():
            self.ngp_auth.addItem(f"{name} ({cid})", cid)
        if config.authcfg and self.ngp_auth.findData(config.authcfg) < 0:
            self.ngp_auth.addItem(config.authcfg, config.authcfg)
        self.ngp_auth.setCurrentIndex(max(0, self.ngp_auth.findData(config.authcfg)))
        self.ngp_env.setCurrentIndex(max(0, self.ngp_env.findData(config.environment)))
        self.ngp_note = QLabel("Nyckel och hemlighet från Lantmäteriets API-portal lagras i QGIS autentiseringsdatabas: "
                               "lägg till en konfiguration av typen <i>Grundläggande autentisering</i> under "
                               "Inställningar → Alternativ → Autentisering (nyckeln som användarnamn, hemligheten som "
                               "lösenord) och välj den här. Leverans till NGP är inte verifierad mot Lantmäteriets "
                               "miljö och kräver producentbehörighet.")
        self.ngp_note.setWordWrap(True)
        self.ngp_note.setEnabled(False)
        self.ngp_test = QPushButton("Testa anslutning")
        self.ngp_result = QLabel()
        self.ngp_result.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Miljö", self.ngp_env)
        form.addRow("Adress till API:et", self.ngp_base)
        form.addRow("Adress till tokentjänsten", self.ngp_token)
        form.addRow("Autentisering", self.ngp_auth)
        self.ngp_box = QGroupBox("Leverans till NGP")
        box = QVBoxLayout(self.ngp_box)
        box.addWidget(self.ngp_note)
        box.addLayout(form)
        box.addWidget(self.ngp_test)
        box.addWidget(self.ngp_result)
        self.ngp_env.currentIndexChanged.connect(self._on_ngp_environment)
        self.ngp_test.clicked.connect(self.test_connection)

    def _on_ngp_environment(self, *_) -> None:
        env = ngp.ENVIRONMENTS.get(self.ngp_env.currentData())
        editable = env is None
        if env is not None:
            self.ngp_base.setText(env.base_url)
            self.ngp_token.setText(env.token_url)
        self.ngp_base.setReadOnly(not editable)
        self.ngp_token.setReadOnly(not editable)

    def ngp_config(self) -> "ngp.NgpConfig":
        return ngp.NgpConfig(environment=self.ngp_env.currentData(), base_url=self.ngp_base.text().strip(),
                             token_url=self.ngp_token.text().strip(), authcfg=self.ngp_auth.currentData() or "")

    def test_connection(self) -> bool:
        """Kontrollerar att tjänsten är uppe och att inloggningen fungerar. Blockerar kort medan anropen görs."""
        config = self.ngp_config()
        problems = config.problems()
        if problems:
            self.ngp_result.setText("<span style='color:#b3261e'>" + " ".join(problems) + "</span>")
            return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            client = self._client(config)
            health = client.health()
            client.token()
        except ngp.NgpError as exc:
            self.ngp_result.setText(f"<span style='color:#b3261e'>{exc}</span>")
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self.ngp_result.setText(f"<span style='color:#1b7f3b'>Tjänsten är {health} och inloggningen fungerar.</span>")
        return True

    def _client(self, config: "ngp.NgpConfig") -> "ngp.NgpClient":  # särskilt för att kunna bytas ut i tester
        return ngp.NgpClient(config)

    def accept(self):
        settings.set_ngp_config(self.ngp_config())
        super().accept()
