from . import IN_QGIS

if IN_QGIS:
    from qgis.PyQt.QtGui import *  # noqa: F401,F403
else:
    from PySide6.QtGui import *  # noqa: F401,F403
