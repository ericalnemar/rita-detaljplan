"""Exempellayouten för plankartan i QGIS layoutläge (ärende 2): karta, teckenförklaring, norrpil, skalstock och titelruta.

Vad som ska stå var bestäms i ``example_sheet`` (ren Python); den här modulen ritar det. Teckenförklaringen är samma som
knappen *Teckenförklaring* i layoutläget skapar (``legend_layout``), så den kan göras om på sin plats när planen ändrats.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from qgis.core import (
    Qgis,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLineSymbol,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
    QgsTextFormat,
)
from qgis.PyQt.QtCore import Qt

from . import example_sheet as es
from . import legend_layout as ll

MM = Qgis.LayoutUnit.Millimeters
NORTH_ARROW = ":/images/north_arrows/layout_default_north_arrow.svg"  # följer med QGIS


@dataclass
class SheetResult:
    layout: QgsPrintLayout
    warnings: list = field(default_factory=list)


def _page(layout: QgsPrintLayout) -> None:
    layout.initializeDefaults()
    page = layout.pageCollection().page(0)
    page.setPageSize(es.PAPER, QgsLayoutItemPage.Orientation.Landscape)


def _map(layout: QgsPrintLayout, project: QgsProject, box: es.Box, bounds: tuple, scale: float) -> QgsLayoutItemMap:
    item = QgsLayoutItemMap(layout)
    item.attemptMove(QgsLayoutPoint(box.x, box.y, MM))
    item.attemptResize(QgsLayoutSize(box.width, box.height, MM))
    item.setCrs(project.crs())
    item.setExtent(QgsRectangle(*es.map_extent(bounds, box, scale)))
    item.setScale(scale)
    item.setFrameEnabled(True)
    item.setFrameStrokeWidth(QgsLayoutMeasurement(0.35, MM))
    item.setId("Karta")
    layout.addLayoutItem(item)
    return item


def _north_arrow(layout: QgsPrintLayout, map_item: QgsLayoutItemMap, box: es.Box) -> QgsLayoutItemPicture:
    size = min(box.height - 4.0, 22.0)
    picture = QgsLayoutItemPicture(layout)
    picture.setPicturePath(NORTH_ARROW)
    picture.setLinkedMap(map_item)  # vrids med kartan
    picture.attemptMove(QgsLayoutPoint(box.x, box.y + 2.0, MM))
    picture.attemptResize(QgsLayoutSize(size, size, MM))
    picture.setId("Norrpil")
    layout.addLayoutItem(picture)
    return picture


def _scale_bar(layout: QgsPrintLayout, map_item: QgsLayoutItemMap, box: es.Box, scale: float) -> QgsLayoutItemScaleBar:
    bar = QgsLayoutItemScaleBar(layout)
    bar.setLinkedMap(map_item)
    bar.applyDefaultSettings()
    bar.setStyle("Single Box")
    bar.setUnits(Qgis.DistanceUnit.Meters)
    bar.setUnitLabel("m")
    bar.setMapUnitsPerScaleBarUnit(1.0)
    bar.setSegmentSizeMode(Qgis.ScaleBarSegmentSizeMode.Fixed)
    bar.setUnitsPerSegment(es.segment_length(scale))
    bar.setNumberOfSegmentsLeft(0)
    bar.setNumberOfSegments(4)
    bar.setHeight(2.0)
    text_format = QgsTextFormat()
    text_format.setFont(ll._font(8))
    text_format.setSize(8)
    text_format.setSizeUnit(Qgis.RenderUnit.Points)
    bar.setTextFormat(text_format)
    bar.attemptMove(QgsLayoutPoint(box.x + 30.0, box.y + 4.0, MM))
    bar.setId("Skalstock")
    layout.addLayoutItem(bar)
    bar.update()
    return bar


def _title_block(layout: QgsPrintLayout, box: es.Box, plan: dict, decision: dict, scale: float) -> None:
    """Titelrutan: kommun, planens namn och skede, skalan och raderna med planbeteckning, datum m.m."""
    frame = ll._outline_symbol(0.35)
    ll._rect(layout, box.x, box.y, box.width, box.height, frame)
    pad = 4.0
    x, width = box.x + pad, box.width - 2 * pad
    kommun, name, stage = es.heading(plan)
    y = box.y + pad
    ll._label(layout, kommun.upper(), x, y, width, 6.0, 9, bold=True)
    y += 7.0
    ll._label(layout, name, x, y, width, 16.0, 14, bold=True)
    y += 17.0
    ll._label(layout, stage, x, y, width, 6.0, 10)
    ll._label(layout, es.scale_text(scale), x, y, width, 6.0, 10, align=Qt.AlignmentFlag.AlignRight)
    y += 8.0
    ll._line(layout, box.x, y, box.right, y, _thin_line())
    y += 3.0
    for title, value in es.title_rows(plan, decision):
        ll._label(layout, title, x, y, 40.0, 5.5, 8)
        ll._label(layout, value, x + 42.0, y, width - 42.0, 5.5, 8)
        y += 6.5
    ll._label(layout, es.BASE_MAP_NOTE, x, y + 1.0, width, 10.0, 7, italic=True)
    ll._label(layout, es.FOOTER, x, box.bottom - pad - 8.0, width, 8.0, 6.5, italic=True)


def _thin_line() -> QgsLineSymbol:
    return QgsLineSymbol.createSimple({"color": "0,0,0,255", "width": "0.25", "width_unit": "MM"})


def create(project: QgsProject, plan: dict, decision: dict, rows: list, catalog, bounds: tuple,
           scale: float) -> SheetResult:
    """Skapar exempellayouten i projektet och returnerar den. ``bounds`` = planområdets utbredning (xmin, ymin, xmax,
    ymax) och ``scale`` = skalans nämnare (planens referensskala). Kastar ``legend_layout.LegendError`` om
    teckenförklaringen inte kan skapas."""
    manager = project.layoutManager()
    layout = QgsPrintLayout(project)
    _page(layout)
    layout.setName(es.layout_name(plan, [existing.name() for existing in manager.printLayouts()]))
    sheet = es.sheet()
    warnings: list[str] = []
    map_item = _map(layout, project, sheet.map, bounds, scale)
    if not es.fits(bounds, sheet.map, scale):
        warnings.append(f"Planen ryms inte i kartan i skala 1:{int(scale)} på {es.PAPER}. Välj en större sida eller "
                        "en annan skala i layouten.")
    legend = ll.add_legend(layout, rows, catalog, decision,
                           (sheet.legend.x, sheet.legend.y, sheet.legend.width, sheet.legend.height))
    warnings += legend.warnings
    _north_arrow(layout, map_item, sheet.scale_row)
    _scale_bar(layout, map_item, sheet.scale_row, scale)
    _title_block(layout, sheet.title_block, plan, decision, scale)
    manager.addLayout(layout)
    return SheetResult(layout, warnings)
