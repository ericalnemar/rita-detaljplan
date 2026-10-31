"""Exempellayouter för plankartan (ärende 2): vilka mallar som finns, var kartan ligger och vad som står i titelrutan.
Ren Python, ingen QGIS.

Mallarna ligger i ``data/layouts/`` som vanliga QGIS-layoutmallar (.qpt), en per pappersformat (A1–A4) och riktning
(liggande, stående). De byggs av ``tools/build_layouts.py`` ur en A2-mall i liggande format: de liggande skalas om, de
stående får kartan överst och teckenförklaringen, upplysningarna och titelrutan under. ``example_sheet_layout`` läser in
en mall, ställer kartan på planen och fyller i teckenförklaringen och planens uppgifter. Exemplen är en utgångspunkt att
anpassa efter kommunens grafiska profil, inte mallar som bestämmer hur kommunens plankartor ska se ut.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LAYOUT_DIR = Path(__file__).resolve().parent.parent / "data" / "layouts"
PAPERS = {"A1": (841.0, 594.0), "A2": (594.0, 420.0), "A3": (420.0, 297.0), "A4": (297.0, 210.0)}  # mm, liggande
LANDSCAPE, PORTRAIT = "liggande", "stående"
ORIENTATIONS = (LANDSCAPE, PORTRAIT)
SOURCE_PAPER = "A2"  # mallarna byggs ur en A2-mall; de andra formaten är samma sida i en annan skala
TITLE = "Plankarta"

# Objekten i mallarna har id, så att pluginet hittar dem
MAP_ID = "Kartvy"
LEGEND_ID = "Plats för teckenförklaring"  # en ruta som visar var teckenförklaringen ska ligga (skrivs inte ut)
PAPER_ID = "Pappersformat"  # "(A2)"
STAGE_ID = "Skede"  # "ARBETSHANDLING"
PLAN_TYPE_ID = "Plantyp"  # "Detaljplan för"
NAME_ID = "Plannamn"
KOMMUN_ID = "Kommun"
ADOPTION_ID = "Antagande"
LAGAKRAFT_ID = "Laga kraft"
DATE_PLACEHOLDER = "202x-xx-xx"


@dataclass(frozen=True)
class Box:
    """Ett rektangulärt område på sidan i mm (x och y från sidans övre vänstra hörn)."""
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def scaled(self, factor: float) -> "Box":
        return Box(self.x * factor, self.y * factor, self.width * factor, self.height * factor)


# Kartan och teckenförklaringen på A2 (mm). Den liggande är A2-mallens; den stående ritas om av tools/build_layouts.py.
A2_MAP = {LANDSCAPE: Box(15.354, 13.783, 408.146, 319.651), PORTRAIT: Box(15.354, 13.783, 397.446, 381.517)}
A2_LEGEND = {LANDSCAPE: Box(431.725, 13.783, 155.093, 319.651), PORTRAIT: Box(15.354, 403.3, 234.346, 158.2)}


def formats() -> list[tuple[str, str]]:
    """Alla mallar som (pappersformat, riktning): A1 liggande, A1 stående, A2 liggande … A4 stående."""
    return [(paper, orientation) for paper in PAPERS for orientation in ORIENTATIONS]


def format_label(paper: str, orientation: str) -> str:
    return f"{paper} {orientation}"


def page_size(paper: str, orientation: str) -> tuple[float, float]:
    """(bredd, höjd) i mm."""
    long_side, short_side = PAPERS[paper]
    return (long_side, short_side) if orientation == LANDSCAPE else (short_side, long_side)


def factor(paper: str) -> float:
    """Hur mycket större sidan är än A2 (A1 √2, A3 1/√2 osv.)."""
    return PAPERS[paper][0] / PAPERS[SOURCE_PAPER][0]


def template_path(paper: str, orientation: str) -> Path:
    """Mallen för ett format: ``data/layouts/plankarta-a2-liggande.qpt`` osv."""
    if paper not in PAPERS or orientation not in ORIENTATIONS:
        raise ValueError(f"Det finns ingen mall för {paper} {orientation}.")
    name = "liggande" if orientation == LANDSCAPE else "staende"
    return LAYOUT_DIR / f"plankarta-{paper.lower()}-{name}.qpt"


def map_box(paper: str, orientation: str) -> Box:
    return A2_MAP[orientation].scaled(factor(paper))


def legend_box(paper: str, orientation: str) -> Box:
    return A2_LEGEND[orientation].scaled(factor(paper))


def map_extent(bounds: tuple, box: Box, scale: float) -> tuple:
    """Kartans utsnitt (xmin, ymin, xmax, ymax i meter) när ``box`` (mm på papper) visar planen i skala 1:``scale``,
    med planens utbredning ``bounds`` (xmin, ymin, xmax, ymax) i mitten."""
    xmin, ymin, xmax, ymax = bounds
    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    half_w, half_h = box.width / 1000.0 * scale / 2.0, box.height / 1000.0 * scale / 2.0
    return cx - half_w, cy - half_h, cx + half_w, cy + half_h


def fits(bounds: tuple, box: Box, scale: float) -> bool:
    """Om planen ryms i kartan i skala 1:``scale``."""
    xmin, ymin, xmax, ymax = bounds
    return (xmax - xmin) <= box.width / 1000.0 * scale and (ymax - ymin) <= box.height / 1000.0 * scale


def suggested_format(bounds: tuple, scale: float) -> tuple[str, str]:
    """Det format som föreslås: A2 liggande om planen ryms där i skala 1:``scale``, annars A1 liggande."""
    if fits(bounds, map_box("A2", LANDSCAPE), scale):
        return "A2", LANDSCAPE
    return "A1", LANDSCAPE


STATUS_TEXT = {  # planens status (Lantmäteriets kodlista) -> handlingens skede som det brukar skrivas i titelrutan
    "påbörjad": "ARBETSHANDLING",
    "samråd": "SAMRÅDSHANDLING",
    "granskning": "GRANSKNINGSHANDLING",
    "antagen": "ANTAGANDEHANDLING",
    "överklagad": "ANTAGEN, ÖVERKLAGAD",
    "laga kraft": "LAGA KRAFT",
}


def _value(values: dict, key: str) -> Optional[str]:
    value = values.get(key)
    return str(value).strip() if value not in (None, "") and str(value).strip() else None


def stage(plan: dict) -> str:
    """Handlingens skede ur planens status, t.ex. "SAMRÅDSHANDLING". "ARBETSHANDLING" om status saknas."""
    status = _value(plan, "status")
    return STATUS_TEXT.get((status or "").lower(), status.upper() if status else "ARBETSHANDLING")


def plan_name(plan: dict) -> str:
    """Planens namn utan "Detaljplan för", som står på raden ovanför i titelrutan."""
    name = _value(plan, "namn") or "Detaljplanens namn"
    for prefix in ("detaljplan för ", "detaljplan "):
        if name.lower().startswith(prefix):
            return name[len(prefix):].strip() or name
    return name


def kommun_text(plan: dict) -> str:
    """"i Eskilstuna kommun" – raden under planens namn."""
    kommun = _value(plan, "kommun") or "Kommun"
    if not kommun.lower().endswith("kommun"):
        kommun = f"{kommun} kommun"
    return f"i {kommun}"


def decision_dates(decision: dict) -> tuple[str, str]:
    """(antagande, laga kraft) som datum (ÅÅÅÅ-MM-DD), eller "202x-xx-xx" att fylla i när de saknas."""
    adopted = (_value(decision, "datumAntagande") or "")[:10] or DATE_PLACEHOLDER
    lagakraft = ((_value(decision, "datumLagakraft") or "").split(";")[0].strip())[:10] or DATE_PLACEHOLDER
    return adopted, lagakraft


def layout_name(plan: dict, paper: str, orientation: str, existing: list[str]) -> str:
    """Ett namn på layouten som inte redan finns i projektet: "Plankarta A2 liggande – Kv Väktaren", sedan "… (2)"."""
    base = f"{TITLE} {format_label(paper, orientation)} – {_value(plan, 'namn') or 'detaljplan'}"
    name, number = base, 2
    while name in existing:
        name = f"{base} ({number})"
        number += 1
    return name
