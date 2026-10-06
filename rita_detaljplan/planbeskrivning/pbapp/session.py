"""Det programmet arbetar med: valda filer, analysen av planbeskrivningen och de val man gjort. Ingen Qt här, så att
logiken går att testa för sig. Val sparas i ``store`` (en ordbok med text, i programmet QSettings) så att de finns kvar
nästa gång samma dokument öppnas."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..pbkarna import geometri as geo
from ..pbkarna import planbeskrivning as pb
from ..pbkarna import planbeskrivning_check as ck
from ..pbkarna import planbeskrivning_docx as dx
from ..pbkarna import plankarta as pk
from ..pbkarna import utbyte

from . import APP_NAME, VERSION

# Status för ett avsnitt i listan
RUBRIK, MOTIV, AUTO, EGEN, OSAKER, SAKNAS, GRANSKAD, HOPPAS = (
    "rubrik", "motiv", "auto", "egen", "osaker", "saknas", "granskad", "hoppas")
STATUS_TEXT = {AUTO: "Automatisk", EGEN: "Egen rubrik", OSAKER: "Osäker", SAKNAS: "Ej taggad", GRANSKAD: "Granskad",
               HOPPAS: "Taggas inte", MOTIV: "Motiv", RUBRIK: ""}
NEEDS_LOOK = (OSAKER, SAKNAS)

# Status för ett motiv
KOPPLAT_AUTO, KOPPLAT, EJ_KOPPLAT = "auto", "kopplat", "ej"


class SessionError(ValueError):
    pass


@dataclass
class Store:
    """Enkel lagring av text per nyckel. Programmet använder QSettings via ``get``/``put``."""
    get: Callable[[str], Optional[str]]
    put: Callable[[str, str], None]

    @classmethod
    def memory(cls) -> "Store":
        data: dict = {}
        return cls(data.get, data.__setitem__)


class Host:
    """Ett program som programmet körs inuti och som själv har planen, t.ex. Rita Detaljplan i QGIS. Planen behöver då
    inte väljas som fil, och syfte och motiv kan skrivas direkt till planen."""
    name = ""  # visas i gränssnittet, t.ex. "QGIS"

    def load_plan(self) -> tuple[pk.Plan, Optional[geo.Karta]]:
        """Den aktiva planen och dess ytor. Kastar ``SessionError`` med en förklaring om det inte finns någon."""
        raise NotImplementedError

    def write_back(self, purpose: str, motives: dict) -> str:
        """Skriver syftet (tom text = lämna orört) och motiven ({``Provision.key``: text}) till planen. Returnerar ett
        meddelande om vad som gjordes."""
        raise NotImplementedError


class Session:
    def __init__(self, store: Optional[Store] = None, host: Optional[Host] = None):
        self.store = store or Store.memory()
        self.host = host
        self.docx: Optional[Path] = None
        self.plankarta: Optional[Path] = None
        self.plans: list[pk.Plan] = []
        self.plan: Optional[pk.Plan] = None
        self.karta: Optional[geo.Karta] = None
        self.analysis: Optional[dx.Analys] = None
        self.approved: set = set()  # path_key för avsnitt man godkänt
        self.skipped: set = set()  # path_key för avsnitt som inte ska taggas
        self.manual_motives: dict = {}  # motivets signatur -> bestämmelsens nyckel som text ("" = ingen)
        self.manual_lage: dict = {}  # path_key -> [bestämmelsens nyckel som text]

    # -- filer -------------------------------------------------------------------------------------
    def load_plankarta(self, path: str | Path) -> list[pk.Plan]:
        plans = pk.read_plankarta(path)
        if not plans:
            raise SessionError("Filen innehåller ingen plan med bestämmelser.")
        self.plankarta, self.plans = Path(path), plans
        self.choose_plan(0)
        return plans

    def load_from_host(self) -> pk.Plan:
        """Hämtar (eller hämtar om) planen från värdprogrammet. Gjorda val i dokumentet finns kvar."""
        plan, karta = self.host.load_plan()
        self.plankarta, self.plans, self.plan, self.karta = None, [plan], plan, karta
        if self.docx is not None:
            self.analyse()
        return plan

    def write_back(self) -> str:
        """Skriver syftet och motiven i planbeskrivningen till planen i värdprogrammet."""
        if self.host is None or self.analysis is None:
            raise SessionError("Det finns ingen plan att skriva till.")
        return self.host.write_back(dx.purpose_from_document(self.analysis), dx.motives_from_document(self.analysis))

    def choose_plan(self, index: int) -> None:
        self.plan = self.plans[index]
        self.karta = geo.read_karta(self.plan.kalla, self.plan.identitet)
        if self.docx is not None:
            self.analyse()

    def load_docx(self, path: str | Path) -> None:
        self.docx = Path(path)
        self.analyse()

    @property
    def provisions(self) -> list:
        return self.plan.provisions if self.plan else []

    def analyse(self) -> dx.Analys:
        if self.docx is None:
            raise SessionError("Välj planbeskrivningen först.")
        try:
            self.analysis = dx.analyse(self.docx, self.provisions, self._overrides())
        except (dx.DocxError, OSError, KeyError) as exc:
            self.analysis = None
            raise SessionError(f"Planbeskrivningen kunde inte läsas: {exc}") from exc
        self._restore()
        return self.analysis

    @property
    def ready(self) -> bool:
        return self.analysis is not None

    # -- minne -------------------------------------------------------------------------------------
    def _overrides(self) -> dx.Overrides:
        return dx.Overrides.from_json(self.store.get("overrides") or "")

    def _doc_key(self) -> str:
        return "dokument/" + str(self.docx.resolve()).lower() if self.docx else ""

    def _restore(self) -> None:
        try:
            saved = json.loads(self.store.get(self._doc_key()) or "{}")
        except ValueError:
            saved = {}
        self.approved = set(saved.get("godkanda") or [])
        self.skipped = set(saved.get("hoppas") or [])
        self.manual_motives = dict(saved.get("motiv") or {})
        self.manual_lage = dict(saved.get("lage") or {})
        self._apply_motives()
        by_text = {pk.key_text(p.key): p.key for p in self.provisions if p.refs}
        for section in self.analysis.sections:
            wanted = self.manual_lage.get(dx.path_key(section.path))
            if wanted is not None:
                section.lage_keys = [by_text[k] for k in wanted if k in by_text]

    def _apply_motives(self) -> None:
        """Kopplingar man gjort för hand går före de automatiska (också efter att analysen räknats om)."""
        by_text = {pk.key_text(p.key): p.key for p in self.provisions if p.refs}
        for motive in self.analysis.motives:
            wanted = self.manual_motives.get(self.signature(motive))
            if wanted == "":
                motive.key = None
            elif wanted in by_text:
                motive.key = by_text[wanted]

    def save(self) -> None:
        if self.analysis is None:
            return
        self.store.put("overrides", self.analysis.overrides.to_json())
        self.store.put(self._doc_key(), json.dumps({
            "plankarta": str(self.plankarta or ""), "godkanda": sorted(self.approved), "hoppas": sorted(self.skipped),
            "motiv": self.manual_motives, "lage": self.manual_lage}, ensure_ascii=False))

    # -- avsnitt -------------------------------------------------------------------------------------
    @staticmethod
    def key(section: dx.Avsnitt) -> str:
        return dx.path_key(section.path)

    def status(self, section: dx.Avsnitt) -> str:
        i = section.indelning
        if i.tema == pb.MOTIV_TEMA:
            return MOTIV
        if not section.has_content:
            return RUBRIK
        key = self.key(section)
        if key in self.skipped:
            return HOPPAS
        if not section.taggas:
            return SAKNAS
        if key in self.approved or section.status == dx.SPARAD:
            return GRANSKAD
        if section.status == dx.NARA:
            return OSAKER
        if section.status == dx.EGEN:
            return EGEN
        return AUTO

    def why(self, section: dx.Avsnitt) -> str:
        i, heading = section.indelning, section.path[-1]
        status = self.status(section)
        if status == HOPPAS:
            return "Du har valt att avsnittet inte ska taggas. Det får inget bokmärke."
        if i.tema is None:
            return f"Rubriken \"{section.path[0]}\" känns inte igen som ett tema i BFS 2020:8. Välj tema, eller välj att " \
                   "avsnittet inte ska taggas."
        if not section.taggas:
            return "Texten ligger direkt under temarubriken och saknar grupp. Välj en grupp."
        if section.status == dx.SPARAD:
            return "Samma val som du gjort tidigare för den här rubriken."
        if section.status == dx.NARA:
            return f"Rubriken \"{heading}\" liknar en rubrik i BFS 2020:8 men är inte exakt lika. Kontrollera förslaget."
        if section.status == dx.EGEN:
            own = i.undergrupp if len(section.path) >= 3 else i.grupp
            return f"\"{own}\" finns inte i BFS 2020:8 och blir en egen grupp. Det är tillåtet, men välj en befintlig om " \
                   "någon passar."
        return "Rubrikerna motsvarar tema och grupp i BFS 2020:8."

    def tagged_sections(self) -> list[dx.Avsnitt]:
        """Avsnitten som visas i listan: allt med text utom motiven (de hanteras för sig)."""
        if self.analysis is None:
            return []
        return [s for s in self.analysis.sections if self.status(s) not in (RUBRIK, MOTIV)]

    def set_indelning(self, section: dx.Avsnitt, tema: str, grupp: str, undergrupp: str) -> None:
        """Sparar valet för rubrikerna (gäller också nästa dokument med samma rubriker), som pluginet gör."""
        overrides = self.analysis.overrides
        tema, grupp, undergrupp = (tema or "").strip(), (grupp or "").strip(), (undergrupp or "").strip()
        if tema:
            overrides.tema[dx.path_key(section.path[:1])] = tema
        if len(section.path) == 1 and grupp:
            overrides.grupp[dx.path_key(section.path[:1]) + "|"] = grupp
        if len(section.path) >= 2 and grupp:
            overrides.grupp[dx.path_key(section.path[:2])] = grupp
        if len(section.path) >= 3:
            if undergrupp:
                overrides.undergrupp[dx.path_key(section.path[:3])] = undergrupp
            else:
                overrides.undergrupp.pop(dx.path_key(section.path[:3]), None)
        self.analysis.refresh()
        self._apply_motives()
        self.skipped.discard(self.key(section))
        self.approved.add(self.key(section))
        self.save()

    def approve(self, section: dx.Avsnitt) -> None:
        if section.taggas:
            self.approved.add(self.key(section))
            self.skipped.discard(self.key(section))
            self.save()

    def skip(self, section: dx.Avsnitt, skip: bool = True) -> None:
        (self.skipped.add if skip else self.skipped.discard)(self.key(section))
        self.save()

    def set_lage(self, section: dx.Avsnitt, keys: list) -> None:
        section.lage_keys = list(keys)
        self.manual_lage[self.key(section)] = [pk.key_text(k) for k in keys]
        self.save()

    def counts(self) -> dict:
        found = {s: 0 for s in STATUS_TEXT}
        for section in self.tagged_sections():
            found[self.status(section)] += 1
        return found

    # -- motiv -------------------------------------------------------------------------------------
    @staticmethod
    def signature(motive: dx.Motiv) -> str:
        return dx.path_key(motive.path) + "||" + dx.path_key((motive.label or motive.title,))

    def provision(self, key) -> Optional[dx.Provision]:
        return next((p for p in self.provisions if p.key == key and p.refs), None)

    def motive_status(self, motive: dx.Motiv) -> str:
        if self.provision(motive.key) is None:
            return EJ_KOPPLAT
        return KOPPLAT if self.signature(motive) in self.manual_motives else KOPPLAT_AUTO

    def link(self, motive: dx.Motiv, key) -> None:
        """Kopplar motivet till bestämmelsen ``key`` (None = ta bort kopplingen)."""
        motive.key = key
        self.manual_motives[self.signature(motive)] = pk.key_text(key) if key is not None else ""
        self.save()

    def motives_for(self, key) -> list[dx.Motiv]:
        return [m for m in self.analysis.motives if m.key == key] if self.analysis else []

    def provisions_without_motive(self) -> list[dx.Provision]:
        linked = {m.key for m in self.analysis.motives} if self.analysis else set()
        return [p for p in self.provisions if p.refs and not p.technical and p.key not in linked]

    # -- kontroll och export -----------------------------------------------------------------------------
    def findings(self) -> list[ck.Fynd]:
        if self.analysis is None:
            return []
        skipped = {" › ".join(s.path) for s in self.analysis.sections if self.key(s) in self.skipped}
        return [f for f in ck.check(self.analysis)
                if not (f.var in skipped and f.text.startswith("Texten taggas inte"))]

    def section_for(self, where: str) -> Optional[dx.Avsnitt]:
        if self.analysis is None or not where:
            return None
        return next((s for s in self.analysis.sections if " › ".join(s.path) == where), None)

    def _header(self) -> pb.Header:
        return pb.next_header(self.analysis.previous, self.plan.identitet if self.plan else "", APP_NAME, VERSION)

    def xml_preview(self) -> str:
        """XML-delen som leveranskopian får, eller en förklaring om den inte går att skapa än."""
        if self.analysis is None:
            return ""
        items = [item for item, _, _, _ in dx._items(self.analysis)]
        try:
            return pb.build_xml(self._header(), items)
        except ValueError as exc:
            return f"<!-- XML-delen kan inte skapas än:\n{exc}\n-->"

    def default_name(self, suffix: str, extension: str = ".docx") -> Path:
        return self.docx.with_name(self.docx.stem + suffix + extension)

    def write_copy(self, path: str | Path, review: bool = False) -> dx.Resultat:
        if self.analysis is None or self.plan is None:
            raise SessionError("Välj både planbeskrivning och plankarta först.")
        try:
            return dx.tag_docx(self.analysis, path, self.plan.identitet, VERSION, comments=review, software=APP_NAME)
        except (dx.DocxError, ValueError, OSError) as exc:
            raise SessionError(str(exc)) from exc

    def write_overview(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(dx.overview_csv(dx.overview(self.analysis)), encoding="utf-8-sig")
        return path

    def write_exchange(self, path: str | Path) -> dict:
        if self.analysis is None or self.plan is None:
            raise SessionError("Välj både planbeskrivning och plankarta först.")
        data = utbyte.build(self.analysis, self.plan.identitet, APP_NAME)
        utbyte.write(path, data)
        return data
