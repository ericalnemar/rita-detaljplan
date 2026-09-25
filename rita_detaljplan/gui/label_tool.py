"""Textverktyget: markera bestämmelsernas texter (klick eller rektangel) och flytta dem till lämpligt ställe.

  * Klick på en text markerar den (skift-klick lägger till). Dra en markerad text för att flytta den (och alla andra
    markerade texter lika långt).
  * Tryck ned musknappen på tomt ställe och dra för att markera texter med en rektangel.
  * En markerad egenskapstext har fyra handtag (hörnen): dra i ett hörn för att omforma textrutan. Texten radbryts då
    efter rutans bredd; bokstävernas storlek ändras aldrig här (den ställs in i skalningsinställningarna).
  * Delete återställer markerade texter till automatisk placering och form. Esc avmarkerar.
Texten kan flyttas utanför sin yta: en tunn, svart ledlinje ritas då automatiskt till ytan.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from qgis.core import Qgis, QgsGeometry, QgsPointXY, QgsRectangle
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from ..controller import LABEL_TABLES, PlanController
from ..core.project import table_of

DRAG_PIXELS = 4  # kortare drag än så räknas som ett klick
HANDLE_PIXELS = 8  # hur nära ett hörn man ska klicka för att ta tag i det


@dataclass(frozen=True)
class LabelRef:
    """En text på kartan: vilken yta den hör till och var den ritades (kartkoordinater)."""
    table: str
    fid: int
    rect: QgsRectangle

    @property
    def key(self) -> tuple[str, int]:
        return self.table, self.fid


class LabelTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, controller: PlanController, report):
        super().__init__(canvas)
        self.controller = controller
        self.report = report
        self.selected: list[LabelRef] = []
        self._mode: Optional[str] = None  # "move" | "rect" | "resize"
        self._resizing: Optional[tuple[LabelRef, QgsPointXY]] = None  # (text, det motsatta hörnet som ligger fast)
        self._start: Optional[QgsPointXY] = None
        self._shift = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._marks = self._band(QColor(30, 110, 200, 40), QColor(30, 110, 200))
        self._ghosts = self._band(QColor(30, 110, 200, 20), QColor(30, 110, 200, 160))
        self._frame = self._band(QColor(30, 110, 200, 20), QColor(30, 110, 200))
        self._handles = QgsRubberBand(self.canvas(), Qgis.GeometryType.Point)
        self._handles.setColor(QColor(30, 110, 200))
        self._handles.setIcon(QgsRubberBand.IconType.ICON_FULL_BOX)
        self._handles.setIconSize(7)

    def _band(self, fill: QColor, stroke: QColor) -> QgsRubberBand:
        band = QgsRubberBand(self.canvas(), Qgis.GeometryType.Polygon)
        band.setColor(fill)
        band.setStrokeColor(stroke)
        band.setWidth(1)
        return band

    # -- vilka texter finns (avläses ur kartans senaste ritning) -----------------------
    def _all(self, positions) -> list[LabelRef]:
        found = []
        for position in positions:
            layer = self.controller.project.mapLayer(position.layerID)
            table = table_of(layer) if layer is not None else None
            if table in LABEL_TABLES and not position.isUnplaced:
                found.append(LabelRef(table, position.featureId, QgsRectangle(position.labelRect)))
        return found

    def labels_at(self, point: QgsPointXY) -> list[LabelRef]:
        results = self.canvas().labelingResults(False)
        return self._all(results.labelsAtPosition(point)) if results is not None else []

    def labels_in(self, rect: QgsRectangle) -> list[LabelRef]:
        results = self.canvas().labelingResults(False)
        return self._all(results.labelsWithinRect(rect)) if results is not None else []

    # -- musen ------------------------------------------------------------------------
    def canvasPressEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.press(event.mapPoint(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))

    def canvasMoveEvent(self, event):  # noqa: N802
        if self._mode:
            self.drag_to(event.mapPoint())

    def canvasReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._mode:
            self.release(event.mapPoint())

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.reset_selected()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.clear()
            event.accept()

    def deactivate(self):
        self.clear()
        super().deactivate()

    # -- själva åtgärderna (kan anropas direkt i tester) -----------------------------------
    def handle_at(self, point: QgsPointXY) -> Optional[tuple[LabelRef, QgsPointXY]]:
        """Handtaget (hörnet) på en markerad, omformbar text som ligger under punkten: (texten, motsatt hörn)."""
        tolerance = self.canvas().mapUnitsPerPixel() * HANDLE_PIXELS
        for label in self.selected:
            if label.table not in self.controller.RESIZABLE_LABELS:
                continue
            for corner, opposite in _corners(label.rect):
                if corner.distance(point) <= tolerance:
                    return label, opposite
        return None

    def press(self, point: QgsPointXY, shift: bool = False) -> None:
        self._start, self._shift = point, shift
        handle = self.handle_at(point)
        if handle is not None:
            self._mode, self._resizing = "resize", handle
            return
        hit = next(iter(self.labels_at(point)), None)
        if hit is None:
            self._mode = "rect"
            return
        self._mode = "move"
        if hit.key not in {label.key for label in self.selected}:
            self.selected = [*self.selected, hit] if shift else [hit]
        elif shift:  # skift på en redan markerad text avmarkerar den
            self.selected = [label for label in self.selected if label.key != hit.key]
            self._mode = None
        self._show_selection()

    def drag_to(self, point: QgsPointXY) -> None:
        if self._start is None:
            return
        if self._mode == "move":
            dx, dy = point.x() - self._start.x(), point.y() - self._start.y()
            self._ghosts.reset(Qgis.GeometryType.Polygon)
            for label in self.selected:
                self._ghosts.addGeometry(QgsGeometry.fromRect(_shifted(label.rect, dx, dy)), None)
        elif self._mode == "rect":
            self._frame.setToGeometry(QgsGeometry.fromRect(QgsRectangle(self._start, point)), None)
        elif self._mode == "resize" and self._resizing is not None:
            self._ghosts.setToGeometry(QgsGeometry.fromRect(QgsRectangle(self._resizing[1], point)), None)

    def release(self, point: QgsPointXY) -> None:
        start, mode, resizing = self._start, self._mode, self._resizing
        self._mode, self._start, self._resizing = None, None, None
        self._ghosts.reset(Qgis.GeometryType.Polygon)
        self._frame.reset(Qgis.GeometryType.Polygon)
        if start is None or mode is None:
            return
        dragged = start.distance(point) > self.canvas().mapUnitsPerPixel() * DRAG_PIXELS
        if mode == "resize":
            if dragged and resizing is not None:
                self.resize_label(resizing[0], QgsRectangle(resizing[1], point))
            return
        if mode == "move":
            if dragged:
                self.move_selected(point.x() - start.x(), point.y() - start.y())
            return
        if not dragged:  # klick på tomt ställe
            if not self._shift:
                self.selected = []
            self._show_selection()
            return
        inside = self.labels_in(QgsRectangle(start, point))
        keep = {label.key: label for label in self.selected} if self._shift else {}
        for label in inside:
            keep[label.key] = label
        self.selected = list(keep.values())
        self._show_selection()
        if not self.selected:
            self.report("Ingen text i rektangeln.", False)

    def move_selected(self, dx: float, dy: float) -> int:
        """Flyttar de markerade texterna. Returnerar hur många som flyttades."""
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser (pennan) för att kunna flytta text.", True)
            return 0
        moved = []
        for label in self.selected:
            center = label.rect.center()
            point = self.controller.move_label(label.table, label.fid, QgsPointXY(center.x() + dx, center.y() + dy))
            if point is not None:
                moved.append(LabelRef(label.table, label.fid,
                                      _shifted(label.rect, point.x() - center.x(), point.y() - center.y())))
        self.selected = moved
        self._show_selection()
        return len(moved)

    def resize_label(self, label: LabelRef, rect: QgsRectangle) -> bool:
        """Omformar en texts ruta (bredden styr radbrytningen). Returnerar om det gjordes."""
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser (pennan) för att kunna ändra text.", True)
            return False
        if self.controller.resize_label(label.table, label.fid, rect) is None:
            return False
        self.selected = [LabelRef(label.table, label.fid, QgsRectangle(rect)) if item.key == label.key else item
                         for item in self.selected]
        self._show_selection()
        return True

    def reset_selected(self) -> int:
        """Återställer markerade texter till automatisk placering."""
        if not self.selected:
            return 0
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser (pennan) för att kunna ändra text.", True)
            return 0
        for label in self.selected:
            self.controller.reset_label(label.table, label.fid)
        count = len(self.selected)
        self.clear()
        return count

    def clear(self) -> None:
        self.selected = []
        self._mode, self._start, self._resizing = None, None, None
        for band in (self._marks, self._ghosts, self._frame):
            band.reset(Qgis.GeometryType.Polygon)
        self._handles.reset(Qgis.GeometryType.Point)

    def _show_selection(self) -> None:
        self._marks.reset(Qgis.GeometryType.Polygon)
        self._handles.reset(Qgis.GeometryType.Point)
        for label in self.selected:
            self._marks.addGeometry(QgsGeometry.fromRect(label.rect), None)
            if label.table in self.controller.RESIZABLE_LABELS:
                for corner, _ in _corners(label.rect):
                    self._handles.addPoint(corner)


def _corners(rect: QgsRectangle) -> list[tuple[QgsPointXY, QgsPointXY]]:
    """Rektangelns fyra hörn, var och ett med det motsatta hörnet."""
    x0, y0, x1, y1 = rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()
    return [(QgsPointXY(x0, y0), QgsPointXY(x1, y1)), (QgsPointXY(x1, y0), QgsPointXY(x0, y1)),
            (QgsPointXY(x1, y1), QgsPointXY(x0, y0)), (QgsPointXY(x0, y1), QgsPointXY(x1, y0))]


def _shifted(rect: QgsRectangle, dx: float, dy: float) -> QgsRectangle:
    return QgsRectangle(rect.xMinimum() + dx, rect.yMinimum() + dy, rect.xMaximum() + dx, rect.yMaximum() + dy)
