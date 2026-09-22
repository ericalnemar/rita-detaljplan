"""Kartverktyget "Fyll resten": klicka i den yta man vill fylla. Ett klick fyller och stänger av verktyget igen
(``on_done``); man behöver inte stänga av det för hand."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.core import QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapTool
from qgis.PyQt.QtCore import Qt

from ..controller import FillResult, PlanController

Fill = Callable[[QgsPointXY], FillResult]  # t.ex. ``controller.fill_use_at`` eller ``controller.fill_property``
Report = Callable[[str, bool], None]  # (text, är_varning)
Done = Callable[[], None]


class FillTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, controller: PlanController, fill: Fill, report: Report,
                 on_done: Optional[Done] = None):
        super().__init__(canvas)
        self.controller = controller
        self.fill = fill
        self.report = report
        self.on_done = on_done
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def canvasReleaseEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.click(event.mapPoint())

    def click(self, point: QgsPointXY) -> FillResult:
        """Fyller ytan under punkten (kan anropas direkt i tester)."""
        result = self.fill(point)
        self.report(result.message, not result.ok)
        if result.ok and self.on_done is not None:
            self.on_done()
        return result
