"""Dialogen "Leverera till NGP": välj att leverera planen till NGP eller spara den som JSON-fil.

Dialogen öppnas alltid, även om inställningarna för leverans till NGP inte är gjorda: då är uppladdning avstängd med en
förklaring av vad som saknas (och en knapp till inställningarna), medan filalternativet fungerar ändå. Filen kan
skickas till NGP-supporten för granskning eller laddas upp av en producent."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                                 QRadioButton, QVBoxLayout)

from ..core.ngp_client import NgpConfig
from .delivery_dialog import confirmation_text

UPLOAD, FILE = "upload", "file"


@dataclass(frozen=True)
class NgpRequest:
    """Vad dialogen behöver veta om planen."""
    plan_name: str = ""
    kommun: str = ""
    kommunkod: str = ""  # tom om planens kommun saknas
    errors: int = 0
    warnings: int = 0
    resuming: bool = False


class NgpDialog(QDialog):
    def __init__(self, request: NgpRequest, config_provider: Callable[[], NgpConfig],
                 open_settings: Optional[Callable[[], None]] = None, parent=None,
                 open_validation: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Leverera till NGP")
        self.setMinimumWidth(520)
        self.request = request
        self._config_provider = config_provider
        self._open_settings = open_settings
        self._open_validation = open_validation

        self.check = QLabel()
        self.check.setWordWrap(True)
        self.btn_validate = QPushButton("Kontrollera planen…")
        self.btn_validate.setToolTip("Visa avvikelserna mot Lantmäteriets regler och hoppa till dem i kartan.")
        self.btn_validate.clicked.connect(self._validate)
        self.btn_validate.setVisible(open_validation is not None)
        self.upload = QRadioButton("Leverera till NGP")
        self.file = QRadioButton("Spara som JSON-fil")
        self.upload_info = QLabel()
        self.upload_info.setWordWrap(True)
        self.upload_info.setTextFormat(Qt.TextFormat.RichText)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet("color: #b3261e;")
        self.btn_settings = QPushButton("Inställningar…")
        self.btn_settings.clicked.connect(self._settings)
        self.understand = QCheckBox("Jag förstår att en godkänd plan publiceras i produktionsmiljön")
        self.file_info = QLabel("Skriver leveransen (detaljplan 4.1, application/vnd.lm.detaljplan.v4+json) till en fil. "
                                "Den kan skickas till NGP-supporten för granskning eller laddas upp av en producent.")
        self.file_info.setWordWrap(True)
        self.file_info.setEnabled(False)

        self.group = QButtonGroup(self)  # de två alternativen ligger i olika rutor: koppla ihop dem
        self.group.addButton(self.upload)
        self.group.addButton(self.file)
        upload_box = QGroupBox()
        upload_layout = QVBoxLayout(upload_box)
        upload_layout.addWidget(self.upload)
        upload_layout.addWidget(self.upload_info)
        upload_layout.addWidget(self.problems)
        settings_row = QHBoxLayout()
        settings_row.addWidget(self.btn_settings)
        settings_row.addStretch(1)
        upload_layout.addLayout(settings_row)
        upload_layout.addWidget(self.understand)
        file_box = QGroupBox()
        file_layout = QVBoxLayout(file_box)
        file_layout.addWidget(self.file)
        file_layout.addWidget(self.file_info)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.check)
        validate_row = QHBoxLayout()
        validate_row.addWidget(self.btn_validate)
        validate_row.addStretch(1)
        layout.addLayout(validate_row)
        layout.addWidget(upload_box)
        layout.addWidget(file_box)
        layout.addWidget(self.buttons)

        self.upload.toggled.connect(self._update)
        self.file.toggled.connect(self._update)
        self.understand.toggled.connect(self._update)
        self._first = True
        self._forced = False
        self.refresh()

    # -- innehåll -----------------------------------------------------------------------
    def config(self) -> NgpConfig:
        return self._config_provider()

    def upload_problems(self) -> list[str]:
        """Skäl till att uppladdning inte går: saknad kommun och ofullständiga inställningar."""
        found = []
        if not self.request.kommunkod:
            found.append("Kommunen är inte angiven i planens uppgifter (den avgör vilken producent som levererar).")
        return found + self.config().problems()

    def refresh(self) -> None:
        """Läser om inställningarna (t.ex. efter att inställningarna ändrats) och uppdaterar dialogen."""
        request = self.request
        parts = []
        if request.errors or request.warnings:
            parts.append(f"Kontroll av planen: <b>{request.errors} fel</b> och {request.warnings} varningar. "
                         "Fel stoppar leveransen hos NGP (se Kontrollera planen).")
        else:
            parts.append("Kontroll av planen: inga avvikelser.")
        self.check.setTextFormat(Qt.TextFormat.RichText)
        self.check.setText(f"Planen <b>{request.plan_name or 'utan namn'}</b>. " + " ".join(parts))
        problems = self.upload_problems()
        can_upload = not problems
        self.upload.setEnabled(can_upload)
        self.problems.setText("\n".join(problems))
        self.problems.setVisible(bool(problems))
        self.btn_settings.setVisible(bool(problems) and self._open_settings is not None)
        config = self.config()
        self.upload_info.setText(confirmation_text(config, request.plan_name, request.kommun, request.kommunkod,
                                                   request.errors, request.resuming) if can_upload
                                 else "Leveransen görs via Lantmäteriets Uppdatering-API och kräver producentbehörighet.")
        self.understand.setVisible(config.is_production)
        if not can_upload:
            self.file.setChecked(True)
            self._forced = True  # filen valdes av programmet, inte av användaren
        elif self._first or self._forced:
            self.upload.setChecked(True)  # standardval när uppladdning går; användarens eget val ändras inte senare
            self._forced = False
        self._first = False
        self._update()

    def choice(self) -> str:
        return UPLOAD if self.upload.isChecked() and self.upload.isEnabled() else FILE

    def _update(self, *_) -> None:
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self.choice() == UPLOAD:
            ok.setText("Leverera")
            ok.setEnabled(not self.config().is_production or self.understand.isChecked())
        else:
            ok.setText("Spara fil…")
            ok.setEnabled(True)
        self.understand.setEnabled(self.choice() == UPLOAD)

    def _validate(self) -> None:
        if self._open_validation is not None:
            self._open_validation()

    def _settings(self) -> None:
        if self._open_settings is not None:
            self._open_settings()
        self.refresh()
