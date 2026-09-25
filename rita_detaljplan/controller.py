"""Styrenhet för planarbetet: hierarki, redigeringssession och tilldelning av bestämmelser.

Hierarkin är planområde → användning → egenskap:
  * Användningsytor får bara ligga inom planområdet (det som ligger utanför beskärs) och får inte överlappa
    varandra (överlappet klipps bort).
  * Egenskaper får bara ligga inom användningsytorna (beskärs annars).
  * Man kan inte börja rita en användning innan planområdet finns, eller en egenskap innan en användning finns.

Man ritar först geometrin och tilldelar sedan bestämmelser till ytorna (``add_bestammelse`` m.fl.): en yta kan ha
flera bestämmelser, och beteckningen på kartan sätts utifrån dem.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable, Optional

from qgis.core import (NULL, Qgis, QgsExpressionContext, QgsExpressionContextUtils, QgsGeometry, QgsPointXY, QgsProject,
                       QgsRectangle, QgsVectorLayer, QgsVectorLayerUtils)
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from .core import assignments, export_ngp, requirements, rows, rules, settings, topology, validation
from .core import catalog as cat
from .core import bestammelse as bm
from .core.project import apply_attributes, find_layer, set_plan_name, table_of

Notify = Callable[[str], None]
PLAN_LAYER = "detaljplan"
AREA_TABLES = (PLAN_LAYER, cat.USE_LAYER, *cat.PROPERTY_LAYERS)
HELPER_LAYER = "hjalplinje"  # hjälplinjer: ritas fritt och ingår aldrig i leveransen
DECISION_TABLE = "beslutsinformation"
DOCUMENT_TABLE = "dokument"
DECISION_FIELDS = ("instansInomKommunen", "diarienummerKommun", "diarienummerFullmaktige", "beslutstyp", "datumPaborjat",
                   "datumAntagande", "datumLagakraft", "genomforandetid", "genomforandetidStartar",
                   "arkividentitetKommun", "foregaendePlansBeteckning", "berordDomsMalnummer")
DOCUMENT_FIELDS = ("roll", "innehall", "huvudomrade", "underlagstyp", "namn", "kortnamn", "datum", "handelse", "lank",
                   "referensIdentitet", "specifikReferens")
EDIT_TABLES = (*AREA_TABLES, HELPER_LAYER, assignments.ROWS_TABLE, DECISION_TABLE, DOCUMENT_TABLE)
TITLES = {cat.USE_LAYER: "Användningsområde", "egenskap_yta": "Egenskapsområde", "egenskap_linje": "Egenskapslinje",
          PLAN_LAYER: "Planområde", HELPER_LAYER: "Hjälplinje"}
LABEL_TABLES = ("anvandning_yta", "egenskap_yta", "egenskap_linje")  # ytor/linjer vars text kan flyttas
ASSIGNABLE = ("egenskap_linje", "egenskap_yta", cat.USE_LAYER)  # det som kan få bestämmelser
SELECTABLE = (HELPER_LAYER, *ASSIGNABLE, PLAN_LAYER)  # det som kan markeras, det översta först


def _creation_order(fid: int) -> tuple:
    """Sorteringsnyckel i den ordning ytorna skapades: sparade objekt (positiva id) först, sedan osparade, vars
    tillfälliga id räknas nedåt (-3 skapades före -4). Den först ritade ytan är den andra ytor anpassar sig till."""
    return (0, fid) if fid >= 0 else (1, -fid)


def _clean(value):
    """Fältvärde utan QGIS NULL; ett datum (QDate, som GeoPackage ger efter sparande) blir ÅÅÅÅ-MM-DD."""
    if value == NULL or value is None:
        return None
    if hasattr(value, "toString") and hasattr(value, "isValid") and not hasattr(value, "toUTC"):
        return value.toString("yyyy-MM-dd") if value.isValid() else None
    return value


@dataclass(frozen=True)
class Summary:
    """Läget i planen: vad som är ritat och vad som återstår."""
    editing: bool = False
    plans: int = 0
    plan_area: float = 0.0
    uses: int = 0
    use_area: float = 0.0
    coverage: float = 0.0  # andel av planområdet som har en användningsyta (0–1)
    properties: int = 0
    unassigned: int = 0  # ytor och linjer som ännu saknar bestämmelse

    @property
    def has_plan(self) -> bool:
        return self.plans > 0

    @property
    def has_use(self) -> bool:
        return self.uses > 0


@dataclass(frozen=True)
class FillResult:
    """Utfallet av "fyll resten": om en yta skapades, en förklaring och den nya ytans id."""
    ok: bool
    message: str
    fid: Optional[int] = None


@dataclass(frozen=True)
class Candidate:
    """En yta (eller linje) under en klickad punkt."""
    table: str
    fid: int
    title: str  # t.ex. "Användningsområde · BC · 4 500 m²"


class PlanController(QObject):
    changed = pyqtSignal()  # något som påverkar knapparnas läge har ändrats

    def __init__(self, notify_error: Notify, notify_warning: Notify, project: Optional[QgsProject] = None,
                 open_form: Optional[Callable[[QgsVectorLayer, object], None]] = None):
        super().__init__()
        self._error = notify_error
        self._warn = notify_warning
        self._open_form = open_form
        self.project = project or QgsProject.instance()
        self._layers: dict[str, QgsVectorLayer] = {}
        self._busy = False  # true medan vi själva ändrar objekt, så att vi inte reagerar på oss själva
        self._detached = False  # sant efter detach(): väntande händelser från den här styrenheten ska då ignoreras
        self._notify_pending = False
        self.project.layersAdded.connect(self.attach)
        self.project.layerWillBeRemoved.connect(self._forget)
        self.attach()

    # -- anslutning till lagren -------------------------------------------------------
    def attach(self, *_):
        """Kopplar på planens lager (även sådana som läses in senare)."""
        for table in EDIT_TABLES:
            layer = find_layer(self.project, table)
            if layer is None or layer.id() in self._layers:
                continue
            self._layers[layer.id()] = layer
            if table in AREA_TABLES:
                layer.featureAdded.connect(partial(self._on_added, layer))
                layer.geometryChanged.connect(partial(self._on_geometry_changed, layer))
                layer.featureDeleted.connect(lambda *_, t=table: self._on_deleted(t))
            layer.editingStarted.connect(lambda *_: self._changed())
            layer.editingStopped.connect(lambda *_: self._changed())
            layer.afterCommitChanges.connect(lambda *_: self._changed())
        self._changed()

    def _forget(self, layer_id: str):
        if self._layers.pop(layer_id, None) is not None:
            self._changed()

    def detach(self):
        try:
            self.project.layersAdded.disconnect(self.attach)
            self.project.layerWillBeRemoved.disconnect(self._forget)
        except (TypeError, RuntimeError):
            pass
        self._layers.clear()
        self._detached = True

    def _changed(self):
        """Talar om att läget ändrats – en gång per varv i händelseslingan, så att många ändringar blir en uppdatering."""
        if not self._notify_pending:
            self._notify_pending = True
            QTimer.singleShot(0, self._emit_changed)

    def _emit_changed(self):
        self._notify_pending = False
        self.changed.emit()

    def layer(self, table: str) -> Optional[QgsVectorLayer]:
        return find_layer(self.project, table)

    # -- redigeringssession -----------------------------------------------------------
    @property
    def editing(self) -> bool:
        return any(layer.isEditable() for layer in self._layers.values() if layer.isValid())

    def has_edits(self) -> bool:
        return any(layer.isModified() for layer in self._layers.values() if layer.isValid())

    def start_editing(self) -> bool:
        """Sätter alla planlager i redigeringsläge på en gång, så att reglerna kan jämföra mellan dem."""
        ok = True
        for table in EDIT_TABLES:
            layer = self.layer(table)
            if layer is not None and not layer.isEditable():
                ok = layer.startEditing() and ok
        self._changed()
        return ok

    def stop_editing(self, save: bool) -> list[str]:
        """Avslutar redigeringen och sparar eller kastar ändringarna. Returnerar felmeddelanden (tom = klart)."""
        errors: list[str] = []
        if save:
            self._modify(lambda: assignments.remove_orphans(self.project))
        for table in reversed(EDIT_TABLES):
            layer = self.layer(table)
            if layer is None or not layer.isEditable():
                continue
            if save:
                if not layer.commitChanges():
                    errors.append(f"{layer.name()}: " + "; ".join(layer.commitErrors()))
            else:
                layer.rollBack()
        self._changed()
        return errors

    # -- hierarki ---------------------------------------------------------------------
    def summary(self) -> Summary:
        plan_layer, use_layer = self.layer(PLAN_LAYER), self.layer(cat.USE_LAYER)
        if plan_layer is None or use_layer is None:
            return Summary(editing=self.editing)
        plan = rules.plan_geometry(plan_layer)
        uses = rules.use_geometry(use_layer)
        properties = unassigned = 0
        for table in (cat.USE_LAYER, *cat.PROPERTY_LAYERS):
            layer = self.layer(table)
            if layer is None:
                continue
            for feature in layer.getFeatures():
                properties += table != cat.USE_LAYER
                unassigned += not (_clean(feature["bestammelser"]) or 0)
        return Summary(
            editing=self.editing,
            plans=plan_layer.featureCount(),
            plan_area=plan.area() if plan else 0.0,
            uses=use_layer.featureCount(),
            use_area=uses.area() if uses else 0.0,
            coverage=rules.coverage(uses, plan),
            properties=properties,
            unassigned=unassigned,
        )

    # -- planens uppgifter och krav ------------------------------------------------------
    PLAN_FIELDS = ("kommun", "beteckning", "namn", "syfte", "status", "typ")

    def plan_feature(self):
        """Planens objekt (planen har ett planområde), eller None om det inte är ritat än."""
        layer = self.layer(PLAN_LAYER)
        if layer is None:
            return None
        return min(layer.getFeatures(), key=lambda f: _creation_order(f.id()), default=None)  # det först ritade

    def plan_values(self) -> dict:
        """Planens uppgifter (kommun, namn, syfte, status, typ, beteckning). Tomma värden är None."""
        feature = self.plan_feature()
        if feature is None:
            return {name: None for name in self.PLAN_FIELDS}
        return {name: _clean(feature[name]) for name in self.PLAN_FIELDS}

    def set_plan_values(self, values: dict) -> None:
        """Sparar planens uppgifter i planlagret (i redigeringsbufferten) och döper gruppen i lagerpanelen efter planen."""
        feature = self.plan_feature()
        if feature is None:
            raise RuntimeError("Planområdet är inte ritat än.")
        layer = self.layer(PLAN_LAYER)
        changed = {name: (values[name] or None) for name in self.PLAN_FIELDS if name in values}
        old_status = _clean(feature["status"])
        if old_status and changed.get("status") and changed["status"] != old_status:
            from datetime import date
            changed["datumStatusforandring"] = date.today().isoformat()  # ska bara anges när status ändras
        ids = [f.id() for f in layer.getFeatures()]  # alla planområden bär samma uppgifter
        self._modify(lambda: apply_attributes(layer, ids, changed))
        set_plan_name(self.project, changed.get("namn") or "")
        self._changed()

    def implementation_months(self) -> Optional[int]:
        """Planens genomförandetid i månader (ur beslutsinformationen), eller None om den inte är angiven."""
        try:
            months = int(self.decision_values().get("genomforandetid"))
        except (TypeError, ValueError):
            return None
        return months if months > 0 else None

    def requirements(self, values: Optional[dict] = None, months: Optional[int] = None,
                     datum_paborjat: Optional[str] = None) -> list[requirements.Requirement]:
        """Vad som återstår före leverans (se ``core.requirements``). ``values``, ``months`` (genomförandetiden) och
        ``datum_paborjat`` är uppgifter som inte sparats än."""
        state = self.summary()
        if datum_paborjat is None:
            datum_paborjat = self.decision_values().get("datumPaborjat")
        return requirements.plan_requirements(values if values is not None else self.plan_values(),
                                              has_plan_area=state.has_plan, uses=state.uses,
                                              coverage=state.coverage, unassigned=state.unassigned,
                                              implementation_months=months if months is not None
                                              else self.implementation_months(),
                                              datum_paborjat=datum_paborjat)

    def validate(self, catalog: Optional[cat.Catalog] = None) -> list[validation.Issue]:
        """Kontrollerar planen mot Lantmäteriets regler (se ``core.validation``). Ändrar ingenting."""
        return validation.validate(validation.collect(self.project), catalog)

    def show_issue(self, issue: validation.Issue) -> None:
        """Markerar ytan som en avvikelse gäller (så att den kan visas i kartan)."""
        if issue.locatable:
            self.select(Candidate(issue.table, issue.fid, ""))

    # -- beslut och handlingar (tabellerna beslutsinformation och dokument) ----------------------
    def decision_values(self) -> dict:
        """Planens beslutsinformation (en rad): fältvärden, tomma är None. Tom dict-lik med None om inget är ifyllt."""
        layer = self.layer(DECISION_TABLE)
        feature = next(iter(layer.getFeatures()), None) if layer is not None else None
        return {name: (_clean(feature[name]) if feature is not None else None) for name in DECISION_FIELDS}

    def set_decision(self, values: dict) -> None:
        """Sparar beslutsinformationen (en rad) i redigeringsbufferten. Tomma värden blir NULL."""
        layer = self.layer(DECISION_TABLE)
        if layer is None:
            raise RuntimeError("Tabellen för beslutsinformation saknas.")
        clean = {name: (values.get(name) if values.get(name) not in ("", None) else None) for name in DECISION_FIELDS}

        def write():
            if not layer.isEditable():
                layer.startEditing()
            existing = next(iter(layer.getFeatures()), None)
            if existing is not None:
                apply_attributes(layer, [existing.id()], clean)
            elif any(value is not None for value in clean.values()):
                layer.addFeature(assignments.new_feature(layer, clean))

        self._modify(write)
        self._changed()

    def documents(self) -> list[dict]:
        """Handlingar och underlag (tabellen dokument), med nyckeln ``_fid``."""
        layer = self.layer(DOCUMENT_TABLE)
        result = []
        for feature in (layer.getFeatures() if layer is not None else []):
            row = {name: _clean(feature[name]) for name in DOCUMENT_FIELDS}
            row["_fid"] = feature.id()
            result.append(row)
        return result

    def set_documents(self, documents: list[dict]) -> None:
        """Ersätter alla handlingar med ``documents`` (rader utan ``roll`` hoppas över)."""
        layer = self.layer(DOCUMENT_TABLE)
        if layer is None:
            raise RuntimeError("Tabellen för dokument saknas.")

        def write():
            if not layer.isEditable():
                layer.startEditing()
            layer.deleteFeatures([f.id() for f in layer.getFeatures()])
            for document in documents:
                if document.get("roll"):
                    attrs = {name: (document.get(name) if document.get(name) not in ("", None) else None)
                             for name in DOCUMENT_FIELDS}
                    layer.addFeature(assignments.new_feature(layer, attrs))

        self._modify(write)
        self._changed()

    # -- teckenförklaring -----------------------------------------------------------------------
    def plan_bounds(self):
        """Planområdets omgivande rektangel, eller None om planområdet inte är ritat."""
        layer = self.layer(PLAN_LAYER)
        geometry = rules.plan_geometry(layer) if layer is not None else None
        return geometry.boundingBox() if geometry is not None and not geometry.isEmpty() else None

    def legend_data(self) -> tuple:
        """(rader, beslut) som teckenförklaringen byggs av: planens bestämmelser och beslutsinformationen."""
        return validation.collect(self.project).rows, self.decision_values()

    # -- topologikontroll ----------------------------------------------------------------------
    def topology_changes(self, tolerance: float = topology.DEFAULT_TOLERANCE) -> list[topology.Change]:
        """Föreslagna ändringar av brytpunkter och små glapp (se ``core.topology``). Ändrar ingenting."""
        plan_layer, use_layer, prop_layer = (self.layer(PLAN_LAYER), self.layer(cat.USE_LAYER), self.layer("egenskap_yta"))
        if plan_layer is None or use_layer is None:
            return []
        plan = rules.plan_geometry(plan_layer)
        uses = sorted(((f.id(), f.geometry()) for f in use_layer.getFeatures()), key=lambda item: _creation_order(item[0]))
        properties = sorted(((f.id(), f.geometry()) for f in prop_layer.getFeatures()),
                            key=lambda item: _creation_order(item[0])) \
            if prop_layer is not None else []
        return topology.analyze(plan, uses, properties, tolerance)

    PROPERTY_GAP_MIN = 1.0  # m²: mindre än så av en kvartersmark utan egenskapsområde räknas inte

    def topology_findings(self) -> list[validation.Issue]:
        """Avvikelser som topologikontrollen visar men inte rättar automatiskt: planområde utan användning (fel) och
        kvartersmark där egenskapsområden saknas (varning, det behöver inte vara fel). Ändrar ingenting."""
        found: list[validation.Issue] = []
        plan = self.plan_feature()
        missing = self.missing_use_area()
        if plan is not None and missing > 0:
            found.append(validation.Issue(validation.ERROR, "DP-0002",
                                          f"{missing:,.0f} m² av planområdet saknar användning.".replace(",", " "),
                                          PLAN_LAYER, plan.id()))
        use_layer = self.layer(cat.USE_LAYER)
        if use_layer is None:
            return found
        properties = rules.use_geometry(self.layer("egenskap_yta")) if self.layer("egenskap_yta") is not None else None
        for use in sorted(use_layer.getFeatures(), key=lambda f: _creation_order(f.id())):
            if _clean(use["anvandningsform"]) != "Kvartersmark":
                continue
            rest = rules.remainder(use.geometry(), properties)
            if not rest.isEmpty() and rest.area() > self.PROPERTY_GAP_MIN:
                found.append(validation.Issue(
                    validation.WARNING, "", f"{rest.area():,.0f} m² av kvartersmarken saknar egenskapsområde."
                    .replace(",", " "), cat.USE_LAYER, use.id()))
        return found

    def missing_use_area(self) -> float:
        """Areal (m²) av planområdet som ännu saknar användning. 0 om planområdet saknas eller redan är täckt."""
        plan_layer, use_layer = self.layer(PLAN_LAYER), self.layer(cat.USE_LAYER)
        if plan_layer is None:
            return 0.0
        uses = rules.use_geometry(use_layer) if use_layer is not None else None
        rest = rules.remainder(rules.plan_geometry(plan_layer), uses)
        return rest.area() if not rest.isEmpty() and rest.area() > rules.MIN_OVERLAP else 0.0

    def apply_topology(self, changes: list[topology.Change]) -> tuple[int, int]:
        """Genomför valda ändringar automatiskt (i redigeringsbufferten, som ett ångra-steg per lager).
        Returnerar (antal gjorda, antal som hoppades över för att de skulle ge en ogiltig geometri)."""
        done = skipped = 0
        by_area: dict[tuple, list] = {}
        for change in changes:
            by_area.setdefault((change.table, change.fid), []).append(change)
        touched: dict[str, QgsVectorLayer] = {}
        for (table, fid), group in by_area.items():
            layer = self.layer(table)
            feature = layer.getFeature(fid) if layer is not None else None
            if feature is None or not feature.isValid():
                skipped += len(group)
                continue
            if not layer.isEditable():
                layer.startEditing()
            if table not in touched:
                layer.beginEditCommand("Topologikontroll")
                touched[table] = layer
            geometry, ok, bad = topology.apply_to_geometry(feature.geometry(), group)
            if ok:
                self._modify(lambda: layer.changeGeometry(fid, geometry))
            done += ok
            skipped += bad
        for layer in touched.values():
            layer.endEditCommand()
        self._changed()
        return done, skipped

    # -- leverans till NGP ---------------------------------------------------------------------
    NGP_SCOPE = "detaljplan_ngp"

    def last_delivery(self) -> dict:
        """Senaste leveransen av planen (mottagningsid, planens id, miljö), eller tom dict."""
        read = lambda key: self.project.readEntry(self.NGP_SCOPE, key)[0]  # noqa: E731
        reception = read("ngp_mottagning")
        return {"mottagning": reception, "plan": read("ngp_plan"), "miljo": read("ngp_miljo")} if reception else {}

    def remember_delivery(self, reception: str, plan: str, environment: str) -> None:
        self.project.writeEntry(self.NGP_SCOPE, "ngp_mottagning", reception)
        self.project.writeEntry(self.NGP_SCOPE, "ngp_plan", plan)
        self.project.writeEntry(self.NGP_SCOPE, "ngp_miljo", environment)

    # -- export -----------------------------------------------------------------------------
    def export_ngp(self) -> dict:
        """Planen som en leverans till NGP (se ``core.export_ngp``). Ändrar ingenting."""
        return export_ngp.export_plan(validation.collect(self.project))

    def can_draw(self, table: str) -> tuple[bool, str]:
        """Om man får börja rita i ett lager nu, och annars varför inte."""
        if not self.editing:
            return False, "Börja rita planbestämmelser först."
        if table == HELPER_LAYER:
            return True, ""
        state = self.summary()
        if table == cat.USE_LAYER and not state.has_plan:
            return False, "Rita planområdet först: användningsytor får bara ligga inom planområdet."
        if table in cat.PROPERTY_LAYERS and not state.has_use:
            return False, "Rita en användningsyta först: egenskaper hör alltid till en användning."
        return True, ""

    # -- fyll resten ------------------------------------------------------------------
    def _add_area(self, table: str, geometry: QgsGeometry) -> int:
        layer = self.layer(table)
        geometry = QgsGeometry(geometry)
        geometry.convertToMultiType()
        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        feature = QgsVectorLayerUtils.createFeature(layer, geometry, {}, context)
        if not layer.addFeature(feature):
            raise RuntimeError("Kunde inte lägga till ytan.")
        return feature.id()

    def fill_use(self) -> FillResult:
        """Fyller det som ännu saknar användning i planområdet med en ny användningsyta."""
        ok, reason = self.can_draw(cat.USE_LAYER)
        if not ok:
            return FillResult(False, reason)
        rest = rules.remainder(rules.plan_geometry(self.layer(PLAN_LAYER)), rules.use_geometry(self.layer(cat.USE_LAYER)))
        if rest.isEmpty():
            return FillResult(False, "Hela planområdet har redan en användning: det finns inget att fylla.")
        fid = self._add_area(cat.USE_LAYER, rest)
        return FillResult(True, f"Fyllde {rest.area():,.0f} m² med en ny användningsyta. Tilldela den en bestämmelse."
                          .replace(",", " "), fid)

    def fill_use_at(self, point: QgsPointXY) -> FillResult:
        """Fyller den sammanhängande delen av planområdet som saknar användning under punkten med en ny
        användningsyta. Är det som saknas uppdelat i flera bitar (t.ex. av redan ritade användningsytor) fylls bara
        den bit man klickar i, inte nödvändigtvis hela planområdet; klicka i övriga bitar för att fylla dem också."""
        ok, reason = self.can_draw(cat.USE_LAYER)
        if not ok:
            return FillResult(False, reason)
        rest = rules.remainder(rules.plan_geometry(self.layer(PLAN_LAYER)), rules.use_geometry(self.layer(cat.USE_LAYER)))
        if rest.isEmpty():
            return FillResult(False, "Hela planområdet har redan en användning: det finns inget att fylla.")
        part = rules.part_at(rest, point)
        if part.isEmpty():
            return FillResult(False, "Klicka i den del av planområdet som saknar användning.")
        fid = self._add_area(cat.USE_LAYER, part)
        return FillResult(True, f"Fyllde {part.area():,.0f} m² med en ny användningsyta. Tilldela den en bestämmelse."
                          .replace(",", " "), fid)

    def fill_property(self, point: QgsPointXY) -> FillResult:
        """Fyller det som ännu saknar egenskapsyta i användningsområdet under punkten med en ny egenskapsyta."""
        ok, reason = self.can_draw("egenskap_yta")
        if not ok:
            return FillResult(False, reason)
        target = QgsGeometry.fromPointXY(point)
        use = next((f for f in self.layer(cat.USE_LAYER).getFeatures() if f.geometry().contains(target)), None)
        if use is None:
            return FillResult(False, "Klicka inne i ett användningsområde.")
        rest = rules.remainder(use.geometry(), rules.use_geometry(self.layer("egenskap_yta")))
        if rest.isEmpty():
            return FillResult(False, "Hela användningsområdet har redan en egenskapsyta: det finns inget att fylla.")
        fid = self._add_area("egenskap_yta", rest)
        return FillResult(True, f"Fyllde {rest.area():,.0f} m² med en ny egenskapsyta. Tilldela den en bestämmelse."
                          .replace(",", " "), fid)

    # -- nya objekt -------------------------------------------------------------------
    def _on_added(self, layer: QgsVectorLayer, fid: int):
        if self._busy or fid >= 0:  # sparade objekt (QGIS anropar även efter sparande) är inte nya
            return
        # Objektet ligger i redigeringsbufferten först när ritverktyget är klart: ändra i nästa varv.
        QTimer.singleShot(0, lambda: self._process(layer, fid))

    def _on_deleted(self, table: Optional[str] = None):
        if not self._busy:
            QTimer.singleShot(0, lambda: self._cleanup(table))
        self._changed()

    def _cleanup(self, table: Optional[str] = None):
        """När en yta raderats ska allt som hör till den försvinna: tas ett planområde bort försvinner alla användningar,
        egenskaper och bestämmelser; tas en användning bort försvinner (eller beskärs) egenskaperna på den, och deras
        bestämmelser följer med. Bestämmelserna för borttagna ytor tas alltid bort."""
        if self._detached:  # en väntande städning från en styrenhet som inte längre används får inte röra projektet
            return
        try:
            removed = self._modify(lambda: self._cascade(table))
            rows = self._modify(lambda: assignments.remove_orphans(self.project))
        except (RuntimeError, KeyError):
            return
        if removed["uses"] or removed["properties"]:
            parts = []
            if removed["uses"]:
                parts.append(f"{removed['uses']} användningsyta" if removed["uses"] == 1 else f"{removed['uses']} användningsytor")
            if removed["properties"]:
                parts.append(f"{removed['properties']} egenskap" if removed["properties"] == 1 else f"{removed['properties']} egenskaper")
            if rows:
                parts.append(f"{rows} bestämmelse" if rows == 1 else f"{rows} bestämmelser")
            self._warn("Tog bort även " + ", ".join(parts[:-1]) + (" och " if len(parts) > 1 else "") + parts[-1]
                       + " som hörde till det du tog bort.")
        self._changed()

    def _cascade(self, table: Optional[str]) -> dict:
        """Tar bort det som ligger under en borttagen yta i hierarkin planområde → användning → egenskap.
        Returnerar hur många användningsytor och egenskaper som togs bort."""
        removed = {"uses": 0, "properties": 0}
        if table not in (PLAN_LAYER, cat.USE_LAYER):
            return removed
        plan_layer, use_layer = self.layer(PLAN_LAYER), self.layer(cat.USE_LAYER)
        if table == PLAN_LAYER and plan_layer is not None and use_layer is not None and use_layer.isEditable():
            if plan_layer.featureCount() == 0:
                ids = [f.id() for f in use_layer.getFeatures()]
                if ids and use_layer.deleteFeatures(ids):  # inget planområde kvar: användningarna hör inte till något
                    removed["uses"] = len(ids)
            else:  # ett av flera planområden togs bort: användningen som låg på det försvinner eller beskärs
                plan = rules.plan_geometry(plan_layer)
                for feature in list(use_layer.getFeatures()):
                    result = rules.constrain_use(feature.geometry(), plan, None)
                    if result.problems:
                        if use_layer.deleteFeature(feature.id()):
                            removed["uses"] += 1
                    elif result.changed:
                        use_layer.changeGeometry(feature.id(), result.geometry)
        uses = rules.use_geometry(use_layer) if use_layer is not None else None
        for prop_table in cat.PROPERTY_LAYERS:
            layer = self.layer(prop_table)
            if layer is None or not layer.isEditable():
                continue
            for feature in list(layer.getFeatures()):
                result = rules.constrain_property(feature.geometry(), uses)
                if result.problems:  # ligger inte längre på någon användning: försvinner
                    if layer.deleteFeature(feature.id()):
                        removed["properties"] += 1
                elif result.changed:  # ligger delvis kvar på andra användningar: det som låg på den borttagna försvinner
                    layer.changeGeometry(feature.id(), result.geometry)
        return removed

    def _process(self, layer: QgsVectorLayer, fid: int):
        if self._detached:
            return
        try:
            if not layer.isValid():
                return
            feature = layer.getFeature(fid)
            if not feature.isValid():
                return
            table = table_of(layer)
            if table == PLAN_LAYER:
                self._modify(lambda: assignments.ensure_identity(layer, fid))
            else:  # nya ytor (även delade eller kopierade) börjar utan bestämmelser
                self._modify(lambda: assignments.reset_new_area(self.project, table, fid))
            if table == PLAN_LAYER:
                self._handle_plan(layer, feature)
            elif table == cat.USE_LAYER:
                self._handle_use(layer, feature)
            elif table in cat.PROPERTY_LAYERS:
                self._handle_property(layer, feature)
        except (RuntimeError, KeyError) as exc:  # t.ex. lagret togs bort under tiden
            self._warn(f"Kunde inte hantera det nya objektet: {exc}")
        finally:
            self._changed()

    def _modify(self, action: Callable[[], object]):
        """Kör en ändring av våra egna objekt utan att reagera på signalerna den ger upphov till."""
        self._busy = True
        try:
            return action()
        finally:
            self._busy = False

    def _reject(self, layer: QgsVectorLayer, fid: int, message: str):
        self._modify(lambda: layer.deleteFeature(fid))
        self._error(message)

    def _handle_plan(self, layer: QgsVectorLayer, feature):
        others = [f for f in layer.getFeatures() if f.id() != feature.id()]
        if not others:  # första planområdet: fråga efter planens uppgifter (namn, syfte, status …)
            if self._open_form is not None:
                self._open_form(layer, feature)
            return
        # ett till planområde: en egen yta som kan markeras och tas bort för sig, men bara ett planområde per plats
        existing = rules.plan_geometry(layer, exclude_fid=feature.id())
        rest = rules.remainder(feature.geometry(), existing)
        if rest.isEmpty():
            self._reject(layer, feature.id(), "Planområdet togs bort: ytan ligger helt inom ett planområde som redan finns.")
            return
        primary = min(others, key=lambda f: _creation_order(f.id()))
        shared = {name: _clean(primary[name]) for name in self.PLAN_FIELDS}

        def adopt():
            if rest.area() < feature.geometry().area() - rules.MIN_OVERLAP:
                layer.changeGeometry(feature.id(), rest)
            apply_attributes(layer, [feature.id()], shared)

        self._modify(adopt)
        self._warn("Planen har nu fler än ett planområde. De hör till samma plan och kan markeras och tas bort var för sig.")

    def _handle_use(self, layer: QgsVectorLayer, feature):
        plan = rules.plan_geometry(self.layer(PLAN_LAYER))
        result = rules.constrain_use(feature.geometry(), plan, rules.use_geometry(layer, exclude_fid=feature.id()))
        if result.problems:
            self._reject(layer, feature.id(), f"Användningsytan togs bort: {result.problems[0]}")
            return
        if result.changed:
            self._modify(lambda: layer.changeGeometry(feature.id(), result.geometry))
        for note in result.notes:
            self._warn(note)

    def _handle_property(self, layer: QgsVectorLayer, feature):
        result = rules.constrain_property(feature.geometry(), rules.use_geometry(self.layer(cat.USE_LAYER)))
        if result.problems:
            self._reject(layer, feature.id(), f"Egenskapen togs bort: {result.problems[0]}")
            return
        if result.changed:
            self._modify(lambda: layer.changeGeometry(feature.id(), result.geometry))
        for note in result.notes:
            self._warn(note)

    # -- ändrad geometri --------------------------------------------------------------
    def _on_geometry_changed(self, layer: QgsVectorLayer, fid: int, geometry: QgsGeometry):
        if self._busy:
            return
        table = table_of(layer)
        try:
            if table == PLAN_LAYER:
                self._check_plan_change(layer)
            elif table == cat.USE_LAYER:
                self._recheck_use(layer, fid, geometry)
            elif table in cat.PROPERTY_LAYERS:
                self._recheck_property(layer, fid, geometry)
        except (RuntimeError, KeyError):
            return
        self._changed()

    def _check_plan_change(self, plan_layer: QgsVectorLayer):
        use_layer = self.layer(cat.USE_LAYER)
        outside = rules.outside_plan(rules.use_geometry(use_layer), rules.plan_geometry(plan_layer)) \
            if use_layer is not None else 0.0
        if outside > rules.MIN_OVERLAP:
            self._warn(f"{outside:.0f} m² användning ligger nu utanför planområdet. "
                       "Flytta tillbaka planområdet eller beskär användningen.")

    def _recheck_use(self, layer: QgsVectorLayer, fid: int, geometry: QgsGeometry):
        plan = rules.plan_geometry(self.layer(PLAN_LAYER))
        result = rules.constrain_use(geometry, plan, rules.use_geometry(layer, exclude_fid=fid))
        if result.problems:
            self._warn(f"{result.problems[0]} Flytta tillbaka den eller ta bort den, annars stoppas leveransen.")
            return
        if result.changed:
            self._modify(lambda: layer.changeGeometry(fid, result.geometry))
            for note in result.notes:
                self._warn(note)

    def _recheck_property(self, layer: QgsVectorLayer, fid: int, geometry: QgsGeometry):
        result = rules.constrain_property(geometry, rules.use_geometry(self.layer(cat.USE_LAYER)))
        if result.problems:
            self._warn(f"Objektet hör inte längre till en användning: {result.problems[0]} "
                       "Flytta tillbaka det eller ta bort det, annars stoppas leveransen.")
            return
        if result.changed:
            self._modify(lambda: layer.changeGeometry(fid, result.geometry))
            for note in result.notes:
                self._warn(note)

    # -- tilldela bestämmelser --------------------------------------------------------
    SELECTABLE = SELECTABLE

    def candidates_at(self, point: QgsPointXY, tolerance: float, tables: tuple = ASSIGNABLE) -> list[Candidate]:
        """Ytor och linjer under en punkt: linjer först, sedan egenskapsytor (minsta först), sist användningen.
        ``tables`` = lagren att leta i, i ordning (det första vinner)."""
        target = QgsGeometry.fromPointXY(point)
        box = QgsRectangle(point.x() - tolerance, point.y() - tolerance, point.x() + tolerance, point.y() + tolerance)
        found: list[tuple[int, float, Candidate]] = []
        for rank, table in enumerate(tables):
            layer = self.layer(table)
            if layer is None:
                continue
            for feature in layer.getFeatures(box):
                geometry = feature.geometry()
                is_area = rules.geometry_kind(geometry) == "yta"
                if not (geometry.contains(target) if is_area else geometry.distance(target) <= tolerance):
                    continue
                size = geometry.area() if is_area else geometry.length()
                found.append((rank, size, Candidate(table, feature.id(), self.describe_area(table, feature.id()))))
        return [candidate for _, _, candidate in sorted(found, key=lambda item: (item[0], item[1]))]

    def describe_area(self, table: str, fid: int) -> str:
        layer = self.layer(table)
        feature = layer.getFeature(fid)
        geometry = feature.geometry()
        is_line = rules.geometry_kind(geometry) == "linje"
        size = f"{geometry.length():,.0f} m" if is_line else f"{geometry.area():,.0f} m²"
        if table in (PLAN_LAYER, HELPER_LAYER):
            return f"{TITLES[table]} · {size}".replace(",", " ")
        label = _clean(feature["beteckning"])
        count = _clean(feature["bestammelser"]) or 0
        state = "saknar bestämmelse" if not count else (label or f"{count} bestämmelse" + ("r" if count > 1 else ""))
        return f"{TITLES[table]} · {state} · {size}".replace(",", " ")

    def select(self, candidate: Candidate, add: bool = False) -> None:
        """Markerar ytan (och avmarkerar allt annat om ``add`` inte är sant)."""
        if not add:
            self.clear_selection()
        layer = self.layer(candidate.table)
        if layer is not None:
            layer.selectByIds([candidate.fid], Qgis.SelectBehavior.AddToSelection if add else Qgis.SelectBehavior.SetSelection)

    def move_label(self, table: str, fid: int, point: QgsPointXY) -> Optional[QgsPointXY]:
        """Flyttar ytans text till ``point``. Texten får gärna hamna utanför ytan: symbologin ritar då automatiskt en
        tunn ledlinje till ytan (se ``core.symbology``). Returnerar läget som sattes, eller None om ytan saknas."""
        layer = self.layer(table)
        feature = layer.getFeature(fid) if layer is not None else None
        if feature is None or not feature.isValid():
            return None
        self._modify(lambda: apply_attributes(layer, [fid], {"label_x": point.x(), "label_y": point.y()}))
        self._changed()
        return QgsPointXY(point)

    RESIZABLE_LABELS = ("egenskap_yta",)  # textrutor som kan omformas (bara bredden styr, aldrig bokstävernas storlek)
    MIN_LABEL_WIDTH = 1.0  # m

    def resize_label(self, table: str, fid: int, rect: QgsRectangle) -> Optional[QgsPointXY]:
        """Omformar ytans textruta till ``rect``: texten radbryts till rektangelns bredd och placeras i dess mitt.
        Textstorleken ändras aldrig (den ställs in i skalningsinställningarna). Returnerar textens nya läge, eller
        None om ytan saknas eller inte har en omformbar textruta."""
        layer = self.layer(table)
        feature = layer.getFeature(fid) if layer is not None and table in self.RESIZABLE_LABELS else None
        if feature is None or not feature.isValid():
            return None
        center = rect.center()
        width = max(rect.width(), self.MIN_LABEL_WIDTH)
        self._modify(lambda: apply_attributes(layer, [fid], {"label_x": center.x(), "label_y": center.y(),
                                                             "label_w": width}))
        self._changed()
        return QgsPointXY(center)

    def reset_label(self, table: str, fid: int) -> None:
        """Låter ytans text placeras automatiskt igen (och textrutan får sin ursprungliga form)."""
        layer = self.layer(table)
        if layer is not None:
            self._modify(lambda: apply_attributes(layer, [fid], {"label_x": None, "label_y": None,
                                                                 "label_w": None}))
            self._changed()

    def select_in_rect(self, rect: QgsRectangle, add: bool = False) -> list[Candidate]:
        """Markerar alla ytor och linjer (i alla markerbara lager) som rektangeln rör vid. Ersätter markeringen om
        ``add`` inte är sant. Returnerar det som markerades."""
        if not add:
            self.clear_selection()
        target = QgsGeometry.fromRect(rect)
        found: list[Candidate] = []
        for table in self.SELECTABLE:
            layer = self.layer(table)
            if layer is None:
                continue
            ids = [f.id() for f in layer.getFeatures(rect) if f.geometry().intersects(target)]
            if not ids:
                continue
            layer.selectByIds(ids, Qgis.SelectBehavior.AddToSelection)
            found += [Candidate(table, fid, self.describe_area(table, fid)) for fid in ids]
        return found

    def clear_selection(self) -> None:
        for table in SELECTABLE:
            layer = self.layer(table)
            if layer is not None:
                layer.removeSelection()

    def rows_of(self, table: str, fid: int) -> list[dict]:
        return assignments.rows_of_area(self.project, table, fid)

    def entries_for(self, catalog: cat.Catalog, table: str, fid: int) -> list[cat.CatalogEntry]:
        return assignments.entries_for(self.project, catalog, table, fid)

    def allowed_forms(self, table: str, fid: int):
        """Användningsformer som ytan får bestämmelser för (kvartersmark, allmän plats …), eller None om det inte är känt."""
        return assignments.allowed_forms(self.project, table, fid)

    def add_bestammelse(self, table: str, fid: int, entry: cat.CatalogEntry, values: list[bm.VariableValue],
                        motiv: Optional[str] = None, formulation: Optional[str] = None) -> dict:
        """Sätter en bestämmelse på en yta. Kastar ``AssignmentError`` (med förklaring) om den inte passar."""
        row = self._modify(lambda: assignments.add(self.project, table, fid, entry, values, motiv, formulation))
        self._after_assignment(table)
        return row

    def update_bestammelse(self, row_fid: int, entry: cat.CatalogEntry, values: list[bm.VariableValue],
                           motiv: Optional[str] = None, formulation: Optional[str] = None) -> dict:
        row = self._modify(lambda: assignments.update(self.project, row_fid, entry, values, motiv, formulation))
        self._after_assignment(row["tabell"])
        return row

    def move_bestammelse(self, row_fid: int, steps: int) -> bool:
        """Flyttar en bestämmelse upp (negativt ``steps``) eller ned bland ytans bestämmelser."""
        moved = self._modify(lambda: assignments.move(self.project, row_fid, steps))
        self._changed()
        return moved

    def remove_bestammelse(self, row_fid: int) -> None:
        self._modify(lambda: assignments.remove(self.project, row_fid))
        self._changed()

    def _after_assignment(self, table: str):
        if table == cat.USE_LAYER:
            conflicts = self.form_conflicts()
            if conflicts:
                self._warn(f"{conflicts} egenskaper ligger nu på en användning med annan användningsform.")
        self._changed()

    def form_conflicts(self) -> int:
        """Antal egenskaper vars användningsform inte stämmer med användningen de ligger på."""
        use_layer = self.layer(cat.USE_LAYER)
        count = 0
        for table in cat.PROPERTY_LAYERS:
            layer = self.layer(table)
            if layer is None:
                continue
            for feature in layer.getFeatures():
                form = _clean(feature["anvandningsform"])
                if form and not rules.link_property(feature.geometry(), use_layer, form).ok:
                    count += 1
        return count
