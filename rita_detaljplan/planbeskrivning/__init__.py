"""Tagga planbeskrivning: programmet som taggar planbeskrivningar (Word) enligt BFS 2020:8 och Lantmäteriets
Planbeskrivning 2.0. Öppnas med knappen Tagga planbeskrivning i verktygsfältet (``gui/planbeskrivning_host.py``) och kan
också köras fristående, utan QGIS: ``python -m rita_detaljplan.planbeskrivning`` (kräver PySide6).

``pbkarna`` är kärnan (ren Python, ingen Qt eller QGIS); ``pbapp`` är fönstret, som importerar Qt via ``pbapp/qt``
(PyQt6 i QGIS, PySide6 fristående)."""
