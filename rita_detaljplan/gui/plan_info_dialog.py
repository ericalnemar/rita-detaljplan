"""Dialogen "Planens uppgifter", med flikarna Plan, Beslut och Handlingar (allt som levereras till NGP utöver
geometrin och bestämmelserna).

Fliken Plan: kommun, namn, syfte, status och plantyp, med tydliga krav inför leverans. Obligatoriska fält är markerade
med * och en checklista visar löpande vad som återstår. Fliken Beslut: beslutsinformationen. Fliken Handlingar:
planbeskrivning, plankarta och underlag. Att spara är aldrig blockerat av att något saknas (man kan fylla i resten
senare), bara av värden som är felaktigt skrivna, t.ex. ett datum som inte är ett datum."""
from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..controller import PlanController
from ..core import codelists as cl
from ..core import requirements, settings
from ..core.project import restyle
from .decision_dialog import DecisionPanel
from .kommun_combo import KommunCombo

SYFTE_MAX = 4000  # fältlängd enligt specifikationen
_REQUIRED = {key for key, _ in requirements.REQUIRED_PLAN_FIELDS} | {"genomforandetid", "datumPaborjat"}
_OK, _MISSING = "#1b7f3b", "#b00020"
_REQUIRED_BG = "#fff3cd"  # gult: rutan är obligatorisk och tom


def _label(text: str, key: str) -> str:
    return f"{text} <span style='color:{_MISSING}'>*</span>" if key in _REQUIRED else text


def mark_required(widget, missing: bool) -> None:
    """Gul bakgrund på en ruta som är obligatorisk och just nu tom."""
    widget.setStyleSheet(f"background-color: {_REQUIRED_BG};" if missing else "")


class PlanInfoDialog(QDialog):
    def __init__(self, controller: PlanController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Planens uppgifter")
        self.setMinimumWidth(600)

        self.kommun = KommunCombo()
        self.beteckning = QLineEdit()
        self.beteckning.setPlaceholderText("Kommunens beteckning på planen (krävs vid laga kraft)")
        self.namn = QLineEdit()
        self.namn.setPlaceholderText("Planens namn, t.ex. fastighetsbeteckning eller kvartersnamn")
        self.syfte = QPlainTextEdit()
        self.syfte.setPlaceholderText("Vad detaljplanen ska möjliggöra och hur den förhåller sig till platsen")
        self.syfte.setFixedHeight(3 * self.syfte.fontMetrics().lineSpacing() + 14)  # tre rader; längre text rullas
        self.syfte_count = QLabel()
        self.syfte_count.setEnabled(False)
        self.status = QComboBox()
        self.status.addItems(cl.PLANSTATUS)
        self.typ = QComboBox()
        self.typ.addItems(cl.PLANTYP)

        form = QFormLayout()
        form.addRow(_label("Kommun", "kommun"), self.kommun)
        form.addRow(_label("Namn", "namn"), self.namn)
        form.addRow(_label("Syfte", "syfte"), self.syfte)
        form.addRow("", self.syfte_count)
        form.addRow(_label("Status", "status"), self.status)
        form.addRow(_label("Plantyp", "typ"), self.typ)
        form.addRow(_label("Beteckning", "beteckning"), self.beteckning)
        self.decision = DecisionPanel(controller, self)
        form.addRow(_label("Genomförandetid", "genomforandetid"), self.decision.implementation)
        self._required_widgets = {"kommun": self.kommun, "namn": self.namn, "syfte": self.syfte,
                                  "status": self.status, "typ": self.typ,
                                  "genomforandetid": self.decision.impl_value}

        self.scale = QComboBox()
        self.scale.setEditable(True)
        for value in settings.SCALES:
            self.scale.addItem(settings.scale_text(value), value)
        self.set_scale(settings.reference_scale())
        self.scale_error = QLabel()
        self.scale_error.setStyleSheet(f"color: {_MISSING};")
        scale_note = QLabel("Linjer och texter ritas så att de ser rätt ut när plankartan skrivs ut i den här skalan, "
                            "oavsett hur mycket du zoomar. Standard är 1:1000. Gäller alla planer.")
        scale_note.setWordWrap(True)
        scale_note.setEnabled(False)
        scale_form = QFormLayout()
        scale_form.addRow("Referensskala", self.scale)
        view_box = QGroupBox("Visning i kartan")
        view_layout = QVBoxLayout(view_box)
        view_layout.addLayout(scale_form)
        view_layout.addWidget(self.scale_error)
        view_layout.addWidget(scale_note)

        self.checklist = QLabel()
        self.checklist.setWordWrap(True)
        self.checklist.setTextFormat(Qt.TextFormat.RichText)
        box = QGroupBox("Före leverans till NGP")
        box_layout = QVBoxLayout(box)
        box_layout.addWidget(self.checklist)
        note = QLabel("<i>Du kan spara när som helst och fylla i resten senare. Fälten markerade med "
                      f"<span style='color:{_MISSING}'>*</span> är obligatoriska för leverans och gula tills "
                      "de är ifyllda.</i>")
        note.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Spara")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        plan_tab = QWidget()
        plan_layout = QVBoxLayout(plan_tab)
        plan_layout.addLayout(form)
        plan_layout.addWidget(box)
        plan_layout.addWidget(view_box)
        plan_layout.addWidget(note)
        self.tabs = QTabWidget()
        self.tabs.addTab(plan_tab, "Plan")
        self.tabs.addTab(self.decision.decision_box, "Beslut")
        self.tabs.addTab(self.decision.documents_box, "Handlingar")

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.buttons)
        self.decision.changed.connect(self._update_save)
        self.decision.changed.connect(self._refresh)
        self.scale.editTextChanged.connect(self._update_save)
        self._update_save()

        self._load()
        for widget in (self.namn, self.beteckning):
            widget.textChanged.connect(self._refresh)
        self.syfte.textChanged.connect(self._refresh)
        self.kommun.currentTextChanged.connect(self._refresh)
        self.status.currentIndexChanged.connect(self._refresh)
        self.typ.currentIndexChanged.connect(self._refresh)
        self._refresh()

    # -- innehåll ---------------------------------------------------------------------
    def _load(self):
        values = self.controller.plan_values()
        self.kommun.set_kommun(values["kommun"])
        self.namn.setText(values["namn"] or "")
        self.beteckning.setText(values["beteckning"] or "")
        self.syfte.setPlainText(values["syfte"] or "")
        if values["status"] in cl.PLANSTATUS:
            self.status.setCurrentText(values["status"])
        if values["typ"] in cl.PLANTYP:
            self.typ.setCurrentText(values["typ"])

    def values(self) -> dict:
        kommun = self.kommun.selected()
        return {
            "kommun": kommun.namn if kommun else (self.kommun.currentText().strip() or None),
            "namn": self.namn.text().strip() or None,
            "beteckning": self.beteckning.text().strip() or None,
            "syfte": self.syfte.toPlainText().strip()[:SYFTE_MAX] or None,
            "status": self.status.currentText(),
            "typ": self.typ.currentText(),
        }

    def checklist_items(self) -> list[requirements.Requirement]:
        datum_paborjat = self.decision.dates["datumPaborjat"].text().strip() or None
        return self.controller.requirements(self.values(), self.decision.months(), datum_paborjat)

    def _refresh(self, *_):
        length = len(self.syfte.toPlainText())
        self.syfte_count.setText(f"{length} av {SYFTE_MAX} tecken")
        self.syfte_count.setStyleSheet(f"color: {_MISSING};" if length > SYFTE_MAX else "")
        lines = []
        by_field = {}
        for req in self.checklist_items():
            mark, colour = ("✔", _OK) if req.ok else ("✘", _MISSING)
            lines.append(f"<span style='color:{colour}'><b>{mark}</b></span> {req.text}")
            if req.field:
                by_field[req.field] = req.ok
        self.checklist.setText("<br>".join(lines))
        for key, widget in self._required_widgets.items():
            mark_required(widget, not by_field.get(key, True))

    def set_scale(self, value: int) -> None:
        index = self.scale.findData(value)
        if index >= 0:
            self.scale.setCurrentIndex(index)
        else:
            self.scale.setEditText(settings.scale_text(value))

    def scale_value(self):
        """Referensskalan som den är angiven, eller None om texten inte är en skala."""
        parsed = settings.parse_scale(self.scale.currentText())
        return None if parsed is None else settings.clamp_scale(parsed)

    def _update_save(self, *_) -> None:
        """Felskrivna värden i beslutet (datum, genomförandetid) eller en felaktig skala hindrar sparande."""
        problems = self.decision.problems()
        scale_ok = self.scale_value() is not None
        self.scale_error.setText("" if scale_ok else "Ange en skala som 1:1000.")
        self.tabs.setTabText(1, "Beslut ✘" if problems else "Beslut")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(not problems and scale_ok)

    # -- spara ------------------------------------------------------------------------
    def accept(self):
        if self.decision.problems():
            self.tabs.setCurrentIndex(1)
            return
        scale = self.scale_value()
        if scale is None:
            self.tabs.setCurrentIndex(0)
            return
        if scale != settings.reference_scale():
            settings.set_reference_scale(scale)
            restyle(self.controller.project, scale)
        self.controller.set_plan_values(self.values())
        self.decision.apply()
        super().accept()
