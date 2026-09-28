"""Kommandoraden: en textruta längst ned i kartvyn, som i CAD-program. Skriv ett kommandonamn (eller en kortform,
t.ex. "m" för Markera) och tryck Enter för att aktivera samma verktyg som knappen i verktygsfältet gör. Rutan visar
också vilket verktyg som är aktivt just nu.

Varje kommando pekar på en riktig ``QAction`` från verktygsfältet (se ``PlanToolBar._register_commands``): rutan
återanvänder därmed samma ``isEnabled``/``isChecked``/``toolTip`` som redan styr knapparna, i stället för att hålla
reda på tillgänglighet på egen hand."""
from __future__ import annotations

from typing import Callable, NamedTuple, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QKeyEvent
from qgis.PyQt.QtWidgets import QCompleter, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget

ERROR_STYLE = "color: #b3261e;"
IDLE_TEXT = "Inget verktyg aktivt"


class Command(NamedTuple):
    names: tuple[str, ...]  # kommandonamn/alias, gemener, t.ex. ("markera", "m")
    label: str              # visningsnamn i rutan, t.ex. "Markera"
    action: object          # QAction som knappen i verktygsfältet använder


class _CommandInput(QLineEdit):
    """Ett textfält där Escape avbryter (kör "esc"-kommandot, om det finns) i stället för QLineEdits vanliga
    beteende – som i CAD-program, där Escape avbryter/avmarkerar."""

    def __init__(self, on_escape: Callable[[], None], parent=None):
        super().__init__(parent)
        self._on_escape = on_escape

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt-namn
        if event.key() == Qt.Key.Key_Escape:
            self._on_escape()
            return
        super().keyPressEvent(event)


class CommandBar(QWidget):
    """Radens innehåll: en etikett som visar aktivt verktyg (eller ett fel-/kvittensmeddelande) och ett fält att
    skriva kommandon i. Byggs tom och fylls med :meth:`register` efter att verktygsfältets knappar finns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._commands: dict[str, Command] = {}
        self._order: list[Command] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        self.active_label = QLabel(IDLE_TEXT)
        self.active_label.setMinimumWidth(170)
        self.input = _CommandInput(self._run_escape, self)
        self.input.setPlaceholderText("Skriv ett kommando (t.ex. markera, text, egenskap) och tryck Enter …")
        self.input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.active_label)
        layout.addWidget(self.input, 1)
        self.input.returnPressed.connect(self._run_current)

    # -- registrering -------------------------------------------------------------
    def register(self, names: tuple[str, ...], label: str, action) -> None:
        command = Command(tuple(n.lower() for n in names), label, action)
        for name in command.names:
            self._commands[name] = command
        self._order.append(command)
        self.input.setCompleter(QCompleter(sorted(self._commands), self.input))

    # -- köra kommandon -------------------------------------------------------------
    def _run_current(self) -> None:
        self.run(self.input.text().strip())
        self.input.clear()

    def _run_escape(self) -> None:
        self.run("esc")
        self.input.clear()

    def run(self, text: str) -> None:
        """Kör ett kommando med namn/alias ``text`` (skiftlägesokänsligt), som om det skrivits i fältet och Enter
        tryckts. Används av fältet självt, men går lika bra att anropa direkt (t.ex. från tester)."""
        if not text:
            return
        command = self._commands.get(text.lower())
        if command is None:
            self._show(f"Okänt kommando: {text}", error=True)
            return
        action = command.action
        if not action.isEnabled():
            self._show(action.toolTip() or f"{command.label} är inte tillgängligt just nu.", error=True)
            return
        if action.isCheckable():
            if not action.isChecked():
                action.trigger()
            self.refresh()
        else:
            action.trigger()
            self._show(f"{command.label} …")

    # -- visa läget -------------------------------------------------------------------
    def refresh(self, *_) -> None:
        """Uppdaterar etiketten med vilket verktyg som är aktivt just nu. Anropas när ett verktyg byts (även via
        knapparna i verktygsfältet, inte bara kommandoraden)."""
        for command in self._order:
            action = command.action
            if action.isCheckable() and action.isChecked():
                self._show(command.label)
                return
        self._show(IDLE_TEXT)

    def _show(self, text: str, error: bool = False) -> None:
        self.active_label.setText(text)
        self.active_label.setStyleSheet(ERROR_STYLE if error else "")
