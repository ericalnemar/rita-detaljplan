"""Exempellayouten för plankartan i QGIS layoutläge (ärende 2): en av mallarna i ``data/layouts/`` med kartan ställd på
planen, teckenförklaringen och planens uppgifter.

Vilka mallar som finns och vad som står i titelrutan bestäms i ``example_sheet`` (ren Python). Teckenförklaringen är
samma som knappen *Teckenförklaring* i layoutläget skapar (``legend_layout``), så den kan göras om på sin plats när
planen ändrats.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qgis.core import QgsLayoutItemLabel, QgsLayoutItemMap, QgsPrintLayout, QgsProject, QgsReadWriteContext, QgsRectangle
from qgis.PyQt.QtXml import QDomDocument

from . import example_sheet as es
from . import legend_layout as ll


@dataclass
class SheetResult:
    layout: QgsPrintLayout
    warnings: list = field(default_factory=list)


def load_template(project: QgsProject, paper: str, orientation: str) -> QgsPrintLayout:
    """En ny layout ur mallen för ``paper`` och ``orientation`` (inte tillagd i projektet)."""
    path = es.template_path(paper, orientation)
    document = QDomDocument()
    if not path.is_file() or not document.setContent(path.read_text(encoding="utf-8")):
        raise ll.LegendError(f"Mallen {path.name} saknas eller går inte att läsa.")
    layout = QgsPrintLayout(project)
    _, ok = layout.loadFromTemplate(document, QgsReadWriteContext())
    if not ok:
        raise ll.LegendError(f"Mallen {path.name} går inte att läsa.")
    return layout


def item(layout: QgsPrintLayout, item_id: str):
    return layout.itemById(item_id)


def _set_text(layout: QgsPrintLayout, item_id: str, text: str) -> None:
    label = item(layout, item_id)
    if isinstance(label, QgsLayoutItemLabel):
        label.setText(text)


def _fill_title_block(layout: QgsPrintLayout, plan: dict, decision: dict) -> None:
    """Skede, planens namn, kommun och beslutens datum. "Ritad av" och upplysningarna lämnas som i mallen."""
    adopted, lagakraft = es.decision_dates(decision)
    _set_text(layout, es.STAGE_ID, es.stage(plan))
    _set_text(layout, es.PLAN_TYPE_ID, "Detaljplan för")
    _set_text(layout, es.NAME_ID, es.plan_name(plan))
    _set_text(layout, es.KOMMUN_ID, es.kommun_text(plan))
    _set_text(layout, es.ADOPTION_ID, f"Antagandebeslut kommunfullmäktige:\n{adopted}")
    _set_text(layout, es.LAGAKRAFT_ID, f"Laga kraft:\n{lagakraft}")


def create(project: QgsProject, plan: dict, decision: dict, rows: list, catalog, bounds: tuple, scale: float,
           paper: str = "A2", orientation: str = es.LANDSCAPE) -> SheetResult:
    """Skapar exempellayouten i projektet ur mallen för ``paper`` och ``orientation`` och returnerar den. ``bounds`` =
    planområdets utbredning (xmin, ymin, xmax, ymax) och ``scale`` = skalans nämnare (planens referensskala). Kastar
    ``legend_layout.LegendError`` om mallen eller teckenförklaringen inte kan skapas."""
    manager = project.layoutManager()
    layout = load_template(project, paper, orientation)
    layout.setName(es.layout_name(plan, paper, orientation, [existing.name() for existing in manager.printLayouts()]))
    warnings: list[str] = []
    map_item = item(layout, es.MAP_ID)
    if not isinstance(map_item, QgsLayoutItemMap):
        raise ll.LegendError("Mallen saknar kartan.")
    box = es.map_box(paper, orientation)
    map_item.setCrs(project.crs())
    map_item.setExtent(QgsRectangle(*es.map_extent(bounds, box, scale)))
    map_item.setScale(scale)
    if not es.fits(bounds, box, scale):
        warnings.append(f"Planen ryms inte i kartan i skala 1:{int(scale)} på {es.format_label(paper, orientation)}. "
                        "Välj ett större format eller en annan skala i kartans egenskaper.")
    placeholder = item(layout, es.LEGEND_ID)
    if placeholder is not None:
        point, size = placeholder.positionWithUnits(), placeholder.sizeWithUnits()
        legend_rect = (point.x(), point.y(), size.width(), size.height())
        layout.removeLayoutItem(placeholder)
    else:
        legend = es.legend_box(paper, orientation)
        legend_rect = (legend.x, legend.y, legend.width, legend.height)
    warnings += ll.add_legend(layout, rows, catalog, decision, legend_rect).warnings
    _fill_title_block(layout, plan, decision)
    manager.addLayout(layout)
    return SheetResult(layout, warnings)
