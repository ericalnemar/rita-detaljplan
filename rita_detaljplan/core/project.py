"""Laddar detaljplanens GeoPackage i ett QGIS-projekt och konfigurerar formulär, kodlistor och relationer."""
from __future__ import annotations

from pathlib import Path

from qgis.core import (
    NULL,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsDefaultValue,
    QgsEditFormConfig,
    QgsEditorWidgetSetup,
    QgsFieldConstraints,
    QgsProject,
    QgsRelation,
    QgsRelationContext,
    QgsVectorLayer,
)

from . import geopackage, model, settings, symbology
from . import storage as storage_module

# Obs: nycklarna nedan behåller det gamla prefixet ``detaljplan_ngp`` (pluginet hette förr Detaljplan NGP) så att redan
# skapade projekt och sparade inställningar fortsätter fungera efter namnbytet.
TABLE_PROPERTY = "detaljplan_ngp/table"
PLAN_GROUP_PROPERTY = "detaljplan_ngp/plan_group"  # markerar gruppen som håller planens lager

# Tekniska fält som användaren aldrig ska behöva se eller skriva i formulären för ytor och bestämmelser.
# Pluginet sätter dem (UUID, koppling till plan och yta, beteckning, färg, lägesmetod m.m.).
_HIDDEN = frozenset({
    "objektidentitet", "objektversion", "versionGiltigFran", "detaljplan", "tabell", "yta", "beteckningsindex",
    "planbestammelsekatalogreferens", "bestammelsekod", "anvandningsform", "farg", "symbol", "avviker",
    "bestammelser", "label_x", "label_y", "ordning", "ursprungligBestammelseformulering", "bestammelsevarde", "reglerarDetaljplan",
    "digitaliseringsniva", "beskrivningNiva", "korrigeradeGranser", "kontrolleratPlaneringsunderlag", "anvandbarhet",
    "beskrivningAnvandbarhet", "lagesmetodTyp", "lagesmetodVariant", "tidpunktForLagesbestamning",
    "absolutLagesosakerhetPlan", "presentationsskala", "tidpunktForKontrollAvGeometri",
})
_READONLY = frozenset({"beteckning", "bestammelseformulering"})


DB_SCOPE = "detaljplan_ngp/db"  # projektets uppgifter om planens plats i en databas (se checkout)


def find_layer(project: QgsProject, table: str) -> QgsVectorLayer | None:
    """Hittar planlagret för en tabell (t.ex. "anvandning_yta") i ett projekt."""
    for layer in project.mapLayers().values():
        if layer.customProperty(TABLE_PROPERTY) == table:
            return layer
    return None


def find_plan_group(project: QgsProject):
    """Gruppen i lagerpanelen som håller planens lager, eller None."""
    for group in project.layerTreeRoot().findGroups():
        if group.customProperty(PLAN_GROUP_PROPERTY):
            return group
    return None


def set_plan_name(project: QgsProject, name: str) -> None:
    """Döper gruppen i lagerpanelen (och projektet) efter planen."""
    name = (name or "").strip()
    if not name:
        return
    group = find_plan_group(project)
    if group is not None:
        group.setName(name)
    project.setTitle(name)


def table_of(layer) -> str | None:
    return layer.customProperty(TABLE_PROPERTY) if layer is not None else None


def apply_attributes(layer: QgsVectorLayer, feature_ids, attributes: dict) -> None:
    """Skriver attribut till objekt i lagrets redigeringsbuffert (startar redigering vid behov)."""
    if not layer.isEditable() and not layer.startEditing():
        raise RuntimeError(f"Kan inte redigera lagret {layer.name()}")
    fields = layer.fields()
    for name, value in attributes.items():
        idx = fields.indexOf(name)
        if idx < 0:
            raise KeyError(f"Lagret {layer.name()} saknar fältet {name}")
        for fid in feature_ids:
            layer.changeAttributeValue(fid, idx, value)


def create_plan_project(directory: str | Path, filnamn: str, kommun: str, kommunkod: str, epsg: int) -> tuple[Path, Path]:
    """Skapar GeoPackage + QGIS-projekt (.qgz) för en ny detaljplan och returnerar sökvägarna."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    gpkg = geopackage.create_geopackage(directory / f"{filnamn}.gpkg", epsg, {"kommun": kommun, "kommunkod": kommunkod})
    return gpkg, _write_project(directory, filnamn, gpkg)


def create_postgis_plan_project(directory: str | Path, filnamn: str, connection_name: str, schema: str, kommun: str,
                                kommunkod: str, epsg: int, connection=None) -> tuple[storage_module.PostgisStorage, Path]:
    """Skapar ett schema med planens tabeller i en PostGIS-databas och ett QGIS-projekt (.qgz) som pekar på det.

    Projektfilen ligger i ``directory``; själva planen ligger i databasen."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    qgz = directory / f"{filnamn}.qgz"
    if qgz.exists():
        raise FileExistsError(f"{qgz} finns redan")
    plan = storage_module.create_postgis_plan(connection_name, schema, epsg, {"kommun": kommun, "kommunkod": kommunkod},
                                              connection)
    return plan, _write_project(directory, filnamn, plan)


def _write_project(directory: Path, filnamn: str, source) -> Path:
    project = QgsProject()  # nytt, fristående projekt – rör inte användarens öppna projekt
    load_plan(source, project)
    qgz = directory / f"{filnamn}.qgz"
    if not project.write(str(qgz)):
        raise OSError(f"Kunde inte skriva projektet {qgz}")
    return qgz


def load_plan(source, project: QgsProject) -> dict[str, QgsVectorLayer]:
    """Lägger till planens lager i ``project`` och konfigurerar dem. Returnerar lager per tabellnamn.

    ``source`` är en GeoPackage (sökväg) eller ett ``Storage`` (t.ex. ett PostGIS-schema)."""
    plan_storage = storage_module.as_storage(source)
    meta = plan_storage.read_meta()
    if not meta:
        raise ValueError(f"{plan_storage.describe()} är inte en detaljplan skapad av detta plugin")
    if plan_storage.upgrade():  # äldre schema: lägg till det som saknas
        meta = plan_storage.read_meta()
    version = meta.get("schema_version")
    if version != str(model.SCHEMA_VERSION):
        raise ValueError(f"{plan_storage.describe()} är skapad med en äldre version av pluginet (schema {version}, "
                         f"nu krävs {model.SCHEMA_VERSION}). Skapa en ny plan med Rita Detaljplan → Ny detaljplan.")
    epsg = int(meta["epsg"])

    project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{epsg}"))

    root = project.layerTreeRoot()
    group = root.insertGroup(0, plan_storage.name)  # hela planen ligger i en grupp som döps efter planen
    group.setCustomProperty(PLAN_GROUP_PROPERTY, "1")
    layers: dict[str, QgsVectorLayer] = {}
    for layer_def in model.LAYERS:
        layer = plan_storage.make_layer(layer_def)
        if not layer.isValid():
            raise ValueError(f"Kunde inte läsa tabellen {layer_def.name} i {plan_storage.describe()}")
        layer.setCustomProperty(TABLE_PROPERTY, layer_def.name)  # så att vi hittar lagret även om det döps om
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        layers[layer_def.name] = layer

    if plan_storage.kind == "postgis":
        # En plan som läses direkt från databasen är skrivskyddad: den redigeras i en utcheckad lokal kopia (checkout)
        project.writeEntry(DB_SCOPE, "connection", plan_storage.connection_name)
        project.writeEntry(DB_SCOPE, "schema", plan_storage.schema)
        for layer in layers.values():
            layer.setReadOnly(True)

    for layer_def in model.LAYERS:
        _configure_fields(layers[layer_def.name], layer_def, layers, meta)
    _suppress_form(layers["detaljplan"])  # planens uppgifter fylls i via pluginet efter att planområdet ritats
    _add_relations(project, layers)
    _configure_snapping(project)
    symbology.apply_symbology(layers, reference_scale=settings.reference_scale())
    plan = next(iter(layers["detaljplan"].getFeatures()), None)  # planen har redan ett namn om den öppnas igen
    set_plan_name(project, (plan["namn"] if plan is not None and plan["namn"] not in (None, NULL) else "") or plan_storage.name)
    collapse_plan_group(project)  # sist: QGIS fäller annars ut gruppen när lagren läggs till
    return layers


def restyle(project: QgsProject, reference_scale: float) -> bool:
    """Ritar om planens lager för en ny referensskala. Returnerar False om projektet saknar planlager."""
    layers = {layer_def.name: find_layer(project, layer_def.name) for layer_def in model.LAYERS}
    layers = {name: layer for name, layer in layers.items() if layer is not None}
    if not layers:
        return False
    symbology.apply_symbology(layers, reference_scale=reference_scale)
    for layer in layers.values():
        layer.triggerRepaint()
    return True


def collapse_plan_group(project: QgsProject) -> None:
    """Fäller in planens grupp i lagerpanelen (den ska vara infälld som standard)."""
    group = find_plan_group(project)
    if group is not None:
        group.setExpanded(False)


def _suppress_form(layer: QgsVectorLayer) -> None:
    config = layer.editFormConfig()
    config.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
    layer.setEditFormConfig(config)


def _configure_fields(layer: QgsVectorLayer, layer_def: model.LayerDef, layers: dict[str, QgsVectorLayer],
                      meta: dict[str, str]) -> None:
    not_null = QgsFieldConstraints.Constraint.ConstraintNotNull
    unique = QgsFieldConstraints.Constraint.ConstraintUnique
    soft = QgsFieldConstraints.ConstraintStrength.ConstraintStrengthSoft
    hard = QgsFieldConstraints.ConstraintStrength.ConstraintStrengthHard

    for field in layer_def.fields:
        idx = layer.fields().indexOf(field.name)
        if idx < 0:
            raise ValueError(f"Fältet {field.name} saknas i tabellen {layer_def.name}")

        layer.setFieldAlias(idx, field.alias)
        default = _default_expression(layer_def, field, layers, meta)
        if default:
            layer.setDefaultValueDefinition(idx, QgsDefaultValue(default, False))
        if field.required:
            layer.setFieldConstraint(idx, not_null, soft)
        if field.name == "objektidentitet":
            layer.setFieldConstraint(idx, unique, hard)
        layer.setEditorWidgetSetup(idx, _widget_setup(field))

    if layer_def in (*model.AREA_LAYERS, model.BESTAMMELSE, model.HJALPLINJE):
        _configure_form(layer, layer_def)


def _configure_form(layer: QgsVectorLayer, layer_def: model.LayerDef) -> None:
    """Gömmer tekniska fält och låser text som sätts av pluginet. Nya ytor får inget formulär: bestämmelser
    tilldelas med verktyget Planbestämmelser, och kopplingen till användning sköts av pluginet."""
    config = layer.editFormConfig()
    for field in layer_def.fields:
        idx = layer.fields().indexOf(field.name)
        if field.name in _HIDDEN:
            layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup("Hidden", {}))
        if field.name in _READONLY:
            config.setReadOnly(idx, True)
    if layer_def in (*model.AREA_LAYERS, model.HJALPLINJE):
        config.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
    layer.setEditFormConfig(config)


def _default_expression(layer_def: model.LayerDef, field: model.FieldDef, layers: dict[str, QgsVectorLayer],
                        meta: dict[str, str]) -> str | None:
    if layer_def.name == "detaljplan" and field.name == "kommun" and meta.get("kommun"):
        return "'" + meta["kommun"].replace("'", "''") + "'"
    if layer_def.name != "detaljplan" and field.name == "detaljplan":
        # Ett GeoPackage = en detaljplan: peka automatiskt på planens objektidentitet.
        return f"aggregate('{layers['detaljplan'].id()}', 'min', \"objektidentitet\")"
    return field.default


def _widget_setup(field: model.FieldDef) -> QgsEditorWidgetSetup:
    if field.codelist:
        return QgsEditorWidgetSetup("ValueMap", {"map": [{value: value} for value in field.codelist]})
    if field.type == model.BOOL:
        return QgsEditorWidgetSetup("CheckBox", {})
    if field.type == model.DATE:
        return QgsEditorWidgetSetup("DateTime", {"allow_null": True, "calendar_popup": True,
                                                 "display_format": "yyyy-MM-dd", "field_format": "yyyy-MM-dd"})
    if field.type == model.DATETIME:
        return QgsEditorWidgetSetup("DateTime", {"allow_null": True, "calendar_popup": True,
                                                 "display_format": "yyyy-MM-dd HH:mm:ss",
                                                 "field_format": "yyyy-MM-dd HH:mm:ss"})
    if field.multiline:
        return QgsEditorWidgetSetup("TextEdit", {"IsMultiline": True})
    return QgsEditorWidgetSetup("TextEdit", {})


def _add_relations(project: QgsProject, layers: dict[str, QgsVectorLayer]) -> None:
    parent = layers["detaljplan"]
    for name, child_name, child_field, parent_field in model.RELATIONS:
        relation = QgsRelation(QgsRelationContext(project))  # utan kontext slås lagren upp i globala projektet
        relation.setId(name)
        relation.setName(name)
        relation.setReferencingLayer(layers[child_name].id())
        relation.setReferencedLayer(parent.id())
        relation.addFieldPair(child_field, parent_field)
        if not relation.isValid():
            raise ValueError(f"Ogiltig relation {name}: {relation.validationError()}")
        project.relationManager().addRelation(relation)


def _configure_snapping(project: QgsProject) -> None:
    """Snappning till hörn och segment i alla lager – ger delade gränser utan glapp (DP-Krav-0009/0013)."""
    config = project.snappingConfig()
    config.setEnabled(True)
    config.setMode(Qgis.SnappingMode.AllLayers)
    config.setTypeFlag(Qgis.SnappingType.Vertex | Qgis.SnappingType.Segment)
    config.setTolerance(12)
    config.setUnits(Qgis.MapToolUnit.Pixels)
    config.setIntersectionSnapping(False)
    project.setSnappingConfig(config)
    project.setTopologicalEditing(True)
