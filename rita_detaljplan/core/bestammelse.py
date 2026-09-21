"""Från ett val i planbestämmelsekatalogen till attribut i planbestämmelse-lagren.

Reglerna kommer från Lantmäteriets Vägledning till Nationell informationsspecifikation Detaljplan:
  * Formuleringen ska vara katalogens exakta text; variablerna anges separat som bestämmelsevärde i
    samma ordning som i formuleringen (DP-0022, stoppar leverans).
  * Decimaltal ska ha värdetyp (min/max/exakt) och enhet (DP-0009, stoppar leverans).
  * Endast variabeln [text:text] är frivillig; utgår den ur formuleringen anges inget värde för den.
  * Tekniska anläggningar: både formulering och motiv ska vara exakt "Tekniska anläggningar"
    (DP-0019/0020/0021).
Modulen är ren Python (inget QGIS).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from . import catalog as cat
from . import codelists as cl


@dataclass(frozen=True)
class VariableValue:
    variable: cat.Variable
    value: str = ""
    vardetyp: Optional[str] = None  # endast decimaltal: min | max | exakt
    enhet: Optional[str] = None  # endast decimaltal


def normalize_decimal(text: str) -> Optional[str]:
    """'12,5' -> '12.5'. Returnerar None om texten inte är ett tal."""
    cleaned = (text or "").strip().replace(",", ".").replace(" ", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        return None
    number = float(cleaned)
    return str(int(number)) if number == int(number) and "." not in cleaned else cleaned


def default_values(entry: cat.CatalogEntry) -> list[VariableValue]:
    """Tomma värden med värdetyp och enhet förifyllda så gott det går."""
    vtype = cat.value_type(entry.uttryckt_varde)
    values = []
    for variable in entry.variables:
        if variable.datatype == "decimaltal":
            values.append(VariableValue(variable, "", vtype, cat.guess_unit(entry.formulering, variable)))
        else:
            values.append(VariableValue(variable))
    return values


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    remaining = iter(haystack)
    return all(token in remaining for token in needle)


def formulation_problems(entry: cat.CatalogEntry, formulation: str) -> list[str]:
    """Kontrollerar en anpassad formulering: variablerna ska vara kvar, i samma ordning (DP-0022)."""
    if not formulation.strip():
        return ["Formuleringen får inte vara tom."]
    tokens = [v.token for v in cat.parse_variables(formulation)]
    if not _is_subsequence(tokens, [v.token for v in entry.variables]):
        return ["Variablerna i formuleringen ([namn:typ]) måste vara desamma som i katalogen och stå i samma ordning."]
    return []


def check(entry: cat.CatalogEntry, values: list[VariableValue], formulation: str | None = None) -> list[str]:
    """Returnerar en lista med felmeddelanden (tom lista = giltigt)."""
    problems: list[str] = []
    if not entry.deliverable:
        problems.append(f"{entry.kod or entry.formulering} kan inte levereras till NGP (typ {entry.typ}).")
    if len(values) != len(entry.variables):
        problems.append(f"Bestämmelsen har {len(entry.variables)} variabler men {len(values)} värden angavs.")
        return problems
    if formulation is not None:
        problems += formulation_problems(entry, formulation)
        values = effective_values(entry, values, formulation)
    for item in values:
        name = item.variable.name
        if not item.value.strip():
            if not item.variable.optional:
                problems.append(f"Värde saknas för [{name}].")
            continue
        if item.variable.datatype == "decimaltal":
            if normalize_decimal(item.value) is None:
                problems.append(f"[{name}] måste vara ett tal (var {item.value!r}).")
            if item.vardetyp not in cl.VARDETYP:
                problems.append(f"Värdetyp (min/max/exakt) saknas för [{name}].")
            if item.enhet not in cl.ENHET:
                problems.append(f"Enhet saknas för [{name}].")
    return problems


def effective_values(entry: cat.CatalogEntry, values: list[VariableValue], formulation: str | None) -> list[VariableValue]:
    """Värden som hör till variabler som finns kvar i en anpassad formulering (annars alla värden)."""
    if formulation is None:
        return list(values)
    remaining = [v.token for v in cat.parse_variables(formulation)]
    kept = []
    for item in values:
        if item.variable.token in remaining:
            remaining.remove(item.variable.token)
            kept.append(item)
    return kept


def deviates(entry: cat.CatalogEntry, values: list[VariableValue], formulation: str | None) -> bool:
    """Sant om formuleringen avviker från katalogens (NGP varnar då, DP-Krav-0017)."""
    return formulation is not None and formulation.strip() != delivered_formulation(entry, values)


def delivered_formulation(entry: cat.CatalogEntry, values: list[VariableValue], formulation: str | None = None) -> str:
    """Formuleringen som levereras: anpassad text, eller katalogtexten utan frivilliga variabler som lämnats tomma."""
    if formulation is not None:
        return formulation.strip()
    text = entry.formulering
    for item in values:
        if item.variable.optional and not item.value.strip():
            text = text.replace(item.variable.token, "", 1)
    if text != entry.formulering:
        text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return text


def display_text(entry: cat.CatalogEntry, values: list[VariableValue], formulation: str | None = None) -> str:
    """Läsbar text med värdena ifyllda, t.ex. till plankartans teckenförklaring."""
    filled = {}
    for item in effective_values(entry, values, formulation):
        if item.value.strip():
            shown = normalize_decimal(item.value) if item.variable.datatype == "decimaltal" else item.value.strip()
            filled[item.variable.token] = shown or item.value
    return cat.render(delivered_formulation(entry, values, formulation), filled)


def bestammelsevarde(entry: cat.CatalogEntry, values: list[VariableValue],
                     formulation: str | None = None) -> list[dict[str, str]]:
    """Listan `bestammelsevarde` enligt JSON-schemat (`variabelvarde`), i formuleringens ordning."""
    out = []
    for item in effective_values(entry, values, formulation):
        if not item.value.strip():
            continue
        if item.variable.datatype == "decimaltal":
            out.append({"datatyp": "decimaltal", "variabelvarde": normalize_decimal(item.value) or item.value,
                        "beskrivning": item.variable.name, "vardetyp": item.vardetyp, "enhet": item.enhet})
        else:
            out.append({"datatyp": "text", "variabelvarde": item.value.strip(), "beskrivning": item.variable.name})
    return out


def feature_attributes(entry: cat.CatalogEntry, values: list[VariableValue], motiv: str | None = None,
                       formulation: str | None = None) -> dict[str, Any]:
    """Attribut som beskriver bestämmelsen (används både för paletten och för objekten som ritas med den).

    Lagret avgör typen (användning/egenskap); den skrivs därför inte som attribut.
    """
    problems = check(entry, values, formulation)
    if problems:
        raise ValueError("; ".join(problems))
    varde = bestammelsevarde(entry, values, formulation)
    attributes: dict[str, Any] = {
        "planbestammelsekatalogreferens": entry.id,
        "bestammelsekod": entry.kod or None,
        "anvandningsform": entry.anvandningsform or None,
        "farg": entry.farg or None,
        "symbol": entry.symbol or None,
        "bestammelseformulering": delivered_formulation(entry, values, formulation),
        "avviker": deviates(entry, values, formulation),
        # katalogens text levereras tillsammans med den anpassade (DP-Krav-0017)
        "ursprungligBestammelseformulering": (delivered_formulation(entry, values)
                                              if deviates(entry, values, formulation) else None),
        "bestammelsevarde": json.dumps(varde, ensure_ascii=False) if varde else None,
    }
    if entry.is_technical:
        attributes["motiv"] = cat.TECHNICAL_FORMULATION
    elif motiv is not None:
        attributes["motiv"] = motiv.strip() or None
    return attributes


def values_from_attributes(entry: cat.CatalogEntry, bestammelsevarde_json: str | None) -> list[VariableValue]:
    """Återskapar värden ur lagrad JSON (för att kunna ändra en befintlig bestämmelse)."""
    values = default_values(entry)
    if not bestammelsevarde_json:
        return values
    try:
        stored = json.loads(bestammelsevarde_json)
    except json.JSONDecodeError:
        return values
    by_name = {item.get("beskrivning"): item for item in stored if isinstance(item, dict)}
    restored = []
    for item in values:
        found = by_name.get(item.variable.name)
        if found:
            restored.append(VariableValue(item.variable, str(found.get("variabelvarde", "")),
                                          found.get("vardetyp") or item.vardetyp, found.get("enhet") or item.enhet))
        else:
            restored.append(item)
    return restored
