"""Hämtar Boverkets planbestämmelsekatalog och uppdaterar den medföljande kopian.

    python tools/update_bundled_catalog.py            # uppdaterar rita_detaljplan/data/planbestammelsekatalog.json
    python tools/update_bundled_catalog.py --fixture  # uppdaterar även tests/data/katalog_urval.json

Den medföljande kopian innehåller endast pågående bestämmelser (så att pluginet fungerar direkt och utan
nätverk). Hela katalogen inklusive upphörda bestämmelser hämtas av pluginet vid behov.
Källa: Boverket, Planbestämmelsekatalogen (öppna data). Kräver ingen API-nyckel.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_detaljplan.core import catalog as cat  # noqa: E402

BUNDLED = ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json"
FIXTURE = ROOT / "tests" / "data" / "katalog_urval.json"

# Bestämmelser som testerna behöver (se tests/test_catalog.py)
FIXTURE_CODES = {
    "DP_KM_E2",  # Tekniska anläggningar
    "DP_KM_Eg_MarkensAnordOchVeg_Markforhallanden_StorstaLutning",  # två decimalvariabler
    "DP_KM_Eg_Utnytt_StorstaAreaProc_ByggnadsEgen",  # procent
    "DP_KM_Eg_VillkorLov_SkyddSakerhet_Bygglov",  # två textvariabler
    "DP_AP_Eg_Rivningsforbud_Rivningsforbud_Annan",  # bara en variabel
    "DP_PO_Eg_Adm_Aldre",  # tolkningsbestämmelse
    "DP_KM_R2_Motorsport",  # användning med indexerad beteckning (R#)
    "DP_KM_R2_Bygdegard",  # samma bokstav, annan bestämmelse -> R1/R2
    "DP_KM_J2",  # användning med fast beteckning (J)
}


def get_json(path: str):
    request = urllib.request.Request(cat.API_BASE + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true", help="skriv även testunderlaget")
    args = parser.parse_args()

    release = cat.latest_release(get_json("/release"))
    print(f"Senaste release: {release['namn']} (id {release['id']})")
    full = get_json(f"/release/full/platt/{release['id']}")
    catalog = cat.Catalog.from_api_release(full)
    print(f"{len(catalog)} bestämmelser, {len(catalog.only_current())} pågående")

    BUNDLED.parent.mkdir(parents=True, exist_ok=True)
    catalog.only_current().save(BUNDLED)
    print(f"Skrev {BUNDLED.relative_to(ROOT)} ({BUNDLED.stat().st_size // 1024} KiB)")

    if args.fixture:
        raws = full["bestammelser"]
        picked = [r for r in raws if r.get("bestammelsekod") in FIXTURE_CODES and not r.get("slutargalla")]
        # ett par upphörda bestämmelser, en punkt och en linje, plus en övergångsbestämmelse om det finns
        def deliverable(r):
            return (r.get("bestammelsetyp"), r.get("geometrityp")) in cat.LAYER_FOR and not r.get("tolkningsbestammelse")

        def current(r):
            return deliverable(r) and not r.get("slutargalla")

        picked += [r for r in raws if r.get("slutargalla") and deliverable(r)][:2]
        # en användning med fast beteckning "B", samt linjer och punkter med symboler i Boverkets katalog
        picked += [r for r in raws if current(r) and r.get("bestammelsetyp") == "Användningsbestämmelse"
                   and r.get("beteckning") == "B"][:1]
        for symbol in ("Utfart får inte finnas", "Stängsel ska finnas"):
            picked += [r for r in raws if current(r) and (r.get("symbol") or "").startswith(symbol)][:1]
        picked += [r for r in raws if current(r) and r.get("geometrityp") == "Linje"][:1]
        # en egenskapsyta på allmän plats och ett utfartsförbud på kvartersmark, båda utan variabler
        picked += [r for r in raws if current(r) and r.get("bestammelsetyp") == "Egenskapsbestämmelse"
                   and r.get("anvandningsform") == "Allmän plats" and r.get("geometrityp") == "Yta/Volym"
                   and "[" not in (r.get("bestammelseformulering") or "")][:1]
        picked += [r for r in raws if current(r) and r.get("bestammelseformulering") == "Utfartsförbud"
                   and r.get("anvandningsform") == "Kvartersmark"][:1]
        # en användning på allmän plats (gata, park …), för att prova användningsformens betydelse
        picked += [r for r in raws if current(r) and r.get("bestammelsetyp") == "Användningsbestämmelse"
                   and r.get("anvandningsform") == "Allmän plats" and "[" not in (r.get("bestammelseformulering") or "")][:1]
        picked += [r for r in raws if r.get("bestammelsetyp") == "Övergångsbestämmelse"][:1]
        seen, unique = set(), []
        for raw in picked:
            if raw["id"] not in seen:
                seen.add(raw["id"])
                unique.append({k: v for k, v in raw.items() if k not in ("forklaring", "webblank") and v is not None})
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps({**{k: v for k, v in full.items() if k != "bestammelser"},
                                       "bestammelser": unique}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Skrev {FIXTURE.relative_to(ROOT)} ({len(unique)} bestämmelser)")


if __name__ == "__main__":
    main()
