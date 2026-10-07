"""Små byggstenar som sidorna delar: etiketter, kort, kartan och notisen längst ner."""
from __future__ import annotations

import html
from typing import Optional

from .qt.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from .qt.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from .qt.QtWidgets import (QBoxLayout, QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from ..pbkarna import geometri as geo

from . import session as ss
from . import theme


def label(text: str = "", name: str = "", wrap: bool = False, rich: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    if wrap:
        widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    return widget


def button(text: str, kind: str = "", tip: str = "") -> QPushButton:
    widget = QPushButton(text)
    if kind:
        widget.setProperty("kind", kind)
    if tip:
        widget.setToolTip(tip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return widget


def box(direction: str, *items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QBoxLayout:
    layout = QVBoxLayout() if direction == "v" else QHBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    for item in items:
        if item is None:
            layout.addStretch(1)
        elif isinstance(item, int):
            layout.addSpacing(item)
        elif isinstance(item, QLayout):
            layout.addLayout(item)
        else:
            layout.addWidget(item)
    return layout


def frame(name: str, layout: QBoxLayout) -> QFrame:
    widget = QFrame()
    widget.setObjectName(name)
    widget.setLayout(layout)
    return widget


def restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Pill(QLabel):
    """Status som en liten etikett med färgad prick."""

    def __init__(self, status: str = "", text: Optional[str] = None):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set(status, text)

    def set(self, status: str, text: Optional[str] = None) -> None:
        text = ss.STATUS_TEXT.get(status, "") if text is None else text
        self.setVisible(bool(text))
        color = theme.status_color(status)
        soft = status in (ss.OSAKER, ss.SAKNAS)
        background = theme.mix(color, .14) if soft else "transparent"
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setText(f'<span style="color:{color}">●</span>&nbsp;{html.escape(text)}')
        self.setStyleSheet(f"QLabel {{ color: {color}; background: {background}; border-radius: 9px; padding: 1px 8px; "
                           "font-size: 9pt; font-weight: 600; }")


def tag_html(tema, grupp=None, undergrupp=None) -> str:
    if not tema:
        return "Ingen tagg"
    parts = [html.escape(p) for p in (tema, grupp, undergrupp) if p]
    sep = f' <span style="color:{theme.C["muted"]}">›</span> '
    return sep.join(parts)


class TagChip(QLabel):
    """Tema › grupp › undergrupp i temats färg."""

    def __init__(self):
        super().__init__()
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)  # radbryts i stället för att göra panelen bredare än fönstret (ingen vågrät rullist)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def set(self, tema, grupp=None, undergrupp=None) -> None:
        color = theme.tema_color(tema)
        self.setText(tag_html(tema, grupp, undergrupp))
        self.setStyleSheet(f"QLabel {{ color: {color}; background: {theme.mix(color, .13)}; border-radius: 6px; "
                           "padding: 3px 9px; font-size: 9pt; font-weight: 600; }")


class _Grip(QLabel):
    """Handtaget under ett stycke: dra för att ändra hur mycket av stycket som syns, dubbelklicka för att visa det hela
    eller korta av det igen."""

    def __init__(self, owner: "ParagraphText"):
        super().__init__()
        self.owner = owner
        self.setObjectName("paragraphGrip")
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("Dra för att se mer eller mindre av stycket. Dubbelklicka för att visa hela stycket.")
        self._start: Optional[tuple] = None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = (event.globalPosition().y(), self.owner.shown_height())
        event.accept()  # ett klick på handtaget ska inte välja avsnittet

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is not None:
            self.owner.set_height(self._start[1] + int(event.globalPosition().y() - self._start[0]))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._start = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.owner.toggle()
        event.accept()


class ParagraphText(QWidget):
    """Ett stycke ur planbeskrivningen. Texten radbryts efter bredden. Ett långt stycke visas först med de första raderna;
    ett handtag under det går att dra i (eller dubbelklicka på) för att se hela stycket."""

    DEFAULT_LINES = 8  # så många rader syns först i ett långt stycke
    MIN_LINES = 3

    def __init__(self, text: str, name: str = "docText"):
        super().__init__()
        self.label = label(text, name, wrap=True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)  # bredden styrs av panelen
        self.grip = _Grip(self)
        self.grip.setVisible(False)
        self.setLayout(box("v", self.label, self.grip, spacing=2))
        self._wanted: Optional[int] = None  # önskad synlig höjd i pixlar; None = standard
        self._clipped = False
        self._busy = False

    # -- mått -----------------------------------------------------------------------------------------
    def _line(self) -> int:
        return max(self.label.fontMetrics().lineSpacing(), 1)

    def full_height(self) -> int:
        """Höjden som hela stycket behöver vid nuvarande bredd, uppmätt med samma teckenmått som texten ritas med."""
        width = max(self.label.width() or self.width(), 80)
        flags = Qt.TextFlag.TextWordWrap.value | Qt.AlignmentFlag.AlignLeft.value
        return self.label.fontMetrics().boundingRect(0, 0, width, 1_000_000, flags, self.label.text()).height() + 2

    def shown_height(self) -> int:
        return self.label.height()

    def is_clipped(self) -> bool:
        return self._clipped

    def set_height(self, pixels: int) -> None:
        """Visar ``pixels`` av stycket (mellan MIN_LINES rader och hela stycket)."""
        self._wanted = pixels
        self._relayout()

    def toggle(self) -> None:
        self.set_height(self._line() * self.DEFAULT_LINES if not self.is_clipped() else self.full_height())

    def _relayout(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            full = self.full_height()
            limit = self._line() * self.DEFAULT_LINES
            long = full > limit + self._line()  # minst en rad över gränsen, annars visas allt
            wanted = limit if self._wanted is None else self._wanted
            show = max(min(wanted, full), self._line() * self.MIN_LINES) if long else full
            self._clipped = long and show < full - 1
            if self._clipped:
                self.label.setFixedHeight(show)
            else:  # hela stycket syns: etiketten bestämmer sin höjd själv efter bredden
                self.label.setMinimumHeight(0)
                self.label.setMaximumHeight(16_777_215)
            self.grip.setVisible(long)
            if long:
                self.grip.setText("▾  dra eller dubbelklicka för att se hela stycket" if self._clipped
                                  else "▴  dubbelklicka för att korta av stycket")
        finally:
            self._busy = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._relayout()


class Card(QFrame):
    """Ett klickbart kort med färgad kant till vänster (temats färg) och markering när det är valt."""
    clicked = Signal()

    def __init__(self, accent: str = "", clickable: bool = True):
        super().__init__()
        self._accent, self._selected, self._clickable = accent, False, clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if clickable else Qt.FocusPolicy.NoFocus)
        self._paint()

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._paint()

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self._paint()

    def _paint(self) -> None:
        c = theme.C
        border = c["accent"] if self._selected else "transparent"
        background = theme.mix(c["accent"], .06, c["page"]) if self._selected else "transparent"
        left = self._accent or "transparent"
        self.setStyleSheet(
            f"Card {{ border: 1.5px solid {border}; border-left: 4px solid {left}; border-radius: 8px; "
            f"background: {background}; }} Card:hover {{ background: {theme.mix(c['fg'], .04, c['page'])}; }}"
            if self._clickable else f"Card {{ border: 0; border-left: 4px solid {left}; background: transparent; }}")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._clickable and event.key() in (Qt.Key.Key_Space,):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class MapView(QWidget):
    """Planens ytor, förenklat. ``highlight`` lyser upp ytorna en bestämmelse gäller."""

    def __init__(self):
        super().__init__()
        self.karta: Optional[geo.Karta] = None
        self.highlighted: set = set()
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(220)

    def set_karta(self, karta: Optional[geo.Karta]) -> None:
        self.karta = karta
        self.highlighted = set()
        self.update()

    def highlight(self, areas) -> None:
        self.highlighted = set(areas or ())
        self.update()

    def has_content(self) -> bool:
        return bool(self.karta and self.karta.bounds())

    def paintEvent(self, event) -> None:  # noqa: N802
        c = theme.C
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["surface2"]))
        painter.drawRoundedRect(QRectF(self.rect()), 8, 8)
        bounds = self.karta.bounds() if self.karta else None
        if not bounds:
            painter.setPen(QColor(c["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Planen har ingen geometri att visa.")
            return
        x0, y0, x1, y1 = bounds
        margin = 12
        width, height = self.width() - 2 * margin, self.height() - 2 * margin
        scale = min(width / max(x1 - x0, 1e-9), height / max(y1 - y0, 1e-9))
        ox = margin + (width - (x1 - x0) * scale) / 2
        oy = margin + (height - (y1 - y0) * scale) / 2

        def point(p):
            return QPointF(ox + (p[0] - x0) * scale, oy + (y1 - p[1]) * scale)

        def path(shape: geo.Shape) -> QPainterPath:
            result = QPainterPath()
            for part in shape.parts:
                if not part:
                    continue
                result.moveTo(point(part[0]))
                for p in part[1:]:
                    result.lineTo(point(p))
                if shape.closed:
                    result.closeSubpath()
            return result

        dim = bool(self.highlighted)
        order = sorted(self.karta.areas.items(), key=lambda kv: (self.karta.layer_of.get(kv[0]) != "anvandning_yta",
                                                                 kv[0] in self.highlighted))
        line = QColor(c["map_line"])
        for ident, shape in order:
            layer = self.karta.layer_of.get(ident)
            text = (self.karta.labels.get(ident) or "").upper()
            lit = ident in self.highlighted
            painter.setOpacity(1.0 if (lit or not dim) else 0.35)
            if layer == "anvandning_yta":
                fill = c["map_street"] if text.startswith("GATA") or text.startswith("TORG") else (
                    c["map_park"] if text.startswith(("PARK", "NATUR")) else c["map_use"])
                brush = QBrush(QColor(fill))
            elif shape.closed:
                brush = QBrush(line, Qt.BrushStyle.BDiagPattern)
            else:
                brush = Qt.BrushStyle.NoBrush
            if lit:
                painter.setBrush(QBrush(QColor(theme.mix(c["accent"], .45, c["surface"]))))
                painter.setPen(QPen(QColor(c["accent"]), 2))
            else:
                painter.setBrush(brush if shape.closed else Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(line, 0.8))
            painter.drawPath(path(shape))
        painter.setOpacity(1.0)
        if self.karta.border:
            pen = QPen(QColor(c["fg"]), 1.2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path(self.karta.border))
        font = QFont(theme.MONO_FONT.split(",")[0].strip('" '))
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.setPen(QColor(c["fg"]))
        for ident, shape in self.karta.areas.items():
            if self.karta.layer_of.get(ident) != "anvandning_yta" or ident not in self.karta.labels:
                continue
            bx = shape.bounds()
            if bx:
                painter.drawText(QRectF(point((bx[0], bx[3])), point((bx[2], bx[1]))),
                                 Qt.AlignmentFlag.AlignCenter, self.karta.labels[ident])


class Toast(QLabel):
    """En kort notis längst ner i fönstret."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setMaximumWidth(560)
        self.hide()
        self._timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_text(self, text: str, ms: int = 3500) -> None:
        self.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)
        self.raise_()
        self.show()
        self._timer.start(ms)
