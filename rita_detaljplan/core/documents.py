"""Handlingar (planbeskrivning, beslutshandlingar, planeringsunderlag) och vad specifikationen kräver av dem. Ren Python.

En beslutshandling har ett innehåll som är en lista (Beslutshandling.innehåll [1..*] i Nationell informationsspecifikation
Detaljplan 4.1): plankarta, beslutsprotokoll och/eller övrigt (t.ex. laga kraftbevis). Handlingarna kan levereras var för sig
eller ihop, så ett protokoll som också innehåller plankartan har båda värdena. Lagras som text med semikolon mellan
värdena. Krav vid laga kraft: planbeskrivning (DP-0005) och minst en beslutshandling som innehåller plankarta (DP-0014,
DP-0017)."""
from __future__ import annotations

from typing import Iterable, Optional

from . import codelists as cl


def contents(value) -> list[str]:
    """Innehållsvärdena ur en lagrad text (``"plankarta; beslutsprotokoll"``) eller lista, i kodlistans ordning."""
    if value is None:
        return []
    parts = value if isinstance(value, (list, tuple)) else str(value).split(";")
    wanted = {str(part).strip() for part in parts}
    return [name for name in cl.INNEHALL if name in wanted]


def join(values: Iterable[str]) -> Optional[str]:
    found = contents(list(values))
    return "; ".join(found) or None


def _of_role(documents, role: str) -> list[dict]:
    return [d for d in documents or [] if d.get("roll") == role]


def has_description(documents) -> bool:
    return bool(_of_role(documents, "planbeskrivning"))


def has_decision_document(documents) -> bool:
    return bool(_of_role(documents, "beslutshandling"))


def has_plan_map(documents) -> bool:
    """Minst en beslutshandling som innehåller plankartan."""
    return any("plankarta" in contents(d.get("innehall")) for d in _of_role(documents, "beslutshandling"))


def missing(documents, laga_kraft: bool) -> list[str]:
    """Handlingar som saknas: planbeskrivning och beslutshandling (vid laga kraft en som innehåller plankartan)."""
    found = []
    if not has_description(documents):
        found.append("planbeskrivning")
    if laga_kraft:
        if not has_plan_map(documents):
            found.append("beslutshandling med plankartan")
    elif not has_decision_document(documents):
        found.append("beslutshandling (t.ex. plankartan)")
    return found
