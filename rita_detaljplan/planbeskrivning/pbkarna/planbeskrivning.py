"""Taggar för en digital planbeskrivning (Nationell dataproduktspecifikation Planbeskrivning 2.0, BFS 2020:8).

En planbeskrivning i Word (.docx) taggas med bokmärken i texten och en anpassad XML-del (customXML) som beskriver vad
varje bokmärke innehåller: tema, grupp, undergrupp och läge. Det här är den XML-delen. Bokmärkets namn i Word är
omfattningens ``identitet``.

``INDELNING`` är bilagan till BFS 2020:8 (tema, grupp, undergrupp). I XML:en skrivs värdena med gemener, som i
Lantmäteriets exempel i specifikationen; vid inläsning spelar skiftläge ingen roll. Ren Python, ingen QGIS behövs.
"""
from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

NAMESPACE = "http://namespace.lantmateriet.se/distribution/geodatakatalog/planbeskrivning/v2"
XSD_URL = NAMESPACE + "/planbeskrivning-2.0.xsd"

IDENTITET_RE = re.compile(r"^[A-Za-zÅÄÖåäö][A-Za-zÅÄÖåäö0-9_]{0,39}$")
UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")

PLANBESTAMMELSE = "planbestammelsereferens"
PLANOMRADE = "planomrade"
OBJEKT = "objektreferens"
LAGEN = (PLANOMRADE, PLANBESTAMMELSE, OBJEKT)

MOTIV_TEMA = "Motiv till detaljplanens regleringar"
MOTIV_GRUPP = "Motiv till reglering"

_RIKSINTRESSEN = [
    "Rennäring", "Yrkesfiske", "Naturvård", "Friluftsliv", "Kulturmiljövård", "Fyndigheter av ämnen och material",
    "Industriell produktion", "Energiproduktion och energidistribution",
    "Slutförvaring av kärnbränsle och kärnavfall", "Elektronisk kommunikation", "Trafikkommunikation",
    "Avfallshantering", "Vattenförsörjning", "Totalförsvar", "Rörligt friluftsliv", "Obruten kust",
    "Högexploaterad kust", "Obrutet fjäll", "Skyddade vattendrag", "Nationalstadspark", "Natura 2000",
    "Områden för geologisk lagring av koldioxid",
]
_HUSHALLNING = ["Jordbruksmark", "Skogsbruk", "Oexploaterade områden", "Ekologiskt särskilt känsliga områden"]
_HUSHALLNING_GRUPP = "Hushållningsbestämmelser enligt 3 kap. miljöbalken"
_MKN = ["Luft", "Vatten", "Buller"]

# tema -> grupp -> undergrupper, i bilagans ordning (BFS 2020:8)
INDELNING: dict[str, dict[str, list[str]]] = {
    "Detaljplanens syfte": {"Syfte": []},
    "Beskrivning av detaljplanen": {
        "Hela detaljplan": [], "Genomförandetid": [], "Allmän plats": ["Huvudmannaskap"], "Kvartersmark": [],
        "Vattenområde": [], "Befintligt": [], "Varför ändring av detaljplan valts": [], "Ärendeinformation": [],
        "Annat": [],
    },
    MOTIV_TEMA: {MOTIV_GRUPP: []},
    "Genomförandefrågor": {
        "Mark- och utrymmesförvärv": ["Skyldighet inlösen, huvudman", "Skyldighet inlösen, stat",
                                      "Rätt till inlösen, huvudman", "Rätt till inlösen av rättighet, kommun"],
        "Fastighetsrättsliga frågor": ["Fastighetsindelningsbestämmelser", "Förändrad fastighetsindelning",
                                       "Rättigheter"],
        "Tekniska frågor": ["Tekniska åtgärder", "Utbyggnad allmän plats", "Utbyggnad vatten och avlopp"],
        "Ekonomiska frågor": ["Planekonomisk bedömning", "Planavgift", "Ersättningsanspråk", "Inlösen",
                              "Gemensamhetsanläggningar", "Drift allmän plats", "Drift vatten och avlopp",
                              "Gatukostnader"],
        "Organisatoriska frågor": ["Exploateringsavtal", "Markanvisning", "Tidplan"],
        "Kulturvärden": ["Rivningsförbud", "Bevarandekrav"],
        "Prövning enligt annan lagstiftning": [], "Upplysningar": [], "Annat": [],
    },
    "Planeringsunderlag": {
        "Kommunala": ["Detaljplan", "Planprogram", "Grundkarta", "Översiktsplan",
                      "Undersökning enligt 6 kap. 6 § plan- och bygglagen (2010:900)", "Miljökonsekvensbeskrivning",
                      "Särskilt beslut om betydande miljöpåverkan"],
        "Utredningar": ["Dagsljus och skugga", "Dagvattenutredning", "Handelsutredning", "Naturinventering",
                        "Geoteknisk utredning", "Markmiljöutredning", "Bullerutredning", "Förprojektering",
                        "Riskutredning", "Trafikutredning", "Barnkonsekvensanalys", "Kulturmiljöutredning"],
        "Regionala": ["Regionplan"], "Annat": [],
    },
    "Planeringsförutsättningar": {
        "Kommunala": ["Detaljplan", "Områdesbestämmelser", "Förhandsbesked", "Planeringsbesked", "Planbesked",
                      "Planprogram", "Översiktsplan"],
        "Regionala": ["Regionplan"],
        "Riksintressen": list(_RIKSINTRESSEN),
        _HUSHALLNING_GRUPP: list(_HUSHALLNING),
        "Miljökvalitetsnormer": list(_MKN),
        "Mellankommunala intressen": [],
        "Miljö": ["Strandskydd", "Dagvatten"],
        "Hälsa och säkerhet": ["Omgivningsbuller", "Risk för olyckor", "Risk för översvämning", "Risk för erosion",
                               "Risk för skred", "Risk för ras"],
        "Geotekniska förhållanden": [], "Hydrologiska förhållanden": [],
        "Kulturmiljö": ["Fornlämningar", "Byggnadsminnen", "Kyrkligt kulturarv"],
        "Fysisk miljö": [], "Sociala": [], "Teknik": [], "Service": [], "Trafik": [], "Annat": [],
    },
    "Konsekvenser": {
        "Fastigheter och rättigheter": [],
        "Natur": ["Grönområde", "Landskapsbild", "Naturreservat"],
        "Miljö": ["Miljökonsekvensbeskrivning", "Miljöbedömning",
                  "Ställningstagande 4 kap. 33 b § plan- och bygglagen (2010:900)", "Strandskydd", "Dagvatten"],
        "Miljökvalitetsnormer": list(_MKN),
        "Hälsa och säkerhet": ["Beräkning av omgivningsbuller", "Översvämning", "Olyckor", "Erosion", "Skred", "Ras"],
        "Sociala": ["Barn", "Jämlikhet"],
        "Riksintresse": list(_RIKSINTRESSEN),
        _HUSHALLNING_GRUPP: list(_HUSHALLNING),
        "Trafik": ["Motortrafik", "Gång- och cykeltrafik"],
        "Mellankommunala frågor": [], "Annat": [],
    },
}


def _key(text: Optional[str]) -> str:
    return " ".join((text or "").split()).casefold()


def canonical(value: Optional[str], options) -> Optional[str]:
    """Värdet i ``options``' stavning (skiftläge och mellanslag spelar ingen roll), eller None om det inte finns."""
    wanted = _key(value)
    return next((o for o in options if _key(o) == wanted), None) if wanted else None


def temas() -> list[str]:
    return list(INDELNING)


def grupper(tema: Optional[str]) -> list[str]:
    found = canonical(tema, INDELNING)
    return list(INDELNING[found]) if found else []


def undergrupper(tema: Optional[str], grupp: Optional[str]) -> list[str]:
    found = canonical(tema, INDELNING)
    group = canonical(grupp, INDELNING[found]) if found else None
    return list(INDELNING[found][group]) if group else []


@dataclass(frozen=True)
class Omfattning:
    """En tagg: ett avsnitt i planbeskrivningen (bokmärket ``identitet`` i Word) med sin indelning och sitt läge."""
    identitet: str
    tema: str
    grupp: str
    undergrupp: Optional[str] = None
    lage: str = PLANOMRADE  # LAGEN
    referens: Optional[str] = None  # planbestämmelsens identitet (UUID) eller annat objekts id; None för planomrade
    ytterligare: tuple = ()  # fler planbestämmelser (UUID) som samma avsnitt gäller, t.ex. samma bestämmelse på flera ytor

    def referenser(self) -> list[str]:
        return [r for r in (self.referens, *self.ytterligare) if r]


def problems(items: list[Omfattning]) -> list[str]:
    """Det som bryter mot specifikationens regler (PLANB-001 till -005, -008) och mot indelningen i BFS 2020:8.
    Tom lista = taggarna går att leverera."""
    found: list[str] = []
    if not items:
        return ["Minst en tagg krävs."]
    seen: dict[str, str] = {}
    for item in items:
        name = item.identitet or "(utan namn)"
        if not IDENTITET_RE.match(item.identitet or ""):
            found.append(f"{name}: identiteten (bokmärkets namn) ska börja med en bokstav och bara ha bokstäver, "
                         "siffror och understreck, högst 40 tecken.")
        key = _key(item.identitet)
        if key in seen:
            found.append(f"{name}: identiteten används flera gånger (skiftläge spelar ingen roll).")
        seen[key] = item.identitet
        tema = canonical(item.tema, INDELNING)
        if tema is None:
            found.append(f"{name}: temat \"{item.tema}\" finns inte i BFS 2020:8.")
        if not (item.grupp or "").strip():
            found.append(f"{name}: grupp saknas.")
        if item.undergrupp and not (item.grupp or "").strip():
            found.append(f"{name}: undergrupp kräver en grupp.")
        if item.lage not in LAGEN:
            found.append(f"{name}: läget \"{item.lage}\" är okänt.")
        elif item.lage == PLANBESTAMMELSE and not (item.referenser() and all(UUID_RE.match(r) for r in item.referenser())):
            found.append(f"{name}: planbestämmelsereferensen ska vara en identitet (UUID).")
        elif item.lage == OBJEKT and not (item.referens or "").strip():
            found.append(f"{name}: objektreferensen saknas.")
        if tema == MOTIV_TEMA and _key(item.grupp) == _key(MOTIV_GRUPP) and item.lage != PLANBESTAMMELSE:
            found.append(f"{name}: \"Motiv till reglering\" ska peka på en planbestämmelse (PLANB-002).")
    return found


# -- XML ---------------------------------------------------------------------------------------
def _q(tag: str) -> str:
    return f"{{{NAMESPACE}}}{tag}"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Header:
    """Planbeskrivningens egna uppgifter i XML-delen (resten är taggarna)."""
    detaljplan: str  # detaljplanens objektidentitet
    objektidentitet: str = ""
    objektversion: int = 1
    arkividentitet: Optional[str] = None
    programvara: Optional[str] = None
    programvaruversion: Optional[str] = None


def build_xml(header: Header, items: list[Omfattning], valid_from: Optional[str] = None) -> str:
    """XML-delen (customXML) som läggs in i Word-filen (Utvecklare → XML-mappningsfönster → Anpassad XML-del).
    Kastar ``ValueError`` om taggarna bryter mot reglerna (se ``problems``)."""
    found = problems(items)
    if found:
        raise ValueError("\n".join(found))
    if not UUID_RE.match(header.detaljplan or ""):
        raise ValueError("Detaljplanens identitet (UUID) saknas.")
    ET.register_namespace("", NAMESPACE)
    root = ET.Element(_q("Planbeskrivning"))
    ET.SubElement(root, _q("objektidentitet")).text = header.objektidentitet or str(uuid.uuid4())
    ET.SubElement(root, _q("objektversion")).text = str(header.objektversion)
    ET.SubElement(root, _q("versionGiltigFran")).text = valid_from or _now()
    ET.SubElement(root, _q("detaljplansreferens")).text = header.detaljplan
    if header.programvara or header.programvaruversion:
        meta = ET.SubElement(root, _q("Objektmetadata"))
        if header.programvara:
            ET.SubElement(meta, _q("programvara")).text = header.programvara
        if header.programvaruversion:
            ET.SubElement(meta, _q("programvaruversion")).text = header.programvaruversion
    if header.arkividentitet:
        ET.SubElement(root, _q("arkividentitetKommun")).text = header.arkividentitet
    for item in items:
        part = ET.SubElement(root, _q("Omfattning"))
        ET.SubElement(part, _q("identitet")).text = item.identitet
        for reference in item.referenser() if item.lage == PLANBESTAMMELSE else [item.referens]:
            lage = ET.SubElement(part, _q("Lage"))
            if item.lage == PLANOMRADE:
                ET.SubElement(lage, _q(PLANOMRADE)).text = "true"
            else:
                ET.SubElement(lage, _q(item.lage)).text = (reference or "").strip()
        split = ET.SubElement(part, _q("Indelning"))
        tema = canonical(item.tema, INDELNING)
        ET.SubElement(split, _q("tema")).text = tema.lower()
        ET.SubElement(split, _q("grupp")).text = _own_or_standard(item.grupp, grupper(tema)).lower()
        if (item.undergrupp or "").strip():
            ET.SubElement(split, _q("undergrupp")).text = _own_or_standard(
                item.undergrupp, undergrupper(tema, item.grupp)).lower()
    ET.indent(root)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _own_or_standard(value: str, options: list[str]) -> str:
    return canonical(value, options) or " ".join(value.split())


def parse_xml(text: str) -> tuple[Header, list[Omfattning]]:
    """Läser en tidigare skapad XML-del. Kastar ``ValueError`` om det inte är en planbeskrivning enligt specifikationen."""
    try:
        root = ET.fromstring(text.encode("utf-8") if text.lstrip().startswith("<?xml") else text)
    except ET.ParseError as exc:
        raise ValueError(f"Filen är inte giltig XML: {exc}") from exc
    if root.tag != _q("Planbeskrivning"):
        raise ValueError("Filen är ingen planbeskrivning enligt Lantmäteriets specifikation (fel rotelement eller namnrymd).")

    def child(parent, tag):
        found = parent.find(_q(tag))
        return (found.text or "").strip() if found is not None and found.text else None

    meta = root.find(_q("Objektmetadata"))
    header = Header(
        detaljplan=child(root, "detaljplansreferens") or "",
        objektidentitet=child(root, "objektidentitet") or "",
        objektversion=int(child(root, "objektversion") or 1),
        arkividentitet=child(root, "arkividentitetKommun"),
        programvara=child(meta, "programvara") if meta is not None else None,
        programvaruversion=child(meta, "programvaruversion") if meta is not None else None,
    )
    items = []
    for part in root.findall(_q("Omfattning")):
        kind, references = PLANOMRADE, []
        for lage in part.findall(_q("Lage")):
            for candidate in (PLANBESTAMMELSE, OBJEKT):
                if lage.find(_q(candidate)) is not None:
                    kind = candidate
                    references.append(child(lage, candidate))
        reference = references[0] if references else None
        split = part.find(_q("Indelning"))
        tema = child(split, "tema") if split is not None else None
        grupp = child(split, "grupp") if split is not None else None
        undergrupp = child(split, "undergrupp") if split is not None else None
        tema = canonical(tema, INDELNING) or tema or ""
        grupp = canonical(grupp, grupper(tema)) or grupp or ""
        undergrupp = (canonical(undergrupp, undergrupper(tema, grupp)) or undergrupp) if undergrupp else None
        items.append(Omfattning(child(part, "identitet") or "", tema, grupp, undergrupp, kind, reference,
                                tuple(references[1:])))
    return header, items


def next_header(previous: Optional[Header], detaljplan: str, software: str, software_version: str) -> Header:
    """Rubriken för en ny version av XML-delen: behåller identiteten och höjer versionen om en tidigare finns."""
    if previous is None or previous.detaljplan != detaljplan:
        return Header(detaljplan, str(uuid.uuid4()), 1, None, software, software_version)
    return replace(previous, objektversion=previous.objektversion + 1, programvara=software,
                   programvaruversion=software_version)
