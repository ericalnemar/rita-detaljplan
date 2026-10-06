"""Skapar exemplet kv. Lärkan i mappen exempel/ (planbeskrivning, GeoPackage och QGIS-projekt), som knappen Öppna
exemplet kv. Lärkan i Tagga planbeskrivning öppnar när programmet körs från repot. Mappen följer inte med zip-filen.

    python tools/skapa_exempel.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from plankarta_case import make_larkan  # noqa: E402

if __name__ == "__main__":
    for kind, path in make_larkan(ROOT / "exempel").items():
        print(f"{kind}: {path}")
