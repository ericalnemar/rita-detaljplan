"""Kartverktyget "Fyll resten av användningsområdet med en egenskapsyta": klicka i ett användningsområde."""
from __future__ import annotations

from typing import Callable

from qgis.core import QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapTool
from qgis.PyQt.QtCore import Qt

from ..controller import PlanController

Report = Callable[[str, bool], None]  # (text, är_varning)


class FillTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, controller: PlanController, report: Report):
        super().__init__(canvas)
        self.controller = controller
        self.report = report
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def canvasReleaseEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.click(event.mapPoint())

    def click(self, point: QgsPointXY):
        """Fyller användningsområdet under punkten (kan anropas direkt i tester)."""
        result = self.controller.fill_property(point)
        self.report(result.message, not result.ok)
        return result
