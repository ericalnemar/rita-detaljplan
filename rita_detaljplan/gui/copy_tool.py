"""Kartverktyget "Kopiera bestämmelser": klicka på en egenskapsyta (eller egenskapslinje) och sedan på ytan som ska få
samma bestämmelser. Verktyget ligger kvar efter en kopiering så att man kan fortsätta till fler ytor; högerklick eller Esc
väljer en ny källa."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.core import Qgis, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from ..controller import Candidate, PlanController
from ..core import catalog as cat
from ..core.assignments import AssignmentError, CopyReport

CLICK_PIXELS = 4  # så nära klicket ska en linje ligga för att räknas
MIN_TOLERANCE = 0.05  # meter: golv för klicktoleransen om kartan ännu inte är ritad

Choose = Callable[[list[Candidate]], Optional[Candidate]]  # visar valet av yta, returnerar den valda (eller None)
Report = Callable[[str, bool], None]  # (text, är_varning)
KIND = {"egenskap_yta": "en egenskapsyta", "egenskap_linje": "en egenskapslinje"}


def _count(n: int) -> str:
    return f"{n} bestämmelse" if n == 1 else f"{n} bestämmelser"


def summary(report: CopyReport, target: str) -> str:
    """Meddelandet efter en kopiering: vad som kopierades, vad som redan fanns och vad som inte passade."""
    parts = []
    if report.copied:
        parts.append(f"Kopierade {_count(report.copied)} till {target}.")
    if report.already:
        parts.append(f"{_count(report.already).capitalize()} fanns redan på ytan." if report.copied or report.skipped
                     else "Ytan har redan alla bestämmelserna.")
    if report.skipped:
        parts.append(f"{_count(len(report.skipped)).capitalize()} passade inte och hoppades över: "
                     + "; ".join(report.skipped))
    return " ".join(parts)


class CopyTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, controller: PlanController, choose: Choose, report: Report):
        super().__init__(canvas)
        self.controller = controller
        self.choose = choose
        self.report = report
        self.source: Optional[Candidate] = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rubber = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self._rubber.setColor(QColor(40, 160, 90, 60))
        self._rubber.setStrokeColor(QColor(40, 160, 90))
        self._rubber.setWidth(2)

    # -- händelser --------------------------------------------------------------------
    def canvasReleaseEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.click(event.mapPoint())
        elif event.button() == Qt.MouseButton.RightButton:
            self.reset_source(announce=True)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reset_source(announce=True)
            event.accept()
        else:
            super().keyPressEvent(event)

    def activate(self):
        super().activate()
        self.report("Kopiera bestämmelser: klicka på ytan du vill kopiera från.", False)

    def deactivate(self):
        self.reset_source()
        super().deactivate()

    # -- själva klicket (kan anropas direkt i tester) -----------------------------------
    def tolerance(self) -> float:
        return max(self.canvas().mapUnitsPerPixel() * CLICK_PIXELS, MIN_TOLERANCE)

    def click(self, point: QgsPointXY) -> Optional[Candidate]:
        """Första klicket väljer källan, nästa klick väljer ytan som får kopiorna. Returnerar ytan som klickades, eller
        None om inget hände."""
        if not self.controller.editing:
            self.report("Börja rita planbestämmelser först.", True)
            return None
        if self.source is not None and not self._source_exists():
            self.reset_source()
        candidates = self.controller.candidates_at(point, self.tolerance(), cat.PROPERTY_LAYERS)
        if self.source is not None:
            same_kind = [c for c in candidates if c.table == self.source.table]
            if candidates and not same_kind:
                self.report(f"Bestämmelserna kommer från {KIND[self.source.table]}: klicka på {KIND[self.source.table]}.",
                            True)
                return None
            candidates = [c for c in same_kind if c.fid != self.source.fid]
        if not candidates:
            self.report("Ingen egenskapsyta här. Klicka på en egenskapsyta eller egenskapslinje.", True)
            return None
        chosen = candidates[0] if len(candidates) == 1 else self.choose(candidates)
        if chosen is None:
            return None
        if self.source is None:
            self._set_source(chosen)
        else:
            self._copy_to(chosen)
        return chosen

    def reset_source(self, announce: bool = False) -> None:
        self.source = None
        self._rubber.reset(Qgis.GeometryType.Polygon)
        if announce:
            self.report("Klicka på ytan du vill kopiera från.", False)

    # -- delar -------------------------------------------------------------------------
    def _source_exists(self) -> bool:
        layer = self.controller.layer(self.source.table)
        return layer is not None and layer.getFeature(self.source.fid).isValid()

    def _set_source(self, candidate: Candidate) -> None:
        if not self.controller.rows_of(candidate.table, candidate.fid):
            self.report("Ytan har inga bestämmelser att kopiera.", True)
            return
        self.source = candidate
        self._highlight(candidate)
        self.report(f"Kopierar från: {candidate.title}. Klicka på ytan som ska få samma bestämmelser. "
                    "Högerklick eller Esc väljer en ny källa.", False)

    def _copy_to(self, target: Candidate) -> None:
        try:
            result = self.controller.copy_bestammelser(self.source.table, self.source.fid, target.fid)
        except AssignmentError as exc:
            self.report(str(exc), True)
            return
        self.report(summary(result, self.controller.describe_area(target.table, target.fid)),
                    bool(result.skipped))

    def _highlight(self, candidate: Candidate) -> None:
        layer = self.controller.layer(candidate.table)
        feature = layer.getFeature(candidate.fid) if layer is not None else None
        if feature is None or not feature.isValid():
            return
        line = candidate.table == "egenskap_linje"
        self._rubber.reset(Qgis.GeometryType.Line if line else Qgis.GeometryType.Polygon)
        self._rubber.setToGeometry(QgsGeometry(feature.geometry()), layer)
