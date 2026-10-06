"""Utbytesfil mellan programmet och Rita Detaljplan: planens syfte och motiven per bestämmelse, så som de står i
planbeskrivningen. Pluginet kan läsa in filen och lägga motiven på bestämmelserna (samma som knappen *Importera motiv till
plankartan*), utan att planbeskrivningen behöver läsas om. JSON, UTF-8. Ren Python.

Format (version 1)::

    {"format": "planbeskrivning-utbyte", "version": 1, "skapad": "...", "programvara": "...",
     "detaljplan": "<UUID>", "planbeskrivning": "<filnamn>", "syfte": "...",
     "motiv": [{"nyckel": "<Provision.key som text>", "beteckning": "e1", "bestammelse": "...",
                "objekt": ["<UUID>", ...], "motiv": "..."}]}
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import planbeskrivning_docx as dx
from .plankarta import key_text

FORMAT = "planbeskrivning-utbyte"
VERSION = 1


class UtbyteError(ValueError):
    pass


def build(analysis: dx.Analys, plan_identity: str, software: str) -> dict:
    motives = dx.motives_from_document(analysis)
    by_key = {p.key: p for p in analysis.provisions}
    return {
        "format": FORMAT, "version": VERSION, "skapad": datetime.now().astimezone().isoformat(timespec="seconds"),
        "programvara": software, "detaljplan": plan_identity,
        "planbeskrivning": Path(analysis.source).name if analysis.source else "",
        "syfte": dx.purpose_from_document(analysis),
        "motiv": [{"nyckel": key_text(key), "beteckning": by_key[key].label, "bestammelse": by_key[key].text,
                   "objekt": list(by_key[key].refs), "motiv": text}
                  for key, text in motives.items() if key in by_key],
    }


def write(path: str | Path, data: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UtbyteError(f"Filen kunde inte läsas: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise UtbyteError("Filen är ingen utbytesfil för planbeskrivningar.")
    if int(data.get("version") or 0) > VERSION:
        raise UtbyteError(f"Filen är skapad med en nyare version (format {data.get('version')}); uppdatera programmet.")
    return data
