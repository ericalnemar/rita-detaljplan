"""Delad QGIS-applikation för testerna (endast en instans får finnas per process)."""
import atexit

from qgis.core import QgsApplication

_app = None


def get_app() -> QgsApplication:
    global _app
    if _app is None:
        _app = QgsApplication([], True)  # GUI=True behövs för widgets; QT_QPA_PLATFORM=offscreen ger inget fönster
        _app.initQgis()
        atexit.register(_app.exitQgis)
    return _app
