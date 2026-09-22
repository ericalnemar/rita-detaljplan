"""Kartverktyget "Markera": klicka eller dra en rektangel för att markera ytor och linjer, oavsett vilket lager som
är valt. Ctrl-klick eller Skift-klick lägger till i markeringen (en rektangel likaså). Högerklick avmarkerar allt."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.core import Qgis, QgsGeometry, QgsPointXY, QgsRectangle
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from ..controller import Candidate, PlanController

CLICK_PIXELS = 4
DRAG_PIXELS = 4  # kortare drag än så räknas som ett klick, inte en rektangel
MIN_TOLERANCE = 0.05  # meter

Choose = Callable[[list[Candidate]], Optional[Candidate]]  # visar valet av yta, returnerar den valda (eller None)
Report = Callable[[str, bool], None]
Selected = Callable[[Candidate], None]
ADD_MODIFIERS = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier


class SelectTool(QgsMapTool):
    """Klick markerar det som ligger under klicket (ligger flera ytor på varandra får man välja vilken det gäller);
    dra för att markera med en rektangel i stället. Ctrl-klick eller Skift-klick lägger till i markeringen.
    Högerklick avmarkerar allt. Det markerade lagret blir aktivt så att redigeringsverktygen fungerar direkt."""

    def __init__(self, canvas: QgsMapCanvas, controller: PlanController, choose: Choose, report: Report,
                 on_selected: Optional[Selected] = None):
        super().__init__(canvas)
        self.controller = controller
        self.choose = choose
        self.report = report
        self.on_selected = on_selected
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start: Optional[QgsPointXY] = None
        self._frame = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self._frame.setColor(QColor(30, 110, 200, 40))
        self._frame.setStrokeColor(QColor(30, 110, 200))
        self._frame.setWidth(1)

    def tolerance(self) -> float:
        return max(self.canvas().mapUnitsPerPixel() * CLICK_PIXELS, MIN_TOLERANCE)

    # -- musen ------------------------------------------------------------------------
    def canvasPressEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.mapPoint()

    def canvasMoveEvent(self, event):  # noqa: N802
        if self._start is not None:
            self._frame.setToGeometry(QgsGeometry.fromRect(QgsRectangle(self._start, event.mapPoint())), None)

    def canvasReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self.controller.clear_selection()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        start, self._start = self._start, None
        self._frame.reset(Qgis.GeometryType.Polygon)
        if start is None:
            return
        point = event.mapPoint()
        add = bool(event.modifiers() & ADD_MODIFIERS)
        if start.distance(point) > self.canvas().mapUnitsPerPixel() * DRAG_PIXELS:
            self.select_rect(QgsRectangle(start, point), add)
        else:
            self.click(point, add)

    def deactivate(self):
        self._start = None
        self._frame.reset(Qgis.GeometryType.Polygon)
        super().deactivate()

    # -- själva åtgärderna (kan anropas direkt i tester) -----------------------------------
    def click(self, point: QgsPointXY, add: bool = False) -> Optional[Candidate]:
        """Markerar ytan under punkten."""
        candidates = self.controller.candidates_at(point, self.tolerance(), self.controller.SELECTABLE)
        if not candidates:
            if not add:
                self.controller.clear_selection()
            self.report("Inget att markera här.", False)
            return None
        chosen = candidates[0] if len(candidates) == 1 else self.choose(candidates)
        if chosen is None:
            return None
        self.controller.select(chosen, add=add)
        if self.on_selected is not None:
            self.on_selected(chosen)
        return chosen

    def select_rect(self, rect: QgsRectangle, add: bool = False) -> list[Candidate]:
        """Markerar allt som rektangeln rör vid."""
        found = self.controller.select_in_rect(rect, add=add)
        if not found:
            if not add:
                self.report("Inget att markera i rektangeln.", False)
        elif self.on_selected is not None:
            self.on_selected(found[0])
        return found
