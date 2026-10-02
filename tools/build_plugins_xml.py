"""Skapar ``plugins.xml``: pluginkällan som QGIS pluginhanterare kan läsa, så att pluginet går att installera och
uppdatera direkt i QGIS utan att ladda ner zip-filen för hand.

    python tools/build_plugins_xml.py    # skriver plugins.xml i repots rot

Filen beskriver den version som står i ``rita_detaljplan/metadata.txt`` och pekar på zip-filen i GitHub Releases
(``tools/build_zip.py`` bygger den). Kör skriptet i samma incheckning som versionen höjs. QGIS läser filen via
``https://raw.githubusercontent.com/ericalnemar/rita-detaljplan/main/plugins.xml`` (Tillägg → Hantera och installera
tillägg → Inställningar → Lägg till). Ingen QGIS behövs.
"""
from __future__ import annotations

import datetime
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import build_zip

ROOT = build_zip.ROOT
PLUGIN = build_zip.PLUGIN
PLUGINS_XML_URL = "https://raw.githubusercontent.com/ericalnemar/rita-detaljplan/main/plugins.xml"


def download_url(meta: dict[str, str]) -> str:
    version = meta["version"]
    return f"{meta['repository']}/releases/download/v{version}/{PLUGIN}-{version}.zip"


def build_tree(meta: dict[str, str], updated: datetime.date) -> ET.ElementTree:
    root = ET.Element("plugins")
    plugin = ET.SubElement(root, "pyqgis_plugin", name=meta["name"], version=meta["version"])
    fields = (
        ("description", meta["description"]),
        ("about", meta["about"]),
        ("version", meta["version"]),
        ("qgis_minimum_version", meta["qgisMinimumVersion"]),
        ("qgis_maximum_version", meta.get("qgisMaximumVersion", "")),
        ("homepage", meta["homepage"]),
        ("file_name", f"{PLUGIN}-{meta['version']}.zip"),
        ("icon", f"{meta['repository']}/raw/main/{PLUGIN}/{meta['icon']}"),
        ("author_name", meta["author"]),
        ("download_url", download_url(meta)),
        ("uploaded_by", meta["author"]),
        ("create_date", updated.isoformat()),
        ("update_date", updated.isoformat()),
        ("experimental", meta.get("experimental", "False")),
        ("deprecated", meta.get("deprecated", "False")),
        ("tracker", meta["tracker"]),
        ("repository", meta["repository"]),
        ("tags", meta["tags"]),
        ("server", "False"),
    )
    for tag, value in fields:
        if value != "":
            ET.SubElement(plugin, tag).text = value
    ET.indent(root)
    return ET.ElementTree(root)


def build(root: Path = ROOT, today: datetime.date | None = None) -> Path:
    meta = build_zip.read_metadata(root)
    build_zip.version(root)  # kontrollerar att versionsnumret är giltigt
    target = root / "plugins.xml"
    build_tree(meta, today or datetime.date.today()).write(target, encoding="utf-8", xml_declaration=True)
    return target


if __name__ == "__main__":
    print(f"Skapade {build()}")
    sys.exit(0)
