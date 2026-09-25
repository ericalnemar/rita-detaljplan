"""Validering av en detaljplan mot Lantmäteriets regler (se docs/ngp-regler.md) inför leverans till NGP.

Valideringen läser planen (``collect``) och kontrollerar den (``validate``); den ändrar ingenting. Varje avvikelse är
ett ``Issue`` med allvarlighet:

  * ``fel``      – leveransen stoppas av NGP (eller pluginets egen regel bryts),
  * ``varning``  – NGP varnar, eller något bör ses över,
  * ``info``     – något som återstår att fylla i men som inte går att göra i pluginet än.

Geometrireglerna räknar med 10 cm tolerans åt båda håll, som NGP.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from qgis.core import NULL, QgsGeometry, QgsProject

from . import bestammelse as bm
from . import catalog as cat
from . import codelists as cl
from . import kommuner, rules
from .assignments import read_rows
from .project import find_layer
from .requirements import REQUIRED_PLAN_FIELDS

ERROR, WARNING, INFO = "fel", "varning", "info"
SEVERITIES = (ERROR, WARNING, INFO)
TOLERANCE = rules.TOLERANCE  # 0,10 m
MIN_AREA = rules.MIN_OVERLAP  # m²: mindre än så är avrundningsfel
SMALL_OVERLAP = 5.0  # m²: mindre överlapp varnar (DP-Krav-0013)
NARROW_HALF_WIDTH = 0.25  # m: ytor som försvinner när de krymps så mycket är smalare än 0,5 m (DP-Krav-0014)
NEAR_NEW = 0.5  # m (DP-Krav-0011): planer påbörjade efter 2021
NEAR_OLD = 2.0  # m (DP-Krav-0012): planer påbörjade före 2022
LAGA_KRAFT = "laga kraft"
NEW_PLAN_FROM = date(2022, 1, 1)

TABLE_TITLES = {"detaljplan": "Planområde", "anvandning_yta": "Användningsområde", "egenskap_yta": "Egenskapsområde",
                "egenskap_linje": "Egenskapslinje", "bestammelse": "Bestämmelse", "beslutsinformation": "Beslut",
                "dokument": "Dokument"}
_TABLE_ORDER = {name: i for i, name in enumerate(TABLE_TITLES)}
_AREA_TABLES = ("anvandning_yta", "egenskap_yta", "egenskap_linje")


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str  # regelns kod hos Lantmäteriet (DP-0002 …), eller tom
    text: str
    table: Optional[str] = None  # var felet finns: ytlager (för att kunna visa det i kartan) eller tabell
    fid: Optional[int] = None

    @property
    def where(self) -> str:
        return TABLE_TITLES.get(self.table or "", "Planen")

    @property
    def locatable(self) -> bool:
        """Kan visas i kartan (hör till en yta)."""
        return self.table in ("detaljplan", *_AREA_TABLES) and self.fid is not None


@dataclass
class Area:
    """En yta eller linje ur ett planlager."""
    table: str
    fid: int
    identity: Optional[str]
    geometry: QgsGeometry
    attrs: dict = field(default_factory=dict)

    @property
    def is_area(self) -> bool:
        return self.table != "egenskap_linje"


@dataclass
class PlanData:
    """Allt valideringen behöver, som vanliga värden (går att bygga i tester utan lager)."""
    plan: Optional[Area] = None  # planområdet (delytorna hopslagna)
    areas: list[Area] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)  # tilldelade bestämmelser (tabellen bestammelse)
    beslut: list[dict] = field(default_factory=list)
    dokument: list[dict] = field(default_factory=list)
    meta_kommun: str = ""  # kommunen planen skapades för
    epsg: int = 3006  # planens koordinatsystem (SWEREF 99-projektion)

    def of(self, table: str) -> list[Area]:
        return [a for a in self.areas if a.table == table]


# -- läsa planen ----------------------------------------------------------------------------
def _clean(value):
    if value == NULL or value is None:
        return None
    if hasattr(value, "toUTC") and hasattr(value, "isValid"):  # QDateTime: exakt tidpunkt, i UTC
        return value.toUTC().toString("yyyy-MM-ddTHH:mm:ss'Z'") if value.isValid() else None
    if hasattr(value, "toString") and hasattr(value, "isValid"):  # QDate
        return value.toString("yyyy-MM-dd") if value.isValid() else None
    return value


def _attrs(feature) -> dict:
    return {name: _clean(value) for name, value in zip([f.name() for f in feature.fields()], feature.attributes())}


def _table_rows(project: QgsProject, table: str) -> list[dict]:
    layer = find_layer(project, table)
    return [_attrs(f) for f in layer.getFeatures()] if layer is not None else []


def collect(project: QgsProject) -> PlanData:
    """Läser planen ur projektets lager (inklusive osparade ändringar)."""
    data = PlanData()
    plan_layer = find_layer(project, "detaljplan")
    if plan_layer is not None:
        features = list(plan_layer.getFeatures())
        if features:
            merged = rules.plan_geometry(plan_layer)
            first = min(features, key=lambda f: (f.id() < 0, abs(f.id())))  # det först ritade planområdet bär planens id
            data.plan = Area("detaljplan", first.id(), _clean(first["objektidentitet"]),
                             merged if merged is not None else first.geometry(), _attrs(first))
    for table in _AREA_TABLES:
        layer = find_layer(project, table)
        if layer is None:
            continue
        for feature in layer.getFeatures():
            data.areas.append(Area(table, feature.id(), _clean(feature["objektidentitet"]), feature.geometry(),
                                   _attrs(feature)))
    data.rows = read_rows(project)
    secondary = {a.identity for a in data.areas if a.table == "egenskap_yta" and a.attrs.get("sekundar")}
    for row in data.rows:  # bestämmelser på sekundära egenskapsytor levereras med sekundarEgenskapsgrans
        if row.get("tabell") == "egenskap_yta" and row.get("yta") in secondary:
            row["sekundarEgenskapsgrans"] = True
    data.beslut = _table_rows(project, "beslutsinformation")
    data.dokument = _table_rows(project, "dokument")
    data.meta_kommun = _created_for(plan_layer)
    if plan_layer is not None and plan_layer.crs().isValid():
        data.epsg = int(plan_layer.crs().postgisSrid()) or 3006
    return data


def _created_for(plan_layer) -> str:
    """Kommunen planen skapades för: standardvärdet på kommunfältet (satt vid skapandet ur planens metadata)."""
    if plan_layer is None:
        return ""
    index = plan_layer.fields().indexOf("kommun")
    expression = plan_layer.defaultValueDefinition(index).expression() if index >= 0 else ""
    return expression[1:-1].replace("''", "'") if len(expression) >= 2 and expression[0] == expression[-1] == "'" else ""


# -- små hjälpmedel -------------------------------------------------------------------------
def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _to_date(value) -> Optional[date]:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _union(geometries: Iterable[QgsGeometry]) -> Optional[QgsGeometry]:
    geometries = [g for g in geometries if g is not None and not g.isNull() and not g.isEmpty()]
    return QgsGeometry.unaryUnion(geometries) if geometries else None


def _m2(value: float) -> str:
    return f"{value:,.1f} m²".replace(",", " ")


def plan_started(data: PlanData) -> Optional[date]:
    """Datum då planen påbörjades (tidigaste datumPaborjat i beslutsinformationen), om det är angivet."""
    dates = [d for d in (_to_date(b.get("datumPaborjat")) for b in data.beslut) if d]
    return min(dates) if dates else None


def is_new_plan(data: PlanData) -> bool:
    """Planer påbörjade efter 2021-12-31 (eller utan angivet startdatum) följer de skarpare reglerna."""
    started = plan_started(data)
    return started is None or started >= NEW_PLAN_FROM


# -- kontroller -----------------------------------------------------------------------------
def check_plan(data: PlanData) -> list[Issue]:
    issues: list[Issue] = []
    if data.plan is None:
        return [Issue(ERROR, "DP-0002", "Planområdet är inte ritat.", "detaljplan")]
    attrs, table, fid = data.plan.attrs, "detaljplan", data.plan.fid
    for name, label in REQUIRED_PLAN_FIELDS:
        if _blank(attrs.get(name)):
            issues.append(Issue(ERROR, "", f"{label} saknas i planens uppgifter.", table, fid))
    kommun = attrs.get("kommun")
    if not _blank(kommun):
        if kommuner.by_name(kommun) is None:
            issues.append(Issue(ERROR, "", f"Kommunen {kommun!r} finns inte i Sveriges kommuner.", table, fid))
        elif data.meta_kommun and kommuner.by_name(data.meta_kommun) and \
                kommuner.by_name(data.meta_kommun) != kommuner.by_name(kommun):
            issues.append(Issue(ERROR, "", f"Kommunen i planens uppgifter ({kommun}) stämmer inte med kommunen planen "
                                f"skapades för ({data.meta_kommun}).", table, fid))
    if is_new_plan(data):
        if plan_started(data) is None:
            issues.append(Issue(WARNING, "", "Datum påbörjat saknas. Det krävs för planer påbörjade efter 2021 och "
                                "anges i beslutsinformationen inför leverans.", "beslutsinformation"))
        for name, label in (("lagesmetodTyp", "Lägesbestämningsmetod i plan"),
                            ("tidpunktForLagesbestamning", "Tidpunkt för lägesbestämning i plan")):
            if _blank(attrs.get(name)):
                issues.append(Issue(ERROR, "", f"{label} saknas (obligatoriskt för planer påbörjade efter 2021).",
                                    table, fid))
    return issues


def check_implementation(data: PlanData) -> list[Issue]:
    """Varje detaljplan ska ha en genomförandetid, och den ska vara mellan fem och femton år (PBL 4 kap. 21 §)."""
    if data.plan is None:
        return []
    months = []
    for beslut in data.beslut:
        try:
            months.append(int(beslut.get("genomforandetid")))
        except (TypeError, ValueError):
            pass
    months = [m for m in months if m > 0]
    table = "detaljplan"
    if not months:
        return [Issue(ERROR, "", "Genomförandetid saknas: varje detaljplan ska ha en genomförandetid (anges i planens "
                      "uppgifter).", table, data.plan.fid)]
    if any(not 60 <= m <= 180 for m in months):
        return [Issue(WARNING, "", "Genomförandetiden ska vara lägst fem och högst femton år (PBL 4 kap. 21 §).",
                      table, data.plan.fid)]
    return []


def check_position_data(data: PlanData) -> list[Issue]:
    """Osäkert läge får inte anges (DP-0010); vertikal avgränsning bara för ytor (DP-0015/0016)."""
    issues = []
    for area in ([data.plan] if data.plan else []) + data.areas:
        if not _blank(area.attrs.get("absolutLagesosakerhetPlan")):
            issues.append(Issue(ERROR, "DP-0010", "Absolut lägesosäkerhet får inte anges.", area.table, area.fid))
    by_identity = {(a.table, a.identity): a for a in data.areas}
    for row in data.rows:
        if row.get("tabell") == "egenskap_linje" and not _blank(row.get("vertikalAvgransning")):
            line = by_identity.get(("egenskap_linje", row.get("yta")))
            issues.append(Issue(ERROR, "DP-0015", "Vertikal avgränsning får bara anges för ytor, inte linjer.",
                                "egenskap_linje", line.fid if line else None))
    return issues


def check_geometry(data: PlanData) -> list[Issue]:
    issues: list[Issue] = []
    everything = ([data.plan] if data.plan else []) + data.areas
    for area in everything:
        geometry = area.geometry
        if geometry is None or geometry.isNull() or geometry.isEmpty():
            issues.append(Issue(ERROR, "", "Ytan saknar geometri.", area.table, area.fid))
            continue
        if area.is_area and not geometry.isGeosValid():
            issues.append(Issue(ERROR, "DP-Krav-0018", f"Gränsen korsar sig själv eller är ogiltig "
                                f"({geometry.lastError() or 'ogiltig geometri'}).", area.table, area.fid))
        elif not area.is_area and not geometry.isSimple():
            issues.append(Issue(ERROR, "DP-Krav-0018", "Linjen korsar sig själv.", area.table, area.fid))
    if data.plan is None or data.plan.geometry is None:
        return issues

    plan = data.plan.geometry
    uses = data.of("anvandning_yta")
    use_union = _union(a.geometry for a in uses)
    if use_union is None:
        issues.append(Issue(ERROR, "DP-0002", "Planområdet saknar användning: hela ytan ska ha en användningsbestämmelse.",
                            "detaljplan", data.plan.fid))
    else:
        if plan.difference(use_union.buffer(TOLERANCE, 4)).area() > MIN_AREA:  # 10 cm tolerans avgör
            uncovered = plan.difference(use_union).area()  # men den rapporterade ytan är den verkliga
            issues.append(Issue(ERROR, "DP-0002", f"{_m2(uncovered)} av planområdet saknar användning.", "detaljplan",
                                data.plan.fid))
        for use in uses:
            outside = use.geometry.difference(plan.buffer(TOLERANCE, 4)).area()
            if outside > MIN_AREA:
                issues.append(Issue(ERROR, "DP-0003", f"{_m2(outside)} av användningen ligger utanför planområdet.",
                                    use.table, use.fid))
    issues += _pairwise(uses, is_use=True, near=NEAR_NEW if is_new_plan(data) else NEAR_OLD,
                        near_code="DP-Krav-0011" if is_new_plan(data) else "DP-Krav-0012")
    issues += _pairwise(data.of("egenskap_yta"), is_use=False, near=None, near_code="")

    for prop in data.of("egenskap_yta"):
        if use_union is None:
            continue
        outside = prop.geometry.difference(use_union.buffer(TOLERANCE, 4)).area()
        if outside > MIN_AREA:
            issues.append(Issue(ERROR, "", f"{_m2(outside)} av egenskapsområdet ligger utanför användningsområdena.",
                                prop.table, prop.fid))
    for line in data.of("egenskap_linje"):
        if use_union is None:
            continue
        padded = use_union.buffer(TOLERANCE, 4)
        outside = line.geometry.difference(padded).length()
        if outside > TOLERANCE:
            issues.append(Issue(ERROR, "", f"{outside:.1f} m av linjen ligger utanför användningsområdena.",
                                line.table, line.fid))
    for area in uses + data.of("egenskap_yta"):
        if not area.geometry.isEmpty() and area.geometry.area() > MIN_AREA \
                and area.geometry.buffer(-NARROW_HALF_WIDTH, 2).isEmpty():
            issues.append(Issue(WARNING, "DP-Krav-0014", "Ytan är onormalt smal (smalare än 0,5 m).", area.table,
                                area.fid))
    return issues


def _pairwise(areas: list[Area], is_use: bool, near: Optional[float], near_code: str) -> list[Issue]:
    """Överlapp mellan ytor i samma lager, och (för användning) glapp som är smalare än ``near`` meter."""
    issues = []
    for i, a in enumerate(areas):
        for b in areas[i + 1:]:
            ga, gb = a.geometry, b.geometry
            if ga.isEmpty() or gb.isEmpty():
                continue
            overlap = ga.intersection(gb).area() if ga.boundingBoxIntersects(gb) else 0.0
            if overlap > MIN_AREA:
                if is_use and overlap >= SMALL_OVERLAP:
                    issues.append(Issue(ERROR, "DP-Krav-0013", f"Användningsområden överlappar varandra "
                                        f"({_m2(overlap)}).", a.table, a.fid))
                elif overlap < SMALL_OVERLAP:
                    issues.append(Issue(WARNING, "DP-Krav-0013", f"{_m2(overlap)} överlapp med ett annat "
                                        f"{'användningsområde' if is_use else 'egenskapsområde'} (mindre än "
                                        f"{SMALL_OVERLAP:.0f} m²).", a.table, a.fid))
            elif near and 0 < ga.distance(gb) < near:
                issues.append(Issue(WARNING, near_code, f"Glapp på {ga.distance(gb) * 100:.0f} cm mot ett annat "
                                    f"användningsområde (bör vara minst {near:g} m eller inget alls).", a.table, a.fid))
    return issues


def check_hierarchy(data: PlanData) -> list[Issue]:
    issues: list[Issue] = []
    rows_by_area: dict[tuple, list[dict]] = {}
    for row in data.rows:
        rows_by_area.setdefault((row.get("tabell"), row.get("yta")), []).append(row)
    uses = data.of("anvandning_yta")
    for area in data.areas:
        count = len(rows_by_area.get((area.table, area.identity), []))
        if not count:
            issues.append(Issue(ERROR, "", "Saknar bestämmelse.", area.table, area.fid))
    for use in uses:
        forms = {r.get("anvandningsform") for r in rows_by_area.get((use.table, use.identity), [])
                 if r.get("anvandningsform")}
        if len(forms) > 1:
            issues.append(Issue(ERROR, "", "Användningen är både " + " och ".join(sorted(f.lower() for f in forms)) +
                                ": en yta har en användningsform.", use.table, use.fid))
    for prop in data.of("egenskap_yta") + data.of("egenskap_linje"):
        forms = {r.get("anvandningsform") for r in rows_by_area.get((prop.table, prop.identity), [])
                 if r.get("anvandningsform") and r.get("anvandningsform") != "Planområdet"}
        if not forms or prop.geometry.isEmpty():
            continue
        under = set()
        for use in uses:
            hit = use.geometry.intersection(prop.geometry)
            touching = hit.area() > MIN_AREA if prop.is_area else use.geometry.distance(prop.geometry) <= TOLERANCE
            if touching:
                under.update(r.get("anvandningsform") for r in rows_by_area.get((use.table, use.identity), [])
                             if r.get("anvandningsform"))
        wrong = forms - under
        if under and wrong:
            issues.append(Issue(ERROR, "", f"Bestämmelsen gäller {', '.join(sorted(f.lower() for f in wrong))} men "
                                f"användningen under är {', '.join(sorted(f.lower() for f in under))}.",
                                prop.table, prop.fid))
    return issues


def check_rows(data: PlanData, catalog: Optional[cat.Catalog]) -> list[Issue]:
    issues: list[Issue] = []
    areas = {(a.table, a.identity): a for a in data.areas}
    for row in data.rows:
        area = areas.get((row.get("tabell"), row.get("yta")))
        table, fid = (area.table, area.fid) if area else (row.get("tabell"), None)
        name = row.get("bestammelsekod") or row.get("beteckning") or "bestämmelse"
        if area is None:
            issues.append(Issue(WARNING, "", f"Bestämmelsen {name} hör till en yta som inte finns längre (tas bort "
                                "vid sparande).", "bestammelse"))
            continue
        reference = row.get("planbestammelsekatalogreferens")
        if _blank(reference):
            issues.append(Issue(ERROR, "", f"Bestämmelsen {name} saknar koppling till planbestämmelsekatalogen.",
                                table, fid))
            continue
        if _blank(row.get("bestammelseformulering")):
            issues.append(Issue(ERROR, "", f"Bestämmelsen {name} saknar formulering.", table, fid))
        if row.get("avviker"):
            issues.append(Issue(WARNING, "DP-Krav-0017", f"Formuleringen för {name} avviker från katalogens.", table,
                                fid))
        entry = catalog.get(reference) if catalog is not None else None
        if entry is None:
            if catalog is not None:
                issues.append(Issue(WARNING, "", f"Bestämmelsen {name} finns inte i den laddade katalogen "
                                    "(uppdatera katalogen).", table, fid))
            continue
        if entry.layer_name != row.get("tabell"):
            issues.append(Issue(ERROR, "", f"Bestämmelsen {name} hör till en annan typ av yta.", table, fid))
        values = bm.values_from_attributes(entry, row.get("bestammelsevarde"))
        formulation = row.get("bestammelseformulering") if row.get("avviker") else None
        problems = bm.check(entry, values, formulation)
        problems += [p for p in _stored_unit_problems(entry, row.get("bestammelsevarde")) if p not in problems]
        for problem in problems:
            code = "DP-0009" if ("Värdetyp" in problem or "Enhet" in problem) else "DP-0022"
            issues.append(Issue(ERROR, code, f"{name}: {problem}", table, fid))
        decimals = [v for v in entry.variables if v.datatype == "decimaltal"]
        if len(decimals) > 1 and "lutning" not in entry.formulering.lower():
            issues.append(Issue(WARNING, "", f"{name} har fler än ett decimaltal.", table, fid))
        if entry.is_technical:
            for label, value, code in (("formuleringen", row.get("bestammelseformulering"), "DP-0019"),
                                       ("motivet", row.get("motiv"), "DP-0020")):
                if (value or "").strip() != cat.TECHNICAL_FORMULATION:
                    issues.append(Issue(ERROR, code, f"För tekniska anläggningar ska {label} vara exakt "
                                        f"\"{cat.TECHNICAL_FORMULATION}\".", table, fid))
    return issues


def _stored_unit_problems(entry: cat.CatalogEntry, stored_json) -> list[str]:
    """Decimaltal ska vara lagrade med värdetyp och enhet (DP-0009); läser det som faktiskt är sparat, inte
    standardvärdena som fylls i när en bestämmelse öppnas för ändring."""
    try:
        stored = json.loads(stored_json) if stored_json else []
    except (TypeError, json.JSONDecodeError):
        return []
    decimals = {var.name for var in entry.variables if var.datatype == "decimaltal"}
    problems = []
    for item in stored if isinstance(stored, list) else []:
        if not isinstance(item, dict) or item.get("beskrivning") not in decimals or _blank(item.get("variabelvarde")):
            continue
        if item.get("vardetyp") not in cl.VARDETYP:
            problems.append(f"Värdetyp (min/max/exakt) saknas för [{item.get('beskrivning')}].")
        if item.get("enhet") not in cl.ENHET:
            problems.append(f"Enhet saknas för [{item.get('beskrivning')}].")
    return problems


def check_laga_kraft(data: PlanData) -> list[Issue]:
    """Kraven som gäller när planen har status laga kraft (DP-0005, DP-0014, DP-0017)."""
    if data.plan is None or data.plan.attrs.get("status") != LAGA_KRAFT:
        return []
    issues = []
    table, fid = "detaljplan", data.plan.fid
    code = "DP-0005"
    if _blank(data.plan.attrs.get("beteckning")):
        issues.append(Issue(ERROR, code, "Planen saknar beteckning (krävs vid laga kraft).", table, fid))
    roles = {d.get("roll"): d for d in data.dokument}
    if "planbeskrivning" not in roles:
        issues.append(Issue(ERROR, code, "Planbeskrivning saknas bland dokumenten (krävs vid laga kraft).", "dokument"))
    if not any(d.get("roll") == "beslutshandling" and d.get("innehall") == "plankarta" for d in data.dokument):
        issues.append(Issue(ERROR, code, "Plankarta saknas som beslutshandling (krävs vid laga kraft).", "dokument"))
    if not data.rows:
        issues.append(Issue(ERROR, code, "Planen har inga bestämmelser (krävs vid laga kraft).", table, fid))
    if not data.beslut:
        issues.append(Issue(ERROR, "DP-0014", "Beslutsinformation saknas (krävs vid laga kraft).", "beslutsinformation"))
    for beslut in data.beslut:
        for name, label in (("diarienummerKommun", "diarienummer"), ("beslutstyp", "beslutstyp"),
                            ("datumAntagande", "datum för antagande"), ("datumLagakraft", "datum för laga kraft"),
                            ("genomforandetidStartar", "när genomförandetiden startar")):
            if _blank(beslut.get(name)):
                issues.append(Issue(ERROR, "DP-0017", f"Beslutsinformationen saknar {label} (krävs vid laga kraft).",
                                    "beslutsinformation"))
    if is_new_plan(data):
        for row in data.rows:
            if _blank(row.get("motiv")):
                area = next((a for a in data.areas if (a.table, a.identity) == (row.get("tabell"), row.get("yta"))), None)
                issues.append(Issue(ERROR, "DP-0011", f"{row.get('bestammelsekod') or 'Bestämmelsen'} saknar motiv "
                                    "(planbestämmelsebeskrivning krävs vid laga kraft).",
                                    area.table if area else "bestammelse", area.fid if area else None))
    return issues


def validate(data: PlanData, catalog: Optional[cat.Catalog] = None) -> list[Issue]:
    """Alla avvikelser, allvarligaste först."""
    issues = (check_plan(data) + check_implementation(data) + check_geometry(data) + check_position_data(data) + check_hierarchy(data)
              + check_rows(data, catalog) + check_laga_kraft(data))
    unique = list(dict.fromkeys(issues))  # samma sak hittad två gånger visas en gång
    return sorted(unique, key=lambda i: (SEVERITIES.index(i.severity), _TABLE_ORDER.get(i.table or "", -1),
                                         i.fid if i.fid is not None else 0, i.code, i.text))


def summary(issues: list[Issue]) -> str:
    errors = sum(i.severity == ERROR for i in issues)
    warnings = sum(i.severity == WARNING for i in issues)
    infos = sum(i.severity == INFO for i in issues)
    if not issues:
        return "Inga avvikelser: planen klarar kontrollen."
    parts = [f"{errors} fel", f"{warnings} varning" + ("ar" if warnings != 1 else "")]
    if infos:
        parts.append(f"{infos} att fylla i")
    return ", ".join(parts)
