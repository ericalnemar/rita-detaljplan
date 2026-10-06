"""Tagga en befintlig planbeskrivning (.docx) enligt Nationell dataproduktspecifikation Planbeskrivning 2.0.

Rubrikerna (Rubrik 1, 2, 3) läses som tema, grupp och undergrupp (BFS 2020:8) och varje avsnitt får ett bokmärke.
Tabellrader med motiv till en planbestämmelse får ett bokmärke som pekar på bestämmelsen. Den anpassade XML-delen
(customXML, se ``planbeskrivning``) läggs in i en NY kopia av filen; originalet rörs inte.

Dokumentets XML läses och ändras som text (inte via ElementTree) så att Words namnrymder, ``mc:Ignorable`` och all
formatering lämnas exakt som de var: bara bokmärken och XML-delen läggs till. Ren Python, ingen QGIS behövs.
"""
from __future__ import annotations

import csv
import difflib
import html
import io
import json
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import planbeskrivning as pb

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REL_CUSTOM = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
REL_PROPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXmlProps"
CT_PROPS = "application/vnd.openxmlformats-officedocument.customXmlProperties+xml"
DS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/customXml"
BOOKMARK_PREFIX = "pb"
COMMENT_AUTHOR = "Rita Detaljplan"  # standard för programvara och kommentarsförfattare (pluginet)
# kommentarer med de här författarna är verktygens egna (granskningskopian) och kan städas bort
OWN_COMMENT_AUTHORS = ("Rita Detaljplan", "Planbeskrivning Taggning", "Tagga planbeskrivning")  # även programmets tidigare namn
REL_COMMENTS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
CT_COMMENTS = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"

# statusar, från säkrast till mest att titta på
EXAKT, SPARAD, EGEN, NARA, OKANT = "exakt", "sparad", "egen", "nära", "okänt tema"
_RANK = {EXAKT: 0, SPARAD: 1, EGEN: 2, NARA: 3, OKANT: 4}
NEEDS_REVIEW = (NARA, OKANT)
DEFAULT_CUTOFF = 0.86


class DocxError(ValueError):
    """Filen går inte att tolka eller tagga. Meddelandet är avsett för användaren."""


# -- läsa dokumentets XML som text ---------------------------------------------------------------
_TAG = re.compile(r"<!--.*?-->|<\?.*?\?>|<(/?)([^\s/>]+)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)(/?)>", re.S)


def _spans(xml: str, lo: int, hi: int) -> list[tuple[str, int, int]]:
    """De direkta barnen (namn, start, slut) till ett element vars innehåll ligger i ``xml[lo:hi]``."""
    found, depth, start, name = [], 0, 0, ""
    for m in _TAG.finditer(xml, lo, hi):
        tag = m.group(2)
        if tag is None:
            continue
        if m.group(1):
            depth -= 1
            if depth == 0:
                found.append((name, start, m.end()))
        elif m.group(4):
            if depth == 0:
                found.append((tag, m.start(), m.end()))
        else:
            if depth == 0:
                name, start = tag, m.start()
            depth += 1
    return found


def _inner(xml: str, start: int, end: int) -> tuple[int, int]:
    first = _TAG.match(xml, start)
    if first.group(4):
        return end, end
    return first.end(), xml.rindex("</", start, end)


def _self_closing(xml: str, start: int) -> bool:
    return bool(_TAG.match(xml, start).group(4))


_FALLBACK = re.compile(r"<mc:Fallback>.*?</mc:Fallback>", re.S)
_TEXT_TOKEN = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|<w:tab\s*/>|<w:br\b[^>]*/>|<w:cr\s*/>|</w:txbxContent>|</w:p>")


def _text(xml: str, start: int, end: int) -> str:
    """Texten i ett stycke (eller en tabell): bara de riktiga texterna, i den ordning de står. Word skriver en textruta
    (t.ex. en symbol med bestämmelsens beteckning) två gånger, som riktig ruta (``mc:Choice``) och som reservversion
    (``mc:Fallback``): bara den förra tas med. Tabbtecken, radbrytningar, slutet av en textruta och slutet av ett stycke
    ger ett mellanslag, så att en beteckning inte klistras ihop med texten efter den. Textbitar i samma stycke slås ihop utan
    mellanrum (Word delar ofta ett enda ord i flera bitar)."""
    parts = []
    for token in _TEXT_TOKEN.finditer(_FALLBACK.sub("", xml[start:end])):
        parts.append(html.unescape(token.group(1)) if token.group(1) is not None else " ")
    return "".join(parts)


def _style(xml: str, start: int, end: int) -> str:
    m = re.search(r'<w:pStyle\s+w:val="([^"]*)"', xml[start:end])
    return m.group(1) if m else ""


def _paragraph_start(xml: str, start: int) -> int:
    """Där ett bokmärkes start läggs i ett stycke: efter styckets egenskaper (``w:pPr``)."""
    after_open = _TAG.match(xml, start).end()
    if xml.startswith("<w:pPr>", after_open) or xml.startswith("<w:pPr ", after_open):
        return xml.index("</w:pPr>", after_open) + len("</w:pPr>")
    return after_open


def _paragraph_end(xml: str, start: int, end: int) -> int:
    return xml.rindex("</w:p>", start, end)


def _edge_paragraph(xml: str, name: str, start: int, end: int, last: bool) -> Optional[tuple[int, int]]:
    """Första (eller sista) stycket i ett stycke/en tabell, utan att gå ner i textrutor och liknande."""
    if name == "w:p":
        return None if _self_closing(xml, start) else (start, end)
    lo, hi = _inner(xml, start, end)
    if name == "w:tbl":
        rows = [s for s in _spans(xml, lo, hi) if s[0] == "w:tr"]
        parts = rows[::-1] if last else rows
    elif name in ("w:tr", "w:tc"):
        parts = [s for s in _spans(xml, lo, hi) if s[0] in ("w:tc", "w:p", "w:tbl")]
        parts = parts[::-1] if last else parts
    else:
        return None
    for part in parts:
        found = _edge_paragraph(xml, *part, last)
        if found:
            return found
    return None


# -- rubriker -> tema, grupp och undergrupp -----------------------------------------------------
def heading_levels(styles_xml: str) -> dict[str, int]:
    """Styckeformatets id -> rubriknivå (1 = Rubrik 1), ur formatmallarna (disposition eller namn ``Rubrik N``)."""
    root = ET.fromstring(styles_xml)
    styles = {}
    for node in root.findall(W + "style"):
        if node.get(W + "type") != "paragraph":
            continue
        name = node.find(W + "name")
        outline = node.find(f"{W}pPr/{W}outlineLvl")
        based = node.find(W + "basedOn")
        styles[node.get(W + "styleId")] = (name.get(W + "val") if name is not None else "",
                                            outline.get(W + "val") if outline is not None else None,
                                            based.get(W + "val") if based is not None else None)
    levels = {}
    for style_id in styles:
        seen, current = set(), style_id
        while current in styles and current not in seen:
            seen.add(current)
            name, outline, based = styles[current]
            if outline is not None and outline.isdigit():
                if int(outline) < 9:
                    levels[style_id] = int(outline) + 1
                break  # nivå 9 = brödtext (t.ex. rubrik till innehållsförteckning)
            m = re.match(r"^(?:heading|rubrik)\s*(\d)$", name.strip(), re.I)
            if m:
                levels[style_id] = int(m.group(1))
                break
            current = based
    return levels


def _key(text: str) -> str:
    text = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s+", "", text or "")  # ev. skriven numrering
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


def _match(text: str, options: list[str], cutoff: float = DEFAULT_CUTOFF) -> tuple[Optional[str], str]:
    wanted = _key(text)
    for option in options:
        if _key(option) == wanted:
            return option, EXAKT
    close = difflib.get_close_matches(wanted, [_key(o) for o in options], n=1, cutoff=cutoff)
    if close:
        return next(o for o in options if _key(o) == close[0]), NARA
    return None, EGEN


@dataclass
class Overrides:
    """Val man gjort för rubriker som inte kändes igen, sparade så att nästa dokument med samma rubriker går av sig
    själv. Nycklar är rubrikernas normaliserade text: ``h1``, ``h1|h2`` respektive ``h1|h2|h3``."""
    tema: dict = field(default_factory=dict)
    grupp: dict = field(default_factory=dict)
    undergrupp: dict = field(default_factory=dict)
    # grupp för text som ligger direkt under en temarubrik (utan underrubrik) har nyckeln ``h1|`` (med ett avslutande streck)

    def to_json(self) -> str:
        return json.dumps({"tema": self.tema, "grupp": self.grupp, "undergrupp": self.undergrupp}, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Overrides":
        try:
            data = json.loads(text) if text else {}
            return cls(**{k: dict(data.get(k) or {}) for k in ("tema", "grupp", "undergrupp")})
        except (ValueError, TypeError, AttributeError):
            return cls()


def path_key(path: tuple[str, ...]) -> str:
    return "|".join(_key(p) for p in path)


@dataclass(frozen=True)
class Indelning:
    tema: Optional[str]
    grupp: Optional[str]
    undergrupp: Optional[str]
    status: str


def resolve(path: tuple[str, ...], overrides: Overrides, cutoff: float = DEFAULT_CUTOFF) -> Indelning:
    """Tema, grupp och undergrupp för en rubriksökväg (rubrik 1, 2 och 3)."""
    status = EXAKT

    def worse(current: str, other: str) -> str:
        return other if _RANK[other] > _RANK[current] else current

    tema = overrides.tema.get(path_key(path[:1]))
    if tema:
        status = worse(status, SPARAD)
    else:
        tema, found = _match(path[0], pb.temas(), cutoff)
        if tema is None:
            return Indelning(None, None, None, OKANT)
        status = worse(status, found)
    if len(path) < 2:
        chosen = overrides.grupp.get(path_key(path[:1]) + "|")  # text direkt under temarubriken: grupp valt för hand
        if chosen:
            return Indelning(tema, chosen, None, worse(status, SPARAD))
        return Indelning(tema, None, None, status)

    grupp = overrides.grupp.get(path_key(path[:2]))
    if grupp:
        status = worse(status, SPARAD)
    else:
        standard, found = _match(path[1], pb.grupper(tema), cutoff)
        grupp = standard or " ".join(path[1].split())
        status = worse(status, found)
    if len(path) < 3:
        return Indelning(tema, grupp, None, status)

    undergrupp = overrides.undergrupp.get(path_key(path[:3]))
    if undergrupp:
        status = worse(status, SPARAD)
    else:
        standard, found = _match(path[2], pb.undergrupper(tema, grupp), cutoff)
        undergrupp = standard or " ".join(path[2].split())
        status = worse(status, found)
    return Indelning(tema, grupp, undergrupp, status)


# -- analys av dokumentet --------------------------------------------------------------------------
@dataclass
class Avsnitt:
    """Ett avsnitt: en rubrik och allt fram till nästa rubrik."""
    path: tuple
    start: int  # där bokmärkets start läggs (förskjutning i dokument-XML:en)
    end: int
    has_content: bool
    indelning: Indelning = Indelning(None, None, None, OKANT)
    lage_keys: list = field(default_factory=list)  # bestämmelser (``Provision.key``) avsnittet gäller; tomt = hela planområdet
    text: str = ""  # avsnittets brödtext (styckena efter rubriken, skilda med en tom rad; tabeller ingår inte)

    @property
    def taggas(self) -> bool:
        i = self.indelning
        return bool(self.has_content and i.tema and i.grupp and i.tema != pb.MOTIV_TEMA)

    @property
    def status(self) -> str:
        return self.indelning.status


@dataclass
class Motiv:
    """Motivet till en planbestämmelse i planbeskrivningen (i avsnitt med temat "Motiv till detaljplanens regleringar"):
    en tabellrad eller ett stycke i löpande text som pekar ut bestämmelsen, med stycken efter sig."""
    path: tuple
    label: str  # tabell: första kolumnen; löptext: bestämmelsens beteckning
    text: str  # tabell: andra kolumnen; löptext: det som pekade ut bestämmelsen och stycken efter den
    start: int
    end: int
    title: str = ""  # tabell: andra kolumnens första stycke; löptext: stycket som pekade ut bestämmelsen
    key: Optional[str] = None  # den matchade bestämmelsen (``Provision.key``), None = ej matchad
    motiv: str = ""  # styckena efter det första: motivet (stycken skilda med en tom rad)
    i_lopande_text: bool = False  # hittat i löpande text i stället för i en tabell


@dataclass
class Provision:
    """En bestämmelse i planen som ett motiv kan höra till: dess beteckning, text och alla objektidentiteter."""
    key: str
    label: str
    text: str
    refs: tuple
    technical: bool = False  # fast motiv (Tekniska anläggningar): kräver inget motiv i planbeskrivningen


@dataclass
class Analys:
    xml: str
    sections: list
    motives: list
    overrides: Overrides
    provisions: list
    cutoff: float = DEFAULT_CUTOFF
    removed: list = field(default_factory=list)  # tidigare taggars bokmärken som städats bort
    previous: Optional[pb.Header] = None
    source: Optional[Path] = None
    parts_override: dict = field(default_factory=dict)  # delar som ändrats av analysen (pluginets egna kommentarer borttagna)
    uncovered: list = field(default_factory=list)  # motivavsnitt med innehåll där inga motiv kändes igen
    front: int = 0  # avsnitt med text före första rubriken (försättsblad m.m.), som inte taggas

    def refresh(self) -> None:
        """Räknar om indelningen efter att ``overrides`` ändrats."""
        for section in self.sections:
            section.indelning = resolve(section.path, self.overrides, self.cutoff)
        for motive in self.motives:
            if motive.key is None:
                motive.key = _match_provision(motive, self.provisions)


def _heading_provision(heading: str, provisions: list) -> Optional[str]:
    """Nyckeln till den bestämmelse en rubrik är precis lika med (bestämmelsens text eller beteckning, skiftläge och
    skiljetecken oväsentliga), om det bara är en."""
    wanted = _key(heading)
    if not wanted:
        return None
    found = [p.key for p in provisions if p.refs and (wanted == _key(p.text) or (p.label and wanted == _key(p.label)))]
    return found[0] if len(found) == 1 else None


def _dedupe(text: str) -> str:
    text = " ".join(text.split())
    half = len(text) // 2
    return text[:half] if len(text) % 2 == 0 and text[:half] == text[half:] and half else text


def _match_provision(motive: Motiv, provisions: list) -> Optional[str]:
    label, title, text = _key(motive.label), _key(motive.title), _key(motive.text)
    if label:
        found = [p for p in provisions if _key(p.label) == label]
        if len(found) == 1:
            return found[0].key
        provisions = found or provisions
    exact = [p for p in provisions if title and _key(p.text) == title]
    if len(exact) == 1:
        return exact[0].key
    candidates = [p for p in provisions if len(_key(p.text)) > 3 and text.startswith(_key(p.text))]
    return max(candidates, key=lambda p: len(_key(p.text))).key if candidates else None


_LABEL_SEPARATOR = r"(?=[\s:.–—)\]]|$)"
_STRIP = " \t:.–—-)]"


def _find_anchor(text: str, provisions: list) -> Optional[tuple["Provision", str]]:
    """Pekar ett stycke ut en bestämmelse? Det gör det om det börjar med bestämmelsens beteckning (t.ex. ``R1``,
    ``m1 Byggnaden ska …``) eller dess text (``Badanläggning: Syftet är …``), eller är precis det. Returnerar bestämmelsen
    och resten av stycket (inledande motivtext), annars None."""
    clean = " ".join(text.split())
    if not clean:
        return None
    norm = _key(clean)
    best: Optional[tuple[int, "Provision", str]] = None
    for provision in provisions:
        if not provision.refs:
            continue
        label, own = provision.label.strip(), _key(provision.text)
        rest, strength = None, 0
        if label and re.match(re.escape(label) + _LABEL_SEPARATOR, clean):
            after = clean[len(label):].lstrip(_STRIP)
            tail = _key(after)
            if not after or (own and tail.startswith(own)) or len(clean) <= 100:
                rest, strength = after, 2 + len(label)
                if own and tail == own:
                    rest = ""
                elif own and tail.startswith(own + " "):
                    rest = " ".join(after.split()[len(own.split()):]).lstrip(_STRIP)
        if rest is None and len(own) > 3 and (norm == own or norm.startswith(own + " ")):
            rest, strength = " ".join(clean.split()[len(own.split()):]).lstrip(_STRIP), 1 + len(own)
        if rest is not None and (best is None or strength > best[0]):
            best = (strength, provision, rest)
    return (best[1], best[2]) if best else None


def _text_motives(xml: str, elements: list, kinds: list, texts: list, in_motive: list, heading_of: list,
                  headings: list, provisions: list) -> list:
    """Motiv i löpande text: ett stycke (eller en rubrik) som pekar ut en bestämmelse och stycken efter det, fram till nästa
    stycke som pekar ut en bestämmelse, nästa rubrik eller en tabell. Bara avsnitt med temat "Motiv till detaljplanens
    regleringar" söks, och bara bestämmelser som inte redan hittats."""
    taken: set = set()
    found = []
    j = 0
    while j < len(elements):
        free = [p for p in provisions if p.key not in taken]
        hit = _find_anchor(texts[j], free) if in_motive[j] and kinds[j] in ("h", "p") else None
        if hit is None:
            j += 1
            continue
        provision, rest = hit
        body = [rest] if rest.strip() else []
        last = j
        k = j + 1
        while k < len(elements) and in_motive[k] and kinds[k] in ("p", "e"):
            if kinds[k] == "p":
                if _find_anchor(texts[k], [p for p in free if p.key != provision.key]):
                    break
                body.append(texts[k])
                last = k
            k += 1
        first_p = _edge_paragraph(xml, *elements[j], last=False)
        last_p = _edge_paragraph(xml, *elements[last], last=True)
        if first_p and last_p and body:
            taken.add(provision.key)
            path = tuple(t for _, t in _path_at(headings, heading_of[j])) if heading_of[j] is not None else ()
            found.append(Motiv(path, provision.label, " ".join([texts[j]] + body[1:] if rest.strip() else [texts[j]] + body),
                               _paragraph_start(xml, first_p[0]), _paragraph_end(xml, *last_p), texts[j],
                               provision.key, "\n\n".join(body), True))
        j = last + 1
    return found


def _read_zip(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except (zipfile.BadZipFile, OSError) as exc:
        raise DocxError(f"Kunde inte öppna filen som ett Word-dokument (.docx): {exc}") from exc


def _existing_part(parts: dict[str, bytes]) -> Optional[str]:
    """Namnet på en tidigare skapad XML-del för planbeskrivningen i filen, eller None."""
    for name, data in parts.items():
        if re.fullmatch(r"customXml/item\d+\.xml", name) and pb.NAMESPACE.encode("utf-8") in data[:1000]:
            return name
    return None


def _strip_old_bookmarks(xml: str, names: list[str]) -> tuple[str, list[str]]:
    removed = []
    for name in names:
        start = re.search(r'<w:bookmarkStart\b[^>]*\bw:name="' + re.escape(name) + r'"[^>]*/>', xml)
        if not start:
            continue
        ident = re.search(r'\bw:id="(\d+)"', start.group(0)).group(1)
        xml = xml.replace(start.group(0), "", 1)
        xml = re.sub(r'<w:bookmarkEnd\b[^>]*\bw:id="' + ident + r'"[^>]*/>', "", xml, count=1)
        removed.append(name)
    return xml, removed


def _strip_own_comments(parts: dict[str, bytes], xml: str) -> tuple[str, dict[str, bytes]]:
    """Tar bort verktygens egna kommentarer (författare i ``OWN_COMMENT_AUTHORS``, från en tidigare granskningskopia) ur dokumentet och
    ur kommentarsdelen, så att de inte dubbleras eller följer med en leveranskopia. Andras kommentarer lämnas orörda."""
    data = parts.get("word/comments.xml")
    if data is None:
        return xml, {}
    comments = data.decode("utf-8")
    own: set[str] = set()

    def keep_or_drop(match):
        attributes = match.group(1)
        author = re.search(r'\bw:author="([^"]*)"', attributes)
        ident = re.search(r'\bw:id="(\d+)"', attributes)
        if author and ident and html.unescape(author.group(1)) in OWN_COMMENT_AUTHORS:
            own.add(ident.group(1))
            return ""
        return match.group(0)

    comments = re.sub(r"<w:comment\b([^>]*)>.*?</w:comment>", keep_or_drop, comments, flags=re.S)
    if not own:
        return xml, {}
    for ident in own:
        xml = re.sub(rf'<w:commentRange(?:Start|End)\b[^>]*\bw:id="{ident}"[^>]*/>', "", xml)
        xml = re.sub(rf'<w:r\b[^>]*>(?:<w:rPr>(?:(?!</w:rPr>).)*</w:rPr>)?<w:commentReference\b[^>]*\bw:id="{ident}"[^>]*/></w:r>',
                     "", xml)
    return xml, {"word/comments.xml": comments.encode("utf-8")}


def analyse(path: str | Path, provisions: list, overrides: Optional[Overrides] = None,
            cutoff: float = DEFAULT_CUTOFF) -> Analys:
    """Läser planbeskrivningen och föreslår tema, grupp och undergrupp för varje avsnitt samt vilka tabellrader som är
    motiv till vilka bestämmelser. Skriver ingenting."""
    path = Path(path)
    parts = _read_zip(path)
    if "word/document.xml" not in parts or "word/styles.xml" not in parts:
        raise DocxError("Filen är inget Word-dokument (word/document.xml eller word/styles.xml saknas).")
    xml = parts["word/document.xml"].decode("utf-8")
    previous, removed = None, []
    existing = _existing_part(parts)
    if existing:
        try:
            previous, old_items = pb.parse_xml(parts[existing].decode("utf-8"))
            xml, removed = _strip_old_bookmarks(xml, [i.identitet for i in old_items])
        except ValueError:
            previous = None
    xml, parts_override = _strip_own_comments(parts, xml)
    levels = heading_levels(parts["word/styles.xml"].decode("utf-8"))
    try:
        body_lo = xml.index("<w:body>") + len("<w:body>")
        body_hi = xml.rindex("</w:body>")
    except ValueError as exc:
        raise DocxError("Dokumentet saknar brödtext (w:body).") from exc
    elements = [e for e in _spans(xml, body_lo, body_hi) if e[0] != "w:sectPr"]

    headings = []  # (index i elements, nivå, text)
    for i, (name, start, end) in enumerate(elements):
        if name == "w:p":
            level = levels.get(_style(xml, start, end))
            text = " ".join(_text(xml, start, end).split())
            if level and text:
                headings.append((i, level, text))

    sections, stack = [], []
    for n, (i, level, text) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
        last = headings[n + 1][0] if n + 1 < len(headings) else len(elements)
        first_p = _edge_paragraph(xml, *elements[i], last=False)
        last_p = None
        content = False
        for j in range(last - 1, i - 1, -1):
            last_p = last_p or _edge_paragraph(xml, *elements[j], last=True)
        for name, s, e in elements[i + 1:last]:
            if name == "w:tbl" or "<w:drawing" in xml[s:e] or _text(xml, s, e).strip():
                content = True
                break
        if first_p and last_p:
            body = [" ".join(_text(xml, s, e).split()) for name, s, e in elements[i + 1:last] if name == "w:p"]
            sections.append(Avsnitt(tuple(t for _, t in stack), _paragraph_start(xml, first_p[0]),
                                    _paragraph_end(xml, *last_p), content, text="\n\n".join(b for b in body if b)))
    analysis = Analys(xml, sections, [], overrides or Overrides(), provisions, cutoff, removed, previous, path,
                      parts_override)
    analysis.refresh()

    # motiv: tabellrader i avsnitt med temat "Motiv till detaljplanens regleringar"
    for n, (i, level, text) in enumerate(headings):
        section = next((s for s in sections if s.start >= elements[i][1]), None)
        if section is None or section.indelning.tema != pb.MOTIV_TEMA:
            continue
        last = headings[n + 1][0] if n + 1 < len(headings) else len(elements)
        for name, s, e in elements[i + 1:last]:
            if name != "w:tbl":
                continue
            lo, hi = _inner(xml, s, e)
            for _, rs, re_ in (r for r in _spans(xml, lo, hi) if r[0] == "w:tr"):
                rlo, rhi = _inner(xml, rs, re_)
                cells = [c for c in _spans(xml, rlo, rhi) if c[0] == "w:tc"]
                if len(cells) < 2:
                    continue
                cell = cells[1]
                first_p = _edge_paragraph(xml, "w:tc", *cell[1:], last=False)
                last_p = _edge_paragraph(xml, "w:tc", *cell[1:], last=True)
                if not first_p or not last_p:
                    continue
                clo, chi = _inner(xml, *cell[1:])
                paragraphs = [" ".join(_text(xml, ps, pe).split()) for name_, ps, pe in _spans(xml, clo, chi)
                              if name_ == "w:p"]
                text_ = " ".join(" ".join(paragraphs).split())
                if not text_:
                    continue  # tom rad (t.ex. tabellens sista)
                filled = [x for x in paragraphs if x]
                analysis.motives.append(Motiv(
                    tuple(t for _, t in _path_at(headings, n)), _dedupe(_text(xml, *cells[0][1:])), text_,
                    _paragraph_start(xml, first_p[0]), _paragraph_end(xml, *last_p),
                    filled[0], motiv="\n\n".join(filled[1:])))
    analysis.refresh()

    # motiv i löpande text, för bestämmelser som inte redan hittats i en tabell
    kinds, texts, in_motive, heading_of = [], [], [False] * len(elements), [None] * len(elements)
    heading_at = {i: n for n, (i, _, _) in enumerate(headings)}
    for j, (name, s, e) in enumerate(elements):
        if name == "w:p":
            text_ = " ".join(_text(xml, s, e).split())
            kinds.append("h" if j in heading_at else ("p" if text_ else "e"))
            texts.append(text_)
        else:
            kinds.append("t" if name == "w:tbl" else "o")
            texts.append("")
    current_n = None
    current_motive = False
    for j in range(len(elements)):
        if j in heading_at:
            current_n = heading_at[j]
            section = next((s for s in sections if s.start >= elements[j][1]), None)
            current_motive = bool(section and section.indelning.tema == pb.MOTIV_TEMA)
        heading_of[j] = current_n
        in_motive[j] = current_motive
    table_keys = {m.key for m in analysis.motives if m.key is not None}
    analysis.motives += _text_motives(xml, elements, kinds, texts, in_motive, heading_of, headings,
                                      [p for p in provisions if p.key not in table_keys])
    analysis.motives.sort(key=lambda m: m.start)
    analysis.refresh()
    analysis.uncovered = _uncovered(sections, analysis.motives)
    for section in sections:  # en rubrik som är precis en bestämmelse gäller bestämmelseområdet, inte hela planområdet
        if section.taggas:
            key = _heading_provision(section.path[-1], provisions)
            if key is not None:
                section.lage_keys = [key]
    first_heading = headings[0][0] if headings else len(elements)
    analysis.front = sum(1 for name, s, e in elements[:first_heading]
                         if name == "w:tbl" or _text(xml, s, e).strip())
    return analysis


def _uncovered(sections: list, motives: list) -> list:
    """Avsnitt med temat "Motiv till detaljplanens regleringar" som har text men där inget motiv hittats, varken i avsnittet
    självt eller i något avsnitt under det (en inledande text under en rubrik som har motiv under sig räknas inte)."""
    found = []
    for i, section in enumerate(sections):
        if section.indelning.tema != pb.MOTIV_TEMA or not section.has_content:
            continue
        end = section.end
        for later in sections[i + 1:]:
            if len(later.path) <= len(section.path) or later.path[:len(section.path)] != section.path:
                break
            end = max(end, later.end)
        if not any(section.start <= m.start <= end for m in motives):
            found.append(section)
    return found


def _path_at(headings: list, n: int) -> list:
    stack: list = []
    for _, level, text in headings[:n + 1]:
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
    return stack


# -- skriva den taggade kopian ------------------------------------------------------------------------
@dataclass
class Resultat:
    avsnitt: int
    motiv: int
    omatchade_motiv: int
    utan_tagg: list
    version: int
    kommentarer: int = 0  # antal kommentarer i en granskningskopia


@dataclass(frozen=True)
class TagRad:
    """En rad i översikten över taggarna: bokmärket, var i dokumentet det sitter och vad det ger för uppgifter."""
    identitet: str
    rubrik: str
    tema: str
    grupp: str
    undergrupp: str
    lage: str


def lage_text(provisions: list) -> str:
    """Läget som text: vilka bestämmelser (och hur många ytor) ett avsnitt eller ett motiv är kopplat till."""
    names = []
    for provision in provisions:
        name = provision.label or provision.text
        names.append(f"{name} ({len(provision.refs)} ytor)" if len(provision.refs) > 1 else name)
    return "Planbestämmelse " + ", ".join(names)


def _items(analysis: Analys) -> list[tuple[pb.Omfattning, int, int, TagRad]]:
    """Taggarna (med var bokmärket sitter och en rad till översikten) i dokumentets ordning."""
    by_key = {p.key: p for p in analysis.provisions}
    found = []
    for section in analysis.sections:
        if section.taggas:
            i = section.indelning
            chosen = [by_key[k] for k in section.lage_keys if k in by_key and by_key[k].refs]
            if chosen:
                refs = [r for p in chosen for r in p.refs]
                found.append((pb.Omfattning("", i.tema, i.grupp, i.undergrupp, pb.PLANBESTAMMELSE, refs[0],
                                            tuple(refs[1:])), section.start, section.end, " › ".join(section.path),
                              lage_text(chosen)))
            else:
                found.append((pb.Omfattning("", i.tema, i.grupp, i.undergrupp, pb.PLANOMRADE), section.start,
                              section.end, " › ".join(section.path), "Hela planområdet"))
    for motive in analysis.motives:
        provision = by_key.get(motive.key)
        if provision is not None and provision.refs:
            found.append((pb.Omfattning("", pb.MOTIV_TEMA, pb.MOTIV_GRUPP, None, pb.PLANBESTAMMELSE,
                                        provision.refs[0], tuple(provision.refs[1:])), motive.start, motive.end,
                          f"{motive.path[-1] if motive.path else ''} › {motive.label or motive.title[:40]}",
                          lage_text([provision])))
    found.sort(key=lambda f: f[1])
    items = []
    for n, (item, start, end, heading, location) in enumerate(found, 1):
        item = replace(item, identitet=f"{BOOKMARK_PREFIX}{n:03d}")
        row = TagRad(item.identitet, heading, item.tema, item.grupp, item.undergrupp or "", location)
        items.append((item, start, end, row))
    return items


OVERVIEW_COLUMNS = ("Bokmärke", "Rubrik", "Tema", "Grupp", "Undergrupp", "Läge")


def overview_csv(rows: list[TagRad]) -> str:
    """Översikten som semikolonavgränsad text, som Excel i Sverige öppnar direkt."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(OVERVIEW_COLUMNS)
    for row in rows:
        writer.writerow([row.identitet, row.rubrik, row.tema, row.grupp, row.undergrupp, row.lage])
    return out.getvalue()


def purpose_from_document(analysis: Analys) -> str:
    """Detaljplanens syfte så som det står i planbeskrivningen: texten under rubrikerna Detaljplanens syfte › Syfte. Flera
    stycken (och underrubriker) slås ihop med ett mellanslag, eftersom syftet är ett enda textfält. Tom text om det saknas."""
    texts = [s.text for s in analysis.sections
             if (s.indelning.tema, s.indelning.grupp) == ("Detaljplanens syfte", "Syfte") and s.text.strip()]
    return " ".join(" ".join(texts).split())


def motives_from_document(analysis: Analys) -> dict:
    """Motiven som står i planbeskrivningens tabeller, för de bestämmelser de kopplats till: {``Provision.key``: text}.
    Första stycket i en rad är bestämmelsens text och styckena efter det är motivet. Rader utan motivtext tas inte med."""
    found: dict = {}
    for motive in analysis.motives:
        if motive.key is not None and motive.motiv.strip():
            found[motive.key] = (found[motive.key] + "\n\n" if motive.key in found else "") + motive.motiv.strip()
    return found


def overview(analysis: Analys) -> list[TagRad]:
    """Alla taggar som den taggade kopian får, i dokumentets ordning: bokmärke, rubrik, tema, grupp, undergrupp, läge."""
    return [row for _, _, _, row in _items(analysis)]


def _comment_xml(ident: int, item: pb.Omfattning, row: "TagRad", date: str, author: str = COMMENT_AUTHOR) -> str:
    """Kommentaren för en tagg: bokmärkets namn med tema, grupp och undergrupp på första raden och läget på andra."""
    indelning = " › ".join(part for part in (row.tema, row.grupp, row.undergrupp) if part)
    lines = (f"{item.identitet} · {indelning}", f"Läge: {row.lage}")
    paragraphs = "".join(f'<w:p><w:r><w:t xml:space="preserve">{html.escape(line, quote=False)}</w:t></w:r></w:p>'
                         for line in lines)
    return (f'<w:comment w:id="{ident}" w:author="{html.escape(author)}" w:date="{date}" w:initials="{_initials(author)}">{paragraphs}</w:comment>')


def _initials(name: str) -> str:
    return "".join(word[0] for word in name.split()[:3]).upper() or "PB"


def _add_relationship(parts: dict[str, bytes], kind: str, target: str) -> str:
    rels = parts["word/_rels/document.xml.rels"].decode("utf-8")
    rid = "rId" + str(max([int(i) for i in re.findall(r'Id="rId(\d+)"', rels)] + [0]) + 1)
    parts["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>", f'<Relationship Id="{rid}" Type="{kind}" Target="{target}"/></Relationships>').encode("utf-8")
    return rid


def _add_override(parts: dict[str, bytes], part_name: str, content_type: str) -> None:
    content_types = parts["[Content_Types].xml"].decode("utf-8")
    if f'PartName="{part_name}"' not in content_types:
        parts["[Content_Types].xml"] = content_types.replace(
            "</Types>", f'<Override PartName="{part_name}" ContentType="{content_type}"/></Types>').encode("utf-8")


def tag_docx(analysis: Analys, destination: str | Path, plan_identity: str, software_version: str,
             comments: bool = False, software: str = COMMENT_AUTHOR) -> Resultat:
    """Skriver en ny kopia av dokumentet med bokmärken och XML-del. Originalfilen rörs inte.

    Med ``comments`` får varje tagg dessutom en kommentar vid avsnittet (bokmärkets namn, tema, grupp, undergrupp och läge): en
    *granskningskopia* där man i Word ser vilka taggar varje stycke har. Kommentarerna är pluginets egna (författaren
    ``software``) och går att ta bort med ett klick; en leveranskopia ska skrivas utan dem. ``software`` är programmets namn,
    som också skrivs som programvara i XML-delen."""
    destination = Path(destination)
    if analysis.source is not None and destination.resolve() == Path(analysis.source).resolve():
        raise DocxError("Spara den taggade kopian under ett annat namn än originalet.")
    items = _items(analysis)
    if not items:
        raise DocxError("Inget i dokumentet kunde taggas. Kontrollera att rubrikerna är riktiga rubrikformat (Rubrik 1, 2, 3) "
                        "och att temana känns igen; motiv kopplas bara till bestämmelser som finns i planen.")
    found = pb.problems([i for i, _, _, _ in items])
    if found:
        raise DocxError("Taggarna följer inte reglerna:\n" + "\n".join(found))
    parts = _read_zip(Path(analysis.source))
    parts.update(analysis.parts_override)  # pluginets egna kommentarer från en tidigare granskningskopia är borta
    xml = analysis.xml

    next_id = max([int(i) for i in re.findall(r'<w:bookmarkStart\b[^>]*\bw:id="(\d+)"', xml)] + [0]) + 1
    existing_comments = parts.get("word/comments.xml", b"").decode("utf-8")
    next_comment = max([int(i) for i in re.findall(r'<w:comment\b[^>]*\bw:id="(\d+)"', existing_comments)]
                       + [int(i) for i in re.findall(r'<w:commentRangeStart\b[^>]*\bw:id="(\d+)"', xml)] + [-1]) + 1
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inserts, new_comments = [], []
    for n, (item, start, end, row) in enumerate(items):
        bid = next_id + n
        opening = f'<w:bookmarkStart w:id="{bid}" w:name="{item.identitet}"/>'
        closing = f'<w:bookmarkEnd w:id="{bid}"/>'
        if comments:
            cid = next_comment + n
            opening += f'<w:commentRangeStart w:id="{cid}"/>'
            closing = (f'<w:commentRangeEnd w:id="{cid}"/><w:r><w:commentReference w:id="{cid}"/></w:r>' + closing)
            new_comments.append(_comment_xml(cid, item, row, date, software))
        inserts.append((start, opening))
        inserts.append((end, closing))
    for position, insert in sorted(inserts, key=lambda x: x[0], reverse=True):
        xml = xml[:position] + insert + xml[position:]
    parts["word/document.xml"] = xml.encode("utf-8")

    if new_comments:
        if "word/comments.xml" in parts and "</w:comments>" in existing_comments:
            parts["word/comments.xml"] = existing_comments.replace("</w:comments>", "".join(new_comments) + "</w:comments>").encode("utf-8")
        else:
            parts["word/comments.xml"] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                f'<w:comments xmlns:w="{W[1:-1]}">' + "".join(new_comments) + "</w:comments>").encode("utf-8")
            _add_relationship(parts, REL_COMMENTS, "comments.xml")
            _add_override(parts, "/word/comments.xml", CT_COMMENTS)

    header = pb.next_header(analysis.previous, plan_identity, software, software_version)
    custom = pb.build_xml(header, [i for i, _, _, _ in items])
    existing = _existing_part(parts)
    if existing:
        parts[existing] = custom.encode("utf-8")
    else:
        number = max([int(n) for n in re.findall(r"customXml/item(\d+)\.xml", " ".join(parts))] + [0]) + 1
        item_name, props_name = f"customXml/item{number}.xml", f"customXml/itemProps{number}.xml"
        parts[item_name] = custom.encode("utf-8")
        parts[props_name] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            f'<ds:datastoreItem ds:itemID="{{{str(uuid.uuid4()).upper()}}}" xmlns:ds="{DS_NS}"><ds:schemaRefs>'
            f'<ds:schemaRef ds:uri="{pb.NAMESPACE}"/></ds:schemaRefs></ds:datastoreItem>').encode("utf-8")
        parts[f"customXml/_rels/item{number}.xml.rels"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{REL_PROPS}" Target="itemProps{number}.xml"/></Relationships>').encode("utf-8")
        _add_relationship(parts, REL_CUSTOM, f"../customXml/item{number}.xml")
        _add_override(parts, f"/{props_name}", CT_PROPS)

    _write_zip(Path(analysis.source), destination, parts)
    sections = sum(1 for item, _, _, _ in items if item.lage == pb.PLANOMRADE)
    untagged = [" › ".join(s.path) for s in analysis.sections if not s.taggas and s.has_content
                and s.indelning.tema != pb.MOTIV_TEMA]
    return Resultat(sections, len(items) - sections, sum(1 for m in analysis.motives if not _matched(analysis, m)),
                    untagged, header.objektversion, len(new_comments))


def _matched(analysis: Analys, motive: Motiv) -> bool:
    return any(p.key == motive.key and p.refs for p in analysis.provisions)


def _write_zip(source: Path, destination: Path, parts: dict[str, bytes]) -> None:
    """Skriver paketet i samma ordning som originalet (``[Content_Types].xml`` först), nya delar sist."""
    with zipfile.ZipFile(source) as original:
        order = [i.filename for i in original.infolist()]
    order += [n for n in parts if n not in order]
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as out:
        for name in order:
            if name in parts:
                out.writestr(name, parts[name])
    temporary.replace(destination)
