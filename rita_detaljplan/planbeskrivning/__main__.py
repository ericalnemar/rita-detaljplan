"""Startar programmet fristående, utan QGIS: python -m rita_detaljplan.planbeskrivning [planbeskrivning.docx] [plan.qgz]"""
import sys

from .pbapp.main import main

sys.exit(main())
