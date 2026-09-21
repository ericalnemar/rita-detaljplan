"""Verktyget i QGIS layoutläge som skapar detaljplanens teckenförklaring.

Verktyget lägger till en knapp i layoutdesignerns verktygsfält. Det skapar bara teckenförklaringen (se
``core.legend_layout``); kartan och plankartemallen gör användaren själv. Markera ett objekt (t.ex. en rektangel) innan du
trycker på knappen så fyller teckenförklaringen den ytan; annars läggs den längst till höger på sidan. Trycker du igen
ersätts den tidigare teckenförklaringen på sin plats.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from qgis.core import Qgis, QgsSettings
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMainWindow, QToolBar

from ..controller import PlanController
from ..core import catalog as cat
from ..core import legend_layout as ll
from .legend_settings_dialog import LegendSettingsDialog

ICONS = Path(__file__).resolve().parent.parent / "icons"
TITLE = "Rita Detaljplan"
KEY_VISIBLE = "detaljplan_ngp/layout_toolbar_visible"
SETTINGS_TIP = "Inställningar för teckenförklaringen: teckensnitt, storlekar, rutor och avstånd."
TIP = ("Teckenförklaring: skapa detaljplanens teckenförklaring i layouten. Markera en yta först för att fylla den, "
       "annars läggs den längst till höger på sidan. En tidigare teckenförklaring ersätts.")


class LayoutLegendTool:
    def __init__(self, iface, controller: PlanController, catalog_provider: Callable[[], cat.Catalog]):
        self.iface = iface
        self.controller = controller
        self.catalog_provider = catalog_provider
        self.actions: dict = {}  # designer -> [knappar]
        self.bars: dict = {}  # designer -> (eget verktygsfält eller None, dess visa/dölj-åtgärd)

    # -- koppling till layoutdesignern ----------------------------------------------------------
    def attach(self) -> None:
        self.iface.layoutDesignerOpened.connect(self.add_to)
        self.iface.layoutDesignerWillBeClosed.connect(self.remove_from)
        for designer in self.iface.openLayoutDesigners():
            self.add_to(designer)

    def detach(self) -> None:
        for signal, slot in ((self.iface.layoutDesignerOpened, self.add_to),
                             (self.iface.layoutDesignerWillBeClosed, self.remove_from)):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        for designer in list(self.actions):
            self.remove_from(designer)

    def add_to(self, designer) -> QAction:
        """Lägger till knapparna Teckenförklaring och Inställningar för teckenförklaring. Returnerar den första."""
        if designer in self.actions:
            return self.actions[designer][0]
        window = designer.window() if hasattr(designer, "window") else None
        own = isinstance(window, QMainWindow)
        if own:  # ett eget verktygsfält som går att stänga (View-menyn i designern, eller högerklick på verktygsfälten)
            bar = QToolBar("Rita Detaljplan", window)
            bar.setObjectName("DetaljplanLayoutToolBar")
            window.addToolBar(bar)
            bar.setVisible(QgsSettings().value(KEY_VISIBLE, True, type=bool))
        else:
            bar = designer.actionsToolbar()
        action = QAction(QIcon(str(ICONS / "legend.svg")), "Teckenförklaring", bar)
        action.setToolTip(TIP)
        action.triggered.connect(lambda _checked=False, d=designer: self.generate(d))
        options = QAction(QIcon(str(ICONS / "legend_settings.svg")), "Inställningar för teckenförklaring", bar)
        options.setToolTip(SETTINGS_TIP)
        options.triggered.connect(lambda _checked=False, d=designer: self.configure(d))
        bar.addAction(action)
        bar.addAction(options)
        toggle = None
        if own:
            toggle = bar.toggleViewAction()
            toggle.setText("Verktygsfält för Rita Detaljplan")
            toggle.triggered.connect(lambda checked: QgsSettings().setValue(KEY_VISIBLE, bool(checked)))  # bara användarens val
            menu = designer.viewMenu() if hasattr(designer, "viewMenu") else None
            if menu is not None:
                menu.addAction(toggle)
        self.actions[designer] = [action, options]
        self.bars[designer] = (bar if own else None, toggle)
        return action

    def remove_from(self, designer) -> None:
        bar, toggle = self.bars.pop(designer, (None, None))
        for action in self.actions.pop(designer, []):
            try:
                if bar is None:
                    designer.actionsToolbar().removeAction(action)
            except RuntimeError:  # designern är redan borta
                pass
            action.deleteLater()
        try:
            if toggle is not None and hasattr(designer, "viewMenu"):
                designer.viewMenu().removeAction(toggle)
            if bar is not None:
                bar.blockSignals(True)  # stängningen ska inte räknas som att användaren dolt verktygsfältet
                designer.window().removeToolBar(bar)
                bar.setParent(None)
                bar.deleteLater()
        except RuntimeError:
            pass

    # -- skapa teckenförklaringen ------------------------------------------------------------------
    def _say(self, designer, text: str, level) -> None:
        designer.messageBar().pushMessage(TITLE, text, level=level)

    @staticmethod
    def target_rect(layout):
        """Ytan (x, y, bredd, höjd i mm) som teckenförklaringen ska fylla: det markerade objektet, om det inte är en
        tidigare teckenförklaring (den ersätts på sin plats). None = standardplacering."""
        for item in layout.selectedLayoutItems():
            if item.customProperty(ll.TAG):
                return None
            box = item.sceneBoundingRect()
            return box.left(), box.top(), box.width(), box.height()
        return None

    def _ask_style(self, designer):
        """Öppnar inställningsdialogen. Returnerar True om de sparades."""
        return LegendSettingsDialog(parent=designer.window() if hasattr(designer, "window") else None).exec()

    def configure(self, designer) -> bool:
        """Inställningar för teckenförklaringen. En teckenförklaring som redan finns i layouten görs om med de nya
        inställningarna, på samma plats. Returnerar True om inställningarna sparades."""
        if not self._ask_style(designer):
            return False
        if ll.existing_legends(designer.layout()):
            self.generate(designer, replace_existing=True)
        return True

    def generate(self, designer, replace_existing: bool = False):
        """Skapar teckenförklaringen i designerns layout. Returnerar resultatet, eller None om det inte gick."""
        if self.controller.plan_feature() is None:
            self._say(designer, "Öppna en detaljplan med ett ritat planområde först: teckenförklaringen byggs av planen.",
                      Qgis.MessageLevel.Warning)
            return None
        layout = designer.layout()
        try:
            rows, decision = self.controller.legend_data()
            rect = None if replace_existing else self.target_rect(layout)
            result = ll.add_legend(layout, rows, self.catalog_provider(), decision, rect)
        except ll.LegendError as exc:
            self._say(designer, str(exc), Qgis.MessageLevel.Critical)
            return None
        if result.group is not None:
            layout.setSelectedItem(result.group)
        self._say(designer, "Skapade teckenförklaringen." + (" " + " ".join(result.warnings) if result.warnings else ""),
                  Qgis.MessageLevel.Warning if result.warnings else Qgis.MessageLevel.Success)
        return result
