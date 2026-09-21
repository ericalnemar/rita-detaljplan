"""Boverkets planbestämmelsekatalog: datamodell, tolkning av API-svar, sökning och rendering.

Källa: Boverket, Planbestämmelsekatalogen (öppna data, API v2, https://api.boverket.se/planbestammelsekatalogen).
Katalogen får användas fritt med källhänvisning till Boverket. Modulen är ren Python (inget QGIS).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Iterable, Optional

API_BASE = "https://api.boverket.se/planbestammelsekatalogen"
ATTRIBUTION = "Källa: Boverket, Planbestämmelsekatalogen"

# Variabler i formuleringar skrivs [namn:datatyp], t.ex. [höjd:decimaltal]. Se Boverkets fältbeskrivningar.
_VARIABLE_RE = re.compile(r"\[([^\]:]+):(text|decimaltal)\]")

# (bestämmelsetyp, geometrityp) i katalogen -> tabell i GeoPackage. Administrativa bestämmelser och
# övergångsbestämmelser saknas medvetet (inga pågående bestämmelser är administrativa). Egenskapspunkter används
# inte: alla egenskaper gäller hela egenskapsytan, och egenskapslinjer finns bara för utfartsförbud och stängsel.
LAYER_FOR = {
    ("Användningsbestämmelse", "Yta/Volym"): "anvandning_yta",
    ("Egenskapsbestämmelse", "Yta/Volym"): "egenskap_yta",
    ("Egenskapsbestämmelse", "Linje"): "egenskap_linje",
}
# Omvänt: tabell -> (bestämmelsetyp, geometrityp)
KIND_OF_LAYER = {table: kind for kind, table in LAYER_FOR.items()}
USE_LAYER = "anvandning_yta"
PROPERTY_LAYERS = ("egenskap_yta", "egenskap_linje")
# Egenskapsbestämmelser som ges leverans via ett eget lagerbegrepp: användnings- och egenskapstyp följer av lagret
LAYER_DELIVERY_TYPE = {
    "anvandning_yta": "användningsbestämmelse",
    "egenskap_yta": "egenskapsbestämmelse",
    "egenskap_linje": "egenskapsbestämmelse",
}
# Katalogens bestämmelsetyp -> värde i Lantmäteriets JSON-schema. Övergångsbestämmelser kan inte levereras.
DELIVERABLE_TYPES = {
    "Användningsbestämmelse": "användningsbestämmelse",
    "Egenskapsbestämmelse": "egenskapsbestämmelse",
    "Administrativ bestämmelse": "administrativ bestämmelse",
}
TECHNICAL_FORMULATION = "Tekniska anläggningar"  # DP-0019/0021: generell bestämmelse för alla tekniska anläggningar

# Katalogens "uttryckt värde" -> Lantmäteriets värdetyp
_VALUE_TYPES = {"Min": "min", "Max": "max", "Exakt": "exakt"}

# Ledtrådar i texten efter en decimalvariabel -> enhet i Lantmäteriets kodlista
_UNIT_HINTS = (
    ("m²", "kvadratmeter"),
    ("kvadratmeter", "kvadratmeter"),
    ("m³", "kubikmeter"),
    ("kubikmeter", "kubikmeter"),
    ("meter", "meter"),
    ("%", "procent"),
    ("procent", "procent"),
    ("grader", "grader"),
    ("dB", "dB(A)"),
    ("år", "år"),
)


@dataclass(frozen=True)
class Variable:
    name: str
    datatype: str  # "text" | "decimaltal"
    token: str  # den exakta texten i formuleringen, t.ex. "[höjd:decimaltal]"

    @property
    def optional(self) -> bool:
        """Endast variabeln [text:text] är frivillig (Boverkets fältbeskrivning för Bestämmelseformulering)."""
        return self.name == "text" and self.datatype == "text"


def parse_variables(formulation: str) -> tuple[Variable, ...]:
    return tuple(Variable(m.group(1), m.group(2), m.group(0)) for m in _VARIABLE_RE.finditer(formulation))


def render(formulation: str, values: dict[str, str] | Iterable[str]) -> str:
    """Fyller i variablerna i en formulering. ``values`` är antingen {token: värde} eller värden i ordning."""
    variables = parse_variables(formulation)
    if isinstance(values, dict):
        lookup = {var.token: values.get(var.token, "") for var in variables}
    else:
        lookup = {var.token: value for var, value in zip(variables, values)}
    out = formulation
    for var in variables:
        out = out.replace(var.token, lookup.get(var.token, "") or var.token, 1)
    return out


def guess_unit(formulation: str, variable: Variable) -> Optional[str]:
    """Gissar enhet för en decimalvariabel utifrån texten som följer efter den."""
    if variable.datatype != "decimaltal":
        return None
    after = formulation.split(variable.token, 1)[-1].lstrip()
    for hint, unit in _UNIT_HINTS:
        if after.startswith(hint):
            return unit
    return None


def value_type(uttryckt_varde: Optional[str]) -> Optional[str]:
    return _VALUE_TYPES.get(uttryckt_varde or "")


def _clean_symbol_name(name: Optional[str]) -> str:
    """"Utfart får inte finnas (1987 - pågående)" -> "Utfart får inte finnas"."""
    return re.sub(r"\s*\(\d{4}\s*-[^)]*\)\s*$", "", name or "").strip()


def _split_ids(text: Optional[str]) -> tuple[str, ...]:
    return tuple(part.strip() for part in (text or "").split(",") if part.strip())


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    kod: str
    formulering: str
    typ: str  # bestämmelsetyp enligt katalogen
    anvandningsform: str
    geometrityp: str
    kategori: str = ""
    underkategori: str = ""
    beteckning: str = ""
    uttryckt_varde: Optional[str] = None
    borjar_galla: str = ""
    slutar_galla: str = ""
    tolkning: bool = False
    symbol_id: Optional[int] = None
    symbol: str = ""  # symbolens namn utan årsintervall, t.ex. "Utfart får inte finnas"
    farg: str = ""
    huvudmannaskap: str = ""
    hilucs: str = ""
    allmanna_rad: str = ""
    ersatter: tuple[str, ...] = ()
    ersatts_av: tuple[str, ...] = ()

    @cached_property
    def variables(self) -> tuple[Variable, ...]:
        return parse_variables(self.formulering)

    @property
    def is_current(self) -> bool:
        return not self.slutar_galla

    @property
    def is_technical(self) -> bool:
        return self.formulering.strip() == TECHNICAL_FORMULATION

    @property
    def layer_name(self) -> Optional[str]:
        return LAYER_FOR.get((self.typ, self.geometrityp))

    @property
    def deliverable(self) -> bool:
        return self.layer_name is not None

    @property
    def is_use(self) -> bool:
        return self.layer_name == USE_LAYER

    @property
    def label_base(self) -> str:
        """Beteckning på plankartan utan indexmarkör, t.ex. "e#" -> "e" (tom om beteckning saknas)."""
        return self.beteckning.replace("#", "").strip()

    @property
    def delivery_type(self) -> Optional[str]:
        return DELIVERABLE_TYPES.get(self.typ)

    @property
    def typ_rubrik(self) -> str:
        """Rubrik för typen av bestämmelse i listor: "Användningsbestämmelser" eller "Egenskapsbestämmelser"."""
        return "Användningsbestämmelser" if self.layer_name == USE_LAYER else "Egenskapsbestämmelser"

    @property
    def search_text(self) -> str:
        return " ".join((self.kod, self.formulering, self.kategori, self.underkategori, self.beteckning)).lower()

    # -- (av)serialisering ----------------------------------------------------------
    @classmethod
    def from_api(cls, raw: dict) -> "CatalogEntry":
        return cls(
            id=raw["id"],
            kod=raw.get("bestammelsekod") or "",
            formulering=raw.get("bestammelseformulering") or "",
            typ=raw.get("bestammelsetyp") or "",
            anvandningsform=raw.get("anvandningsform") or "",
            geometrityp=raw.get("geometrityp") or "",
            kategori=raw.get("kategori") or "",
            underkategori=raw.get("underkategori") or "",
            beteckning=raw.get("beteckning") or "",
            uttryckt_varde=raw.get("uttrycktvarde"),
            borjar_galla=(raw.get("borjargalla") or "")[:10],
            slutar_galla=(raw.get("slutargalla") or "")[:10],
            tolkning=bool(raw.get("tolkningsbestammelse")),
            symbol_id=raw.get("symbolid"),
            symbol=_clean_symbol_name(raw.get("symbol")),
            farg=raw.get("farg") or "",
            huvudmannaskap=raw.get("huvudmannaskap") or "",
            hilucs=raw.get("hilucs") or "",
            allmanna_rad=raw.get("allmannarad") or "",
            ersatter=_split_ids(raw.get("ersatter")),
            ersatts_av=_split_ids(raw.get("ersattsav")),
        )

    def to_compact(self) -> dict:
        data = {
            "id": self.id, "kod": self.kod, "formulering": self.formulering, "typ": self.typ,
            "anvandningsform": self.anvandningsform, "geometrityp": self.geometrityp,
            "kategori": self.kategori, "underkategori": self.underkategori, "beteckning": self.beteckning,
            "uttryckt_varde": self.uttryckt_varde, "borjar_galla": self.borjar_galla,
            "slutar_galla": self.slutar_galla, "tolkning": self.tolkning, "symbol_id": self.symbol_id,
            "symbol": self.symbol, "farg": self.farg, "huvudmannaskap": self.huvudmannaskap, "hilucs": self.hilucs,
            "allmanna_rad": self.allmanna_rad, "ersatter": list(self.ersatter), "ersatts_av": list(self.ersatts_av),
        }
        return {k: v for k, v in data.items() if v not in (None, "", [], False)}

    @classmethod
    def from_compact(cls, data: dict) -> "CatalogEntry":
        data = dict(data)
        for required in ("kod", "formulering", "typ", "anvandningsform", "geometrityp"):
            data.setdefault(required, "")  # tomma värden utelämnas i den kompakta formen
        data["ersatter"] = tuple(data.get("ersatter", ()))
        data["ersatts_av"] = tuple(data.get("ersatts_av", ()))
        return cls(**data)


@dataclass
class Catalog:
    release_id: int
    release_name: str
    published: str
    entries: list[CatalogEntry] = field(default_factory=list)

    def __post_init__(self):
        self._by_id = {entry.id: entry for entry in self.entries}

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, entry_id: str) -> Optional[CatalogEntry]:
        return self._by_id.get(entry_id)

    @property
    def has_historic(self) -> bool:
        return any(not entry.is_current for entry in self.entries)

    def search(self, text: str = "", *, geometrityp: str | None = None, anvandningsform: str | None = None,
               typ: str | None = None, layer: str | None = None, include_historic: bool = False,
               include_interpretation: bool = False, only_deliverable: bool = True) -> list[CatalogEntry]:
        """Filtrerar katalogen. Alla ord i ``text`` måste förekomma (utan hänsyn till versaler)."""
        words = text.lower().split()
        result = []
        for entry in self.entries:
            if only_deliverable and not entry.deliverable:
                continue
            if not include_historic and not entry.is_current:
                continue
            if not include_interpretation and entry.tolkning:
                continue
            if geometrityp and entry.geometrityp != geometrityp:
                continue
            if anvandningsform and entry.anvandningsform != anvandningsform:
                continue
            if typ and entry.typ != typ:
                continue
            if layer and entry.layer_name != layer:
                continue
            haystack = entry.search_text
            if all(word in haystack for word in words):
                result.append(entry)
        return result

    def forms(self) -> list[str]:
        return sorted({entry.anvandningsform for entry in self.entries if entry.anvandningsform})

    # -- (av)serialisering ----------------------------------------------------------
    @classmethod
    def from_api_release(cls, release: dict) -> "Catalog":
        """Bygger katalogen från ``/release/full/platt/{id}``."""
        return cls(
            release_id=int(release["id"]),
            release_name=str(release.get("namn", "")),
            published=str(release.get("publicerad", ""))[:10],
            entries=[CatalogEntry.from_api(raw) for raw in release["bestammelser"]],
        )

    def only_current(self) -> "Catalog":
        return Catalog(self.release_id, self.release_name, self.published,
                       [entry for entry in self.entries if entry.is_current])

    def to_json(self) -> str:
        return json.dumps(
            {"release_id": self.release_id, "release_name": self.release_name, "published": self.published,
             "entries": [entry.to_compact() for entry in self.entries]},
            ensure_ascii=False, separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, text: str) -> "Catalog":
        data = json.loads(text)
        return cls(data["release_id"], data["release_name"], data["published"],
                   [CatalogEntry.from_compact(entry) for entry in data["entries"]])

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)  # atomiskt: en avbruten nedladdning förstör aldrig en fungerande cache

    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


def latest_release(releases: list[dict]) -> dict:
    """Väljer senaste juridiska release ur svaret från ``/release`` (tekniska releaser är interna)."""
    legal = [r for r in releases if (r.get("typ") or {}).get("namn") == "Juridisk"]
    if not legal:
        raise ValueError("Inga juridiska releaser i svaret från Boverket")
    return max(legal, key=lambda r: (r.get("publicerad") or "", r["id"]))
