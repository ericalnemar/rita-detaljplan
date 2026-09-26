"""Fliken "Motiv till planbestämmelser" i Planens uppgifter: alla använda planbestämmelser i en lista där motivet
(planbestämmelsebeskrivningen) fylls i. Motivet hör till bestämmelsen och gäller alla ytor som har den. Det krävs först
vid laga kraft (då blir tomma motiv gula), men kan fyllas i när som helst."""
from __future__ import annotations

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QVBoxLayout, QWidget

from ..core import catalog as cat

_OK, _MISSING = "#1b7f3b", "#b00020"
_REQUIRED_BG = "#fff3cd"  # gult: motivet krävs (laga kraft) och saknas
KIND_TITLES = {"anvandning_yta": "Användning", "egenskap_yta": "Egenskapsyta", "egenskap_linje": "Egenskapslinje"}
HINT = ("Motivet förklarar varför regleringen finns och hur den stödjer planens syfte (planbestämmelsebeskrivning). "
        "Det gäller alla ytor som har bestämmelsen. Det krävs först vid laga kraft, men du kan fylla i det när som helst.")


class MotiveTab(QWidget):
    """``provisions`` = ``controller.provisions()``. ``values()`` ger de ändrade motiven som {nyckel: text}."""

    changed = pyqtSignal()

    def __init__(self, provisions: list[dict], parent=None):
        super().__init__(parent)
        self.provisions = provisions
        self._original = {p["key"]: p["motiv"] for p in provisions}
        self._texts = {p["key"]: p["motiv"] for p in provisions}
        self._required = False

        hint = QLabel(HINT)
        hint.setWordWrap(True)
        hint.setEnabled(False)
        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold;")
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.where = QLabel()
        self.where.setWordWrap(True)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Motiv för den markerade planbestämmelsen")
        self.editor.setMinimumHeight(90)
        self.empty = QLabel("Inga planbestämmelser har tilldelats än. Tilldela dem med verktyget Planbestämmelser.")
        self.empty.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.summary)
        layout.addWidget(self.empty)
        layout.addWidget(self.list, 2)
        layout.addWidget(self.where)
        layout.addWidget(self.editor, 1)

        for provision in provisions:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, provision["key"])
            self.list.addItem(item)
        self.list.currentItemChanged.connect(self._select)
        self.editor.textChanged.connect(self._edited)
        self.empty.setVisible(not provisions)
        self.list.setVisible(bool(provisions))
        self.where.setVisible(bool(provisions))
        self.editor.setVisible(bool(provisions))
        self._refresh_items()
        if provisions:
            self.list.setCurrentRow(0)
        else:
            self._refresh_summary()

    # -- läge -------------------------------------------------------------------------
    def _provision(self, key) -> dict:
        return next(p for p in self.provisions if p["key"] == key)

    def _current_key(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def set_required(self, required: bool) -> None:
        """Vid laga kraft krävs motivet: tomma motiv markeras då gula och röda."""
        self._required = required
        self._refresh_items()

    def missing(self) -> list[dict]:
        """Bestämmelser utan motiv (utom de vars motiv är fast)."""
        return [p for p in self.provisions if not p["technical"] and not self._texts[p["key"]].strip()]

    def values(self) -> dict:
        """Motiv som ändrats sedan fliken öppnades: {nyckel: text}."""
        return {key: text.strip() for key, text in self._texts.items()
                if text.strip() != (self._original[key] or "").strip()}

    # -- uppdatering ------------------------------------------------------------------
    def _refresh_items(self) -> None:
        for index, provision in enumerate(self.provisions):
            item = self.list.item(index)
            text = self._texts[provision["key"]].strip()
            done = bool(text) or provision["technical"]
            label = f"[{provision['label']}] " if provision["label"] else ""
            item.setText(f"{'✔' if done else '✘'}  {label}{provision['text']}")
            item.setForeground(Qt.GlobalColor.darkGreen if done else (Qt.GlobalColor.red if self._required
                                                                       else Qt.GlobalColor.darkGray))
        self._style_editor()
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        total = len(self.provisions)
        filled = total - len(self.missing())
        self.summary.setText(f"{filled} av {total} har motiv" if total else "")

    def _style_editor(self) -> None:
        key = self._current_key()
        missing = (key is not None and self._required and not self._provision(key)["technical"]
                   and not self._texts[key].strip())
        self.editor.setStyleSheet(f"background-color: {_REQUIRED_BG};" if missing else "")

    def _select(self, *_) -> None:
        key = self._current_key()
        if key is None:
            return
        provision = self._provision(key)
        self.editor.blockSignals(True)
        self.editor.setPlainText(cat.TECHNICAL_FORMULATION if provision["technical"] else self._texts[key])
        self.editor.blockSignals(False)
        self.editor.setEnabled(not provision["technical"])
        kind = KIND_TITLES.get(provision["kind"], "")
        count = provision["areas"]
        self.where.setText(f"{kind}, {count} {'yta' if count == 1 else 'ytor'}: {provision['text']}"
                           + (" (motivet är fast för tekniska anläggningar)" if provision["technical"] else ""))
        self._style_editor()

    def _edited(self) -> None:
        key = self._current_key()
        if key is None or self._provision(key)["technical"]:
            return
        self._texts[key] = self.editor.toPlainText()
        self._refresh_items()
        self.changed.emit()
