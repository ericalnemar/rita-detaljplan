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
from . import model, rows, rules
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


def copy_rows(project: QgsProject, table: str, from_identity: str, to_identity: str) -> int:
    """Kopierar en ytas bestämmelser till en annan yta (t.ex. när en yta delats): var och en får egen identitet.
    Returnerar antal kopierade rader."""
    rows_lyr = rows_layer(project)
    if rows_lyr is None:
        return 0
    copied = 0
    for row in read_rows(project, table, from_identity):
        if not rows_lyr.isEditable() and not rows_lyr.startEditing():
            break
        attributes = {**{k: row.get(k) for k in _ROW_KEYS}, "tabell": table, "yta": to_identity,
                      "ordning": row.get("ordning")}
        if rows_lyr.addFeature(_new_row_feature(rows_lyr, attributes)):
            copied += 1
    return copied


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


def _inherit_motive(project: QgsProject, row: dict, exclude_fid: Optional[int] = None) -> None:
    """Saknar bestämmelsen motiv får den samma motiv som samma bestämmelse har på en annan yta i planen: motivet hör
    till bestämmelsen och skrivs en gång (fliken Motiv till planbestämmelser i Planens uppgifter)."""
    if _clean(row.get("motiv")):
        return
    for other in read_rows(project):
        if other["_fid"] != exclude_fid and rows.identity(other) == rows.identity(row) and _clean(other.get("motiv")):
            row["motiv"] = other["motiv"]
            return


def set_motives(project: QgsProject, motives: dict) -> int:
    """Sätter motiv per bestämmelse: ``motives`` = {rows.identity(rad): text}. Gäller alla rader med den bestämmelsen
    (utom "Tekniska anläggningar", vars motiv är fast). Returnerar antal ändrade rader."""
    rows_lyr = rows_layer(project)
    if rows_lyr is None:
        return 0
    changed = 0
    for row in read_rows(project):
        key = rows.identity(row)
        if key not in motives or row.get("bestammelseformulering") == cat.TECHNICAL_FORMULATION:
            continue
        text = (motives[key] or "").strip() or None
        if text != (_clean(row.get("motiv")) or None):
            apply_attributes(rows_lyr, [row["_fid"]], {"motiv": text})
            changed += 1
    return changed


def add(project: QgsProject, table: str, fid: int, entry: cat.CatalogEntry, values: list[bm.VariableValue],
        motiv: Optional[str] = None, formulation: Optional[str] = None, label: Optional[str] = None) -> dict:
    """Sätter en bestämmelse på en yta och returnerar den nya raden. ``label``: beteckningen planförfattaren valt när
    katalogens beteckning har en variabel."""
    layer, feature = _area(project, table, fid)
    rows_lyr = rows_layer(project)
    if rows_lyr is None:
        raise AssignmentError("Tabellen för bestämmelser saknas i projektet.")
    yta = feature["objektidentitet"]
    existing = read_rows(project, table, yta)
    _check(project, table, feature, entry, existing)
    try:
        row = rows.build_row(entry, values, motiv, formulation, existing_rows=read_rows(project), label=label)
    except ValueError as exc:
        raise AssignmentError(str(exc)) from exc
    if any(rows.identity(r) == rows.identity(row) for r in existing):
        raise AssignmentError("Ytan har redan den bestämmelsen.")
    _inherit_motive(project, row)

    if not rows_lyr.isEditable() and not rows_lyr.startEditing():
        raise AssignmentError("Kan inte redigera tabellen för bestämmelser.")
    order = max([r.get("ordning") or 0 for r in existing] + [len(existing)]) + 1  # sist bland ytans bestämmelser
    new = _new_row_feature(rows_lyr, {**{k: row.get(k) for k in _ROW_KEYS}, "tabell": table, "yta": yta,
                                      "ordning": order})
    if not rows_lyr.addFeature(new):
        raise AssignmentError("Kunde inte lägga till bestämmelsen.")
    row.update(_keep_label_unique(project, rows_lyr, new.id()) or {})
    refresh_area(project, table, fid)
    return {**row, "yta": yta, "_fid": new.id()}


def update(project: QgsProject, row_fid: int, entry: cat.CatalogEntry, values: list[bm.VariableValue],
           motiv: Optional[str] = None, formulation: Optional[str] = None, label: Optional[str] = None) -> dict:
    """Byter ut en tilldelad bestämmelse mot en annan (eller ändrar dess värden, text eller motiv). Anges ingen
    ``label`` behåller samma bestämmelse sin beteckning."""
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
    if label is None and current.get("planbestammelsekatalogreferens") == entry.id:
        label = rows.label_text(entry, current)
    try:
        row = rows.build_row(entry, values, motiv, formulation,
                             existing_rows=[r for r in read_rows(project) if r["_fid"] != row_fid], label=label)
    except ValueError as exc:
        raise AssignmentError(str(exc)) from exc
    if any(rows.identity(r) == rows.identity(row) for r in existing if r["_fid"] != row_fid):
        raise AssignmentError("Ytan har redan den bestämmelsen.")
    if motiv is None and rows.identity(current) == rows.identity(row):
        row["motiv"] = current.get("motiv")  # samma bestämmelse: motivet ligger kvar
    _inherit_motive(project, row, exclude_fid=row_fid)
    apply_attributes(rows_lyr, [row_fid], {k: row.get(k) for k in _ROW_KEYS})
    row.update(_keep_label_unique(project, rows_lyr, row_fid) or {})
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


def quality_values(project: QgsProject, row_fid: int) -> dict:
    """Bestämmelsens kvalitetsbeskrivning (digitaliseringsnivå, korrigerade gränser m.m.) och användbarhet – krävs
    vid laga kraft (se ``core.validation.check_laga_kraft``). Ett eget litet läs/skriv-par, fristående från
    ``add``/``update`` (som bygger om hela raden ur en katalogpost): kvalitet hör inte till bestämmelsens
    innehåll utan beskriver hur den digitaliserats, så den ändras utan att röra bestämmelsen i övrigt."""
    row = next((r for r in read_rows(project) if r["_fid"] == row_fid), None)
    return {name: (row.get(name) if row else None) for name in model.QUALITY_FIELDS}


def set_quality(project: QgsProject, row_fid: int, values: dict) -> None:
    """Sparar en bestämmelses kvalitetsbeskrivning och användbarhet."""
    rows_lyr = rows_layer(project)
    if rows_lyr is None or not any(r["_fid"] == row_fid for r in read_rows(project)):
        raise AssignmentError("Bestämmelsen finns inte längre.")
    if not rows_lyr.isEditable() and not rows_lyr.startEditing():
        raise AssignmentError("Kan inte redigera tabellen för bestämmelser.")
    changed = {name: (values[name] if values.get(name) not in ("", None) else None)
              for name in model.QUALITY_FIELDS if name in values}
    apply_attributes(rows_lyr, [row_fid], changed)


def regulates_plan(project: QgsProject, row_fid: int) -> Optional[str]:
    """Identiteten (UUID) på den andra detaljplan en egenskapsbestämmelse reglerar (``reglerarDetaljplan``, NIS
    Detaljplan 4.1, t.ex. vid samordning mellan grannplaner), eller None. Gäller bara egenskapsbestämmelser –
    fältet finns bara för tabellerna "egenskap_yta"/"egenskap_linje"."""
    row = next((r for r in read_rows(project) if r["_fid"] == row_fid), None)
    return row.get("reglerarDetaljplan") if row else None


def set_regulates_plan(project: QgsProject, row_fid: int, identity: Optional[str]) -> None:
    """Sparar vilken annan detaljplan bestämmelsen reglerar (eller tar bort kopplingen om ``identity`` är tomt)."""
    rows_lyr = rows_layer(project)
    if rows_lyr is None or not any(r["_fid"] == row_fid for r in read_rows(project)):
        raise AssignmentError("Bestämmelsen finns inte längre.")
    if not rows_lyr.isEditable() and not rows_lyr.startEditing():
        raise AssignmentError("Kan inte redigera tabellen för bestämmelser.")
    apply_attributes(rows_lyr, [row_fid], {"reglerarDetaljplan": (identity or "").strip() or None})


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


def reindex(project: QgsProject, table: str, fid: int) -> int:
    """Numrerar om index i beteckningen (t.ex. F1/F2) bland ytans bestämmelser så att de följer ordningen i
    listan i stället för när de först lades till (``ordning`` styr bara teckenordningen i beteckningen, se
    ``move`` – inte indexsiffran). Gäller bara indexerade beteckningar ("#" i katalogens egen beteckning, t.ex.
    "e#"). En indexerad bestämmelse delas eventuellt av flera ytor (samma bestämmelse ska ha samma beteckning
    överallt, se ``rows.identity``) och räknas om där också, men bara inom det redan använda talområdet för
    ytans egna bestämmelser (t.ex. F1/F2 byter bara plats med varandra) – andra ytors bestämmelser med samma
    bokstav men andra tal rörs inte. Returnerar antal ändrade rader."""
    rows_lyr = rows_layer(project)
    layer = find_layer(project, table)
    if rows_lyr is None or layer is None:
        return 0
    siblings = read_rows(project, table, layer.getFeature(fid)["objektidentitet"])  # redan sorterade efter ordning
    groups: dict[str, list[tuple]] = {}
    for row in siblings:
        index = row.get("beteckningsindex")
        if index is None:
            continue
        key = rows.base(row.get("beteckning"), index)
        identity = rows.identity(row)
        bucket = groups.setdefault(key, [])
        if identity not in bucket:
            bucket.append(identity)

    all_rows = read_rows(project)
    changed = 0
    touched: set[tuple[str, str]] = set()
    for key, identities in groups.items():
        if len(identities) < 2:
            continue  # bara en bestämmelse med den bokstaven: inget att numrera om
        current = [next(r["beteckningsindex"] for r in siblings if rows.identity(r) == identity)
                  for identity in identities]
        for identity, old_index, new_index in zip(identities, current, sorted(current)):
            if old_index == new_index:
                continue
            matching = [r for r in all_rows if rows.identity(r) == identity
                        and rows.base(r.get("beteckning"), r.get("beteckningsindex")) == key]
            if not rows_lyr.isEditable() and not rows_lyr.startEditing():
                raise AssignmentError("Kan inte redigera tabellen för bestämmelser.")
            apply_attributes(rows_lyr, [r["_fid"] for r in matching],
                             {"beteckningsindex": new_index, "beteckning": f"{key}{new_index}"})
            changed += len(matching)
            touched.update((r["tabell"], r["yta"]) for r in matching)

    changed += _resolve_duplicate_labels(project, rows_lyr, touched)
    _refresh_touched(project, touched)
    return changed


def _refresh_touched(project: QgsProject, touched: set) -> None:
    """Uppdaterar beteckning, färg och symbol på ytorna ((tabell, yta-identitet)) vars bestämmelser ändrats."""
    for touched_table, touched_yta in touched:
        layer = find_layer(project, touched_table)
        feature = next((f for f in layer.getFeatures() if f["objektidentitet"] == touched_yta), None) \
            if layer is not None else None
        if feature is not None:
            refresh_area(project, touched_table, feature.id())


def fix_duplicate_labels(project: QgsProject) -> int:
    """Rättar beteckningar som används för olika bestämmelser i planen (den som lades till sist får nästa lediga
    siffra). Returnerar antal ändrade rader. Körs när planen sparas."""
    rows_lyr = rows_layer(project)
    if rows_lyr is None:
        return 0
    touched: set = set()
    changed = _resolve_duplicate_labels(project, rows_lyr, touched)
    _refresh_touched(project, touched)
    return changed


def _keep_label_unique(project: QgsProject, rows_lyr: QgsVectorLayer, row_fid: int) -> Optional[dict]:
    """Säkerhetsnät: en rad som just lagts till eller ändrats får aldrig samma beteckning som en annan bestämmelse i
    planen. Ger raden i så fall nästa lediga siffra. Returnerar de ändrade värdena, eller None."""
    all_rows = read_rows(project)
    mine = next((r for r in all_rows if r["_fid"] == row_fid), None)
    if mine is None or mine.get("beteckningsindex") is None:
        return None
    is_use = mine.get("tabell") == cat.USE_LAYER
    key = rows.base(mine.get("beteckning"), mine["beteckningsindex"])
    same_kind = [r for r in all_rows if r["_fid"] != row_fid and r.get("beteckningsindex") is not None
                 and (r.get("tabell") == cat.USE_LAYER) == is_use
                 and rows.base(r.get("beteckning"), r["beteckningsindex"]) == key]
    if not any(r["beteckningsindex"] == mine["beteckningsindex"] and rows.identity(r) != rows.identity(mine)
               for r in same_kind):
        return None
    used = {r["beteckningsindex"] for r in same_kind}
    new_index = 1
    while new_index in used:
        new_index += 1
    values = {"beteckningsindex": new_index, "beteckning": f"{key}{new_index}"}
    apply_attributes(rows_lyr, [row_fid], values)
    return values


def duplicate_labels(all_rows: list[dict]) -> dict[tuple, dict[tuple, list[dict]]]:
    """Beteckningar som används för olika bestämmelser i planen: {(är användning, bokstav, index): {identitet: rader}}.
    En beteckning (f1) ska höra till exakt en bestämmelse i hela planen."""
    found: dict[tuple, dict[tuple, list[dict]]] = {}
    for row in all_rows:
        index = row.get("beteckningsindex")
        if index is None:
            continue
        key = (row.get("tabell") == cat.USE_LAYER, rows.base(row.get("beteckning"), index), index)
        found.setdefault(key, {}).setdefault(rows.identity(row), []).append(row)
    return {key: identities for key, identities in found.items() if len(identities) > 1}


def _resolve_duplicate_labels(project: QgsProject, rows_lyr: QgsVectorLayer, touched: set) -> int:
    """Ger en beteckning som används för flera olika bestämmelser i planen nästa lediga siffra för alla utom den
    bestämmelse som lades till först. Returnerar antal ändrade rader."""
    all_rows = read_rows(project)
    changed = 0
    for (is_use, key, index), identities in sorted(duplicate_labels(all_rows).items(), key=lambda kv: kv[0][2]):
        used = {r.get("beteckningsindex") for r in all_rows
                if r.get("beteckningsindex") is not None
                and (r.get("tabell") == cat.USE_LAYER) == is_use
                and rows.base(r.get("beteckning"), r.get("beteckningsindex")) == key}
        groups = sorted(identities.values(), key=lambda rs: min(r["_fid"] for r in rs))
        for group in groups[1:]:
            new_index = 1
            while new_index in used:
                new_index += 1
            used.add(new_index)
            if not rows_lyr.isEditable() and not rows_lyr.startEditing():
                raise AssignmentError("Kan inte redigera tabellen för bestämmelser.")
            apply_attributes(rows_lyr, [r["_fid"] for r in group],
                             {"beteckningsindex": new_index, "beteckning": f"{key}{new_index}"})
            changed += len(group)
            touched.update((r["tabell"], r["yta"]) for r in group)
    return changed


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
