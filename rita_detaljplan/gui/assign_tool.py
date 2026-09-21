"""Kartverktyget "Planbestämmelser": klicka på en yta för att tilldela den bestämmelser."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.core import Qgis, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from ..controller import Candidate, PlanController

CLICK_PIXELS = 4  # så nära klicket ska en linje ligga för att räknas
MIN_TOLERANCE = 0.05  # meter: golv för klicktoleransen om kartan ännu inte är ritad

OpenDialog = Callable[[list[Candidate], "AssignTool"], None]
Report = Callable[[str, bool], None]  # (text, är_varning)


class AssignTool(QgsMapTool):
    """Klick på en yta öppnar dialogen för ytans bestämmelser. Ytan som dialogen gäller markeras i kartan."""

    def __init__(self, canvas: QgsMapCanvas, controller: PlanController, open_dialog: OpenDialog, report: Report):
        super().__init__(canvas)
        self.controller = controller
        self.open_dialog = open_dialog
        self.report = report
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rubber = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self._rubber.setColor(QColor(30, 110, 200, 50))
        self._rubber.setStrokeColor(QColor(30, 110, 200))
        self._rubber.setWidth(2)

    # -- händelser --------------------------------------------------------------------
    def canvasReleaseEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.click(event.mapPoint())

    def deactivate(self):
        self.clear_highlight()
        super().deactivate()

    # -- själva klicket (kan anropas direkt i tester) -----------------------------------
    def tolerance(self) -> float:
        return max(self.canvas().mapUnitsPerPixel() * CLICK_PIXELS, MIN_TOLERANCE)

    def click(self, point: QgsPointXY) -> list[Candidate]:
        """Hittar ytorna under punkten och öppnar dialogen för dem. Returnerar ytorna som hittades."""
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser först.", True)
            return []
        candidates = self.controller.candidates_at(point, self.tolerance())
        if not candidates:
            self.report("Ingen yta här. Klicka på ett användnings- eller egenskapsområde.", True)
            return []
        try:
            self.open_dialog(candidates, self)
        finally:
            self.clear_highlight()
        return candidates

    # -- markering av vald yta ----------------------------------------------------------
    def highlight(self, candidate: Optional[Candidate]) -> None:
        self.clear_highlight()
        if candidate is None:
            return
        layer = self.controller.layer(candidate.table)
        feature = layer.getFeature(candidate.fid) if layer is not None else None
        if feature is None or not feature.isValid():
            return
        geometry = QgsGeometry(feature.geometry())
        line = candidate.table == "egenskap_linje"
        self._rubber.reset(Qgis.GeometryType.Line if line else Qgis.GeometryType.Polygon)
        self._rubber.setToGeometry(geometry, layer)

    def clear_highlight(self) -> None:
        self._rubber.reset(Qgis.GeometryType.Polygon)
