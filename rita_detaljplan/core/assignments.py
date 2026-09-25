"""Tilldelning av bestämmelser till ytor: lägga till, ändra och ta bort rader i tabellen ``bestammelse``.

Ändringarna görs i lagrens redigeringsbuffert, så de sparas (eller kastas) tillsammans med resten av planen när
redigeringen avslutas. Efter varje ändring uppdateras ytans beteckning, färg och symbol (``rows.summarize``).
"""
from __future__ import annotations

import uuid
from typing import Optional

from qgis.core import NULL, QgsExpressionContext, QgsExpressionContextUtils, QgsFeature, QgsGeometry, QgsProject, \
    QgsVectorLayer, QgsVectorLayerUtils

from . import bestammelse as bm
from . import catalog as cat
from . import rows, rules
from .project import apply_attributes, find_layer

ROWS_TABLE = "bestammelse"
_FORMS = ("Kvartersmark", "Allmän plats", "Vattenområde")
_ROW_KEYS = (*rows.ATTRIBUTE_KEYS, "beteckning", "beteckningsindex")


class AssignmentError(RuntimeError):
    """Bestämmelsen kan inte sättas på ytan. Meddelandet är avsett för användaren."""


def _clean(value):
    return None if value == NULL or value is None else value


def rows_layer(project: QgsProject) -> Optional[QgsVectorLayer]:
    return find_layer(project, ROWS_TABLE)


def read_rows(project: QgsProject, table: str | None = None, yta: str | None = None) -> list[dict]:
    """Alla bestämmelserader (eller de som hör till en yta). Varje rad får nyckeln ``_fid`` med objektets id."""
    layer = rows_layer(project)
    if layer is None:
        return []
    names = [field.name() for field in layer.fields()]
    result = []
    for feature in layer.getFeatures():
        row = {name: _clean(value) for name, value in zip(names, feature.attributes())}
        if (table is None or row["tabell"] == table) and (yta is None or row["yta"] == yta):
            row["_fid"] = feature.id()
            result.append(row)
    # ordningen bland en ytas bestämmelser; rader utan ordning (äldre planer) kommer först, i den ordning de skapades
    result.sort(key=lambda r: (r.get("ordning") or 0, r["_fid"]))
    return result


def rows_of_area(project: QgsProject, table: str, fid: int) -> list[dict]:
    layer = find_layer(project, table)
    if layer is None:
        return []
    return read_rows(project, table, layer.getFeature(fid)["objektidentitet"])


def ensure_identity(layer: QgsVectorLayer, fid: int) -> None:
    """Ger en yta som saknar objektidentitet en (objekt som inte skapats med ritverktyget får inga standardvärden).

    Utan identitet skulle alla ytor dela identiteten NULL och därmed samma bestämmelser."""
    feature = layer.getFeature(fid)
    if feature.isValid() and not _clean(feature["objektidentitet"]):
        apply_attributes(layer, [fid], {"objektidentitet": str(uuid.uuid4())})


def reset_new_area(project: QgsProject, table: str, fid: int) -> None:
    """Gör en nyskapad yta till en ren yta: egen identitet, inga bestämmelser och automatiskt textläge.

    En yta som delats med delaverktyget (eller kopierats) får kopior av grannens beteckning, färg, symbol och
    textläge men inga bestämmelser: den ska då visas som "saknar bestämmelse"."""
    layer = find_layer(project, table)
    feature = layer.getFeature(fid) if layer is not None else None
    if layer is None or not feature.isValid():
        return
    identity = _clean(feature["objektidentitet"])
    duplicate = identity and any(f.id() != fid and _clean(f["objektidentitet"]) == identity
                                 for f in layer.getFeatures())
    if not identity or duplicate:
        apply_attributes(layer, [fid], {"objektidentitet": str(uuid.uuid4())})
    if find_layer(project, ROWS_TABLE) is not None and table in (cat.USE_LAYER, *cat.PROPERTY_LAYERS):
        refresh_area(project, table, fid)
    apply_attributes(layer, [fid], {"label_x": None, "label_y": None, "label_w": None})


def _area(project: QgsProject, table: str, fid: int) -> tuple[QgsVectorLayer, QgsFeature]:
    layer = find_layer(project, table)
    feature = layer.getFeature(fid) if layer is not None else None
    if layer is None or not feature.isValid():
        raise AssignmentError("Ytan finns inte längre.")
    if not _clean(feature["objektidentitet"]):
        ensure_identity(layer, fid)
        feature = layer.getFeature(fid)
    return layer, feature


def new_feature(layer: QgsVectorLayer, attributes: dict) -> QgsFeature:
    """Ett nytt objekt (utan geometri) med standardvärden och angivna attribut, redo att läggas till i lagret."""
    return _new_row_feature(layer, attributes)


def _new_row_feature(layer: QgsVectorLayer, attributes: dict) -> QgsFeature:
    context = QgsExpressionContext()
    context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    indexed = {layer.fields().indexOf(name): value for name, value in attributes.items()
               if layer.fields().indexOf(name) >= 0}
    return QgsVectorLayerUtils.createFeature(layer, QgsGeometry(), indexed, context)


def _check(project: QgsProject, table: str, feature: QgsFeature, entry: cat.CatalogEntry,
           existing: list[dict], ignore_fid: Optional[int] = None) -> None:
    """Regler för att sätta en bestämmelse på en yta."""
    if entry.layer_name != table:
        raise AssignmentError("Bestämmelsen hör till en annan typ av yta.")
    others = [r for r in existing if r["_fid"] != ignore_fid]
    if table == cat.USE_LAYER:
        forms = {r["anvandningsform"] for r in others if r["anvandningsform"]}
        if entry.anvandningsform in _FORMS and forms and entry.anvandningsform not in forms:
            raise AssignmentError(f"Ytan är {', '.join(sorted(forms)).lower()}: en användningsyta kan inte "
                                  f"samtidigt vara {entry.anvandningsform.lower()}.")
    else:
        use_layer = find_layer(project, cat.USE_LAYER)
        link = rules.link_property(feature.geometry(), use_layer, entry.anvandningsform)
        if not link.ok:
            raise AssignmentError(link.problems[0])


def refresh_area(project: QgsProject, table: str, fid: int) -> dict:
    """Uppdaterar ytans beteckning, färg, symbol och användningsform utifrån dess bestämmelser."""
    layer, feature = _area(project, table, fid)
    summary = rows.summarize(read_rows(project, table, feature["objektidentitet"]))
    apply_attributes(layer, [fid], summary)
    return summary


def add(project: QgsProject, table: str, fid: int, entry: cat.CatalogEntry, values: list[bm.VariableValue],
        motiv: Optional[str] = None, formulation: Optional[str] = None) -> dict:
    """Sätter en bestämmelse på en yta och returnerar den nya raden."""
    layer, feature = _area(project, table, fid)
    rows_lyr = rows_layer(project)
    if rows_lyr is None:
        raise AssignmentError("Tabellen för bestämmelser saknas i projektet.")
    yta = feature["objektidentitet"]
    existing = read_rows(project, table, yta)
    _check(project, table, feature, entry, existing)
    try:
        row = rows.build_row(entry, values, motiv, formulation, existing_rows=read_rows(project))
    except ValueError as exc:
        raise AssignmentError(str(exc)) from exc
    if any(rows.identity(r) == rows.identity(row) for r in existing):
        raise AssignmentError("Ytan har redan den bestämmelsen.")

    if not rows_lyr.isEditable() and not rows_lyr.startEditing():
        raise AssignmentError("Kan inte redigera tabellen för bestämmelser.")
    order = max([r.get("ordning") or 0 for r in existing] + [len(existing)]) + 1  # sist bland ytans bestämmelser
    new = _new_row_feature(rows_lyr, {**{k: row.get(k) for k in _ROW_KEYS}, "tabell": table, "yta": yta,
                                      "ordning": order})
    if not rows_lyr.addFeature(new):
        raise AssignmentError("Kunde inte lägga till bestämmelsen.")
    refresh_area(project, table, fid)
    return {**row, "yta": yta, "_fid": new.id()}


def update(project: QgsProject, row_fid: int, entry: cat.CatalogEntry, values: list[bm.VariableValue],
           motiv: Optional[str] = None, formulation: Optional[str] = None) -> dict:
    """Byter ut en tilldelad bestämmelse mot en annan (eller ändrar dess värden, text eller motiv)."""
    rows_lyr = rows_layer(project)
    current = next((r for r in read_rows(project) if r["_fid"] == row_fid), None)
    if current is None:
        raise AssignmentError("Bestämmelsen finns inte längre.")
    table = current["tabell"]
    layer = find_layer(project, table)
    feature = next((f for f in layer.getFeatures() if f["objektidentitet"] == current["yta"]), None)
    if feature is None:
        raise AssignmentError("Ytan finns inte längre.")
    existing = read_rows(project, table, current["yta"])
    _check(project, table, feature, entry, existing, ignore_fid=row_fid)
    try:
        row = rows.build_row(entry, values, motiv, formulation,
                             existing_rows=[r for r in read_rows(project) if r["_fid"] != row_fid])
    except ValueError as exc:
        raise AssignmentError(str(exc)) from exc
    if any(rows.identity(r) == rows.identity(row) for r in existing if r["_fid"] != row_fid):
        raise AssignmentError("Ytan har redan den bestämmelsen.")
    apply_attributes(rows_lyr, [row_fid], {k: row.get(k) for k in _ROW_KEYS})
    refresh_area(project, table, feature.id())
    return {**current, **row}


def remove(project: QgsProject, row_fid: int) -> None:
    rows_lyr = rows_layer(project)
    current = next((r for r in read_rows(project) if r["_fid"] == row_fid), None)
    if current is None:
        return
    if not rows_lyr.isEditable() and not rows_lyr.startEditing():
        raise AssignmentError("Kan inte redigera tabellen för bestämmelser.")
    rows_lyr.deleteFeature(row_fid)
    layer = find_layer(project, current["tabell"])
    feature = next((f for f in layer.getFeatures() if f["objektidentitet"] == current["yta"]), None) if layer else None
    if feature is not None:
        refresh_area(project, current["tabell"], feature.id())


def move(project: QgsProject, row_fid: int, steps: int) -> bool:
    """Flyttar en bestämmelse ``steps`` platser upp (negativt) eller ned (positivt) bland ytans bestämmelser.

    Ordningen styr ordningen i ytans beteckning (t.ex. BC eller CB) och vilken färg och symbol som visas.
    Returnerar False om raden redan ligger ytterst."""
    rows_lyr = rows_layer(project)
    current = next((r for r in read_rows(project) if r["_fid"] == row_fid), None)
    if rows_lyr is None or current is None:
        return False
    siblings = read_rows(project, current["tabell"], current["yta"])
    position = next(i for i, r in enumerate(siblings) if r["_fid"] == row_fid)
    target = max(0, min(len(siblings) - 1, position + steps))
    if target == position:
        return False
    siblings.insert(target, siblings.pop(position))
    if not rows_lyr.isEditable() and not rows_lyr.startEditing():
        raise AssignmentError("Kan inte redigera tabellen för bestämmelser.")
    for number, sibling in enumerate(siblings, start=1):  # numrera om alla så att det aldrig blir lika
        if sibling.get("ordning") != number:
            apply_attributes(rows_lyr, [sibling["_fid"]], {"ordning": number})
    layer = find_layer(project, current["tabell"])
    feature = next((f for f in layer.getFeatures() if f["objektidentitet"] == current["yta"]), None) if layer else None
    if feature is not None:
        refresh_area(project, current["tabell"], feature.id())
    return True


def remove_orphans(project: QgsProject) -> int:
    """Tar bort bestämmelser vars yta har raderats. Returnerar antal borttagna rader."""
    rows_lyr = rows_layer(project)
    if rows_lyr is None:
        return 0
    existing = {}
    for table in cat.LAYER_DELIVERY_TYPE:
        layer = find_layer(project, table)
        existing[table] = {f["objektidentitet"] for f in layer.getFeatures()} if layer is not None else set()
    orphans = [r["_fid"] for r in read_rows(project) if r["yta"] not in existing.get(r["tabell"], set())]
    if orphans:
        if not rows_lyr.isEditable() and not rows_lyr.startEditing():
            return 0
        for fid in orphans:
            rows_lyr.deleteFeature(fid)
    return len(orphans)


def refresh_all(project: QgsProject) -> None:
    for table in cat.LAYER_DELIVERY_TYPE:
        layer = find_layer(project, table)
        if layer is not None:
            for feature in layer.getFeatures():
                refresh_area(project, table, feature.id())


def allowed_forms(project: QgsProject, table: str, fid: int) -> Optional[set[str]]:
    """Användningsformer som passar ytan, eller None om alla passar (inget är känt än)."""
    layer, feature = _area(project, table, fid)
    if table == cat.USE_LAYER:
        forms = {r["anvandningsform"] for r in rows_of_area(project, table, fid) if r["anvandningsform"]}
        return forms or None
    use_layer = find_layer(project, cat.USE_LAYER)
    forms = set()
    geometry = feature.geometry()
    is_area = rules.geometry_kind(geometry) == "yta"
    for use in use_layer.getFeatures():
        if not _clean(use["anvandningsform"]):
            continue
        if is_area:
            # bara användning som ytan faktiskt ligger på; en granne som bara delar kant räknas inte
            touching = use.geometry().intersection(geometry).area() > rules.MIN_OVERLAP
        else:
            touching = use.geometry().intersects(geometry) or use.geometry().distance(geometry) <= rules.TOLERANCE
        if touching:
            forms.add(use["anvandningsform"])
    return forms or None


def entries_for(project: QgsProject, catalog: cat.Catalog, table: str, fid: int) -> list[cat.CatalogEntry]:
    """Bestämmelser som kan sättas på ytan: rätt lager, och användningsform som passar det som ligger under."""
    forms = allowed_forms(project, table, fid)
    entries = catalog.search(layer=table)
    if forms:
        entries = [e for e in entries if e.anvandningsform in forms or e.anvandningsform == "Planområdet"]
    return sorted(entries, key=lambda e: (e.anvandningsform, e.kategori, e.kod))
