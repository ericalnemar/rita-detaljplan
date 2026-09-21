"""Tilldelade bestämmelser (tabellen ``bestammelse``): en rad per bestämmelse och yta.

En yta kan ha flera bestämmelser (kombinerad användning, flera egenskaper). Beteckningen på plankartan är
sammansatt av ytans bestämmelser: användning skrivs ihop ("B" + "C" = "BC"), egenskaper med mellanrum ("e1 a2").
Indexerade beteckningar ("R#", "e#") numreras per bokstav i hela planen: samma bestämmelse (samma text och
värden) får samma beteckning överallt, en annan får nästa lediga nummer.

Raderna är vanliga dictar med kolumnerna i ``model.BESTAMMELSE``. Modulen är ren Python (inget QGIS).
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from . import bestammelse as bm
from . import catalog as cat

# Attribut som beskriver en bestämmelse (kommer från ``bestammelse.feature_attributes``).
ATTRIBUTE_KEYS = ("planbestammelsekatalogreferens", "bestammelsekod", "anvandningsform", "farg", "symbol",
                  "bestammelseformulering", "avviker", "ursprungligBestammelseformulering", "bestammelsevarde",
                  "motiv")


def label_for(entry: cat.CatalogEntry, index: Optional[int]) -> str:
    """Beteckning på plankartan: "e#" med index 2 blir "e2"; utan "#" används beteckningen som den är."""
    if "#" in entry.beteckning and index is not None:
        return entry.beteckning.replace("#", str(index))
    return entry.beteckning.strip()


def identity(row: dict) -> tuple:
    """Det som gör två bestämmelser till samma bestämmelse i planen (motivet räknas inte)."""
    return (row.get("planbestammelsekatalogreferens"), row.get("bestammelseformulering"),
            row.get("bestammelsevarde") or None)


def _base(label: Optional[str], index: Optional[int]) -> str:
    """Beteckningens bokstav ("R2" med index 2 -> "R")."""
    text = (label or "").strip()
    suffix = str(index) if index is not None else ""
    return text[: -len(suffix)] if suffix and text.endswith(suffix) else text


def next_index(rows: Iterable[dict], entry: cat.CatalogEntry) -> int:
    """Lägsta lediga index bland raderna med samma beteckningsbokstav."""
    used = {row.get("beteckningsindex") for row in rows
            if row.get("beteckningsindex") is not None
            and _base(row.get("beteckning"), row.get("beteckningsindex")) == entry.label_base}
    index = 1
    while index in used:
        index += 1
    return index


def build_row(entry: cat.CatalogEntry, values: list[bm.VariableValue], motiv: Optional[str] = None,
              formulation: Optional[str] = None, existing_rows: Iterable[dict] = ()) -> dict[str, Any]:
    """Skapar en bestämmelserad. ``existing_rows`` = alla rader i planen, för numreringen av beteckningen."""
    if not entry.deliverable:
        raise ValueError(f"{entry.kod or entry.formulering} kan inte användas i en detaljplan (typ {entry.typ}).")
    rows = list(existing_rows)
    attributes = bm.feature_attributes(entry, values, motiv, formulation)
    index: Optional[int] = None
    if "#" in entry.beteckning:
        same = next((r for r in rows if identity(r) == identity(attributes) and r.get("beteckningsindex") is not None),
                    None)
        index = same["beteckningsindex"] if same else next_index(rows, entry)
    return {**attributes, "tabell": entry.layer_name, "beteckning": label_for(entry, index) or None,
            "beteckningsindex": index}


def summarize(rows: Iterable[dict]) -> dict[str, Any]:
    """Det en yta visar utifrån sina bestämmelser: beteckning, färg, symbol och användningsform.

    Saknas bestämmelser är ``bestammelser`` 0 och beteckningen tom (NULL), och ytan ritas som "saknar bestämmelse"."""
    rows = list(rows)
    if not rows:
        return {"beteckning": None, "farg": None, "symbol": None, "anvandningsform": None, "bestammelser": 0}
    labels: list[str] = []
    for row in rows:
        label = (row.get("beteckning") or "").strip()
        if label and label not in labels:
            labels.append(label)
    use = rows[0].get("tabell") == cat.USE_LAYER
    return {
        "beteckning": ("" if use else " ").join(labels),
        "farg": next((r["farg"] for r in rows if r.get("farg")), None),
        "symbol": next((r["symbol"] for r in rows if r.get("symbol")), None),
        "anvandningsform": next((r["anvandningsform"] for r in rows if r.get("anvandningsform")), None),
        "bestammelser": len(rows),
    }


def display_text(row: dict) -> str:
    """Formuleringen med värdena ifyllda, ur en lagrad rad."""
    text = row.get("bestammelseformulering") or ""
    try:
        stored = json.loads(row.get("bestammelsevarde") or "[]")
    except json.JSONDecodeError:
        stored = []
    by_name = {item.get("beskrivning"): item.get("variabelvarde", "") for item in stored if isinstance(item, dict)}
    filled = {var.token: by_name[var.name] for var in cat.parse_variables(text) if var.name in by_name}
    return cat.render(text, filled)


def describe(row: dict) -> str:
    """Kort text till listor: "R1 – Motorsportbana"."""
    label = (row.get("beteckning") or "").strip()
    text = display_text(row)
    return f"{label} – {text}" if label else text
