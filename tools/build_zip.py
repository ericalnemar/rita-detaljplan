"""Bygger zip-filen som installeras i QGIS (Tillägg → Hantera och installera tillägg → Installera från ZIP).

    python tools/build_zip.py            # skapar dist/rita_detaljplan-<version>.zip

Zip-filen har mappen ``rita_detaljplan/`` i roten (det QGIS kräver) med pluginets filer plus LICENSE, NOTICE.md och
CHANGELOG.md. Textfiler får LF som radslut (som i repot). Versionen läses ur ``rita_detaljplan/metadata.txt``. Ingen QGIS behövs.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = "rita_detaljplan"
EXTRA = ("LICENSE", "NOTICE.md", "CHANGELOG.md")  # följer med in i pluginmappen
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # samma innehåll ger samma zip


def read_metadata(root: Path = ROOT) -> dict[str, str]:
    values = {}
    for line in (root / PLUGIN / "metadata.txt").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def version(root: Path = ROOT) -> str:
    found = read_metadata(root).get("version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", found):
        raise SystemExit(f"Ogiltigt versionsnummer i metadata.txt: {found!r} (förväntar t.ex. 0.1.0)")
    return found


def plugin_files(root: Path = ROOT) -> list[tuple[Path, str]]:
    """(källfil, sökväg i zip) för allt som ska med, sorterat."""
    files = []
    for path in sorted((root / PLUGIN).rglob("*")):
        if path.is_dir() or SKIP_DIRS & set(path.relative_to(root).parts) or path.suffix in SKIP_SUFFIXES:
            continue
        files.append((path, path.relative_to(root).as_posix()))
    for name in EXTRA:
        source = root / name
        if source.exists():
            files.append((source, f"{PLUGIN}/{name}"))
    return files


def normalized(data: bytes) -> bytes:
    """Textfiler med LF som radslut, som i repot (`.gitattributes`), även om arbetskopian på Windows har CRLF. Då blir
    zip-filen densamma på alla datorer och matchar incheckningen. Binära filer lämnas orörda."""
    if b"\0" in data:
        return data
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return data.replace(b"\r\n", b"\n")


def build(root: Path = ROOT, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or root / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{PLUGIN}-{version(root)}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, name in plugin_files(root):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, normalized(source.read_bytes()))
    return target


if __name__ == "__main__":
    path = build()
    print(f"Skapade {path} ({path.stat().st_size / 1024:.0f} kB)")
    sys.exit(0)
