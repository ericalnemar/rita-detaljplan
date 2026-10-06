from . import IN_QGIS

if IN_QGIS:
    from qgis.PyQt.QtCore import *  # noqa: F401,F403
else:
    from PySide6.QtCore import *  # noqa: F401,F403

if IN_QGIS:
    from qgis.PyQt.QtCore import pyqtSignal as Signal  # noqa: F401
