"""Bygger Rita Detaljplans märke och bannrar som SVG (och social preview som PNG).

    python-qgis.bat tools/build_branding.py <mapp med Archivo-var.ttf och IBMPlexMono-Regular.ttf>

Märket (R2) och färgerna kommer från identitetsarbetet: Tusch #16181A, Gummiband #E2553A, Ritpapper #F5F5F2. Texten i
bannrarna görs om till konturer med typsnitten Archivo och IBM Plex Mono (båda SIL Open Font License 1.1), så att
bilderna ser likadana ut överallt utan att typsnitten behöver finnas på läsarens dator. Typsnittsfilerna följer inte med
i repot. Körs med QGIS Python (behöver Qt, inte QGIS-kärnan).

Skriver:  rita_detaljplan/icon.svg, docs/images/banner-mork.svg, docs/images/banner-ljus.svg och
          docs/images/social-preview.png
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from qgis.PyQt.QtCore import QPointF, QRectF, QSize, Qt  # noqa: E402
from qgis.PyQt.QtGui import (QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QImage, QPainter,  # noqa: E402
                             QPainterPath)
from qgis.PyQt.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INK, ACCENT, PAPER, GUIDE = "#16181A", "#E2553A", "#F5F5F2", "#C9C9C2"

# -- märket -------------------------------------------------------------------------------------------------------------
# två storlekar: L (stor, för bannrarna) och M (mellan, för ikonen), båda i viewBox 200
_LINE = "44,172 44,28 122,28 154,60 122,92 86,92"


def _squares(points, size, stroke_width, paper, ink):
    rects = "".join(f'<rect x="{x}" y="{y}" width="{size}" height="{size}"/>' for x, y in points)
    return f'<g fill="{paper}" stroke="{ink}" stroke-width="{stroke_width}">{rects}</g>'


def mark(size: str, ink: str, paper: str, accent: str = ACCENT) -> str:
    """Märkets SVG-element. ``ink`` är färgen på linjen, ``paper`` fyllningen i brytpunkterna."""
    if size == "L":
        return (f'<polyline points="{_LINE}" fill="none" stroke="{ink}" stroke-width="9" stroke-linejoin="miter"/>'
                f'<line x1="86" y1="92" x2="152" y2="172" stroke="{accent}" stroke-width="5" stroke-dasharray="10 8"/>'
                f'<path d="M152 156 V188 M136 172 H168" stroke="{accent}" stroke-width="3"/>'
                + _squares([(36, 164), (36, 20), (114, 20), (146, 52), (114, 84), (78, 84)], 16, 4, paper, ink))
    return (f'<polyline points="{_LINE}" fill="none" stroke="{ink}" stroke-width="11" stroke-linejoin="miter"/>'
            f'<line x1="86" y1="92" x2="152" y2="172" stroke="{accent}" stroke-width="7" stroke-dasharray="14 10"/>'
            f'<path d="M152 154 V190 M134 172 H170" stroke="{accent}" stroke-width="5"/>'
            + _squares([(34, 162), (34, 18), (112, 18), (144, 50), (112, 82), (76, 82)], 20, 6, paper, ink))


def svg(width, height, body, title, view_box=None) -> str:
    box = view_box or f"0 0 {width} {height}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}" width="{width}" height="{height}" role="img" '
            f'aria-label="{title}">\n  <title>{title}</title>\n{body}\n</svg>\n')


def tile_icon() -> str:
    """Pluginikonen: det ljusa märket på en mörk platta, så att den syns i både ljust och mörkt QGIS-tema."""
    body = (f'  <rect width="200" height="200" rx="28" fill="{INK}"/>\n'
            f'  <g transform="translate(100 100) scale(0.8) translate(-102 -104)">{mark("M", PAPER, INK)}</g>')
    return svg(48, 48, body, "Rita Detaljplan", "0 0 200 200")


# -- text som konturer --------------------------------------------------------------------------------------------------
class Face:
    def __init__(self, family: str, pixel_size: float, weight=None):
        self.font = QFont(family)
        self.font.setPixelSize(round(pixel_size))
        if weight is not None:
            self.font.setWeight(QFont.Weight(weight))
            try:  # variabelt typsnitt (Archivo): ställ in viktaxeln
                self.font.setVariableAxis(QFont.Tag("wght"), float(weight))
            except Exception:  # äldre Qt utan variabla axlar
                pass
        self.metrics = QFontMetricsF(self.font)
        self.size = pixel_size

    @property
    def ascent(self) -> float:
        return self.metrics.ascent()

    @property
    def descent(self) -> float:
        return self.metrics.descent()

    @property
    def line(self) -> float:
        return self.ascent + self.descent

    def width(self, text: str, spacing: float = 0.0) -> float:
        return self.metrics.horizontalAdvance(text) + spacing * len(text)

    def outline(self, text: str, x: float, baseline: float, spacing: float = 0.0, align: str = "left") -> str:
        """SVG-sökväg (path d) för texten med baslinjen på ``baseline``. Tecknen placeras ett och ett så att
        bokstavsavståndet blir som i webbläsaren, men med kerning mellan paren."""
        if align == "center":
            x -= self.width(text, spacing) / 2
        elif align == "right":
            x -= self.width(text, spacing)
        path = QPainterPath()
        for index, char in enumerate(text):
            if char == " ":
                continue
            offset = self.metrics.horizontalAdvance(text[:index]) + spacing * index
            path.addText(QPointF(x + offset, baseline), self.font, char)
        return _path_data(path)


def _path_data(path: QPainterPath) -> str:
    parts, count, i = [], path.elementCount(), 0
    open_ = False
    while i < count:
        e = path.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            if open_:
                parts.append("Z")
            parts.append(f"M{e.x:.2f} {e.y:.2f}")
            open_ = True
        elif e.type == QPainterPath.ElementType.LineToElement:
            parts.append(f"L{e.x:.2f} {e.y:.2f}")
        else:  # kurva: tre punkter
            c1, c2 = path.elementAt(i + 1), path.elementAt(i + 2)
            parts.append(f"C{e.x:.2f} {e.y:.2f} {c1.x:.2f} {c1.y:.2f} {c2.x:.2f} {c2.y:.2f}")
            i += 2
        i += 1
    if open_:
        parts.append("Z")
    return "".join(parts)


def text_path(d: str, fill: str, label: str = "") -> str:
    return f'  <path d="{d}" fill="{fill}" fill-rule="nonzero"/>'


# -- bannrarna ----------------------------------------------------------------------------------------------------------
def dark_banner(title: Face, mono_14: Face, mono_13: Face, mono_20: Face) -> str:
    w, h, pad_y, pad_x = 1280, 640, 80, 88
    top_h, bottom_h = mono_14.line, mono_13.line
    text_h = 2 * 92 + 24 + mono_20.line
    mid_h = max(240.0, text_h)
    gap = (h - 2 * pad_y - top_h - mid_h - bottom_h) / 2
    mid_top = pad_y + top_h + gap
    mark_y = mid_top + (mid_h - 240) / 2
    text_top = mid_top + (mid_h - text_h) / 2
    spacing = -0.035 * 100
    x_text = pad_x + 240 + 64
    parts = [f'  <rect width="{w}" height="{h}" fill="{INK}"/>',
             f'  <g transform="translate({pad_x} {mark_y:.2f}) scale(1.2)">{mark("L", PAPER, INK)}</g>']
    # övre raden
    base = pad_y + mono_14.ascent
    parts.append(text_path(mono_14.outline("QGIS-PLUGIN", pad_x, base, spacing=0.12 * 14), "#A9ADB2"))
    parts.append(text_path(mono_14.outline("GPL-2.0-OR-LATER", w - pad_x, base, spacing=0.12 * 14, align="right"), "#A9ADB2"))
    # rubrik, två rader med radhöjd 0,92
    for n, word in enumerate(("Rita", "Detaljplan")):
        line_top = text_top + n * 92
        baseline = line_top + (92 - title.line) / 2 + title.ascent
        parts.append(text_path(title.outline(word, x_text, baseline, spacing=spacing), PAPER))
    slogan_base = text_top + 2 * 92 + 24 + mono_20.ascent
    parts.append(text_path(mono_20.outline("Ett QGIS-plugin för att rita detaljplaner", x_text, slogan_base), "#C9CCD0"))
    # nedre raden
    url = "github.com/ericalnemar/rita-detaljplan"
    bottom_top = h - pad_y - bottom_h
    url_w = mono_13.width(url)
    parts.append(f'  <line x1="{pad_x}" y1="{bottom_top + bottom_h / 2:.2f}" x2="{w - pad_x - url_w - 20:.2f}" '
                 f'y2="{bottom_top + bottom_h / 2:.2f}" stroke="#3A3D42" stroke-width="1"/>')
    parts.append(text_path(mono_13.outline(url, w - pad_x, bottom_top + mono_13.ascent, align="right"), "#A9ADB2"))
    return svg(w, h, "\n".join(parts), "Rita Detaljplan – ett QGIS-plugin för att rita detaljplaner")


def light_banner(title: Face, mono_16: Face) -> str:
    w, h = 1280, 640
    title_h = 64.0
    slogan_h = mono_16.line
    total = 220 + 36 + title_h + 14 + slogan_h
    top = (h - total) / 2
    parts = [f'  <rect width="{w}" height="{h}" fill="{PAPER}"/>',
             f'  <g transform="translate({w / 2 - 110} {top:.2f}) scale(1.1)">{mark("L", INK, PAPER)}</g>']
    title_top = top + 220 + 36
    parts.append(text_path(title.outline("Rita Detaljplan", w / 2, title_top + (title_h - title.line) / 2 + title.ascent,
                                         spacing=-0.03 * 64, align="center"), INK))
    slogan_top = title_top + title_h + 14
    parts.append(text_path(mono_16.outline("Ett QGIS-plugin för att rita detaljplaner", w / 2, slogan_top + mono_16.ascent,
                                           spacing=0.04 * 16, align="center"), "#4A4D52"))
    return svg(w, h, "\n".join(parts), "Rita Detaljplan – ett QGIS-plugin för att rita detaljplaner")


def render_png(svg_text: str, out: Path, width: int, height: int) -> None:
    renderer = QSvgRenderer(svg_text.encode("utf-8"))
    image = QImage(QSize(width, height), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    image.save(str(out))


def main(font_dir: Path, preview_dir: Path | None = None) -> None:
    app = QGuiApplication([])  # noqa: F841 - Qt kräver en applikation för typsnitt
    for name in ("Archivo-var.ttf", "IBMPlexMono-Regular.ttf"):
        if QFontDatabase.addApplicationFont(str(font_dir / name)) < 0:
            raise SystemExit(f"Kunde inte läsa typsnittet {font_dir / name}")
    archivo_100 = Face("Archivo", 100, 500)
    archivo_64 = Face("Archivo", 64, 500)
    mono = {size: Face("IBM Plex Mono", size, 400) for size in (13, 14, 16, 20)}
    dark = dark_banner(archivo_100, mono[14], mono[13], mono[20])
    light = light_banner(archivo_64, mono[16])
    outputs = {
        ROOT / "rita_detaljplan" / "icon.svg": tile_icon(),
        ROOT / "docs" / "images" / "banner-mork.svg": dark,
        ROOT / "docs" / "images" / "banner-ljus.svg": light,
    }
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print("skrev", path.relative_to(ROOT))
    render_png(dark, ROOT / "docs" / "images" / "social-preview.png", 1280, 640)
    print("skrev docs/images/social-preview.png")
    if preview_dir:  # förhandsbilder för kontroll, hamnar inte i repot
        preview_dir.mkdir(parents=True, exist_ok=True)
        render_png(light, preview_dir / "ljus.png", 1280, 640)
        render_png(tile_icon(), preview_dir / "icon48.png", 48, 48)
        render_png(tile_icon(), preview_dir / "icon256.png", 256, 256)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
