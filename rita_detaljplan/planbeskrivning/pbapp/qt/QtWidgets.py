from . import IN_QGIS

if IN_QGIS:
    from qgis.PyQt.QtWidgets import *  # noqa: F401,F403
else:
    from PySide6.QtWidgets import *  # noqa: F401,F403
