"""Kartverktyget "Markera": klicka i planen för att markera en yta eller linje, oavsett vilket lager som är valt."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.core import QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapTool
from qgis.PyQt.QtCore import Qt

from ..controller import Candidate, PlanController

CLICK_PIXELS = 4
MIN_TOLERANCE = 0.05  # meter

Choose = Callable[[list[Candidate]], Optional[Candidate]]  # visar valet av yta, returnerar den valda (eller None)
Report = Callable[[str, bool], None]
Selected = Callable[[Candidate], None]


class SelectTool(QgsMapTool):
    """Klick markerar det som ligger under klicket. Ligger flera ytor på varandra får man välja vilken det gäller.
    Skift-klick lägger till i markeringen. Det markerade lagret blir aktivt så att redigeringsverktygen fungerar."""

    def __init__(self, canvas: QgsMapCanvas, controller: PlanController, choose: Choose, report: Report,
                 on_selected: Optional[Selected] = None):
        super().__init__(canvas)
        self.controller = controller
        self.choose = choose
        self.report = report
        self.on_selected = on_selected
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def canvasReleaseEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.click(event.mapPoint(), add=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))

    def tolerance(self) -> float:
        return max(self.canvas().mapUnitsPerPixel() * CLICK_PIXELS, MIN_TOLERANCE)

    def click(self, point: QgsPointXY, add: bool = False) -> Optional[Candidate]:
        """Markerar ytan under punkten (kan anropas direkt i tester). Returnerar det som markerades."""
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
