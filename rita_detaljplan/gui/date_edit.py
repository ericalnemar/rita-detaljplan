"""Datumruta: en textruta där man skriver ÅÅÅÅ-MM-DD, med en kalenderknapp till höger som öppnar en kalender att välja
datum i. Ett valt datum skrivs in i rutan; i en ruta med flera datum (``multiple``, t.ex. laga kraft) läggs det till
efter de som redan står där."""
from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QCalendarWidget, QLineEdit, QMenu, QWidgetAction

ICON = Path(__file__).resolve().parent.parent / "icons" / "calendar.svg"


class DateLineEdit(QLineEdit):
    def __init__(self, parent=None, multiple: bool = False):
        super().__init__(parent)
        self.multiple = multiple
        self.setPlaceholderText("ÅÅÅÅ-MM-DD")
        self.calendar_action = self.addAction(QIcon(str(ICON)), QLineEdit.ActionPosition.TrailingPosition)
        self.calendar_action.setToolTip("Välj datum i en kalender")
        self.calendar_action.triggered.connect(self.open_calendar)
        self.menu = None

    def start_date(self) -> QDate:
        """Datumet kalendern öppnas på: det sista datumet i rutan om det är ett riktigt datum, annars idag."""
        parts = [part.strip() for part in self.text().split(";") if part.strip()]
        date = QDate.fromString(parts[-1], "yyyy-MM-dd") if parts else QDate()
        return date if date.isValid() else QDate.currentDate()

    def make_calendar(self) -> QCalendarWidget:
        calendar = QCalendarWidget()
        calendar.setGridVisible(True)
        calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        calendar.setSelectedDate(self.start_date())
        calendar.clicked.connect(self.choose)
        return calendar

    def open_calendar(self) -> None:
        """Visar kalendern under rutan (ett litet fönster som stängs när man väljer ett datum)."""
        self.menu = QMenu(self)
        action = QWidgetAction(self.menu)
        action.setDefaultWidget(self.make_calendar())
        self.menu.addAction(action)
        self.menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def choose(self, date: QDate) -> None:
        """Skriver in det valda datumet och stänger kalendern."""
        text = date.toString("yyyy-MM-dd")
        if self.multiple and self.text().strip():
            parts = [part.strip() for part in self.text().split(";") if part.strip()]
            if text not in parts:
                parts.append(text)
            text = "; ".join(parts)
        self.setText(text)
        if self.menu is not None:
            self.menu.close()
