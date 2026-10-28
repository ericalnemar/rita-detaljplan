"""Arkivpaket för en detaljplan: en mapp med planens filer och bevarandemetadata (PREMIS 3.0) enligt Boverkets
dataelementkatalog för långtidsbevarande av digitala detaljplaner (maj 2026).

Paketet::

    <plannamn>_arkivpaket_<datum>/
        metadata/
            PREMIS.xml          all bevarandemetadata: planen, filerna, händelserna och aktörerna
        schemas/                scheman: PREMIS 3.0, schemat för planens uppgifter och, med leveransfilen, Lantmäteriets JSON-scheman
        content/                själva filerna: planen, plankartan, planbeskrivningen m.fl.

``PREMIS.xml`` är giltig mot Library of Congress XML-schema för PREMIS 3.0 (``premis-v3-0.xsd``) och är självbärande:
varje UUID den hänvisar till finns i den. Det som skiljer från Boverkets exempelfiler, som inte är schemagiltiga, är att
objektets kategori anges med ``xsi:type`` (schemat har inget ``objectCategory``-element), att elementen står i schemats
ordning, att planen är en *representation* (``premis:representation``, som Boverkets specifikation anger) med filerna som
delar, och att planens uppgifter ligger i ``significantProperties`` på planen (en representation får inte ha
``objectCharacteristics``), i ett eget namnrymd med ett eget schema (``schemas/detaljplan-1.xsd``). Värdena är de ur Boverkets värdelistor, som är LoC:s. Allt som är obligatoriskt i
katalogen fylls i: identifierare (UUID), kategori, kontrollsumma (SHA-256), storlek, format, skapande program,
händelser och aktörer, med relationer i båda riktningarna. Modulen är ren Python (ingen QGIS) så att den kan provas
utan QGIS."""
from __future__ import annotations

import hashlib
import re
import shutil
import struct
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote, unquote
from xml.etree import ElementTree as ET

PREMIS_NS = "http://www.loc.gov/premis/v3"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
DETALJPLAN_NS = "https://ritaplan.xyz/ns/detaljplan/1"  # planens uppgifter (utanför PREMIS) i significantPropertiesExtension
SCHEMA_LOCATION = f"{PREMIS_NS} http://www.loc.gov/standards/premis/v3/premis-v3-0.xsd"  # slutversionen, inte utkastet
PREMIS_FILE = "PREMIS.xml"
METADATA, CONTENT = "metadata", "content"  # mapparna i paketet
LEGACY_GENERAL_FILE = "detaljplan.xml"  # fanns i paket från 0.1.55-0.1.59 (egen fil för planen, inte schemagiltig)
SCHEMAS = "schemas"  # mappen med scheman i paketet
PREMIS_XSD, DETALJPLAN_XSD = "premis-v3-0.xsd", "detaljplan-1.xsd"
# Lantmäteriets JSON-scheman för leveransfilen (Detaljplan 4.1); följer med när paketet innehåller en leveransfil
JSON_SCHEMAS = ("detaljplan-4.1.json", "geometri-2.0.json", "geometrimetadata-2.0.1.json")
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "data" / "schemas"  # pluginets egna kopior av schemana
# schemat för planens uppgifter har ingen publik adress; sökvägen räknas från metadata/PREMIS.xml till paketets schemas/
DETALJPLAN_SCHEMA_LOCATION = f"{DETALJPLAN_NS} ../{SCHEMAS}/{DETALJPLAN_XSD}"
# planens uppgifter i den ordning ``detaljplan-1.xsd`` kräver (ett okänt element hamnar sist och gör filen ogiltig mot schemat)
PLAN_ELEMENTS = ("beteckning", "namn", "status", "datumStatusforandring", "typ", "datumLagakraft", "anvandbarhet", "kommun",
                 "kommunkod")
HASH_ALGORITHM = "SHA-256"
UNKNOWN_APPLICATION = "Okänt program"

_HASHES = {"SHA-1": "sha1", "SHA-256": "sha256", "SHA-384": "sha384", "SHA-512": "sha512", "MD5": "md5"}
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_FORMATS = {".json": "JSON", ".xml": "XML", ".txt": "Text", ".csv": "CSV", ".png": "PNG", ".jpg": "JPEG",
            ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF", ".gml": "GML", ".zip": "ZIP", ".gpkg": "GeoPackage",
            ".docx": "DOCX", ".pdf": "PDF", ".odt": "ODT", ".xlsx": "XLSX", ".dwg": "DWG", ".svg": "SVG"}


class ArchiveError(RuntimeError):
    """Paketet kunde inte skapas eller kontrolleras. Meddelandet är avsett för användaren."""


@dataclass
class App:
    """Programmet som skapar paketet (förs in som aktör)."""
    name: str
    version: str
    homepage: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}".strip()


@dataclass
class Item:
    """En fil som ska med i paketet. ``creator`` är (program, version) när filen skapats av pluginet eller QGIS i samband
    med paketeringen (den räknas då som exporterad); annars läses programmet ur filen om det går."""
    source: Path
    name: Optional[str] = None
    creator: Optional[tuple[str, Optional[str]]] = None


@dataclass
class Record:
    """Det paketet vet om en fil."""
    id: str
    path: str  # relativ sökväg i paketet, med snedstreck
    name: str  # filens ursprungliga namn
    size: int
    digest: str
    format_name: str
    format_version: Optional[str]
    app_name: str
    app_version: Optional[str]
    created: str
    generated: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class Package:
    folder: Path
    premis: Path  # metadata/PREMIS.xml: all bevarandemetadata
    records: list[Record]

    @property
    def notes(self) -> list[str]:
        return [f"{r.name}: {note}" for r in self.records for note in r.notes]


# -- filerna ----------------------------------------------------------------------------------------------------------
def clean_filename(name: str, fallback: str = "fil") -> str:
    """Filnamn utan tecken som Windows inte tillåter."""
    text = _ILLEGAL.sub("_", name).strip(" .")
    return text or fallback


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _head_tail(path: Path, size: int = 2_000_000) -> bytes:
    with open(path, "rb") as handle:
        head = handle.read(size)
        total = handle.seek(0, 2)
        if total <= size:
            return head
        handle.seek(max(size, total - size))
        return head + handle.read()


def _iso(moment: datetime) -> str:
    return moment.astimezone().isoformat(timespec="seconds")


def _mtime(path: Path) -> str:
    return _iso(datetime.fromtimestamp(path.stat().st_mtime))


def _pdf_date(text: str) -> Optional[str]:
    match = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?", text.strip())
    if not match:
        return None
    parts = [int(g) if g else d for g, d in zip(match.groups(), (0, 1, 1, 0, 0, 0))]
    try:
        return _iso(datetime(*parts))
    except ValueError:
        return None


def _decode(raw: bytes) -> str:
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def sniff_format(path: Path) -> tuple[str, Optional[str], list[str]]:
    """(formatnamn, version, anmärkningar). PDF/A känns igen på filens XMP-metadata."""
    suffix = path.suffix.lower()
    notes: list[str] = []
    with open(path, "rb") as handle:
        head = handle.read(1024)
    if head.startswith(b"%PDF-"):
        match = re.match(rb"%PDF-(\d\.\d)", head)
        version = match.group(1).decode() if match else None
        data = _head_tail(path)
        part = re.search(rb'pdfaid:part(?:=["\']|>)\s*(\d)', data)
        conformance = re.search(rb'pdfaid:conformance(?:=["\']|>)\s*([A-Za-z])', data)
        if part:
            level = part.group(1).decode() + (conformance.group(1).decode().upper() if conformance else "")
            return "PDF/A", level, notes
        notes.append("Filen är inte PDF/A, som är det arkivformat som rekommenderas för dokument.")
        return "PDF", version, notes
    if head.startswith(b"SQLite format 3\x00") and suffix == ".gpkg":
        version = None
        if len(head) >= 64:
            user_version = struct.unpack(">I", head[60:64])[0]
            if user_version:
                version = f"{user_version // 10000}.{(user_version // 100) % 100}"
        return "GeoPackage", version, notes
    if suffix == ".docx" and zipfile.is_zipfile(path):
        notes.append("Word-dokument är inget arkivbeständigt format; spara också en PDF/A-kopia.")
        return "DOCX", None, notes
    return _FORMATS.get(suffix, suffix.lstrip(".").upper() or "okänt"), None, notes


def sniff_application(path: Path, format_name: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(program, version, skapad) ur filens egna uppgifter, eller None för det som inte går att läsa."""
    try:
        if format_name == "DOCX":
            with zipfile.ZipFile(path) as archive:
                app = ET.fromstring(archive.read("docProps/app.xml"))
                core = ET.fromstring(archive.read("docProps/core.xml"))
            name = (app.findtext("{*}Application") or "").strip() or None
            version = (app.findtext("{*}AppVersion") or "").strip() or None
            created = (core.findtext("{http://purl.org/dc/terms/}created") or "").strip() or None
            return name, version, created
        if format_name in ("PDF", "PDF/A"):
            data = _head_tail(path)
            name = None
            for pattern in (rb"<xmp:CreatorTool>([^<]+)<", rb"/Creator\s*\(([^)]{1,200})\)", rb"<pdf:Producer>([^<]+)<",
                            rb"/Producer\s*\(([^)]{1,200})\)"):
                match = re.search(pattern, data)
                if match:
                    name = _decode(match.group(1)).strip() or None
                    if name:
                        break
            created = None
            match = re.search(rb"/CreationDate\s*\(([^)]{1,40})\)", data)
            if match:
                created = _pdf_date(_decode(match.group(1)))
            if created is None:
                match = re.search(rb"<xmp:CreateDate>([^<]+)<", data)
                created = _decode(match.group(1)).strip() if match else None
            return name, None, created
    except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile):
        pass
    return None, None, None


def describe(path: Path, creator: Optional[tuple[str, Optional[str]]], now: datetime) -> Record:
    """Läser filens tekniska uppgifter (utan att kopiera den)."""
    format_name, format_version, notes = sniff_format(path)
    if creator is not None:
        app_name, app_version, created = creator[0], creator[1], _iso(now)
    else:
        app_name, app_version, created = sniff_application(path, format_name)
        if not app_name:
            notes.append("Programmet som skapade filen kunde inte läsas ur den och anges som okänt.")
        if not created:
            created = _mtime(path)
    return Record(id=str(uuid.uuid4()), path="", name=path.name, size=path.stat().st_size, digest=sha256_of(path),
                  format_name=format_name, format_version=format_version, app_name=app_name or UNKNOWN_APPLICATION,
                  app_version=app_version, created=created or _mtime(path), generated=creator is not None, notes=notes)


# -- PREMIS ------------------------------------------------------------------------------------------------------------
def _q(tag: str) -> str:
    return f"{{{PREMIS_NS}}}{tag}"


def _add(parent: ET.Element, tag: str, text: Optional[str] = None) -> ET.Element:
    element = ET.SubElement(parent, _q(tag))
    if text is not None:
        element.text = text
    return element


def _identifier(parent: ET.Element, prefix: str, value: str, kind: str = "UUID") -> None:
    box = _add(parent, f"{prefix}Identifier")
    _add(box, f"{prefix}IdentifierType", kind)
    _add(box, f"{prefix}IdentifierValue", value)


def _link(parent: ET.Element, prefix: str, value: str, role: Optional[str] = None) -> None:
    box = _add(parent, f"linking{prefix}Identifier")
    _add(box, f"linking{prefix}IdentifierType", "UUID")
    _add(box, f"linking{prefix}IdentifierValue", value)
    if role:
        _add(box, f"linking{prefix}Role", role)


# Programmets id räknades först ut ur dess adress. Projektet flyttade till GitHub-organisationen ritaplan (2026-10-27) och
# fick då en ny adress, men id:t ska vara detsamma: paket från före och efter flytten pekar då på samma aktör. Därför
# räknas id:t fortfarande ut ur den gamla adressen.
_AGENT_ID_SEEDS = {"Rita Detaljplan": "https://github.com/ericalnemar/rita-detaljplan"}


def plugin_agent_id(app: App) -> str:
    """Samma id för samma program varje gång, så att paket från olika datum hänvisar till samma aktör. Pluginets eget id är
    låst (se ``_AGENT_ID_SEEDS``); andra program får ett id härlett ur sin adress."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, _AGENT_ID_SEEDS.get(app.name) or app.homepage or app.name))


def _new_root(with_details: bool = False) -> ET.Element:
    """Rotelementet. ``with_details``: planens uppgifter finns med, så schemat för dem anges också."""
    ET.register_namespace("premis", PREMIS_NS)
    ET.register_namespace("xsi", XSI_NS)
    ET.register_namespace("dp", DETALJPLAN_NS)
    location = SCHEMA_LOCATION + (f" {DETALJPLAN_SCHEMA_LOCATION}" if with_details else "")
    return ET.Element(_q("premis"), {f"{{{XSI_NS}}}schemaLocation": location, "version": "3.0"})


def _object(parent: ET.Element, kind: str) -> ET.Element:
    """Ett ``object``. Kategorin (``file`` eller ``representation``) anges med ``xsi:type``: PREMIS XML-schema har
    inget ``objectCategory``-element, det finns bara i dataordlistan."""
    return ET.SubElement(parent, _q("object"), {f"{{{XSI_NS}}}type": f"premis:{kind}"})


def _relationship(parent: ET.Element, subtype: str, others: list[str]) -> None:
    relation = _add(parent, "relationship")
    _add(relation, "relationshipType", "structural")
    _add(relation, "relationshipSubType", subtype)
    for other in others:
        _identifier(relation, "relatedObject", other)


def premis_tree(records: list[Record], plan_name: str, plan: dict, app: App, performer: Optional[str],
                now: datetime) -> ET.Element:
    """``metadata/PREMIS.xml`` som träd: planen som en *representation* (med planens uppgifter i
    ``significantProperties`` och alla filer som delar), varje fil, händelserna och aktörerna. Allt hänvisar till varandra
    med UUID och varje länk finns åt båda hållen. Elementen står i den ordning schemat kräver."""
    root = _new_root(bool(plan))
    when = _iso(now)
    app_id = plugin_agent_id(app)
    person_id = str(uuid.uuid4()) if performer else None
    representation = str(uuid.uuid4())
    create_id, digest_id, export_id = (str(uuid.uuid4()) for _ in range(3))
    generated = [r for r in records if r.generated]
    event_ids_for = {r.id: [create_id, digest_id] + ([export_id] if r.generated else []) for r in records}
    used_events = [create_id, digest_id] + ([export_id] if generated else [])

    box = _object(root, "representation")
    _identifier(box, "object", representation)
    if plan:
        properties = _add(box, "significantProperties")
        _add(properties, "significantPropertiesType", "detaljplan")
        details = ET.SubElement(_add(properties, "significantPropertiesExtension"), f"{{{DETALJPLAN_NS}}}detaljplan")
        for key, value in sorted(plan.items(), key=lambda item: PLAN_ELEMENTS.index(item[0]) if item[0] in PLAN_ELEMENTS
                                 else len(PLAN_ELEMENTS)):
            ET.SubElement(details, f"{{{DETALJPLAN_NS}}}{key}").text = value
    _add(box, "originalName", plan_name)
    _relationship(box, "has Part", [r.id for r in records])
    _link(box, "Event", create_id)

    for record in records:
        box = _object(root, "file")
        _identifier(box, "object", record.id)
        characteristics = _add(box, "objectCharacteristics")
        _add(characteristics, "compositionLevel", "0")
        fixity = _add(characteristics, "fixity")
        _add(fixity, "messageDigestAlgorithm", HASH_ALGORITHM)
        _add(fixity, "messageDigest", record.digest)
        _add(fixity, "messageDigestOriginator", app.label)
        _add(characteristics, "size", str(record.size))
        designation = _add(_add(characteristics, "format"), "formatDesignation")
        _add(designation, "formatName", record.format_name)
        if record.format_version:
            _add(designation, "formatVersion", record.format_version)
        creating = _add(characteristics, "creatingApplication")
        _add(creating, "creatingApplicationName", record.app_name)
        if record.app_version:
            _add(creating, "creatingApplicationVersion", record.app_version)
        _add(creating, "dateCreatedByApplication", record.created)
        _add(box, "originalName", record.name)
        place = _add(_add(box, "storage"), "contentLocation")
        _add(place, "contentLocationType", "Uniform Resource Identifier")
        _add(place, "contentLocationValue", quote(record.path))
        _relationship(box, "is Part Of", [representation])
        for event in event_ids_for[record.id]:
            _link(box, "Event", event)

    def event(identifier: str, kind: str, detail: str, objects: list[tuple[str, str]]) -> None:
        box = _add(root, "event")
        _identifier(box, "event", identifier)
        _add(box, "eventType", kind)
        _add(box, "eventDateTime", when)
        _add(_add(box, "eventDetailInformation"), "eventDetail", detail)
        _add(_add(box, "eventOutcomeInformation"), "eventOutcome", "success")
        _link(box, "Agent", app_id, "executing program")  # i schemat står agenterna före objekten
        if person_id:
            _link(box, "Agent", person_id, "implementer")
        for value, role in objects:
            _link(box, "Object", value, role)

    event(create_id, "information package creation",
          f"Arkivpaket för planen {plan_name} skapades med {app.label}.",
          [(representation, "outcome")] + [(r.id, "source") for r in records])
    event(digest_id, "message digest calculation", f"Kontrollsummor ({HASH_ALGORITHM}) beräknades för alla filer.",
          [(r.id, "source") for r in records])
    if generated:
        event(export_id, "exporting", "Filerna exporterades ur planen när paketet skapades.",
              [(r.id, "outcome") for r in generated])

    def agent(identifier: str, name: str, kind: str, version: Optional[str] = None, note: str = "") -> None:
        box = _add(root, "agent")
        _identifier(box, "agent", identifier)
        _add(box, "agentName", name)
        _add(box, "agentType", kind)
        if version:
            _add(box, "agentVersion", version)
        if note:
            _add(box, "agentNote", note)
        for event_id in used_events:
            _link(box, "Event", event_id)

    agent(app_id, app.name, "software", app.version or None, app.homepage)
    if person_id:
        agent(person_id, performer, "person")
    return root


def _links(box: ET.Element, tag: str) -> list[str]:
    return [(link.findtext(_q(tag + "Value")) or "") for link in box.findall(_q(tag))]


def link_problems(root: ET.Element) -> list[str]:
    """Kontrollerar att varje UUID i PREMIS-dokumentet går att slå upp och att varje länk finns åt båda hållen: objekt ↔
    händelse, agent ↔ händelse och planen ``has Part`` filen ↔ filen ``is Part Of`` planen (Boverkets krav i manualen).
    Returnerar en lista med beskrivningar av det som inte stämmer; tom när allt hänger ihop."""
    objects = {box.findtext(f"{_q('objectIdentifier')}/{_q('objectIdentifierValue')}") or "": box
               for box in root.findall(_q("object"))}
    events = {box.findtext(f"{_q('eventIdentifier')}/{_q('eventIdentifierValue')}") or "": box
              for box in root.findall(_q("event"))}
    agents = {box.findtext(f"{_q('agentIdentifier')}/{_q('agentIdentifierValue')}") or "": box
              for box in root.findall(_q("agent"))}
    problems: list[str] = []
    ids = [value for kind, tag in (("object", "objectIdentifier"), ("event", "eventIdentifier"),
                                   ("agent", "agentIdentifier"))
           for value in (box.findtext(f"{_q(tag)}/{_q(tag + 'Value')}") for box in root.findall(_q(kind)))]
    if len(ids) != len(set(ids)):
        problems.append("Samma id används för mer än en sak.")
    for object_id, box in objects.items():
        for event_id in _links(box, "linkingEventIdentifier"):
            if event_id not in events:
                problems.append(f"Ett objekt hänvisar till en händelse som inte finns ({event_id[:8]}).")
            elif object_id not in _links(events[event_id], "linkingObjectIdentifier"):
                problems.append(f"Händelsen {event_id[:8]} saknar länk tillbaka till objektet {object_id[:8]}.")
        for relation in box.findall(_q("relationship")):
            subtype = relation.findtext(_q("relationshipSubType")) or ""
            inverse = {"has Part": "is Part Of", "is Part Of": "has Part"}.get(subtype)
            for other in _links(relation, "relatedObjectIdentifier"):
                if other not in objects:
                    problems.append(f"Ett objekt hänvisar till ett annat objekt som inte finns ({other[:8]}).")
                elif inverse and not any((r.findtext(_q("relationshipSubType")) or "") == inverse
                                         and object_id in _links(r, "relatedObjectIdentifier")
                                         for r in objects[other].findall(_q("relationship"))):
                    problems.append(f"Relationen {subtype} från {object_id[:8]} till {other[:8]} saknar motsvarigheten "
                                    f"{inverse}.")
    for event_id, box in events.items():
        for object_id in _links(box, "linkingObjectIdentifier"):
            if object_id not in objects:
                problems.append(f"Händelsen {event_id[:8]} hänvisar till ett objekt som inte finns ({object_id[:8]}).")
            elif event_id not in _links(objects[object_id], "linkingEventIdentifier"):
                problems.append(f"Objektet {object_id[:8]} saknar länk tillbaka till händelsen {event_id[:8]}.")
        for agent_id in _links(box, "linkingAgentIdentifier"):
            if agent_id not in agents:
                problems.append(f"Händelsen {event_id[:8]} hänvisar till en agent som inte finns ({agent_id[:8]}).")
            elif event_id not in _links(agents[agent_id], "linkingEventIdentifier"):
                problems.append(f"Agenten {agent_id[:8]} saknar länk tillbaka till händelsen {event_id[:8]}.")
    for agent_id, box in agents.items():
        for event_id in _links(box, "linkingEventIdentifier"):
            if event_id not in events:
                problems.append(f"En agent hänvisar till en händelse som inte finns ({event_id[:8]}).")
            elif agent_id not in _links(events[event_id], "linkingAgentIdentifier"):
                problems.append(f"Händelsen {event_id[:8]} saknar länk tillbaka till agenten {agent_id[:8]}.")
    return problems


def to_xml(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


# -- paketet -----------------------------------------------------------------------------------------------------------
def package_folder(parent: Path, plan_name: str, now: datetime) -> Path:
    """Namnet på paketmappen: ``<plannamn>_arkivpaket_<datum>``, med ett löpnummer om den redan finns (en befintlig
    mapp skrivs aldrig över)."""
    base = f"{clean_filename(plan_name, 'detaljplan').replace(' ', '_')}_arkivpaket_{now:%Y-%m-%d}"
    folder, number = parent / base, 1
    while folder.exists():
        number += 1
        folder = parent / f"{base}_{number}"
    return folder


def bundled_schemas(with_details: bool, with_delivery_file: bool = False) -> list[Path]:
    """Schemafilerna som ska med i paketets ``schemas/``: PREMIS 3.0 alltid, schemat för planens uppgifter när de finns och
    Lantmäteriets JSON-scheman när paketet innehåller leveransfilen (så att den går att validera utan internet)."""
    names = [PREMIS_XSD] + ([DETALJPLAN_XSD] if with_details else []) + (list(JSON_SCHEMAS) if with_delivery_file else [])
    return [SCHEMA_DIR / name for name in names]


def build_package(parent: Path, plan_name: str, items: list[Item], app: App, performer: Optional[str] = None,
                  now: Optional[datetime] = None, progress: Optional[Callable[[str], None]] = None,
                  plan: Optional[dict] = None) -> Package:
    """Skapar paketmappen under ``parent``: kopierar filerna till ``content/``, beskriver dem i ``metadata/PREMIS.xml``
    och planens uppgifter (``plan``: elementnamn -> värde), och lägger schemana i ``schemas/``. Originalfilerna rörs inte.
    Misslyckas något tas den halvfärdiga mappen bort och ``ArchiveError`` kastas."""
    if not items:
        raise ArchiveError("Inga filer att lägga i paketet.")
    if not parent.is_dir():
        raise ArchiveError(f"Mappen finns inte: {parent}")
    missing = [item.source.name for item in items if not item.source.is_file()]
    if missing:
        raise ArchiveError("Filerna finns inte: " + ", ".join(missing))
    now = now or datetime.now()
    folder = package_folder(parent, plan_name, now)
    say = progress or (lambda _text: None)
    try:
        folder.mkdir()
        (folder / CONTENT).mkdir()
        (folder / METADATA).mkdir()
        records, used = [], set()
        for item in items:
            name = clean_filename(item.name or item.source.name)
            target_name, number = name, 1
            while target_name.lower() in used:
                number += 1
                target_name = f"{Path(name).stem}_{number}{Path(name).suffix}"
            used.add(target_name.lower())
            say(f"Kopierar {target_name}")
            target = folder / CONTENT / target_name
            shutil.copy2(item.source, target)
            record = describe(target, item.creator, now)
            record.path, record.name = f"{CONTENT}/{target_name}", item.name or item.source.name
            records.append(record)
        say("Skriver bevarandemetadata")
        premis = folder / METADATA / PREMIS_FILE
        premis.write_text(to_xml(premis_tree(records, plan_name, plan or {}, app, performer, now)), encoding="utf-8",
                          newline="\n")
        say("Lägger med scheman")
        (folder / SCHEMAS).mkdir()
        delivery_file = any(item.creator is not None and item.source.suffix.lower() == ".json" for item in items)
        for schema in bundled_schemas(bool(plan), delivery_file):
            shutil.copy2(schema, folder / SCHEMAS / schema.name)
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(exc, ArchiveError):
            raise
        raise ArchiveError(f"Kunde inte skapa arkivpaketet: {exc}") from exc
    return Package(folder, premis, records)


# -- kontroll av ett paket -----------------------------------------------------------------------------------------------
@dataclass
class VerifyReport:
    folder: Path
    ok: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)  # t.ex. okänd kontrollsummealgoritm eller ogiltig sökväg
    notes: list[str] = field(default_factory=list)  # om metadatan, inte om filerna (ändrar inte ``clean``)

    @property
    def clean(self) -> bool:
        return not (self.changed or self.missing or self.extra or self.unchecked)

    def text(self) -> str:
        lines = [f"{len(self.ok)} filer är oförändrade."]
        for title, names in (("Ändrade sedan paketet skapades", self.changed), ("Saknas", self.missing),
                             ("Finns i mappen men inte i metadatan", self.extra),
                             ("Kunde inte kontrolleras", self.unchecked)):
            if names:
                lines.append(f"{title}: " + ", ".join(names))
        lines += self.notes
        return "\n".join(lines)


def _object_kind(box: ET.Element) -> str:
    """``file``/``representation`` (eller ``intellectualEntity`` i paket från 0.1.63-0.1.64): ur ``xsi:type`` (så som schemat
    vill ha det) eller, i paket från 0.1.55-0.1.59, ur elementet ``objectCategory``."""
    typed = box.get(f"{{{XSI_NS}}}type")
    return typed.split(":")[-1] if typed else (box.findtext(_q("objectCategory")) or "")


def verify_package(folder: Path) -> VerifyReport:
    """Räknar om kontrollsummorna för filerna i PREMIS.xml och jämför. Ändrar ingenting. Metadatans länkar kontrolleras
    också (se ``link_problems``) och avvikelser läggs i ``notes``; de ändrar inte om paketet räknas som oförändrat."""
    premis = folder / METADATA / PREMIS_FILE
    if not premis.is_file():
        raise ArchiveError(f"Hittar ingen {METADATA}/{PREMIS_FILE} i mappen. Är det ett arkivpaket från Rita Detaljplan?")
    try:
        root = ET.parse(premis).getroot()
    except ET.ParseError as exc:
        raise ArchiveError(f"{PREMIS_FILE} går inte att läsa: {exc}") from exc
    report = VerifyReport(folder)
    base = folder.resolve()
    listed: set[Path] = {premis.resolve()}
    objects = root.findall(_q("object"))
    if objects and all(box.get(f"{{{XSI_NS}}}type") is None for box in objects):
        general = folder / LEGACY_GENERAL_FILE  # paket från 0.1.55-0.1.59
        listed.add(general.resolve())
        if not general.is_file():
            report.missing.append(LEGACY_GENERAL_FILE)
        report.notes.append("Paketet är skapat med en äldre version (före 0.1.60) och metadatan följer inte PREMIS XML-schema. "
                            "Kontrollsummorna kontrolleras ändå. Skapa paketet på nytt för en giltig PREMIS-fil.")
    else:
        report.notes += link_problems(root)
    for box in objects:
        if _object_kind(box) != "file":
            continue
        location = unquote(box.findtext(f"{_q('storage')}/{_q('contentLocation')}/{_q('contentLocationValue')}") or "")
        label = location or (box.findtext(_q("originalName")) or "?")
        target = (folder / location).resolve() if location else None
        if target is None or base not in target.parents:
            report.unchecked.append(f"{label} (ogiltig sökväg)")
            continue
        listed.add(target)
        if not target.is_file():
            report.missing.append(label)
            continue
        fixity = box.find(f"{_q('objectCharacteristics')}/{_q('fixity')}")
        algorithm = (fixity.findtext(_q("messageDigestAlgorithm")) if fixity is not None else None) or ""
        expected = ((fixity.findtext(_q("messageDigest")) if fixity is not None else None) or "").strip().lower()
        size = box.findtext(f"{_q('objectCharacteristics')}/{_q('size')}")
        if algorithm not in _HASHES or not expected:
            report.unchecked.append(f"{label} (kontrollsumma saknas eller har okänd algoritm)")
            continue
        digest = hashlib.new(_HASHES[algorithm])
        with open(target, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != expected or (size and size.strip().isdigit() and int(size) != target.stat().st_size):
            report.changed.append(label)
        else:
            report.ok.append(label)
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if path.is_file() and path.resolve() not in listed and relative.parts[0] != SCHEMAS:  # schemana beskrivs inte i PREMIS
            report.extra.append(relative.as_posix())
    return report
