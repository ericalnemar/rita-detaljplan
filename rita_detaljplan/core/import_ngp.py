"""Import av en leverans i Lantmäteriets JSON-format (samma ``FeatureCollection`` som ``core.export_ngp`` skriver,
mediatyp ``application/vnd.lm.detaljplan.v4+json``) till en ny, tom detaljplan i pluginet.

Filen kan komma från Rita Detaljplan självt, eller från ett annat verktyg (t.ex. ArcGIS Pro) som levererar enligt
Nationell informationsspecifikation Detaljplan 4.1 – bara strukturen följs, inte var filen kom ifrån.

Detta är den rena tolkningen av filen: geometrier byggs upp och planbestämmelseobjekten grupperas till de ytor
(eller linjer) de hör till (en yta per unik geometri; bara ytor med minst en bestämmelse finns i leveransen, precis
som vid export). Vilken katalogpost varje bestämmelse motsvarar, och själva skrivandet till planens lager, sköts av
``PlanController.import_ngp`` (som har tillgång till den laddade planbestämmelsekatalogen och redigeringsbufferten).
Modulen ändrar ingenting: den bara läser och bygger geometrier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from qgis.core import QgsGeometry, QgsPointXY

from . import catalog as cat

USE_TYPE = "användningsbestämmelse"
PROPERTY_TYPE = "egenskapsbestämmelse"


class ImportError_(ValueError):
    """Filen är inte en leverans i det förväntade formatet."""


@dataclass
class ImportedProvision:
    """En rad i tabellen ``bestammelse``, tolkad ur ett planbestämmelseobjekt."""
    catalog_id: str
    formulering: str
    values: list[dict]  # samma form som ``bestammelsevarde`` (beskrivning/variabelvarde/vardetyp/enhet)
    motiv: Optional[str] = None
    giltighetstid: Optional[int] = None
    borjar_galla_efter: Optional[int] = None


@dataclass
class ImportedArea:
    """En yta eller linje, med de bestämmelser som hör till den (samma geometri i leveransen)."""
    table: str  # "anvandning_yta" | "egenskap_yta" | "egenskap_linje"
    geometry: QgsGeometry
    sekundar: bool = False
    provisions: list[ImportedProvision] = field(default_factory=list)


@dataclass
class ImportedPlan:
    attrs: dict[str, Any]  # kommun, namn, syfte, status, typ, beteckning …: skrivs som planlagrets attribut
    geometry: QgsGeometry
    decision: Optional[dict] = None  # första beslutsinformationen, i beslutsinformation-tabellens form
    documents: list[dict] = field(default_factory=list)  # dokument-tabellens form
    areas: list[ImportedArea] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# -- geometri ---------------------------------------------------------------------------------
def _points(coordinates) -> list[QgsPointXY]:
    return [QgsPointXY(float(x), float(y)) for x, y in coordinates]


def _part_geometry(position: dict) -> Optional[QgsGeometry]:
    kind = position.get("type")
    if kind == "Polygon":
        rings = [_points(ring) for ring in position.get("coordinates") or []]
        return QgsGeometry.fromPolygonXY(rings) if rings and rings[0] else None
    if kind == "LineString":
        points = _points(position.get("coordinates") or [])
        return QgsGeometry.fromPolylineXY(points) if len(points) >= 2 else None
    return None


def build_geometry(descriptions: list[dict]) -> Optional[QgsGeometry]:
    """Slår ihop delarna av en ``plangeometri``/``bestammelsegeometri`` (en post per del, se ``export_ngp``) till en
    enda (multi-)geometri. Ger None om den saknar giltiga delar."""
    parts = []
    for item in descriptions or []:
        part = _part_geometry((item.get("geometri") or {}).get("position") or {})
        if part is not None and not part.isEmpty():
            parts.append(part)
    if not parts:
        return None
    geometry = QgsGeometry.unaryUnion(parts) if len(parts) > 1 else parts[0]
    geometry.convertToMultiType()
    return geometry


# -- planbestämmelseobjekt ----------------------------------------------------------------------
def _provision(properties: dict) -> ImportedProvision:
    motiv = ((properties.get("planbestammelsebeskrivning") or {}).get("motiv") or "").strip() or None
    return ImportedProvision(
        catalog_id=properties.get("planbestammelsekatalogreferens") or "",
        formulering=properties.get("bestammelseformulering") or "",
        values=[v for v in properties.get("bestammelsevarde") or [] if isinstance(v, dict)],
        motiv=motiv,
        giltighetstid=properties.get("giltighetstid"),
        borjar_galla_efter=properties.get("borjarGallaEfter"),
    )


def _table(properties: dict, descriptions: list[dict]) -> Optional[str]:
    is_use = properties.get("feature:typ") == USE_TYPE
    if is_use:
        return cat.USE_LAYER
    kind = ((descriptions or [{}])[0].get("geometri") or {}).get("typ")
    return "egenskap_yta" if kind == "yta" else "egenskap_linje" if kind == "linje" else None


# -- beslut och dokument ------------------------------------------------------------------------
def _decision(info: dict) -> dict:
    """En rad i ``beslutsinformation``, ur ett ``beslutsinformation``-objekt (se ``export_ngp.decision_info``)."""
    values: dict[str, Any] = {}
    for key in ("instansInomKommunen", "diarienummerKommun", "diarienummerFullmaktige", "beslutstyp",
                "arkividentitetKommun", "datumPaborjat", "datumAntagande", "genomforandetidStartar"):
        values[key] = info.get(key)
    values["genomforandetid"] = info.get("genomforandetid")
    values["datumLagakraft"] = "; ".join(info.get("datumLagakraft") or []) or None
    values["foregaendePlansBeteckning"] = "; ".join(info.get("foregaendePlansBeteckning") or []) or None
    values["berordDomsMalnummer"] = "; ".join(info.get("berordDomsMalnummer") or []) or None
    return values


def _document_reference(reference: dict) -> dict:
    date_event = reference.get("datum") or {}
    links = reference.get("referens") or []
    link = links[0] if links else {}
    return {
        "namn": reference.get("namn"),
        "kortnamn": reference.get("kortnamn"),
        "datum": date_event.get("datum"),
        "handelse": date_event.get("handelse"),
        "lank": link.get("lank"),
        "referensIdentitet": link.get("identitet"),
        "specifikReferens": "; ".join(reference.get("specifikReferens") or []) or None,
    }


def _documents(properties: dict) -> list[dict]:
    documents: list[dict] = []
    description = (properties.get("planbeskrivning") or {}).get("planbeskrivning")
    if description:
        documents.append({"roll": "planbeskrivning", **_document_reference(description)})
    for beslut in properties.get("beslutsinformation") or []:
        for handling in beslut.get("beslutshandling") or []:
            reference = handling.get("dokument") or {}
            documents.append({"roll": "beslutshandling", "innehall": "; ".join(handling.get("innehall") or []) or None,
                              **_document_reference(reference)})
    for underlag in properties.get("planeringsunderlag") or []:
        reference = underlag.get("underlag") or {}
        documents.append({"roll": "planeringsunderlag", "huvudomrade": underlag.get("huvudomrade"),
                          "underlagstyp": underlag.get("underlagstyp"), **_document_reference(reference)})
    return documents


# -- hela leveransen ----------------------------------------------------------------------------
def parse(collection: dict) -> ImportedPlan:
    """Tolkar en ``FeatureCollection`` (se ``export_ngp.export_plan``). Kastar ``ImportError_`` om den inte ser ut
    som en leverans av en detaljplan."""
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise ImportError_("Filen är inte en FeatureCollection.")
    features = collection.get("features") or []
    plan_feature = next((f for f in features if f.get("properties", {}).get("feature:typ") == "detaljplan"), None)
    if plan_feature is None:
        raise ImportError_("Filen innehåller ingen detaljplan (feature:typ = detaljplan saknas).")
    attrs = plan_feature["properties"]
    quality = attrs.get("kvalitetsbeskrivning") or {}
    plan = ImportedPlan(
        attrs={
            "kommun": attrs.get("kommun"), "beteckning": attrs.get("beteckning"), "namn": attrs.get("namn"),
            "syfte": attrs.get("syfte"), "status": attrs.get("status"), "typ": attrs.get("typ"),
            "vertikalAvgransning": attrs.get("vertikalAvgransning"),
            "digitaliseringsniva": quality.get("digitaliseringsniva"), "beskrivningNiva": quality.get("beskrivningNiva"),
            "korrigeradeGranser": quality.get("korrigeradeGranser"),
            "kontrolleratPlaneringsunderlag": quality.get("kontrolleratPlaneringsunderlag"),
            "anvandbarhet": attrs.get("anvandbarhet"), "beskrivningAnvandbarhet": attrs.get("beskrivningAnvandbarhet"),
        },
        geometry=build_geometry(attrs.get("plangeometri")),
        documents=_documents(attrs),
    )
    decisions = attrs.get("beslutsinformation") or []
    if decisions:
        plan.decision = _decision(decisions[0])
        if len(decisions) > 1:
            plan.warnings.append(f"Planen har {len(decisions)} beslut i leveransen; bara det första importeras "
                                 "(en rad kan redigeras här).")
    if plan.geometry is None or plan.geometry.isEmpty():
        raise ImportError_("Detaljplanen saknar en giltig plangeometri.")

    grouped: dict[tuple, ImportedArea] = {}
    order: list[tuple] = []
    for feature in features:
        properties = feature.get("properties") or {}
        if properties.get("feature:typ") not in (USE_TYPE, PROPERTY_TYPE):
            continue
        descriptions = properties.get("bestammelsegeometri") or []
        table = _table(properties, descriptions)
        geometry = build_geometry(descriptions)
        if table is None or geometry is None or geometry.isEmpty():
            plan.warnings.append("En bestämmelse utan giltig geometri hoppades över.")
            continue
        key = (table, geometry.asWkt(3))
        if key not in grouped:
            grouped[key] = ImportedArea(table=table, geometry=geometry)
            order.append(key)
        area = grouped[key]
        if table == "egenskap_yta" and properties.get("sekundarEgenskapsgrans"):
            area.sekundar = True
        area.provisions.append(_provision(properties))
    plan.areas = [grouped[key] for key in order]
    return plan
