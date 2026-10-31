"""Bygger exempellayouternas mallar (``rita_detaljplan/data/layouts/*.qpt``) ur A2-mallen i ``tools/layouts/``.

    python-qgis tools/build_layouts.py      (QGIS egen Python, t.ex. "C:/Program Files/QGIS 4.2.2/bin/python-qgis.bat")

Källan är en plankarta på A2 i liggande format (``plankarta-a2-liggande-original.qpt``), oförändrad som den ritades i
QGIS. Skriptet ger objekten id (så att pluginet hittar dem), lägger in en ruta för teckenförklaringen som inte skrivs ut
och skriver åtta mallar: A1–A4, liggande och stående. ISO-formaten har samma proportioner, så A1, A3 och A4 är A2-sidan i
en annan skala (även text, linjer och skalstockar). De stående har kartan överst, teckenförklaringen under den till
vänster med skalstocken under, och grundkartans beteckningar, upplysningarna och titelrutan i en kolumn till höger.
Kör skriptet igen när källan ändrats och checka in mallarna.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qgis.core import (  # noqa: E402
    Qgis,
    QgsApplication,
    QgsFillSymbol,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutItemShape,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsReadWriteContext,
)
from qgis.PyQt.QtXml import QDomDocument  # noqa: E402

from rita_detaljplan.core import example_sheet as es  # noqa: E402

MM = Qgis.LayoutUnit.Millimeters
SOURCE = ROOT / "tools" / "layouts" / "plankarta-a2-liggande-original.qpt"

# Etiketterna i källan, igenkända på hur texten börjar -> id
LABEL_IDS = (
    ("PLANKARTA", "Rubrik plankarta"),
    ("ARBETSHANDLING", es.STAGE_ID),
    ("GRUNDKARTANS BETECKNINGAR", "Grundkartans beteckningar"),
    ("UPPLYSNINGAR", "Upplysningar rubrik"),
    ("Planen är upprättad", "Upplysningar"),
    ("Detaljplan för", es.PLAN_TYPE_ID),
    ("Testbädden", es.NAME_ID),
    ("i Nya staden", es.KOMMUN_ID),
    ("Antagandebeslut", es.ADOPTION_ID),
    ("Ritad av", "Ritad av"),
    ("Laga kraft", es.LAGAKRAFT_ID),
    ("Upprättad", "Upprättad"),
    ("(A2)", es.PAPER_ID),
    ("[% format_date", "Datum"),
)
SCALE_BAR_IDS = {"Numeric": "Skala", "Line Ticks Up": "Skalstock"}
# Grundkartan ritas i planens koordinatsystem: texten följer projektet i stället för att vara fast
CRS_TEXT = ("SWEREF99 13 30", "[% @project_crs_description %]")

# Den stående A2-sidan (420 x 594 mm): hur långt (dx, dy i mm) varje objekt flyttas från den liggande. Kartan och
# teckenförklaringen får sina ytor ur example_sheet (A2_MAP, A2_LEGEND).
_RIGHT, _BOTTOM = 412.8, 174.0  # högerkanten på den stående sidan; den är 174 mm högre än den liggande
_COLUMN = _RIGHT - 155.1  # kolumnen till höger: grundkartan, upplysningarna och titelrutan, lika bred som titelrutan
_MAP_CORNER = (es.A2_MAP[es.PORTRAIT].right - es.A2_MAP[es.LANDSCAPE].right,
               es.A2_MAP[es.PORTRAIT].bottom - es.A2_MAP[es.LANDSCAPE].bottom)
PORTRAIT_MOVES = {
    "Norrpil": _MAP_CORNER,  # ligger kvar i kartans nedre högra hörn
    "Rubrik plankarta": _MAP_CORNER,
    "Grundkartans beteckningar": (_COLUMN - 16.17, es.A2_LEGEND[es.PORTRAIT].y - 343.892),
    "Upplysningar rubrik": (_COLUMN - 237.018, 463.3 - 344.581),
    "Upplysningar": (_COLUMN - 237.018, 463.3 - 344.581),
    "Skala": (175.0 - 373.709, _BOTTOM),  # skalstocken längst ned under teckenförklaringen
    "Skalstock": (175.0 - 373.709, _BOTTOM),
    es.PAPER_ID: (175.0 - 373.709, _BOTTOM),
}
TITLE_BLOCK_MOVE = (_RIGHT - 586.818, _BOTTOM)  # titelrutan längst ned till höger, som på den liggande sidan
PORTRAIT_MAX_BAR = 120.0  # mm: den stående skalstocken växer åt vänster och får inte gå utanför sidan


def load(path: Path) -> QgsPrintLayout:
    layout = QgsPrintLayout(QgsProject.instance())
    document = QDomDocument()
    document.setContent(path.read_text(encoding="utf-8"))
    _, ok = layout.loadFromTemplate(document, QgsReadWriteContext())
    if not ok:
        raise RuntimeError(f"Kunde inte läsa {path}")
    return layout


def items(layout: QgsPrintLayout) -> list:
    return [item for item in layout.items() if hasattr(item, "uuid") and item.type() != 65638]  # 65638 = sidan


def name_items(layout: QgsPrintLayout) -> None:
    """Ger källans objekt id och gör upplysningarnas koordinatsystem dynamiskt."""
    for item in items(layout):
        if isinstance(item, QgsLayoutItemLabel):
            text = item.text()
            for start, item_id in LABEL_IDS:
                if text.startswith(start):
                    item.setId(item_id)
                    break
            else:
                raise RuntimeError(f"Okänd etikett i källan: {text!r}")
            if CRS_TEXT[0] in text:
                item.setText(text.replace(*CRS_TEXT))
        elif isinstance(item, QgsLayoutItemScaleBar):
            item.setId(SCALE_BAR_IDS[item.style()])
        elif isinstance(item, QgsLayoutItemMap):
            item.setId(es.MAP_ID)
        elif isinstance(item, QgsLayoutItemPicture):
            item.setId("Norrpil")
    missing = {item_id for _, item_id in LABEL_IDS} - {item.id() for item in items(layout)}
    if missing:
        raise RuntimeError(f"Saknas i källan: {', '.join(sorted(missing))}")


def add_legend_box(layout: QgsPrintLayout, box: es.Box) -> None:
    """En streckad ruta där teckenförklaringen ska ligga. Den skrivs inte ut; pluginet ersätter den med
    teckenförklaringen, och den som använder mallen själv ser var den är tänkt."""
    shape = QgsLayoutItemShape(layout)
    shape.setShapeType(QgsLayoutItemShape.Shape.Rectangle)
    shape.setSymbol(QgsFillSymbol.createSimple({"style": "no", "outline_color": "150,150,150,255",
                                                "outline_style": "dash", "outline_width": "0.3",
                                                "outline_width_unit": "MM"}))
    shape.attemptMove(QgsLayoutPoint(box.x, box.y, MM))
    shape.attemptResize(QgsLayoutSize(box.width, box.height, MM))
    shape.setExcludeFromExports(True)
    shape.setId(es.LEGEND_ID)
    layout.addLayoutItem(shape)




def move(item, dx: float, dy: float) -> None:
    point = item.positionWithUnits()
    locked = item.isLocked()
    item.setLocked(False)
    item.attemptMove(QgsLayoutPoint(point.x() + dx, point.y() + dy, MM))
    item.setLocked(locked)


def to_portrait(layout: QgsPrintLayout) -> None:
    """Flyttar A2-sidans objekt till den stående sidan (fortfarande A2)."""
    for item in items(layout):
        item_id = item.id()
        if item_id == es.MAP_ID:
            box = es.A2_MAP[es.PORTRAIT]
            item.attemptResize(QgsLayoutSize(box.width, box.height, MM))
        elif item_id == es.LEGEND_ID:
            box = es.A2_LEGEND[es.PORTRAIT]
            item.attemptMove(QgsLayoutPoint(box.x, box.y, MM))
            item.attemptResize(QgsLayoutSize(box.width, box.height, MM))
        elif item_id in PORTRAIT_MOVES:
            move(item, *PORTRAIT_MOVES[item_id])
        else:
            move(item, *TITLE_BLOCK_MOVE)
        if isinstance(item, QgsLayoutItemScaleBar):
            item.setMaximumBarWidth(min(item.maximumBarWidth(), PORTRAIT_MAX_BAR))


def scale(layout: QgsPrintLayout, factor: float) -> None:
    """Gör hela sidan ``factor`` gånger större: lägen, storlekar, text, linjer och skalstockar."""
    for item in items(layout):
        point, size = item.positionWithUnits(), item.sizeWithUnits()
        locked = item.isLocked()
        item.setLocked(False)
        item.attemptMove(QgsLayoutPoint(point.x() * factor, point.y() * factor, MM))
        item.attemptResize(QgsLayoutSize(size.width() * factor, size.height() * factor, MM))
        item.setLocked(locked)
        if isinstance(item, QgsLayoutItemLabel):
            text_format = item.textFormat()
            text_format.setSize(text_format.size() * factor)
            item.setTextFormat(text_format)
            item.setMarginX(item.marginX() * factor)
            item.setMarginY(item.marginY() * factor)
        elif isinstance(item, QgsLayoutItemScaleBar):
            text_format = item.textFormat()
            text_format.setSize(text_format.size() * factor)
            item.setTextFormat(text_format)
            item.setHeight(item.height() * factor)
            item.setLabelBarSpace(item.labelBarSpace() * factor)
            item.setBoxContentSpace(item.boxContentSpace() * factor)
            item.setMinimumBarWidth(item.minimumBarWidth() * factor)
            item.setMaximumBarWidth(item.maximumBarWidth() * factor)
            for get, put in ((item.lineSymbol, item.setLineSymbol),
                             (item.divisionLineSymbol, item.setDivisionLineSymbol),
                             (item.subdivisionLineSymbol, item.setSubdivisionLineSymbol)):
                symbol = get().clone()
                symbol.setWidth(symbol.width() * factor)
                put(symbol)
            item.setSubdivisionsHeight(item.subdivisionsHeight() * factor)
            item.update()
        elif isinstance(item, QgsLayoutItemShape):
            symbol = item.symbol().clone()
            for layer in symbol.symbolLayers():
                layer.setStrokeWidth(layer.strokeWidth() * factor)
            item.setSymbol(symbol)
        elif isinstance(item, QgsLayoutItemMap):
            for grid in item.grids().asList():  # kryssen och koordinaterna i kartans kant
                text_format = grid.annotationTextFormat()
                text_format.setSize(text_format.size() * factor)
                grid.setAnnotationTextFormat(text_format)
                grid.setAnnotationFrameDistance(grid.annotationFrameDistance() * factor)
                grid.setCrossLength(grid.crossLength() * factor)
                grid.setFrameWidth(grid.frameWidth() * factor)
                grid.setFramePenSize(grid.framePenSize() * factor)
                line = grid.lineSymbol().clone()
                line.setWidth(line.width() * factor)
                grid.setLineSymbol(line)


def build(paper: str, orientation: str, target: Path) -> None:
    layout = load(SOURCE)
    name_items(layout)
    add_legend_box(layout, es.A2_LEGEND[es.LANDSCAPE])
    if orientation == es.PORTRAIT:
        to_portrait(layout)
    scale(layout, es.factor(paper))
    width, height = es.page_size(paper, orientation)
    layout.pageCollection().page(0).setPageSize(QgsLayoutSize(width, height, MM))
    for item in items(layout):
        if item.id() == es.PAPER_ID:
            item.setText(f"({paper})")
    layout.setName(f"{es.TITLE} {es.format_label(paper, orientation)}")
    if not layout.saveAsTemplate(str(target), QgsReadWriteContext()):
        raise RuntimeError(f"Kunde inte spara {target}")


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    try:
        es.LAYOUT_DIR.mkdir(parents=True, exist_ok=True)
        for paper, orientation in es.formats():
            target = es.template_path(paper, orientation)
            build(paper, orientation, target)
            print(f"Skapade {target.relative_to(ROOT)}")
    finally:
        app.exitQgis()
    return 0


if __name__ == "__main__":
    sys.exit(main())
