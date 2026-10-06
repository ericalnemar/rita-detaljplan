"""Qt för programmet: PyQt6 via ``qgis.PyQt`` inne i QGIS, annars PySide6 när programmet körs fristående. Programmet
importerar Qt härifrån (``from .qt.QtCore import ...``), så att samma kod fungerar på båda ställena."""
try:
    import qgis.PyQt.QtCore  # noqa: F401
    IN_QGIS = True
except ImportError:
    IN_QGIS = False
