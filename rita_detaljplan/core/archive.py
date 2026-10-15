"""Arkivpaket för en detaljplan: en mapp med planens filer och bevarandemetadata (PREMIS 3.0) enligt Boverkets
dataelementkatalog för långtidsbevarande av digitala detaljplaner (maj 2026).

Paketet följer Boverkets illustration av ett arkivpaket::

    <plannamn>_arkivpaket_<datum>/
        detaljplan.xml          generell metadata om detaljplanen (planens uppgifter ur Detaljplan 4.1)
        metadata/
            PREMIS.xml          metadata om de bifogade filerna: kontrollsumma, format, händelser, aktörer
        content/                själva filerna: planen, plankartan, planbeskrivningen m.fl.

Metadatan följer Boverkets exempelfiler (elementnamn och ordning är som i dem). Allt som är obligatoriskt i katalogen
fylls i: identifierare (UUID), kategori, kontrollsumma (SHA-256), storlek, format, skapande program, händelser och
aktörer, med relationer i båda riktningarna. Modulen är ren Python (ingen QGIS) så att den kan provas utan QGIS."""
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
SCHEMA_LOCATION = f"{PREMIS_NS} http://www.loc.gov/standards/premis/v3/premis-3-0-draft.xsd"
PREMIS_FILE = "PREMIS.xml"
METADATA, CONTENT = "metadata", "content"  # mapparna i paketet
GENERAL_FILE = "detaljplan.xml"  # generell metadata, i paketets rot
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
    premis: Path  # metadata/PREMIS.xml: metadata om filerna
    general: Path  # detaljplan.xml: generell metadata om detaljplanen
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


def plugin_agent_id(app: App) -> str:
    """Samma id för samma program varje gång (härlett ur dess adress), så att paket från olika datum hänvisar till
    samma aktör."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, app.homepage or app.name))


def _new_root() -> ET.Element:
    ET.register_namespace("premis", PREMIS_NS)
    ET.register_namespace("xsi", XSI_NS)
    return ET.Element(_q("premis"), {f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION, "version": "3.0"})


def premis_trees(records: list[Record], plan_name: str, plan: dict, app: App, performer: Optional[str],
                 now: datetime) -> tuple[ET.Element, ET.Element]:
    """De två metadatafilerna som träd: (``detaljplan.xml``, ``metadata/PREMIS.xml``). Den första beskriver planen som en
    helhet (en *representation* med planens uppgifter och alla filer som delar), den andra varje fil, händelserna och
    aktörerna. De hänvisar till varandra med UUID."""
    general, root = _new_root(), _new_root()
    when = _iso(now)
    app_id = plugin_agent_id(app)
    person_id = str(uuid.uuid4()) if performer else None
    representation = str(uuid.uuid4())
    create_id, digest_id, export_id = (str(uuid.uuid4()) for _ in range(3))
    generated = [r for r in records if r.generated]
    event_ids_for = {r.id: [create_id, digest_id] + ([export_id] if r.generated else []) for r in records}

    box = _add(general, "object")
    _identifier(box, "object", representation)
    _add(box, "objectCategory", "representation")
    if plan:
        extension = _add(_add(box, "objectCharacteristics"), "objectCharacteristicsExtension")
        details = ET.SubElement(extension, "detaljplan")
        for key, value in plan.items():
            ET.SubElement(details, key).text = value
    relation = _add(box, "relationship")
    _add(relation, "relationshipType", "structural")
    _add(relation, "relationshipSubType", "has Part")
    for record in records:
        related = _add(relation, "relatedObjectIdentifier")
        _add(related, "relatedObjectIdentifierType", "UUID")
        _add(related, "relatedObjectIdentifierValue", record.id)
    _link(box, "Event", create_id)

    for record in records:
        box = _add(root, "object")
        _identifier(box, "object", record.id)
        _add(box, "objectCategory", "file")
        _add(box, "originalName", record.name)
        place = _add(_add(box, "storage"), "contentLocation")
        _add(place, "contentLocationType", "Uniform Resource Identifier")
        _add(place, "contentLocationValue", quote(record.path))
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
        for event in event_ids_for[record.id]:
            _link(box, "Event", event)
        _link(box, "Agent", app_id, "executing program")

    def event(identifier: str, kind: str, detail: str, objects: list[tuple[str, str]]) -> None:
        box = _add(root, "event")
        _identifier(box, "event", identifier)
        _add(box, "eventType", kind)
        _add(box, "eventDateTime", when)
        _add(_add(box, "eventDetailInformation"), "eventDetail", detail)
        for value, role in objects:
            _link(box, "Object", value, role)
        _link(box, "Agent", app_id, "executing program")
        if person_id:
            _link(box, "Agent", person_id, "implementer")

    event(create_id, "information package creation",
          f"Arkivpaket för planen {plan_name} skapades med {app.label}.",
          [(representation, "outcome")] + [(r.id, "source") for r in records])
    event(digest_id, "message digest calculation", f"Kontrollsummor ({HASH_ALGORITHM}) beräknades för alla filer.",
          [(r.id, "source") for r in records])
    if generated:
        event(export_id, "exporting", "Filerna exporterades ur planen när paketet skapades.",
              [(r.id, "outcome") for r in generated])

    agent = _add(root, "agent")
    _identifier(agent, "agent", app_id)
    _add(agent, "agentName", app.label)
    _add(agent, "agentType", "software")
    if app.homepage:
        _add(agent, "agentNote", app.homepage)
    if person_id:
        person = _add(root, "agent")
        _identifier(person, "agent", person_id)
        _add(person, "agentName", performer)
        _add(person, "agentType", "person")
    return general, root


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


def build_package(parent: Path, plan_name: str, items: list[Item], app: App, performer: Optional[str] = None,
                  now: Optional[datetime] = None, progress: Optional[Callable[[str], None]] = None,
                  plan: Optional[dict] = None) -> Package:
    """Skapar paketmappen under ``parent``: kopierar filerna till ``content/``, beskriver dem i ``metadata/PREMIS.xml``
    och skriver ``detaljplan.xml`` med planens uppgifter (``plan``: elementnamn -> värde). Originalfilerna rörs inte.
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
        general_tree, files_tree = premis_trees(records, plan_name, plan or {}, app, performer, now)
        premis = folder / METADATA / PREMIS_FILE
        premis.write_text(to_xml(files_tree), encoding="utf-8", newline="\n")
        general = folder / GENERAL_FILE
        general.write_text(to_xml(general_tree), encoding="utf-8", newline="\n")
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(exc, ArchiveError):
            raise
        raise ArchiveError(f"Kunde inte skapa arkivpaketet: {exc}") from exc
    return Package(folder, premis, general, records)


# -- kontroll av ett paket -----------------------------------------------------------------------------------------------
@dataclass
class VerifyReport:
    folder: Path
    ok: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)  # t.ex. okänd kontrollsummealgoritm eller ogiltig sökväg

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
        return "\n".join(lines)


def verify_package(folder: Path) -> VerifyReport:
    """Räknar om kontrollsummorna för filerna i PREMIS.xml och jämför. Ändrar ingenting."""
    premis = folder / METADATA / PREMIS_FILE
    if not premis.is_file():
        raise ArchiveError(f"Hittar ingen {METADATA}/{PREMIS_FILE} i mappen. Är det ett arkivpaket från Rita Detaljplan?")
    try:
        root = ET.parse(premis).getroot()
    except ET.ParseError as exc:
        raise ArchiveError(f"{PREMIS_FILE} går inte att läsa: {exc}") from exc
    report = VerifyReport(folder)
    base = folder.resolve()
    general = folder / GENERAL_FILE
    listed: set[Path] = {premis.resolve(), general.resolve()}
    if not general.is_file():
        report.missing.append(GENERAL_FILE)
    for box in root.findall(_q("object")):
        if (box.findtext(_q("objectCategory")) or "") != "file":
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
        if path.is_file() and path.resolve() not in listed:
            report.extra.append(path.relative_to(folder).as_posix())
    return report
