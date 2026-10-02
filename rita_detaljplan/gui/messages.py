"""Meddelanden i QGIS meddelandefält (överkanten av kartfönstret): alla stängs av sig själva efter några sekunder."""
from qgis.core import Qgis

DURATION = {
    Qgis.MessageLevel.Info: 5,
    Qgis.MessageLevel.Success: 5,
    Qgis.MessageLevel.Warning: 10,
    Qgis.MessageLevel.Critical: 10,
}


def push(bar, title: str, text: str, level=Qgis.MessageLevel.Info) -> None:
    bar.pushMessage(title, text, level=level, duration=DURATION.get(level, 10))
