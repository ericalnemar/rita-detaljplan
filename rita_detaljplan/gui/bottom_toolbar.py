"""En flytande verktygsrad ovanpå kartduken, längst ned, listlös och halvgenomskinlig – som ett CAD-program.
Byggd som en riktig ``QToolBar`` (samma bas som "Rita Detaljplan" högst upp, se ``PlanToolBar``): knapparnas
storlek och utseende blir desamma som i ett vanligt QGIS-verktygsfält, vi behöver bara kalla ``addAction``.

Den är barn till kartduken (inte QGIS eget huvudfönster/dockningssystem): en flytande panel ovanpå kartan,
centrerad längst ned och storleksanpassad efter sitt innehåll. Går inte att dra runt (det behövs inte) – bara
osynlig tills den behövs, se ``PlanToolBar`` för när den visas (när en geometri är vald att rita).

Historik: var tidigare ett vanligt, dockat verktygsfält (``iface.addToolBar``, dra till valfri kant) – det bytte
vi tillbaka från eftersom det inte alls kändes bättre i praktiken."""
from __future__ import annotations

from qgis.PyQt.QtCore import QEvent, QSize, Qt
from qgis.PyQt.QtWidgets import QToolBar

ICON_SIZE = QSize(28, 28)  # standardvärde om ingen ikonstorlek anges (se __init__): PlanToolBar skickar alltid
# med QGIS egen ``iface.iconSize()`` i stället, så raden matchar QGIS aktuella inställning (Inställningar →
# Alternativ → Allmänt) i stället för ett fast värde – annars blir den fel storlek jämfört med resten av QGIS
# så fort användaren har en annan ikonstorlek inställd.
BOTTOM_MARGIN = 14  # avstånd till kartvyns nederkant, i pixlar


class BottomToolBar(QToolBar):
    """Ett urval av egna verktyg (Markera, Fyll osv.) och QGIS egna (Parallell, Vinkelrätt, Spårning m.fl.), som
    flyter ovanpå kartduken. Knapparna läggs till av ``PlanToolBar`` med ``addAction`` – samma metod som ett
    vanligt verktygsfält. Dold som standard: ``PlanToolBar`` visar den bara när en geometri är vald att rita."""

    def __init__(self, canvas, icon_size: QSize = ICON_SIZE):
        super().__init__("Rita Detaljplan – fler verktyg", canvas)
        self._canvas = canvas
        self.setObjectName("DetaljplanBottomToolBar")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(icon_size)
        self.setMovable(False)
        # QToolBar ritar inte ut stylesheetens bakgrund/kant själv (till skillnad från t.ex. QFrame) om man inte
        # sätter WA_StyledBackground – annars syns bara knapparna flytande ovanpå kartan, ingen bakgrund/kant.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "#DetaljplanBottomToolBar {"
            "  background-color: rgba(245, 245, 245, 140);"  # halvgenomskinlig
            "  border: 1px solid rgba(0, 0, 0, 60);"
            "  border-radius: 6px;"
            "}"
        )

        canvas.installEventFilter(self)
        self.hide()  # osynlig tills PlanToolBar visar den (en geometri vald att rita)
        self.reposition()

    def add_action(self, action) -> None:
        """Lägger till en knapp för ``action`` längst till höger i raden."""
        self.addAction(action)
        self.reposition()  # bredden ändras när knappar läggs till

    # -- placering (flytande, listlös, centrerad längst ned i kartduken) ------------------------
    def reposition(self) -> None:
        """Lägger raden centrerad längst ned i kartduken, storleksanpassad efter innehållet. Körs vid start och
        varje gång kartduken ändrar storlek eller raden får nya knappar."""
        width, height = self.sizeHint().width(), self.sizeHint().height()
        x = max((self._canvas.width() - width) // 2, 0)
        self.setGeometry(x, max(self._canvas.height() - height - BOTTOM_MARGIN, 0), width, height)
        self.raise_()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt-namn
        if obj is self._canvas and event.type() == QEvent.Type.Resize:
            self.reposition()
        return False
