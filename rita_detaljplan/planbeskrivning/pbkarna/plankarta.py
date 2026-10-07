"""Planens bestämmelser, lästa direkt ur filerna som Rita Detaljplan skapar, utan QGIS.

En plan ligger i en GeoPackage (en SQLite-databas). Tabellen ``detaljplan`` har planen och tabellen ``bestammelse`` en rad
per bestämmelse och yta. Samma bestämmelse på flera ytor blir *en* ``Provision`` med alla ytornas identiteter i ``refs``,
precis som ``PlanController.provision_targets`` i pluginet. Ett QGIS-projekt (.qgz/.qgs) pekar ut sina GeoPackage-filer.
Ren Python, ingen QGIS behövs.
"""
from __future__ import annotations

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from .geometri import read_only_uri
from .planbeskrivning_docx import Provision

PLAN_TABLE = "detaljplan"
ROWS_TABLE = "bestammelse"
TECHNICAL_FORMULATION = "Tekniska anläggningar"  # fast motiv, se catalog.TECHNICAL_FORMULATION i pluginet
_KIND_ORDER = {"anvandning_yta": 0, "egenskap_yta": 1, "egenskap_linje": 2}
KIND_NAMES = {"anvandning_yta": "Användning", "egenskap_yta": "Egenskap", "egenskap_linje": "Egenskap (linje)"}

# Variabler i formuleringar skrivs [namn:datatyp], t.ex. [höjd:decimaltal] (samma som catalog.py i pluginet).
_VARIABLE_RE = re.compile(r"\[([^\]:]+):(text|decimaltal)\]")


class PlankartaError(ValueError):
    """Plankartan gick inte att läsa; texten förklarar varför."""


@dataclass
class Plan:
    """En detaljplan med sina bestämmelser."""
    identitet: str  # detaljplanens objektidentitet (UUID)
    namn: str
    beteckning: str
    kalla: Optional[Path]  # GeoPackage-filen; None när planen kommer direkt från QGIS
    provisions: list = field(default_factory=list)  # Provision, användningar först
    kinds: dict = field(default_factory=dict)  # Provision.key -> ytlager (anvandning_yta, egenskap_yta …)
    areas: dict = field(default_factory=dict)  # Provision.key -> ytornas identiteter (UUID)
    syfte: str = ""
    motiv: dict = field(default_factory=dict)  # Provision.key -> motivet som står på bestämmelsen i plankartan

    @property
    def rubrik(self) -> str:
        return " · ".join(p for p in (self.namn, self.beteckning) if p) or self.identitet


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def display_text(row: dict) -> str:
    """Formuleringen med värdena ifyllda (som ``rows.display_text`` i pluginet)."""
    text = row.get("bestammelseformulering") or ""
    try:
        stored = json.loads(row.get("bestammelsevarde") or "[]")
    except (json.JSONDecodeError, TypeError):
        stored = []
    by_name = {item.get("beskrivning"): item.get("variabelvarde", "") for item in stored if isinstance(item, dict)}

    def fill(match):
        value = by_name.get(match.group(1))
        return str(value) if value not in (None, "") else match.group(0)

    return _VARIABLE_RE.sub(fill, text)


def identity(row: dict) -> tuple:
    """Det som gör två rader till samma bestämmelse i planen (som ``rows.identity`` i pluginet)."""
    return (row.get("planbestammelsekatalogreferens"), row.get("bestammelseformulering"),
            row.get("bestammelsevarde") or None)


def _rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    cursor = connection.execute(f'SELECT * FROM "{table}"')
    names = [d[0] for d in cursor.description]
    return [{n: _clean(v) for n, v in zip(names, values)} for values in cursor.fetchall()]


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}


def read_geopackage(path: str | Path) -> list[Plan]:
    """Planerna i en GeoPackage från Rita Detaljplan (oftast en). Kastar ``PlankartaError`` om filen inte är en sådan."""
    path = Path(path)
    if not path.is_file():
        raise PlankartaError(f"Filen finns inte: {path}")
    try:
        connection = sqlite3.connect(read_only_uri(path), uri=True)
    except sqlite3.Error as exc:
        raise PlankartaError(f"Kunde inte öppna {path.name}: {exc}") from exc
    try:
        tables = _tables(connection)
        if PLAN_TABLE not in tables or ROWS_TABLE not in tables:
            raise PlankartaError(f"{path.name} är ingen plan från Rita Detaljplan (tabellerna {PLAN_TABLE} och "
                                 f"{ROWS_TABLE} saknas).")
        plan_rows = _rows(connection, PLAN_TABLE)
        rows = _rows(connection, ROWS_TABLE)
    except sqlite3.DatabaseError as exc:
        raise PlankartaError(f"{path.name} är ingen GeoPackage: {exc}") from exc
    finally:
        connection.close()

    plans = {}
    for row in plan_rows:
        ident = row.get("objektidentitet")
        if ident and ident not in plans:
            plans[ident] = Plan(ident, row.get("namn") or "", row.get("beteckning") or "", path,
                                syfte=row.get("syfte") or "")
    rows.sort(key=lambda r: (r.get("ordning") or 0, r.get("fid") or 0))
    for row in rows:
        if not row.get("objektidentitet"):
            continue
        plan_id = row.get("detaljplan")
        plan = plans.get(plan_id) if plan_id else (next(iter(plans.values())) if len(plans) == 1 else None)
        if plan is None:
            continue
        key = identity(row)
        provision = next((p for p in plan.provisions if p.key == key), None)
        if provision is None:
            provision = Provision(key, row.get("beteckning") or "", display_text(row), (),
                                  row.get("bestammelseformulering") == TECHNICAL_FORMULATION)
            plan.provisions.append(provision)
            plan.kinds[key] = row.get("tabell") or ""
            plan.areas[key] = []
        provision.refs = provision.refs + (row["objektidentitet"],)
        if row.get("yta"):
            plan.areas[key].append(row["yta"])
        if row.get("motiv") and not plan.motiv.get(key):
            plan.motiv[key] = row["motiv"]
    for plan in plans.values():
        plan.provisions.sort(key=lambda p: (_KIND_ORDER.get(plan.kinds.get(p.key), 9), p.label.lower(), p.text.lower()))
    return list(plans.values())


def _project_xml(path: Path) -> str:
    if path.suffix.lower() == ".qgz":
        try:
            with zipfile.ZipFile(path) as archive:
                name = next((n for n in archive.namelist() if n.lower().endswith(".qgs")), None)
                if name is None:
                    raise PlankartaError(f"{path.name} innehåller inget QGIS-projekt (.qgs).")
                return archive.read(name).decode("utf-8")
        except zipfile.BadZipFile as exc:
            raise PlankartaError(f"{path.name} är ingen giltig .qgz-fil.") from exc
    return path.read_text(encoding="utf-8")


def geopackages_in_project(path: str | Path) -> list[Path]:
    """GeoPackage-filerna som projektets bestämmelselager ligger i, i projektets ordning. Kastar ``PlankartaError`` om
    projektet inte har några, och förklarar om planen ligger i PostGIS (stöds inte än)."""
    path = Path(path)
    if not path.is_file():
        raise PlankartaError(f"Filen finns inte: {path}")
    try:
        root = ET.fromstring(_project_xml(path))
    except ET.ParseError as exc:
        raise PlankartaError(f"{path.name} går inte att läsa som QGIS-projekt: {exc}") from exc
    found, postgis = [], False
    for layer in root.iter("maplayer"):
        source = (layer.findtext("datasource") or "").strip()
        provider = (layer.findtext("provider") or "").strip()
        if not re.search(rf"(layername|table)=(\"?\w+\"?\.)?\"?{ROWS_TABLE}\b", source):
            continue
        if provider == "postgres":
            postgis = True
            continue
        file_part = unquote(source.split("|", 1)[0])
        candidate = Path(file_part)
        if not candidate.is_absolute():
            candidate = (path.parent / candidate).resolve()
        if candidate not in found:
            found.append(candidate)
    if not found:
        if postgis:
            raise PlankartaError("Planen i projektet ligger i PostGIS. Det stöds inte än: välj planens GeoPackage-fil i "
                                 "stället, eller exportera planen från Rita Detaljplan.")
        raise PlankartaError(f"Projektet {path.name} har inget lager med planbestämmelser från Rita Detaljplan.")
    return found


def read_plankarta(path: str | Path) -> list[Plan]:
    """Planerna i en GeoPackage (.gpkg) eller i ett QGIS-projekt (.qgz/.qgs) med planer från Rita Detaljplan."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".gpkg":
        return read_geopackage(path)
    if suffix in (".qgz", ".qgs"):
        plans: list[Plan] = []
        missing = []
        for gpkg in geopackages_in_project(path):
            if not gpkg.is_file():
                missing.append(gpkg)
                continue
            plans += [p for p in read_geopackage(gpkg) if all(p.identitet != q.identitet for q in plans)]
        if not plans and missing:
            raise PlankartaError("Projektets GeoPackage-fil hittades inte: " + ", ".join(str(m) for m in missing))
        return plans
    raise PlankartaError("Välj ett QGIS-projekt (.qgz, .qgs) eller en GeoPackage (.gpkg).")


def key_text(key) -> str:
    """En bestämmelses nyckel som text (för att spara i JSON), samma som i pluginet."""
    return key if isinstance(key, str) else json.dumps(list(key), ensure_ascii=False)


def find_provision(plan: Optional[Plan], text: str) -> Optional[Provision]:
    if plan is None:
        return None
    return next((p for p in plan.provisions if key_text(p.key) == text), None)
