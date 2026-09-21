"""Vad som krävs av planen för att den ska kunna levereras till NGP (det som pluginet kan kontrollera hittills).

Att spara är aldrig blockerat: man kan arbeta med en ofärdig plan. Kraven visas i dialogen "Planens uppgifter" och
när man avslutar redigeringen, så att det är tydligt vad som återstår före leverans. Ren Python (inget QGIS).

Källa: Nationell informationsspecifikation Detaljplan 4.1, kap. 4.1: för en detaljplan ska alltid finnas
objektidentitet, version, kommun, namn, syfte, status, typ och plangeometri; hela planområdet ska ha en
användningsbestämmelse (DP-0002); varje bestämmelse ska ha bestämmelseformulering och geometri.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import kommuner

# (fält i detaljplan-lagret, visningsnamn) – alltid obligatoriska enligt specifikationen
REQUIRED_PLAN_FIELDS = (
    ("kommun", "Kommun"),
    ("namn", "Namn"),
    ("syfte", "Syfte"),
    ("status", "Status"),
    ("typ", "Plantyp"),
)
COVERAGE_OK = 0.999  # andel av planområdet som ska ha en användning


@dataclass(frozen=True)
class Requirement:
    key: str
    text: str
    ok: bool
    field: Optional[str] = None  # fält i planens uppgifter som löser kravet, om det finns ett


def plan_requirements(values: dict, *, has_plan_area: bool, uses: int, coverage: float,
                      unassigned: int, implementation_months: Optional[int] = None) -> list[Requirement]:
    """Kraven i den ordning man brukar uppfylla dem."""
    reqs = [Requirement("planomrade", "Planområdet är ritat", has_plan_area)]
    for key, label in REQUIRED_PLAN_FIELDS:
        value = (values.get(key) or "").strip() if isinstance(values.get(key), str) else values.get(key)
        ok = bool(value)
        text = f"{label} är angivet"
        if key == "kommun" and ok and kommuner.by_name(value) is None:
            ok, text = False, f"Kommun måste vara en av Sveriges kommuner ({value!r} finns inte)"
        reqs.append(Requirement(key, text, ok, key))
    reqs.append(Requirement("genomforandetid", "Genomförandetid är angiven (varje detaljplan ska ha en)",
                            bool(implementation_months and implementation_months > 0), "genomforandetid"))
    reqs.append(Requirement(
        "anvandning",
        "Användning täcker hela planområdet" + ("" if not uses else f" (nu {coverage:.0%})"),
        has_plan_area and uses > 0 and coverage >= COVERAGE_OK))
    reqs.append(Requirement(
        "bestammelser",
        "Alla ytor har bestämmelse" + (f" ({unassigned} saknar)" if unassigned else ""),
        has_plan_area and unassigned == 0 and uses > 0))
    return reqs


def missing(requirements: list[Requirement]) -> list[Requirement]:
    return [req for req in requirements if not req.ok]
