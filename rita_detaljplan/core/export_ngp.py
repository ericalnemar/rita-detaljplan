"""Export av detaljplanen till Lantmäteriets JSON-format för NGP (Nationell informationsspecifikation Detaljplan 4.1).

Resultatet är en GeoJSON-liknande ``FeatureCollection`` (mediatyp ``application/vnd.lm.detaljplan.v4+json``) med

  * ett detaljplanobjekt (planens uppgifter, plangeometri, beslutsinformation, planbeskrivning och underlag), och
  * ett planbestämmelseobjekt per tilldelad bestämmelse (en rad i tabellen ``bestammelse``), med ytans eller linjens
    geometri.

Avvikelser från lagringen i pluginet, som exporten löser (se docs/ngp-regler.md):

  * **Inga multigeometrier**: ``plangeometri`` och ``bestammelsegeometri`` är listor, och varje del av en
    multigeometri blir en egen post (DP-0004, DP-0018).
  * ``reglerarAnvandningsbestammelse`` lagras inte utan härleds här ur geometrin.
  * Kolumner som bara pluginet använder (beteckning, färg, symbol …) följer inte med.
  * Hjälplinjer exporteras aldrig.

Koordinater skrivs som [x, y] = [öst, nord] (som i GeoJSON) med millimeters precision, med ytterringar moturs.
Exporten läser bara planen och ändrar ingenting.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from qgis.core import Qgis, QgsGeometry

from . import model, rules
from .validation import Area, PlanData, _blank, _clean, _to_date

MEDIATYP = model.MEDIATYP
DECIMALS = 3  # millimeter
USE_TYPE = "användningsbestämmelse"
PROPERTY_TYPE = "egenskapsbestämmelse"


# -- hjälpmedel -----------------------------------------------------------------------------
def _put(target: dict, key: str, value: Any) -> None:
    """Lägger till ``key`` om värdet är ifyllt (tomma värden utelämnas ur leveransen)."""
    if value is None or value == "" or value == [] or value == {}:
        return
    target[key] = value


def _split(text) -> list[str]:
    """"a; b" -> ["a", "b"] (flera värden lagras som semikolonseparerad text)."""
    return [part.strip() for part in str(text or "").split(";") if part.strip()]


def _as_int(value) -> Optional[int]:
    try:
        return None if _blank(value) else int(float(value))
    except (TypeError, ValueError):
        return None


def _as_bool(value) -> bool:
    return value in (True, 1, "1", "true", "True")


def _date(value) -> Optional[str]:
    parsed = _to_date(value)
    return parsed.isoformat() if parsed else None


def _round(value: float) -> float:
    rounded = round(float(value), DECIMALS)
    return 0.0 if rounded == 0 else rounded  # inget "-0.0"


def _signed_area(ring: list[tuple[float, float]]) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])) / 2.0


def _ring(points) -> list[list[float]]:
    return [[_round(p.x()), _round(p.y())] for p in points]


def _oriented(ring: list[list[float]], counter_clockwise: bool) -> list[list[float]]:
    """Ringen med önskat varv (den är sluten: första och sista punkten är lika, så omvänd ordning är också sluten)."""
    pairs = [(x, y) for x, y in ring[:-1]]
    return ring if (_signed_area(pairs) > 0) == counter_clockwise else ring[::-1]


def geometry_parts(geometry: Optional[QgsGeometry]) -> list[tuple[str, dict]]:
    """Delarna av en geometri som (typ, GeoJSON-position): "yta" (Polygon) eller "linje" (LineString).

    Multigeometrier delas upp (NGP godtar inte multigeometrier); punkter och tomma delar hoppas över. Ytor får
    ytterringen moturs och hålen medurs. Dubbla punkter efter avrundning tas bort."""
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return []
    parts: list[tuple[str, dict]] = []
    for part in geometry.asGeometryCollection():
        kind = part.type()
        if kind == Qgis.GeometryType.Polygon:
            rings = part.asPolygon()
            if not rings:
                continue
            coordinates = []
            for index, points in enumerate(rings):
                ring = _dedupe(_ring(points))
                if len(ring) < 4:
                    if index == 0:
                        coordinates = []
                        break
                    continue
                coordinates.append(_oriented(ring, counter_clockwise=(index == 0)))
            if coordinates:
                parts.append(("yta", {"type": "Polygon", "coordinates": coordinates}))
        elif kind == Qgis.GeometryType.Line:
            line = _dedupe(_ring(part.asPolyline()))
            if len(line) >= 2:
                parts.append(("linje", {"type": "LineString", "coordinates": line}))
    return parts


def _dedupe(points: list[list[float]]) -> list[list[float]]:
    result: list[list[float]] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return result


# -- geometribeskrivning --------------------------------------------------------------------
def geometry_metadata(attrs: dict) -> dict:
    """``geometrimetadata`` ur ytans kolumner (lägesbestämningsmetod, tidpunkter)."""
    meta: dict[str, Any] = {}
    _put(meta, "tidpunktForLagesbestamning", attrs.get("tidpunktForLagesbestamning"))
    _put(meta, "tidpunktForKontrollAvGeometri", attrs.get("tidpunktForKontrollAvGeometri"))
    method_type = attrs.get("lagesmetodTyp")
    if not _blank(method_type):
        method: dict[str, Any] = {"typ": method_type}
        _put(method, "variant", attrs.get("lagesmetodVariant"))
        scale = _as_int(attrs.get("presentationsskala"))
        if scale and method_type == "lägesplacering":
            method["presentationsskala"] = scale
        meta["lagesbestamningsmetodIPlan"] = method
    return meta


def geometry_descriptions(geometry: Optional[QgsGeometry], attrs: dict, epsg: int) -> list[dict]:
    """``plangeometri``/``bestammelsegeometri``: en post per del av geometrin."""
    metadata = geometry_metadata(attrs)
    result = []
    for kind, position in geometry_parts(geometry):
        result.append({"geometri": {"typ": kind, "position": position, "koordinatsystemPlan": f"EPSG:{epsg}",
                                    "dimension": 2},
                       "geometrimetadata": dict(metadata)})
    return result


# -- dokument och beslut --------------------------------------------------------------------
def document_reference(row: dict) -> dict:
    """``dokumentreferens`` ur en rad i tabellen ``dokument``."""
    reference: dict[str, Any] = {}
    _put(reference, "namn", row.get("namn"))
    _put(reference, "kortnamn", row.get("kortnamn"))
    date, event = _date(row.get("datum")), row.get("handelse")
    if date and event:
        reference["datum"] = {"datum": date, "handelse": event}
    link: dict[str, Any] = {}
    _put(link, "identitet", row.get("referensIdentitet"))
    _put(link, "lank", row.get("lank"))
    reference["referens"] = [link] if link else []
    _put(reference, "specifikReferens", _split(row.get("specifikReferens")))
    return reference


def decision_info(beslut: dict, documents: list[dict], rule_ids: list[str]) -> dict:
    """``beslutsinformation`` ur en rad i tabellen ``beslutsinformation``."""
    info: dict[str, Any] = {}
    for key in ("instansInomKommunen", "diarienummerKommun", "diarienummerFullmaktige", "beslutstyp",
                "arkividentitetKommun"):
        _put(info, key, beslut.get(key))
    handlingar = [{"innehall": [doc["innehall"]], "dokument": document_reference(doc)}
                  for doc in documents if doc.get("roll") == "beslutshandling" and not _blank(doc.get("innehall"))]
    _put(info, "beslutshandling", handlingar)
    for key in ("datumPaborjat", "datumAntagande", "genomforandetidStartar"):
        _put(info, key, _date(beslut.get(key)))
    _put(info, "datumLagakraft", [d for d in (_date(x) for x in _split(beslut.get("datumLagakraft"))) if d])
    _put(info, "genomforandetid", _as_int(beslut.get("genomforandetid")))
    _put(info, "foregaendePlansBeteckning", _split(beslut.get("foregaendePlansBeteckning")))
    _put(info, "berordDomsMalnummer", _split(beslut.get("berordDomsMalnummer")))
    _put(info, "planbestammelse", rule_ids)
    return info


# -- kvalitet -------------------------------------------------------------------------------
def quality(attrs: dict) -> dict:
    """``kvalitetsbeskrivning``; de två booleska fälten är obligatoriska så snart beskrivningen finns."""
    if all(_blank(attrs.get(k)) for k in ("digitaliseringsniva", "beskrivningNiva", "korrigeradeGranser",
                                          "kontrolleratPlaneringsunderlag")):
        return {}
    result: dict[str, Any] = {}
    _put(result, "digitaliseringsniva", attrs.get("digitaliseringsniva"))
    _put(result, "beskrivningNiva", attrs.get("beskrivningNiva"))
    result["korrigeradeGranser"] = _as_bool(attrs.get("korrigeradeGranser"))
    result["kontrolleratPlaneringsunderlag"] = _as_bool(attrs.get("kontrolleratPlaneringsunderlag"))
    return result


def _identity(properties: dict, attrs: dict) -> None:
    properties["objektidentitet"] = attrs.get("objektidentitet")
    properties["objektversion"] = _as_int(attrs.get("objektversion")) or 1
    properties["versionGiltigFran"] = attrs.get("versionGiltigFran")


# -- objekten -------------------------------------------------------------------------------
def plan_feature(data: PlanData) -> dict:
    plan = data.plan
    attrs = plan.attrs
    properties: dict[str, Any] = {"feature:typ": "detaljplan"}
    _identity(properties, attrs)
    for key in ("kommun", "beteckning", "namn", "syfte", "status", "typ"):
        _put(properties, key, attrs.get(key))
    _put(properties, "datumStatusforandring", _date(attrs.get("datumStatusforandring")))
    _put(properties, "kvalitetsbeskrivning", quality(attrs))
    _put(properties, "anvandbarhet", attrs.get("anvandbarhet"))
    _put(properties, "beskrivningAnvandbarhet", attrs.get("beskrivningAnvandbarhet"))
    properties["plangeometri"] = geometry_descriptions(plan.geometry, attrs, data.epsg)
    _put(properties, "vertikalAvgransning", attrs.get("vertikalAvgransning"))

    documents = data.dokument
    rule_ids = [row["objektidentitet"] for row in data.rows if row.get("objektidentitet")]
    decisions = [decision_info(b, documents, rule_ids if len(data.beslut) == 1 else []) for b in data.beslut]
    properties["beslutsinformation"] = [d for d in decisions]
    description = next((d for d in documents if d.get("roll") == "planbeskrivning"), None)
    if description is not None:
        properties["planbeskrivning"] = {"planbeskrivning": document_reference(description)}
    background = []
    for doc in documents:
        if doc.get("roll") == "planeringsunderlag" and not _blank(doc.get("huvudomrade")):
            item: dict[str, Any] = {"huvudomrade": doc["huvudomrade"]}
            _put(item, "underlagstyp", doc.get("underlagstyp"))
            item["underlag"] = document_reference(doc)
            background.append(item)
    _put(properties, "planeringsunderlag", background)
    return {"type": "Feature", "geometry": None, "properties": properties}


def regulated_uses(area: Area, data: PlanData) -> list[str]:
    """``reglerarAnvandningsbestammelse``: användningsbestämmelserna på de användningsytor som egenskapen ligger på."""
    if area.geometry is None or area.geometry.isEmpty():
        return []
    ids: list[str] = []
    for use in data.of("anvandning_yta"):
        if use.geometry.isEmpty():
            continue
        if area.is_area:
            touching = use.geometry.intersection(area.geometry).area() > rules.MIN_OVERLAP
        else:
            touching = use.geometry.distance(area.geometry) <= rules.TOLERANCE
        if touching:
            ids += [r["objektidentitet"] for r in data.rows
                    if r.get("tabell") == "anvandning_yta" and r.get("yta") == use.identity and r.get("objektidentitet")]
    return list(dict.fromkeys(ids))


def provision_feature(row: dict, area: Area, data: PlanData) -> dict:
    row = {key: _clean(value) for key, value in row.items()}  # tidpunkter som text, tomma värden som None
    is_use = row.get("tabell") == "anvandning_yta"
    properties: dict[str, Any] = {"feature:typ": USE_TYPE if is_use else PROPERTY_TYPE,
                                  "detaljplan": data.plan.attrs.get("objektidentitet")}
    _identity(properties, row)
    properties["planbestammelsekatalogreferens"] = row.get("planbestammelsekatalogreferens")
    properties["bestammelseformulering"] = row.get("bestammelseformulering")
    if row.get("avviker"):
        _put(properties, "ursprungligBestammelseformulering", row.get("ursprungligBestammelseformulering"))
    values = _stored_values(row.get("bestammelsevarde"))
    _put(properties, "bestammelsevarde", values)
    _put(properties, "kvalitetsbeskrivning", quality(row))
    _put(properties, "anvandbarhet", row.get("anvandbarhet"))
    _put(properties, "beskrivningAnvandbarhet", row.get("beskrivningAnvandbarhet"))
    properties["bestammelsegeometri"] = geometry_descriptions(area.geometry, area.attrs, data.epsg)
    _put(properties, "vertikalAvgransning", row.get("vertikalAvgransning") if area.is_area else None)
    if not _blank(row.get("motiv")):
        properties["planbestammelsebeskrivning"] = {"motiv": row["motiv"]}
    if is_use:
        _put(properties, "giltighetstid", _as_int(row.get("giltighetstid")))
        _put(properties, "borjarGallaEfter", _as_int(row.get("borjarGallaEfter")))
    else:
        if row.get("sekundarEgenskapsgrans") is not None:
            properties["sekundarEgenskapsgrans"] = _as_bool(row.get("sekundarEgenskapsgrans"))
        _put(properties, "reglerarAnvandningsbestammelse", regulated_uses(area, data))
    return {"type": "Feature", "geometry": None, "properties": properties}


def _stored_values(stored) -> list[dict]:
    try:
        values = json.loads(stored) if stored else []
    except (TypeError, json.JSONDecodeError):
        return []
    return [v for v in values if isinstance(v, dict)]


def export_plan(data: PlanData) -> dict:
    """Hela leveransen som en ``FeatureCollection``. Kastar ``ValueError`` om planområdet saknas."""
    if data.plan is None:
        raise ValueError("Planområdet är inte ritat.")
    areas = {(a.table, a.identity): a for a in data.areas}
    features = [plan_feature(data)]
    for row in data.rows:
        area = areas.get((row.get("tabell"), row.get("yta")))
        if area is not None:  # bestämmelser vars yta raderats levereras inte
            features.append(provision_feature(row, area, data))
    return {"type": "FeatureCollection", "feature:mediatyp": MEDIATYP, "features": features}


def counts(collection: dict) -> tuple[int, int]:
    """(antal bestämmelseobjekt, antal geometrier) i en leverans, till meddelandet efter exporten."""
    provisions = collection["features"][1:]
    geometries = sum(len(f["properties"]["bestammelsegeometri"]) for f in provisions)
    return len(provisions), geometries


def dumps(collection: dict) -> str:
    return json.dumps(collection, ensure_ascii=False, indent=2)
