"""Plankartans teckenförklaring: en vanlig förklaring i en kolumn, byggd av planens bestämmelser (ingen innehållsförteckning).

Uppbyggnad, efter plankartor enligt Boverkets föreskrifter (BFS 2020:5):

    PLANBESTÄMMELSER  + inledande text
    GRÄNSLINJER                          planområdesgräns, användningsgräns, egenskapsgräns
    ANVÄNDNING AV ALLMÄN PLATS           färgruta med beteckning (GATA, PARK …) och text
    ANVÄNDNING AV KVARTERSMARK           (samma för kvartersmark och vattenområde)
    EGENSKAPSBESTÄMMELSER FÖR KVARTERSMARK / ALLMÄN PLATS / VATTENOMRÅDE
        Kategori                         underrubrik ur Boverkets katalog
        mönster eller beteckning (u₁)    text
    GENOMFÖRANDETID

Modulen bygger bara innehållet (``build``); att rita det i en layout görs i ``plankarta``. Rena Python, ingen QGIS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import catalog as cat
from . import rows as rows_module
from . import symbology

SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉"
INTRO = ("Följande gäller inom områden med nedanstående beteckningar. Endast angiven användning och utformning är "
         "tillåten. Där beteckning saknas gäller bestämmelserna inom all kvartersmark eller all allmän plats eller allt "
         "vattenområde på plankartan.")
FORMS = ("Allmän plats", "Kvartersmark", "Vattenområde")
USE_TITLES = {"Allmän plats": "ANVÄNDNING AV ALLMÄN PLATS", "Kvartersmark": "ANVÄNDNING AV KVARTERSMARK",
              "Vattenområde": "ANVÄNDNING AV VATTENOMRÅDE"}
PROPERTY_TITLES = {"Allmän plats": "EGENSKAPSBESTÄMMELSER FÖR ALLMÄN PLATS",
                   "Kvartersmark": "EGENSKAPSBESTÄMMELSER FÖR KVARTERSMARK",
                   "Vattenområde": "EGENSKAPSBESTÄMMELSER FÖR VATTENOMRÅDE"}
GENERAL_TITLE = "EGENSKAPSBESTÄMMELSER FÖR PLANOMRÅDET"
LINE_SYMBOLS = symbology.LINE_SYMBOLS + symbology.OUTLINE_SYMBOLS  # visas som en linje i förklaringen
FILL, PATTERN, LINE, NONE = "fill", "pattern", "line", "none"


def subscript(text: str) -> str:
    """Siffror som nedsänkta tecken: "R1" -> "R₁" (som beteckningarna på kartan)."""
    return "".join(SUBSCRIPT_DIGITS[int(c)] if c.isdigit() else c for c in text or "")


@dataclass(frozen=True)
class Entry:
    """En rad i teckenförklaringen: ruta eller linje med en beteckning och en text."""
    code: str  # beteckning med nedsänkta siffror ("R₁"), eller tom
    text: str
    swatch: str  # FILL | PATTERN | LINE | NONE
    color: Optional[tuple] = None  # RGB för FILL
    symbol: Optional[str] = None  # stilbibliotekets symbol för PATTERN och LINE


@dataclass
class Group:
    heading: Optional[str]  # kursiv underrubrik, eller None
    entries: list = field(default_factory=list)


@dataclass
class Section:
    title: str  # VERSALER
    groups: list = field(default_factory=list)
    note: str = ""  # löpande text under rubriken (t.ex. genomförandetiden)

    @property
    def entries(self) -> list:
        return [entry for group in self.groups for entry in group.entries]


def _order(code: str) -> tuple:
    match = re.match(r"^(\D*)(\d*)$", (code or "").strip())
    letters, number = (match.group(1), int(match.group(2) or 0)) if match else (code or "", 0)
    return letters.lower(), number


def _distinct(rows: list[dict]) -> list[dict]:
    """En rad per bestämmelse i planen (samma bestämmelse på flera ytor visas en gång)."""
    seen, result = set(), []
    for row in rows:
        key = rows_module.identity(row)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def boundary_section(has_uses: bool = True, has_properties: bool = False, has_secondary: bool = False) -> Section:
    """GRÄNSLINJER: de linjer som förekommer på kartan."""
    entries = [Entry("", "Planområdesgräns", LINE, symbol="Planområdesgräns")]
    if has_uses:
        entries.append(Entry("", "Användningsgräns", LINE, symbol="Användningsgräns"))
    if has_properties:
        entries.append(Entry("", "Egenskapsgräns", LINE, symbol="Egenskapsgräns"))
    if has_secondary:
        entries.append(Entry("", "Sekundär egenskapsgräns", LINE, symbol="Sekundär egenskapsgräns"))
    return Section("GRÄNSLINJER", [Group(None, entries)])


def use_sections(rows: list[dict]) -> list[Section]:
    sections = []
    uses = _distinct([r for r in rows if r.get("tabell") == cat.USE_LAYER])
    for form in FORMS:
        wanted = sorted((r for r in uses if r.get("anvandningsform") == form),
                        key=lambda r: (_order(r.get("beteckning")), rows_module.display_text(r)))
        if not wanted:
            continue
        entries = [Entry(subscript(r.get("beteckning") or ""), rows_module.display_text(r), FILL,
                         symbology.FARGER.get(r.get("farg") or "", symbology.FALLBACK_FARG)) for r in wanted]
        sections.append(Section(USE_TITLES[form], [Group(None, entries)]))
    return sections


def _swatch(row: dict) -> tuple[str, Optional[str]]:
    name = symbology.SYMBOL_ALIAS.get(row.get("symbol") or "", row.get("symbol") or "")
    if not name:
        return NONE, None
    if name in symbology.AREA_SYMBOLS or row.get("symbol") in symbology.AREA_SYMBOLS:
        return PATTERN, name
    if name in LINE_SYMBOLS:
        return LINE, name
    return NONE, None


def property_sections(rows: list[dict], catalog: Optional[cat.Catalog] = None) -> list[Section]:
    sections = []
    properties = _distinct([r for r in rows if r.get("tabell") in cat.PROPERTY_LAYERS])
    for form in (*FORMS, None):
        if form is None:
            wanted = [r for r in properties if r.get("anvandningsform") not in FORMS]
            title = GENERAL_TITLE
        else:
            wanted = [r for r in properties if r.get("anvandningsform") == form]
            title = PROPERTY_TITLES[form]
        if not wanted:
            continue
        by_category: dict[str, list] = {}
        for row in wanted:
            entry = catalog.get(row.get("planbestammelsekatalogreferens")) if catalog is not None else None
            by_category.setdefault((entry.kategori if entry else "") or "", []).append(row)
        groups = []
        for category in sorted(by_category, key=lambda c: (c == "", c.lower())):
            items = sorted(by_category[category],
                           key=lambda r: (_swatch(r)[0] == NONE, _order(r.get("beteckning")), rows_module.display_text(r)))
            entries = []
            for row in items:
                kind, symbol = _swatch(row)
                entries.append(Entry(subscript(row.get("beteckning") or ""), rows_module.display_text(row), kind,
                                     symbol=symbol))
            groups.append(Group(category or None, entries))
        sections.append(Section(title, groups))
    return sections


def implementation_section(decision: dict) -> Optional[Section]:
    """GENOMFÖRANDETID ur beslutsinformationen (månader → år när det går jämnt upp)."""
    months = decision.get("genomforandetid")
    try:
        months = int(months)
    except (TypeError, ValueError):
        return None
    if months <= 0:
        return None
    length = f"{months // 12} år" if months % 12 == 0 else f"{months} månader"
    start = str(decision.get("genomforandetidStartar") or "")[:10]
    begins = f"fr.o.m. {start}" if start else "fr.o.m. laga kraft datum"
    return Section("GENOMFÖRANDETID", note=f"Genomförandetiden är {length} över hela planområdet och börjar gälla {begins}.")


def build(rows: list[dict], catalog: Optional[cat.Catalog] = None, decision: Optional[dict] = None,
          has_properties: Optional[bool] = None) -> list[Section]:
    """Hela teckenförklaringen (utan rubriken PLANBESTÄMMELSER och den inledande texten, som layouten lägger till)."""
    properties = [r for r in rows if r.get("tabell") in cat.PROPERTY_LAYERS]
    secondary = any(r.get("sekundarEgenskapsgrans") for r in properties)
    sections = [boundary_section(True, bool(properties) if has_properties is None else has_properties, secondary)]
    sections += use_sections(rows)
    sections += property_sections(rows, catalog)
    genomforande = implementation_section(decision or {})
    if genomforande is not None:
        sections.append(genomforande)
    return sections
