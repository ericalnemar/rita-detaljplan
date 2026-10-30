"""Exempellayout för plankartan (ärende 2): vad som ska stå var på sidan. Ren Python, ingen QGIS.

Exemplet är en utgångspunkt, inte en mall som bestämmer hur kommunens plankartor ska se ut: en A2-sida i liggande format
med kartan till vänster och en kolumn till höger med teckenförklaringen, norrpil och skalstock, och längst ned en
titelruta med planens uppgifter. Sidan byggs i QGIS layoutläge av ``example_sheet_layout``; där kan den anpassas efter
kommunens grafiska profil och sparas som mall.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

PAPER = "A2"
PAGE_WIDTH, PAGE_HEIGHT = 594.0, 420.0  # mm, liggande
MARGIN = 10.0  # mm runt sidan
COLUMN = 150.0  # mm: kolumnen till höger (teckenförklaring, norrpil, skalstock och titelruta)
GAP = 8.0  # mm mellan kartan och kolumnen
LEGEND_HEIGHT = 228.0  # mm överst i kolumnen
SCALE_ROW_HEIGHT = 30.0  # mm: norrpil och skalstock under teckenförklaringen
BLANK = "_______________"  # att fylla i för hand
NICE_STEPS = (1, 2, 2.5, 5)  # skalstockens delar: 1, 2, 2,5 eller 5 gånger en tiopotens
TITLE = "Plankarta"


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


@dataclass(frozen=True)
class Sheet:
    """Var allt ligger på sidan."""
    map: Box
    legend: Box
    scale_row: Box
    title_block: Box


def sheet() -> Sheet:
    """Sidans indelning: kartan till vänster, kolumnen till höger (teckenförklaring, norrpil och skalstock, titelruta)."""
    column_x = PAGE_WIDTH - MARGIN - COLUMN
    inner_height = PAGE_HEIGHT - 2 * MARGIN
    map_box = Box(MARGIN, MARGIN, column_x - GAP - MARGIN, inner_height)
    legend = Box(column_x, MARGIN, COLUMN, LEGEND_HEIGHT)
    scale_row = Box(column_x, legend.bottom + 4.0, COLUMN, SCALE_ROW_HEIGHT)
    title_top = scale_row.bottom + 4.0
    title_block = Box(column_x, title_top, COLUMN, PAGE_HEIGHT - MARGIN - title_top)
    return Sheet(map_box, legend, scale_row, title_block)


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


def segment_length(scale: float, target_mm: float = 20.0) -> float:
    """Längden i meter på en del av skalstocken: ett jämnt tal (1, 2, 2,5 eller 5 gånger en tiopotens) som blir ungefär
    ``target_mm`` på papperet. 1:1000 ger 20 m, 1:400 ger 10 m och 1:2000 ger 50 m."""
    wanted = target_mm / 1000.0 * scale
    power = 1.0
    while power * 10 <= wanted:
        power *= 10
    while power > wanted:
        power /= 10
    candidates = [step * power for step in NICE_STEPS] + [10 * power]
    return min(candidates, key=lambda value: abs(value - wanted))


def scale_text(scale: float) -> str:
    """"Skala 1:1000 (A2)" – skalan gäller bara när sidan skrivs ut i rätt storlek."""
    return f"Skala 1:{int(round(scale)):,} ({PAPER})".replace(",", " ")


STATUS_TEXT = {  # planens status (Lantmäteriets kodlista) -> handlingens skede som det brukar skrivas i titelrutan
    "påbörjad": "Plankarta under arbete",
    "samråd": "Samrådshandling",
    "granskning": "Granskningshandling",
    "antagen": "Antagandehandling",
    "överklagad": "Antagen, överklagad",
    "laga kraft": "Laga kraft",
}


def _value(values: dict, key: str) -> Optional[str]:
    value = values.get(key)
    return str(value).strip() if value not in (None, "") and str(value).strip() else None


def title_rows(plan: dict, decision: dict, today: Optional[date] = None) -> list[tuple[str, str]]:
    """Raderna i titelrutans nedre del: (rubrik, värde). Det som saknas i planens uppgifter blir en linje att fylla i."""
    today = today or date.today()
    lagakraft = (_value(decision, "datumLagakraft") or "").split(";")[0].strip() or None
    rows = [
        ("Planbeteckning", _value(plan, "beteckning") or BLANK),
        ("Diarienummer", _value(decision, "diarienummerKommun") or BLANK),
        ("Upprättad", today.isoformat()),
        ("Handläggare", BLANK),
        ("Antagen", (_value(decision, "datumAntagande") or "")[:10] or BLANK),
        ("Laga kraft", (lagakraft or "")[:10] or BLANK),
    ]
    return rows


def heading(plan: dict) -> tuple[str, str, str]:
    """Titelrutans överdel: (kommun, planens namn, skede)."""
    kommun = _value(plan, "kommun") or "Kommun"
    if not kommun.lower().endswith("kommun"):
        kommun = f"{kommun} kommun"
    name = _value(plan, "namn") or "Detaljplanens namn"
    status = _value(plan, "status")
    stage = STATUS_TEXT.get((status or "").lower(), status.capitalize() if status else "Handling")
    return kommun, f"Detaljplan för {name}" if not name.lower().startswith("detaljplan") else name, stage


BASE_MAP_NOTE = "Grundkarta: ange vem som upprättat grundkartan, när och i vilket koordinat- och höjdsystem."
FOOTER = "Exempellayout från Rita Detaljplan. Anpassa den efter kommunens grafiska profil och spara den som mall."


def layout_name(plan: dict, existing: list[str]) -> str:
    """Ett namn på layouten som inte redan finns i projektet: "Plankarta – Kv Väktaren", sedan "… (2)" osv."""
    base = f"{TITLE} – {_value(plan, 'namn') or 'detaljplan'}"
    name, number = base, 2
    while name in existing:
        name = f"{base} ({number})"
        number += 1
    return name
