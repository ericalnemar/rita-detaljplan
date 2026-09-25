"""Beslut och handlingar: beslutsinformation och dokument (planbeskrivning, plankarta, underlag) som levereras till NGP
tillsammans med planen. Panelen ingår som flikar i dialogen "Planens uppgifter" (``PlanInfoDialog``). Allt är valfritt att
fylla i tills planen ska levereras (vid laga kraft krävs det, se Kontrollera planen)."""
from __future__ import annotations

import re
from typing import Optional

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                                 QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..controller import PlanController
from ..core import codelists as cl
from ..core import model

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
ROLE_TITLES = {"planbeskrivning": "Planbeskrivning", "beslutshandling": "Beslutshandling",
               "planeringsunderlag": "Planeringsunderlag"}
MAX_IMPLEMENTATION_MONTHS = 180  # 15 år
_MISSING = "#b3261e"
_REQUIRED_BG = "#fff3cd"  # gult: rutan är obligatorisk och tom
_INVALID_BG = "#f8d7da"  # svagt rött: ifylld men felaktigt skriven


def _mark(edit: QLineEdit, *, missing: bool = False, invalid: bool = False) -> None:
    if invalid:
        edit.setStyleSheet(f"background-color: {_INVALID_BG};")
    elif missing:
        edit.setStyleSheet(f"background-color: {_REQUIRED_BG};")
    else:
        edit.setStyleSheet("")


def valid_date(text: str) -> bool:
    """ÅÅÅÅ-MM-DD och ett riktigt datum."""
    from datetime import date
    if not DATE_RE.match(text or ""):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _combo(values, blank: bool = True) -> QComboBox:
    combo = QComboBox()
    if blank:
        combo.addItem("", None)
    for value in values:
        combo.addItem(value, value)
    return combo


def _text(value) -> str:
    return "" if value is None else str(value)


class DocumentDialog(QDialog):
    """En handling: planbeskrivning, beslutshandling (plankarta, protokoll) eller planeringsunderlag."""

    def __init__(self, parent=None, values: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Handling")
        self.setMinimumWidth(460)
        values = values or {}
        self.roll = QComboBox()
        for role in model.DOKUMENTROLLER:
            self.roll.addItem(ROLE_TITLES[role], role)
        self.innehall = _combo(cl.INNEHALL)
        self.huvudomrade = _combo(cl.HUVUDOMRADE)
        self.underlagstyp = _combo(cl.UNDERLAGSTYP)
        self.namn = QLineEdit()
        self.kortnamn = QLineEdit()
        self.datum = QLineEdit()
        self.datum.setPlaceholderText("ÅÅÅÅ-MM-DD")
        self.handelse = _combo(cl.RESURSHANDELSE)
        self.lank = QLineEdit()
        self.lank.setPlaceholderText("https://…")
        self.identitet = QLineEdit()
        self.identitet.setPlaceholderText("Sätts när handlingen laddats upp till NGP")
        self.specifik = QLineEdit()
        self.specifik.setPlaceholderText("t.ex. sidor eller kapitel, separerade med semikolon")
        self.error = QLabel()
        self.error.setStyleSheet("color: #b3261e;")
        self.error.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Typ av handling *", self.roll)
        form.addRow("Innehåll (beslutshandling)", self.innehall)
        form.addRow("Huvudområde (underlag)", self.huvudomrade)
        form.addRow("Underlagstyp", self.underlagstyp)
        form.addRow("Namn *", self.namn)
        form.addRow("Kortnamn", self.kortnamn)
        form.addRow("Datum", self.datum)
        form.addRow("Händelse", self.handelse)
        form.addRow("Länk (https)", self.lank)
        form.addRow("Referensidentitet", self.identitet)
        form.addRow("Specifik referens", self.specifik)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)

        self._load(values)
        for widget in (self.namn, self.datum, self.lank, self.identitet):
            widget.textChanged.connect(self._validate)
        for combo in (self.roll, self.innehall, self.huvudomrade, self.handelse):
            combo.currentIndexChanged.connect(self._validate)
        self.roll.currentIndexChanged.connect(self._enable_fields)
        self._enable_fields()
        self._validate()

    def _load(self, values: dict) -> None:
        for combo, key in ((self.roll, "roll"), (self.innehall, "innehall"), (self.huvudomrade, "huvudomrade"),
                           (self.underlagstyp, "underlagstyp"), (self.handelse, "handelse")):
            index = combo.findData(values.get(key))
            if index >= 0:
                combo.setCurrentIndex(index)
        for edit, key in ((self.namn, "namn"), (self.kortnamn, "kortnamn"), (self.datum, "datum"),
                          (self.lank, "lank"), (self.identitet, "referensIdentitet"), (self.specifik, "specifikReferens")):
            edit.setText(_text(values.get(key))[:10] if key == "datum" else _text(values.get(key)))

    def _enable_fields(self, *_) -> None:
        role = self.roll.currentData()
        self.innehall.setEnabled(role == "beslutshandling")
        self.huvudomrade.setEnabled(role == "planeringsunderlag")
        self.underlagstyp.setEnabled(role == "planeringsunderlag")

    def problems(self) -> list[str]:
        role = self.roll.currentData()
        found = []
        if not self.namn.text().strip():
            found.append("Namn saknas.")
        if role == "beslutshandling" and not self.innehall.currentData():
            found.append("Ange vad beslutshandlingen innehåller (plankarta, beslutsprotokoll eller övrigt).")
        if role == "planeringsunderlag" and not self.huvudomrade.currentData():
            found.append("Ange huvudområde för planeringsunderlaget.")
        date, event = self.datum.text().strip(), self.handelse.currentData()
        if date and not valid_date(date):
            found.append("Datum ska anges som ÅÅÅÅ-MM-DD.")
        if bool(date) != bool(event):
            found.append("Datum och händelse hör ihop: ange båda eller ingen.")
        link = self.lank.text().strip()
        if link and not link.lower().startswith("https://"):
            found.append("Länken ska börja med https://.")
        identity = self.identitet.text().strip()
        if identity and not UUID_RE.match(identity):
            found.append("Referensidentiteten ska vara ett UUID.")
        return found

    def _validate(self, *_) -> None:
        found = self.problems()
        self.error.setText("\n".join(found))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not found)

    def values(self) -> dict:
        role = self.roll.currentData()
        return {
            "roll": role,
            "innehall": self.innehall.currentData() if role == "beslutshandling" else None,
            "huvudomrade": self.huvudomrade.currentData() if role == "planeringsunderlag" else None,
            "underlagstyp": self.underlagstyp.currentData() if role == "planeringsunderlag" else None,
            "namn": self.namn.text().strip(),
            "kortnamn": self.kortnamn.text().strip() or None,
            "datum": self.datum.text().strip() or None,
            "handelse": self.handelse.currentData() if self.datum.text().strip() else None,
            "lank": self.lank.text().strip() or None,
            "referensIdentitet": self.identitet.text().strip() or None,
            "specifikReferens": self.specifik.text().strip() or None,
        }


def describe_document(document: dict) -> str:
    role = ROLE_TITLES.get(document.get("roll"), document.get("roll") or "")
    kind = document.get("innehall") or document.get("underlagstyp") or ""
    return f"{role}{' (' + kind + ')' if kind else ''}: {document.get('namn') or ''}"


class DecisionPanel(QObject):
    """Beslutsinformationen och handlingarna som två rutor (``decision_box``, ``documents_box``) att lägga i valfri
    dialog. ``apply()`` sparar dem i planen; ``changed`` sänds när något ändras."""

    changed = pyqtSignal()

    def __init__(self, controller: PlanController, parent=None):
        super().__init__(parent)
        self.controller = controller
        current = controller.decision_values()

        self.instans = _combo(cl.KOMMUNINSTANS)
        self.beslutstyp = _combo(cl.BESLUTSTYP)
        self.diarie_kommun = QLineEdit()
        self.diarie_fullmaktige = QLineEdit()
        self.dates = {}
        for key in ("datumPaborjat", "datumAntagande", "genomforandetidStartar"):
            edit = QLineEdit()
            edit.setPlaceholderText("ÅÅÅÅ-MM-DD")
            self.dates[key] = edit
        self.lagakraft = QLineEdit()
        self.lagakraft.setPlaceholderText("ÅÅÅÅ-MM-DD (flera separeras med semikolon)")
        # genomförandetiden är obligatorisk och visas på fliken Plan (se PlanInfoDialog)
        self.impl_value = QSpinBox()
        self.impl_value.setRange(0, MAX_IMPLEMENTATION_MONTHS)
        self.impl_value.setSpecialValueText("ej angiven")
        self.impl_unit = QComboBox()
        self.impl_unit.addItem("år", "ar")
        self.impl_unit.addItem("månader", "manader")
        self.impl_unit.currentIndexChanged.connect(self._update_range)
        self.implementation = QWidget()
        impl_layout = QHBoxLayout(self.implementation)
        impl_layout.setContentsMargins(0, 0, 0, 0)
        impl_layout.addWidget(self.impl_value)
        impl_layout.addWidget(self.impl_unit)
        impl_layout.addStretch(1)
        self.arkiv = QLineEdit()
        self.foregaende = QLineEdit()
        self.foregaende.setPlaceholderText("flera separeras med semikolon")
        self.domar = QLineEdit()
        self.domar.setPlaceholderText("flera separeras med semikolon")
        self.error = QLabel()
        self.error.setStyleSheet("color: #b3261e;")
        self.error.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Beslutsinstans", self.instans)
        form.addRow("Beslutstyp", self.beslutstyp)
        form.addRow("Diarienummer kommun", self.diarie_kommun)
        form.addRow("Diarienummer fullmäktige", self.diarie_fullmaktige)
        form.addRow(f"Datum påbörjat <span style='color:{_MISSING}'>*</span>", self.dates["datumPaborjat"])
        form.addRow("Datum antagande", self.dates["datumAntagande"])
        form.addRow("Datum laga kraft", self.lagakraft)
        form.addRow("Genomförandetiden startar", self.dates["genomforandetidStartar"])
        form.addRow("Arkividentitet kommun", self.arkiv)
        form.addRow("Föregående plans beteckning", self.foregaende)
        form.addRow("Berörd doms målnummer", self.domar)
        decision_hint = QLabel(f"Fält markerade med <span style='color:{_MISSING}'>*</span> är obligatoriska "
                               "för leverans och gula tills de är ifyllda.")
        decision_hint.setWordWrap(True)
        decision_hint.setEnabled(False)
        self.decision_box = QWidget()
        box_layout = QVBoxLayout(self.decision_box)
        box_layout.addWidget(decision_hint)
        box_layout.addLayout(form)
        box_layout.addWidget(self.error)
        box_layout.addStretch(1)

        self.documents: list[dict] = controller.documents()
        self.list = QListWidget()
        self.list.setMinimumHeight(140)
        self.btn_add = QPushButton("Lägg till…")
        self.btn_edit = QPushButton("Ändra…")
        self.btn_remove = QPushButton("Ta bort")
        buttons = QHBoxLayout()
        for button in (self.btn_add, self.btn_edit, self.btn_remove):
            buttons.addWidget(button)
        buttons.addStretch(1)
        hint = QLabel("Planbeskrivning, beslutshandlingar (plankarta, protokoll) och planeringsunderlag.")
        hint.setWordWrap(True)
        hint.setEnabled(False)
        self.documents_box = QWidget()
        documents_layout = QVBoxLayout(self.documents_box)
        documents_layout.addWidget(hint)
        documents_layout.addWidget(self.list, 1)
        documents_layout.addLayout(buttons)

        self._load(current)
        self._reload_documents()
        for edit in (*self.dates.values(), self.lagakraft):
            edit.textChanged.connect(self._validate)
        self.impl_value.valueChanged.connect(self._validate)
        self.impl_unit.currentIndexChanged.connect(self._validate)
        self.btn_add.clicked.connect(self.add_document)
        self.btn_edit.clicked.connect(self.edit_document)
        self.btn_remove.clicked.connect(self.remove_document)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.list.itemDoubleClicked.connect(lambda *_: self.edit_document())
        self._validate()
        self._update_buttons()

    # -- beslut ----------------------------------------------------------------------------
    def _load(self, values: dict) -> None:
        for combo, key in ((self.instans, "instansInomKommunen"), (self.beslutstyp, "beslutstyp")):
            index = combo.findData(values.get(key))
            if index >= 0:
                combo.setCurrentIndex(index)
        self.diarie_kommun.setText(_text(values.get("diarienummerKommun")))
        self.diarie_fullmaktige.setText(_text(values.get("diarienummerFullmaktige")))
        for key, edit in self.dates.items():
            edit.setText(_text(values.get(key))[:10])
        self.lagakraft.setText("; ".join(part.strip()[:10] for part in _text(values.get("datumLagakraft")).split(";")
                                         if part.strip()))
        self._set_months(values.get("genomforandetid"))
        self.arkiv.setText(_text(values.get("arkividentitetKommun")))
        self.foregaende.setText(_text(values.get("foregaendePlansBeteckning")))
        self.domar.setText(_text(values.get("berordDomsMalnummer")))

    def problems(self) -> list[str]:
        found = []
        labels = {"datumPaborjat": "Datum påbörjat", "datumAntagande": "Datum antagande",
                  "genomforandetidStartar": "Genomförandetiden startar"}
        for key, edit in self.dates.items():
            if edit.text().strip() and not valid_date(edit.text().strip()):
                found.append(f"{labels[key]} ska anges som ÅÅÅÅ-MM-DD.")
        for part in self.lagakraft.text().split(";"):
            if part.strip() and not valid_date(part.strip()):
                found.append("Datum laga kraft ska anges som ÅÅÅÅ-MM-DD (flera separeras med semikolon).")
                break
        return found

    def _mark_fields(self) -> None:
        for key, edit in self.dates.items():
            text = edit.text().strip()
            invalid = bool(text) and not valid_date(text)
            missing = key == "datumPaborjat" and not text
            _mark(edit, missing=missing, invalid=invalid)
        lagakraft_invalid = any(part.strip() and not valid_date(part.strip())
                                for part in self.lagakraft.text().split(";"))
        _mark(self.lagakraft, invalid=lagakraft_invalid)

    def months(self) -> Optional[int]:
        """Genomförandetiden i månader (så lagras den i beslutsinformationen), eller None om den inte är angiven."""
        value = self.impl_value.value()
        if value <= 0:
            return None
        return value * 12 if self.impl_unit.currentData() == "ar" else value

    def _set_months(self, months) -> None:
        try:
            months = int(months)
        except (TypeError, ValueError):
            months = 0
        if months > 0 and months % 12 == 0:
            self.impl_unit.setCurrentIndex(self.impl_unit.findData("ar"))
            self._update_range()
            self.impl_value.setValue(months // 12)
        else:
            self.impl_unit.setCurrentIndex(self.impl_unit.findData("manader"))
            self._update_range()
            self.impl_value.setValue(max(0, min(months, MAX_IMPLEMENTATION_MONTHS)))

    def _update_range(self, *_) -> None:
        """Genomförandetiden kan högst vara 15 år (PBL 4 kap. 21 §): större värden går inte att välja."""
        self.impl_value.setMaximum(MAX_IMPLEMENTATION_MONTHS // 12 if self.impl_unit.currentData() == "ar"
                                   else MAX_IMPLEMENTATION_MONTHS)

    def _validate(self, *_) -> None:
        self.error.setText("\n".join(self.problems()))
        self._mark_fields()
        self.changed.emit()

    def values(self) -> dict:
        def semicolons(text: str) -> Optional[str]:
            parts = [part.strip() for part in text.split(";") if part.strip()]
            return "; ".join(parts) or None

        values = {
            "instansInomKommunen": self.instans.currentData(),
            "beslutstyp": self.beslutstyp.currentData(),
            "diarienummerKommun": self.diarie_kommun.text().strip() or None,
            "diarienummerFullmaktige": self.diarie_fullmaktige.text().strip() or None,
            "datumLagakraft": semicolons(self.lagakraft.text()),
            "genomforandetid": self.months(),
            "arkividentitetKommun": self.arkiv.text().strip() or None,
            "foregaendePlansBeteckning": semicolons(self.foregaende.text()),
            "berordDomsMalnummer": semicolons(self.domar.text()),
        }
        values.update({key: edit.text().strip() or None for key, edit in self.dates.items()})
        return values

    # -- handlingar ------------------------------------------------------------------------
    def _reload_documents(self) -> None:
        self.list.clear()
        for index, document in enumerate(self.documents):
            item = QListWidgetItem(describe_document(document))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.list.addItem(item)
        self._update_buttons()

    def _selected(self) -> Optional[int]:
        item = self.list.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _update_buttons(self) -> None:
        selected = self._selected() is not None
        self.btn_edit.setEnabled(selected)
        self.btn_remove.setEnabled(selected)

    def add_document(self) -> None:
        dialog = DocumentDialog(self.documents_box)
        if dialog.exec():
            self.documents.append(dialog.values())
            self._reload_documents()
            self.list.setCurrentRow(self.list.count() - 1)

    def edit_document(self) -> None:
        index = self._selected()
        if index is None:
            return
        dialog = DocumentDialog(self.documents_box, self.documents[index])
        if dialog.exec():
            self.documents[index] = {**self.documents[index], **dialog.values()}
            self._reload_documents()
            self.list.setCurrentRow(index)

    def remove_document(self) -> None:
        index = self._selected()
        if index is not None:
            del self.documents[index]
            self._reload_documents()

    def apply(self) -> None:
        """Sparar beslutsinformationen och handlingarna i planen (redigeringsbufferten)."""
        self.controller.set_decision(self.values())
        self.controller.set_documents(self.documents)
