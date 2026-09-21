"""Generate ``rita_detaljplan/core/codelists.py`` from Lantmäteriet's JSON schemas.

Run with any Python 3.10+ (no QGIS needed):

    python tools/generate_codelists.py

The schemas in ``spec/`` are the source of truth. When Lantmäteriet publishes a
new version, replace the files in ``spec/`` and re-run this script; the tests
fail if the generated module is out of date.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec"
OUT = ROOT / "rita_detaljplan" / "core" / "codelists.py"

# Codelists taken from detaljplan-4.1.json: constant name -> schema definition.
DETALJPLAN_LISTS = {
    "PLANSTATUS": "planstatus",
    "PLANTYP": "plantyp",
    "DIGITALISERINGSNIVA": "digitaliseringsniva",
    "TILLFORLITLIGHET": "tillforlitlighet",
    "AVGRANSNING": "avgransning",
    "KOMMUNINSTANS": "kommuninstans",
    "BESLUTSTYP": "beslutstyp",
    "INNEHALL": "innehall",
    "RESURSHANDELSE": "resurshandelse",
    "HUVUDOMRADE": "huvudomrade",
    "UNDERLAGSTYP": "underlagstyp",
    "VARIABELTYP": "typ",
    "VARDETYP": "vardetyp",
    "ENHET": "enhet",
}

# Method definitions in geometrimetadata-2.0.1.json: definition -> variant definition
# (``None`` when the method has no variant, ``"inline"`` when it is embedded).
METOD_DEFS = {
    "geodetiskDetaljmatning": "variantAvGeodetiskDetaljmatning",
    "lagesplacering": "variantAvLagesplacering",
    "fotogrammetriskDetaljmatning": "variantAvFotogrammetriskDetaljmatning",
    "vektoriseringAvAnalogtMaterial": "variantAvVektoriseringAvAnalogtMaterial",
    "detaljmatningILaserdata": "variantAvDetaljmatningILaserdata",
    "konvertering": "variantAvKonvertering",
    "interpolering": "variantAvInterpolering",
    "fjarranalys": None,
    "batymetri": None,
    "okand": "inline",
}


def _load(name: str) -> dict:
    with open(SPEC / name, encoding="utf-8") as fh:
        return json.load(fh)["definitions"]


def _enum(defs: dict, name: str) -> list[str]:
    return list(defs[name]["enum"])


def _metod_typ(defs: dict, name: str) -> str:
    for part in defs[name]["allOf"]:
        typ = part.get("properties", {}).get("typ", {})
        if "enum" in typ:
            return typ["enum"][0]
    raise ValueError(f"no typ enum in {name}")


def _fmt_list(values: list[str], indent: str = "    ") -> str:
    lines = [f"{indent}{json.dumps(v, ensure_ascii=False)}," for v in values]
    return "(\n" + "\n".join(lines) + "\n)"


def build() -> str:
    dp = _load("detaljplan-4.1.json")
    gm = _load("geometrimetadata-2.0.1.json")
    geo = _load("geometri-2.0.json")

    out = [
        '"""Kodlistor (värdemängder) för Nationell informationsspecifikation Detaljplan 4.1.',
        "",
        "AUTOGENERERAD av tools/generate_codelists.py från spec/*.json. Redigera inte för hand.",
        '"""',
        "",
    ]
    for const, name in DETALJPLAN_LISTS.items():
        out.append(f"{const} = {_fmt_list(_enum(dp, name))}\n")

    out.append(f"KOORDINATSYSTEM_PLAN = {_fmt_list(_enum(geo, 'koordinatsystemPlan'))}\n")
    out.append(f"HOJDSYSTEM = {_fmt_list(_enum(geo, 'hojdsystem'))}\n")
    out.append(f"OSAKERT_LAGE = {_fmt_list(_enum(gm, 'anledningTillOsakertLage'))}\n")

    out.append("# Lägesbestämningsmetod -> tillåtna varianter (tom lista = ingen variant).")
    out.append("LAGESMETODER = {")
    for definition, variant_def in METOD_DEFS.items():
        typ = _metod_typ(gm, definition)
        if variant_def is None:
            variants: list[str] = []
        elif variant_def == "inline":
            variants = list(
                next(p for p in gm[definition]["allOf"] if "properties" in p and "variant" in p["properties"])[
                    "properties"
                ]["variant"]["enum"]
            )
        else:
            variants = _enum(gm, variant_def)
        out.append(f"    {json.dumps(typ, ensure_ascii=False)}: {_fmt_list(variants, '        ')},")
    out.append("}\n")

    return "\n".join(out)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"Skrev {OUT.relative_to(ROOT)}")
