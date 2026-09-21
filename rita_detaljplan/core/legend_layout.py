"""Detaljplanens teckenförklaring som layoutobjekt (för QGIS layoutläge).

Bara teckenförklaringen skapas: rubriken PLANBESTÄMMELSER, gränslinjer, användning, egenskapsbestämmelser och längst ner
genomförandetiden. Kartan, titelblock och övrig plankartamall gör användaren själv. Innehållet byggs i ``legend``.

Teckenförklaringen ritas som layoutobjekt (färgrutor med samma symboler som kartan, linjer och texter) som grupperas till
ett objekt. Storleken utgår från A1 (841 mm bred sida) och skalas med sidans bredd. Den krymps eller delas i två
kolumner om den inte ryms i den yta som getts.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field, fields, replace
from typing import Optional

from qgis.core import (Qgis, QgsFillSymbol, QgsLayoutItemGroup, QgsLayoutItemLabel, QgsLayoutItemPicture, QgsLayoutItemPolyline,
                       QgsLayoutItemShape, QgsLayoutPoint, QgsLayoutSize, QgsLineSymbol, QgsPointPatternFillSymbolLayer, QgsSimpleLineSymbolLayer,
                       QgsStyle, QgsTextFormat)
from qgis.PyQt.QtCore import QPointF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QFontMetricsF, QPolygonF

from . import legend as lg
from . import symbology

MM = Qgis.LayoutUnit.Millimeters
FONT = "Arial"
TAG_RECT = "detaljplan_ngp/legend_rect"  # ytan (bredd; högsta höjd) som teckenförklaringen fick, så att den kan göras om
TAG = "detaljplan_ngp/legend"  # egenskap på gruppen så att en ny teckenförklaring kan ersätta den förra
DEFAULT_WIDTH = 130.0  # mm vid A1; skalas med sidans bredd


class LegendError(RuntimeError):
    """Teckenförklaringen kunde inte skapas. Meddelandet är avsett för användaren."""


KEY_STYLE = "detaljplan_ngp/legend/"


@dataclass
class LegendStyle:
    """Teckenförklaringens utseende. Storlekar i punkter (pt) och avstånd i mm, för en A1-sida; om ``scale_with_page`` är
    sant skalas allt med sidans bredd (mindre på A3 än på A1). Standardvärdena är det som används om inget ändrats."""
    font: str = "Arial"
    heading_size: float = 30.0  # PLANBESTÄMMELSER
    title_size: float = 15.0  # rubrikerna (ANVÄNDNING AV …)
    group_size: float = 12.0  # underrubrikerna (kategorierna)
    text_size: float = 10.0  # bestämmelsernas texter
    swatch_width: float = 15.0  # färg- och mönsterrutor
    swatch_height: float = 5.6
    line_length: float = 15.0  # linjesymboler (gränser, utfart, stängsel)
    text_gap: float = 2.5  # mellan ruta/linje och text
    entry_gap: float = 1.4  # mellan raderna
    group_gap: float = 0.0  # extra avstånd före en underrubrik
    section_gap: float = 4.5  # före varje rubrik
    column_gap: float = 6.0  # mellan kolumner
    intro: bool = True  # den inledande texten under PLANBESTÄMMELSER
    scale_with_page: bool = True

    @classmethod
    def load(cls) -> "LegendStyle":
        """Det som sparats i QGIS-profilen; standardvärden för det som saknas eller är fel."""
        from qgis.core import QgsSettings
        store, default = QgsSettings(), cls()
        values = {}
        for f in fields(cls):
            base = getattr(default, f.name)
            raw = store.value(KEY_STYLE + f.name, base)
            try:
                if isinstance(base, bool):
                    values[f.name] = raw if isinstance(raw, bool) else str(raw).lower() in ("true", "1")
                elif isinstance(base, float):
                    values[f.name] = float(raw)
                else:
                    values[f.name] = str(raw) or base
            except (TypeError, ValueError):
                values[f.name] = base
        return cls(**values).clamped()

    def save(self) -> None:
        from qgis.core import QgsSettings
        store = QgsSettings()
        for f in fields(self):
            store.setValue(KEY_STYLE + f.name, getattr(self, f.name))

    def clamped(self) -> "LegendStyle":
        """Samma värden, men inom rimliga gränser (ingen negativ storlek eller ruta som inte syns)."""
        limits = {"heading_size": (6, 120), "title_size": (4, 80), "group_size": (4, 60), "text_size": (3, 40),
                  "swatch_width": (3, 80), "swatch_height": (1.5, 40), "line_length": (3, 80), "text_gap": (0, 30),
                  "entry_gap": (0, 20), "group_gap": (0, 30), "section_gap": (0, 40), "column_gap": (0, 60)}
        return replace(self, **{name: min(max(getattr(self, name), lo), hi) for name, (lo, hi) in limits.items()})


@dataclass
class LegendResult:
    group: Optional[QgsLayoutItemGroup]
    columns: int = 1
    scale: float = 1.0  # 1.0 = full storlek; mindre när den krympts för att rymmas
    height: float = 0.0
    warnings: list = field(default_factory=list)
    labels: list = field(default_factory=list)


# -- textmätning ---------------------------------------------------------------------------
class Measure:
    """Mäter text i mm oberoende av skärmens upplösning (mäter ett stort teckensnitt och räknar om)."""

    def __init__(self, family: str = FONT):
        self.family = family

    def _metrics(self, bold: bool, italic: bool) -> QFontMetricsF:
        font = QFont(self.family)
        font.setPixelSize(200)
        font.setBold(bold)
        font.setItalic(italic)
        return QFontMetricsF(font)

    def width(self, text: str, size_pt: float, bold: bool = False, italic: bool = False) -> float:
        em_mm = size_pt * 25.4 / 72.0
        return self._metrics(bold, italic).horizontalAdvance(text) / 200.0 * em_mm

    def line_height(self, size_pt: float) -> float:
        return size_pt * 25.4 / 72.0 * 1.22

    def wrap(self, text: str, size_pt: float, width_mm: float, bold: bool = False, italic: bool = False) -> list[str]:
        lines: list[str] = []
        for paragraph in (text or "").split("\n"):
            current = ""
            for word in paragraph.split(" "):
                trial = f"{current} {word}".strip()
                if current and self.width(trial, size_pt, bold, italic) > width_mm * 0.96:
                    lines.append(current)
                    current = word
                else:
                    current = trial
            lines.append(current)
        return lines


def _font(size_pt: float, bold: bool = False, italic: bool = False, family: str = FONT) -> QFont:
    font = QFont(family)
    font.setPointSizeF(size_pt)
    font.setBold(bold)
    font.setItalic(italic)
    return font


# -- teckenförklaringens placering (mäts först, ritas sedan) -------------------------------------
@dataclass
class Placed:
    kind: str  # heading | title | group | text | entry
    x: float
    y: float
    w: float
    h: float
    text: str = ""
    entry: Optional[lg.Entry] = None
    lines: int = 1
    factor: float = 1.0  # < 1 när texten krympts för att det längsta ordet ska rymmas i kolumnen


@dataclass
class LegendPlan:
    items: list
    height: float
    columns: int
    scale: float
    style: "LegendStyle" = None  # type: ignore[assignment]


class LegendLayout:
    """Beräknar var varje rad i teckenförklaringen hamnar för en given kolumnbredd och skala."""

    def __init__(self, sections: list, style: "LegendStyle", measure: Measure):
        self.sections = sections
        self.style = style
        self.intro = style.intro
        self.m = measure

    def build(self, width: float, k: float, columns: int = 1, max_height: float = float("inf")) -> LegendPlan:
        m, st = self.m, self.style
        HEADING, TITLE, GROUP, BODY = st.heading_size, st.title_size, st.group_size, st.text_size
        column_w = (width - (columns - 1) * st.column_gap * k) / columns
        swatch_w, swatch_h = st.swatch_width * k, st.swatch_height * k
        code_w = max([m.width(e.code, BODY * k) for s in self.sections for e in s.entries
                      if e.code and e.swatch == lg.NONE] or [0.0])
        marker_lines = any(e.swatch == lg.LINE and e.symbol in symbology.LINE_SYMBOLS for s in self.sections
                           for e in s.entries)
        line_w = st.line_length * (1.6 if marker_lines else 1.0) * k  # linjer med markörer behöver längre bit för att synas
        text_x = max(swatch_w, line_w, code_w) + st.text_gap * k
        items: list[Placed] = []
        cursor = [0.0, 0]  # y, kolumn

        def line_h(size):
            return m.line_height(size * k)

        def shrink(text, size, bold=True, italic=False):
            """Faktor (högst 1) som gör att det längsta ordet i en rubrik ryms i kolumnen: ett ord kan inte brytas."""
            widest = max((m.width(word, size * k, bold, italic) for word in text.split()), default=0.0)
            return min(1.0, column_w * 0.97 / widest) if widest > 0 else 1.0

        def add(kind, height, text="", entry=None, x=0.0, w=None, lines=1, factor=1.0):
            items.append(Placed(kind, cursor[1] * (column_w + st.column_gap * k) + x, cursor[0], (w if w is not None else column_w) - x,
                                height, text, entry, lines, factor))
            cursor[0] += height

        def paragraph(text, size, kind="text", bold=False, italic=False, gap=1.0):
            lines = m.wrap(text, size * k, column_w, bold, italic)
            add(kind, len(lines) * line_h(size) + gap * k, text, lines=len(lines))  # etiketten bryter raderna själv

        fh = shrink("PLANBESTÄMMELSER", HEADING)
        add("heading", line_h(HEADING * fh) + 2 * k, "PLANBESTÄMMELSER", factor=fh)
        if self.intro:
            paragraph(lg.INTRO, BODY)
        for section in self.sections:
            start_y, start_index = cursor[0], len(items)
            cursor[0] += st.section_gap * k
            ft = shrink(section.title, TITLE)
            title_lines = m.wrap(section.title, TITLE * k * ft, column_w, bold=True)
            add("title", len(title_lines) * line_h(TITLE * ft) + 1.2 * k, section.title, lines=len(title_lines), factor=ft)
            if section.note:
                paragraph(section.note, BODY)
            for group in section.groups:
                if group.heading:
                    fg = shrink(group.heading, GROUP, italic=True)
                    head_lines = m.wrap(group.heading, GROUP * k * fg, column_w, bold=True, italic=True)
                    cursor[0] += st.group_gap * k
                    add("group", len(head_lines) * line_h(GROUP * fg) + 0.8 * k, group.heading, lines=len(head_lines),
                        factor=fg)
                for entry in group.entries:
                    plain = entry.swatch == lg.NONE and not entry.code  # bara text: börjar längst till vänster
                    wrap_w = column_w - (0.0 if plain else text_x)
                    lines = m.wrap(entry.text, BODY * k, wrap_w)
                    height = max(swatch_h if entry.swatch != lg.NONE else 0.0, len(lines) * line_h(BODY)) + st.entry_gap * k
                    add("entry", height, entry.text, entry, lines=len(lines))
            if cursor[0] > max_height and columns > 1 and cursor[1] < columns - 1 and start_index > 1:
                # sektionen ryms inte i kolumnen: flytta den till nästa kolumn
                shift = start_y
                cursor[1] += 1
                cursor[0] -= shift
                for placed in items[start_index:]:
                    placed.x += column_w + st.column_gap * k
                    placed.y -= shift
        height = max(p.y + p.h for p in items) if items else 0.0
        plan = LegendPlan(items, height, columns, k, st)
        plan.text_x = text_x  # type: ignore[attr-defined]
        plan.swatch = (swatch_w, swatch_h)  # type: ignore[attr-defined]
        plan.line_w = line_w  # type: ignore[attr-defined]
        plan.column_w = column_w  # type: ignore[attr-defined]
        return plan

    def fit(self, width: float, max_height: float, base_k: float) -> LegendPlan:
        """Största skalan (högst ``base_k``) där teckenförklaringen ryms i en kolumn; annars två kolumner."""
        k = base_k
        while k >= 0.55 * base_k:
            plan = self.build(width, k)
            if plan.height <= max_height:
                return plan
            k *= 0.94
        k = base_k
        while k >= 0.55 * base_k:
            plan = self.build(width, k, columns=2, max_height=max_height)
            if plan.height <= max_height:
                return plan
            k *= 0.94
        return self.build(width, 0.55 * base_k, columns=2, max_height=max_height)


# -- bygga layouten -----------------------------------------------------------------------------------
def _label(layout, text, x, y, w, h, size, bold=False, italic=False, align=Qt.AlignmentFlag.AlignLeft,
           valign=Qt.AlignmentFlag.AlignTop, family: str = FONT) -> QgsLayoutItemLabel:
    label = QgsLayoutItemLabel(layout)
    label.setText(text)
    text_format = QgsTextFormat()
    text_format.setFont(_font(size, bold, italic, family))
    text_format.setSize(size)
    text_format.setSizeUnit(Qgis.RenderUnit.Points)
    label.setTextFormat(text_format)
    label.setHAlign(align)
    label.setVAlign(valign)
    label.setMargin(0.0)
    label.attemptMove(QgsLayoutPoint(x, y, MM))
    label.attemptResize(QgsLayoutSize(max(w, 1.0), max(h, 1.0), MM))
    layout.addLayoutItem(label)
    return label


def _rect(layout, x, y, w, h, symbol) -> QgsLayoutItemShape:
    shape = QgsLayoutItemShape(layout)
    shape.setShapeType(QgsLayoutItemShape.Shape.Rectangle)
    shape.setSymbol(symbol)
    shape.attemptMove(QgsLayoutPoint(x, y, MM))
    shape.attemptResize(QgsLayoutSize(w, h, MM))
    layout.addLayoutItem(shape)
    return shape


def _line(layout, x0, y0, x1, y1, symbol) -> QgsLayoutItemPolyline:
    line = QgsLayoutItemPolyline(QPolygonF([QPointF(x0, y0), QPointF(x1, y1)]), layout)
    line.setSymbol(symbol)
    layout.addLayoutItem(line)
    return line


def _outline_symbol(width_mm: float = 0.25) -> QgsFillSymbol:
    """Ruta med svart ram (utan fyllning): grunden för färgrutor och mönsterrutor."""
    symbol = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "0,0,0,255",
                                         "outline_width": str(width_mm), "outline_width_unit": "MM"})
    return symbol


PT = 25.4 / 72.0  # mm per punkt
MIN_DOT = 0.5  # mm: en prick ska synas även på skärmen


def _to_mm(value: float, unit) -> float:
    return value * PT if unit == Qgis.RenderUnit.Points else value


def marker_grid(width: float, height: float, dx: float, dy: float, shift: float, margin: float) -> list:
    """Markörernas mittpunkter (mm) i en ruta: så många rader och kolumner som ryms med ``margin`` till kanten,
    centrerade. Varannan rad är förskjuten ``shift`` i sidled, som i kartans mönster."""
    rows = max(1, int((height - 2 * margin) / dy + 1e-6) + 1)
    usable = width - 2 * margin - (shift if rows > 1 else 0.0)
    cols = max(1, int(usable / dx + 1e-6) + 1)
    x0 = (width - ((cols - 1) * dx + (shift if rows > 1 else 0.0))) / 2.0
    y0 = (height - (rows - 1) * dy) / 2.0
    return [(x0 + c * dx + (shift if r % 2 else 0.0), y0 + r * dy) for r in range(rows) for c in range(cols)]


def pattern_svg(layer, width: float, height: float) -> Optional[str]:
    """Prick-, ring- och plusmarkens mönster som en SVG i mm (viewBox = rutans storlek), eller None om mönstret inte
    kan tolkas. Markörerna ritas uttryckligen i stället för med QGIS mönsterfyllning, som beroende på visning och
    utskrift klipper eller tappar markörerna i så små rutor."""
    inner = layer.subSymbol()
    marker = inner.symbolLayer(0) if inner is not None and inner.symbolLayerCount() else None
    if marker is None or not hasattr(marker, "shape"):
        return None
    dx, dy = _to_mm(layer.distanceX(), layer.distanceXUnit()), _to_mm(layer.distanceY(), layer.distanceYUnit())
    if dx <= 0 or dy <= 0:
        return None
    shift = _to_mm(layer.displacementX(), layer.displacementXUnit())
    size = _to_mm(marker.size(), marker.sizeUnit())
    stroke = max(0.12, _to_mm(marker.strokeWidth(), marker.strokeWidthUnit()))  # 0 = hårfin linje: gör den synlig
    colour = marker.strokeColor().name() if marker.strokeColor().alpha() else marker.color().name()
    points = marker_grid(width, height, dx, dy, shift, margin=max(size, MIN_DOT) / 2.0 + 0.4)
    parts = []
    for x, y in points:
        if marker.shape() == Qgis.MarkerShape.Cross:
            half = size / 2.0
            parts.append(f'<path d="M{x - half:.3f} {y:.3f}H{x + half:.3f}M{x:.3f} {y - half:.3f}V{y + half:.3f}" '
                         f'stroke="{colour}" stroke-width="{stroke:.3f}" fill="none"/>')
        elif marker.color().alpha() and marker.strokeStyle() == Qt.PenStyle.NoPen:  # prick: ifylld cirkel
            parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{max(size, MIN_DOT) / 2.0:.3f}" fill="{marker.color().name()}"/>')
        elif marker.color().alpha():
            parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{size / 2.0:.3f}" fill="{marker.color().name()}" '
                         f'stroke="{colour}" stroke-width="{stroke:.3f}"/>')
        else:  # ring
            parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{size / 2.0:.3f}" fill="none" stroke="{colour}" '
                         f'stroke-width="{stroke:.3f}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.3f}mm" height="{height:.3f}mm" '
            f'viewBox="0 0 {width:.3f} {height:.3f}">' + "".join(parts) + "</svg>")


def entry_pattern_svg(entry: lg.Entry, style: QgsStyle, width: float, height: float) -> Optional[str]:
    """SVG för en mönsterrad ur stilbiblioteket (symbolen måste leva så länge dess skikt används)."""
    pattern = style.symbol(symbology.SYMBOL_ALIAS.get(entry.symbol, entry.symbol))
    if pattern is None:
        return None
    symbol = symbology._robust_pattern(pattern.clone())
    layer = next((l for l in symbol.symbolLayers() if isinstance(l, QgsPointPatternFillSymbolLayer)), None)
    return pattern_svg(layer, width, height) if layer is not None else None


def _picture(layout, svg: str, x: float, y: float, w: float, h: float) -> QgsLayoutItemPicture:
    picture = QgsLayoutItemPicture(layout)
    picture.setResizeMode(QgsLayoutItemPicture.ResizeMode.Stretch)
    picture.setPicturePath("base64:" + base64.b64encode(svg.encode("utf-8")).decode("ascii"),
                           Qgis.PictureFormat.SVG)
    picture.attemptMove(QgsLayoutPoint(x, y, MM))
    picture.attemptResize(QgsLayoutSize(w, h, MM))
    layout.addLayoutItem(picture)
    return picture


def _swatch_symbol(entry: lg.Entry, style: QgsStyle, width: float, height: float,
                   outline: float = 0.25) -> Optional[QgsFillSymbol]:
    if entry.swatch == lg.FILL:
        return QgsFillSymbol.createSimple({"color": "%d,%d,%d,255" % tuple(entry.color or symbology.FALLBACK_FARG),
                                           "outline_color": "0,0,0,255", "outline_width": str(outline),
                                           "outline_width_unit": "MM"})
    if entry.swatch == lg.PATTERN:  # ramen; markörerna läggs som bild ovanpå (se _pattern_svg)
        return _outline_symbol(outline)
    return None


def _line_symbol(name: Optional[str], style: QgsStyle) -> QgsLineSymbol:
    symbol = style.symbol(name) if name else None
    return symbol.clone() if symbol is not None else QgsLineSymbol.createSimple({"color": "0,0,0", "width": "0.4"})


def _draw_legend(layout, plan: LegendPlan, x0: float, y0: float, style: QgsStyle, warnings: list) -> list:
    """Skapar layoutobjekten för teckenförklaringen. Returnerar de textetiketter som skapades (för tester)."""
    k = plan.scale
    created = []
    text_x, (swatch_w, swatch_h), column_w = plan.text_x, plan.swatch, plan.column_w  # type: ignore[attr-defined]
    line_w = plan.line_w  # type: ignore[attr-defined]
    st = plan.style
    body = st.text_size
    sizes = {"heading": (st.heading_size, True, False), "title": (st.title_size, True, False),
             "group": (st.group_size, True, True), "text": (body, False, False)}
    for placed in plan.items:
        x, y = x0 + placed.x, y0 + placed.y
        if placed.kind in sizes:
            size, bold, italic = sizes[placed.kind]
            created.append(_label(layout, placed.text, x, y, placed.w, placed.h, size * k * placed.factor, bold, italic,
                                  family=st.font))
            continue
        entry = placed.entry
        code_x = x  # kolumnens vänsterkant (x = 0 i kolumnen: raderna börjar där)
        if entry.swatch in (lg.FILL, lg.PATTERN):
            _rect(layout, code_x, y, swatch_w, swatch_h, _swatch_symbol(entry, style, swatch_w, swatch_h))
            if entry.swatch == lg.PATTERN:
                svg = entry_pattern_svg(entry, style, swatch_w, swatch_h)
                if svg is not None:
                    _picture(layout, svg, code_x, y, swatch_w, swatch_h)
            if entry.code:
                created.append(_label(layout, entry.code, code_x, y, swatch_w, swatch_h, body * k * 1.15,
                                      align=Qt.AlignmentFlag.AlignHCenter, valign=Qt.AlignmentFlag.AlignVCenter,
                                      family=st.font))
        elif entry.swatch == lg.LINE:
            _line(layout, code_x, y + swatch_h / 2, code_x + line_w, y + swatch_h / 2, _line_symbol(entry.symbol, style))
        elif entry.code:
            created.append(_label(layout, entry.code, code_x, y, text_x, swatch_h, body * k * 1.1, family=st.font))
        plain = entry.swatch == lg.NONE and not entry.code
        created.append(_label(layout, placed.text, code_x + (0.0 if plain else text_x), y,
                              column_w - (0.0 if plain else text_x), placed.h, body * k, family=st.font))
    return created


def page_factor(layout, style: Optional[LegendStyle] = None) -> float:
    """Storleksfaktor för teckenförklaringen: 1.0 på A1 (841 mm bred sida), mindre på mindre papper. Alltid 1.0 om
    inställningen att skala med sidan är avstängd."""
    if style is not None and not style.scale_with_page:
        return 1.0
    width = layout.pageCollection().page(0).pageSize().width() if layout.pageCollection().pageCount() else 841.0
    return max(0.35, min(1.6, width / 841.0))


def existing_legends(layout) -> list:
    return [i for i in layout.items() if isinstance(i, QgsLayoutItemGroup) and i.customProperty(TAG)]


def add_legend(layout, rows: list, catalog, decision: Optional[dict], rect: Optional[tuple] = None,
               style: Optional[LegendStyle] = None, symbols: Optional[QgsStyle] = None) -> LegendResult:
    """Lägger teckenförklaringen i layouten som en grupp. ``rect`` = (x, y, bredd, högsta höjd) i mm; utan den läggs
    teckenförklaringen längst till höger på första sidan, och en tidigare teckenförklaring ersätts på sin plats."""
    if not layout.pageCollection().pageCount():
        raise LegendError("Layouten saknar sida.")
    symbols = symbols or symbology.load_style()
    style = (style or LegendStyle.load()).clamped()
    k = page_factor(layout, style)
    page = layout.pageCollection().page(0).pageSize()
    old = existing_legends(layout)
    if rect is None:
        margin = max(6.0, 10.0 * page.width() / 841.0)
        if old:
            box = old[0].sceneBoundingRect()
            given = str(old[0].customProperty(TAG_RECT) or "").split(",")
            try:
                width, height = float(given[0]), float(given[1])
            except (ValueError, IndexError):
                width, height = box.width(), page.height() - margin - box.top()
            rect = (box.left(), box.top(), width, height)
        else:
            width = min(DEFAULT_WIDTH * k, page.width() - 2 * margin)
            rect = (page.width() - margin - width, margin, width, page.height() - 2 * margin)
    x, y, width, max_height = rect
    if width < 20.0 or max_height < 20.0:
        raise LegendError("Ytan för teckenförklaringen är för liten.")
    sections = lg.build(rows, catalog, decision)
    plan = LegendLayout(sections, style, Measure(style.font)).fit(width, max_height, k)
    warnings = []
    if not lg.implementation_section(decision or {}):
        warnings.append("Genomförandetid saknas i planens uppgifter, så den står inte i teckenförklaringen.")
    if plan.height > max_height + 0.5 or plan.scale < 0.8 * k:
        warnings.append("Teckenförklaringen är lång och har gjorts mindre eller delats i två kolumner för att rymmas. "
                        "Ge den en större yta om texten blir för liten." if plan.height <= max_height + 0.5 else
                        "Teckenförklaringen ryms inte i ytan ens i minsta storlek. Ge den en högre eller bredare yta.")
    layout.undoStack().beginMacro("Skapa teckenförklaring")
    try:
        for previous in old:
            layout.removeLayoutItem(previous)
        before = set(layout.items())
        labels = _draw_legend(layout, plan, x, y, symbols, warnings)
        created = [i for i in layout.items() if i not in before and not isinstance(i, QgsLayoutItemGroup)]
        group = layout.groupItems(created) if created else None
        if group is not None:
            group.setCustomProperty(TAG, True)
            group.setCustomProperty(TAG_RECT, f"{width},{max_height}")
            group.setId("Teckenförklaring")
    finally:
        layout.undoStack().endMacro()
    return LegendResult(group, plan.columns, plan.scale / k, plan.height, warnings, labels)
