"""Skapar och läser detaljplanens GeoPackage utifrån datamodellen i :mod:`model`."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from osgeo import gdal, ogr, osr

from . import codelists as cl
from . import model

gdal.UseExceptions()

_GEOMETRY_TYPES = {
    "MultiPolygon": ogr.wkbMultiPolygon,
    "MultiLineString": ogr.wkbMultiLineString,
    "MultiPoint": ogr.wkbMultiPoint,
    None: ogr.wkbNone,
}

_FIELD_TYPES = {
    model.TEXT: (ogr.OFTString, None),
    model.INT: (ogr.OFTInteger, None),
    model.REAL: (ogr.OFTReal, None),
    model.DATE: (ogr.OFTDate, None),
    model.DATETIME: (ogr.OFTDateTime, None),
    model.BOOL: (ogr.OFTInteger, ogr.OFSTBoolean),
}


def epsg_codes() -> list[int]:
    """De SWEREF 99-projektioner som specifikationen tillåter (EPSG:3006–3018)."""
    return [int(code.split(":")[1]) for code in cl.KOORDINATSYSTEM_PLAN]


def create_geopackage(path: str | Path, epsg: int, meta: dict[str, str] | None = None) -> Path:
    """Skapar en tom GeoPackage med alla tabeller för en detaljplan.

    Tabellerna skapas utan NOT NULL i databasen; obligatoriska fält kontrolleras i QGIS-formulären
    och av valideringen före leverans, så att man kan spara ofärdiga planer.
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} finns redan")
    if epsg not in epsg_codes():
        raise ValueError(f"EPSG:{epsg} är inte en tillåten SWEREF 99-projektion (EPSG:3006–3018)")

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    try:
        for layer_def in model.LAYERS:
            _create_table(ds, layer_def, srs)
        _create_meta(ds, {"schema_version": str(model.SCHEMA_VERSION), "spec_version": model.SPEC_VERSION,
                          "epsg": str(epsg), **(meta or {})})
    finally:
        ds = None  # stänger och skriver till disk
    return path


def _create_table(ds: ogr.DataSource, layer_def: model.LayerDef, srs: osr.SpatialReference) -> None:
    layer = ds.CreateLayer(
        layer_def.name,
        srs=srs if layer_def.geometry else None,
        geom_type=_GEOMETRY_TYPES[layer_def.geometry],
        options=["GEOMETRY_NAME=geom", "FID=fid", f"IDENTIFIER={layer_def.alias}",
                 f"DESCRIPTION={layer_def.description}"],
    )
    for field in layer_def.fields:
        ogr_type, subtype = _FIELD_TYPES[field.type]
        definition = ogr.FieldDefn(field.name, ogr_type)
        if subtype is not None:
            definition.SetSubType(subtype)
        if field.length:
            definition.SetWidth(field.length)
        layer.CreateField(definition)


def _create_meta(ds: ogr.DataSource, values: dict[str, str]) -> None:
    layer = ds.CreateLayer(model.META_TABLE, geom_type=ogr.wkbNone, options=["FID=fid"])
    layer.CreateField(ogr.FieldDefn("key", ogr.OFTString))
    layer.CreateField(ogr.FieldDefn("value", ogr.OFTString))
    for key, value in values.items():
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("key", key)
        feature.SetField("value", value)
        layer.CreateFeature(feature)


def read_meta(path: str | Path) -> dict[str, str]:
    """Läser planens metadata (kommun, kommunkod, schemaversion m.m.). Tom dict om filen inte är en plan."""
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(f'SELECT key, value FROM "{model.META_TABLE}"').fetchall()
    except sqlite3.DatabaseError:
        return {}
    finally:
        con.close()
    return {k: v for k, v in rows}


def upgrade(path: str | Path) -> bool:
    """Uppgraderar en äldre plan (schema 3–5) till nuvarande schema. Returnerar True om något ändrades."""
    path = Path(path)
    version = read_meta(path).get("schema_version")
    if not version or not version.isdigit() or not 3 <= int(version) < model.SCHEMA_VERSION:
        return False
    ds = ogr.Open(str(path), 1)
    try:
        srs = ds.GetLayerByName("detaljplan").GetSpatialRef()
        if ds.GetLayerByName(model.HJALPLINJE.name) is None:  # schema 4: hjälplinjer
            _create_table(ds, model.HJALPLINJE, srs)
        for layer_def in model.AREA_LAYERS:  # schema 5: textens läge
            layer = ds.GetLayerByName(layer_def.name)
            for field in model.LABEL_FIELDS:
                if layer.GetLayerDefn().GetFieldIndex(field.name) < 0:
                    layer.CreateField(ogr.FieldDefn(field.name, ogr.OFTReal))
        rows_layer = ds.GetLayerByName(model.BESTAMMELSE.name)  # schema 6: ordning
        if rows_layer.GetLayerDefn().GetFieldIndex(model.ORDNING.name) < 0:
            rows_layer.CreateField(ogr.FieldDefn(model.ORDNING.name, ogr.OFTInteger))
    finally:
        ds = None
    con = sqlite3.connect(str(path))
    try:
        con.execute(f'UPDATE "{model.META_TABLE}" SET value = ? WHERE key = ?',
                    (str(model.SCHEMA_VERSION), "schema_version"))
        con.commit()
    finally:
        con.close()
    return True
