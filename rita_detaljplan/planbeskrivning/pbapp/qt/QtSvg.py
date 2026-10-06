from . import IN_QGIS

if IN_QGIS:
    from qgis.PyQt.QtSvg import *  # noqa: F401,F403
else:
    from PySide6.QtSvg import *  # noqa: F401,F403
