"""Var planen lagras: en lokal GeoPackage eller ett schema i en PostGIS-databas.

Båda lagringssätten har samma tabeller (se :mod:`model`). ``load_plan`` och resten av pluginet arbetar mot
``Storage`` och behöver inte veta vilket det är. En PostGIS-plan får ett eget schema i databasen (flera planer kan
ligga i samma databas), och databasanslutningen är en av QGIS sparade PostgreSQL-anslutningar, så inloggningen
sköts av QGIS.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from qgis.core import Qgis, QgsDataSourceUri, QgsProviderRegistry, QgsVectorLayer

from . import geopackage, model

PROVIDER = "postgres"
_SCHEMA_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_TRANSLITERATE = str.maketrans({"å": "a", "ä": "a", "ö": "o", "é": "e", "ü": "u"})

_SQL_TYPES = {model.TEXT: "text", model.INT: "integer", model.REAL: "double precision", model.DATE: "date",
              model.DATETIME: "timestamp", model.BOOL: "boolean"}
_WKB = {"MultiPolygon": Qgis.WkbType.MultiPolygon, "MultiLineString": Qgis.WkbType.MultiLineString}


class PostgisError(RuntimeError):
    """Något gick fel mot databasen. Meddelandet är avsett för användaren."""


# -- namn och SQL (rena funktioner) ---------------------------------------------------------
def schema_name(text: str) -> str:
    """Gör ett plannamn till ett schemanamn: gemener, a–z, siffror och understreck, börjar med en bokstav."""
    name = re.sub(r"[^a-z0-9_]+", "_", (text or "").strip().lower().translate(_TRANSLITERATE)).strip("_")
    if name and not name[0].isalpha():
        name = "dp_" + name
    return name[:63]


def is_valid_schema(name: str) -> bool:
    return bool(_SCHEMA_RE.match(name or "")) and name not in ("public", "information_schema") \
        and not name.startswith("pg_")


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _column(field: model.FieldDef) -> str:
    return f"{quote(field.name)} {_SQL_TYPES[field.type]}"


def _table_ddl(schema: str, layer_def: model.LayerDef, epsg: int) -> list[str]:
    columns = ['"fid" serial PRIMARY KEY']
    if layer_def.geometry:
        columns.append(f'"geom" geometry({layer_def.geometry}, {int(epsg)})')
    columns += [_column(field) for field in layer_def.fields]
    table = f"{quote(schema)}.{quote(layer_def.name)}"
    statements = [f"CREATE TABLE {table} ({', '.join(columns)})"]
    if layer_def.geometry:
        statements.append(f"CREATE INDEX {quote(layer_def.name + '_geom_idx')} ON {table} USING gist (\"geom\")")
    statements.append(f"COMMENT ON TABLE {table} IS {literal(layer_def.alias)}")
    return statements


def _meta_ddl(schema: str, values: dict[str, str]) -> list[str]:
    table = f"{quote(schema)}.{quote(model.META_TABLE)}"
    statements = [f'CREATE TABLE {table} ("fid" serial PRIMARY KEY, "key" text, "value" text)']
    statements += [f"INSERT INTO {table} (\"key\", \"value\") VALUES ({literal(k)}, {literal(v)})"
                   for k, v in values.items()]
    return statements


def postgis_ddl(schema: str, epsg: int, meta: Optional[dict[str, str]] = None) -> list[str]:
    """SQL som skapar planens schema med alla tabeller (samma som GeoPackage-planens) och metadata."""
    statements = [f"CREATE SCHEMA {quote(schema)}"]
    for layer_def in model.LAYERS:
        statements += _table_ddl(schema, layer_def, epsg)
    statements += _meta_ddl(schema, {"schema_version": str(model.SCHEMA_VERSION), "spec_version": model.SPEC_VERSION,
                                     "epsg": str(int(epsg)), **(meta or {})})
    return statements


def postgis_upgrade(schema: str, version: int, epsg: int) -> list[str]:
    """SQL som uppgraderar ett schema från schemaversion ``version`` till nuvarande."""
    statements: list[str] = []
    if version < 4:
        statements += _table_ddl(schema, model.HJALPLINJE, epsg)
    if version < 5:
        for layer_def in model.AREA_LAYERS:
            for field in model.LABEL_FIELDS:
                if field.name == "label_w":
                    continue  # kommer med schema 7
                statements.append(f"ALTER TABLE {quote(schema)}.{quote(layer_def.name)} "
                                  f"ADD COLUMN IF NOT EXISTS {_column(field)}")
    if version < 6:
        statements.append(f"ALTER TABLE {quote(schema)}.{quote(model.BESTAMMELSE.name)} "
                          f"ADD COLUMN IF NOT EXISTS {_column(model.ORDNING)}")
    if version < 7:  # textens bredd på alla ytor, sekundär egenskapsgräns på egenskapsytorna
        width = next(field for field in model.LABEL_FIELDS if field.name == "label_w")
        for layer_def in model.AREA_LAYERS:
            statements.append(f"ALTER TABLE {quote(schema)}.{quote(layer_def.name)} "
                              f"ADD COLUMN IF NOT EXISTS {_column(width)}")
        statements.append(f"ALTER TABLE {quote(schema)}.{quote(model.EGENSKAP_YTA.name)} "
                          f"ADD COLUMN IF NOT EXISTS {_column(model.SEKUNDAR)}")
    statements.append(f"UPDATE {quote(schema)}.{quote(model.META_TABLE)} SET \"value\" = "
                      f"{literal(str(model.SCHEMA_VERSION))} WHERE \"key\" = 'schema_version'")
    return statements


# -- lagringssätt ---------------------------------------------------------------------------
class Storage:
    """Där en plans tabeller finns."""
    kind = ""

    @property
    def name(self) -> str:  # standardnamn på planen (gruppen i lagerpanelen) innan den fått ett namn
        raise NotImplementedError

    def read_meta(self) -> dict[str, str]:
        raise NotImplementedError

    def upgrade(self) -> bool:
        raise NotImplementedError

    def make_layer(self, layer_def: model.LayerDef) -> QgsVectorLayer:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


class GeoPackageStorage(Storage):
    kind = "geopackage"

    def __init__(self, path):
        self.path = Path(path)

    @property
    def name(self) -> str:
        return self.path.stem

    def read_meta(self) -> dict[str, str]:
        return geopackage.read_meta(self.path)

    def upgrade(self) -> bool:
        return geopackage.upgrade(self.path)

    def make_layer(self, layer_def: model.LayerDef) -> QgsVectorLayer:
        return QgsVectorLayer(f"{self.path.as_posix()}|layername={layer_def.name}", layer_def.alias, "ogr")

    def describe(self) -> str:
        return self.path.name

    def __eq__(self, other):
        return isinstance(other, GeoPackageStorage) and other.path == self.path

    def __hash__(self):
        return hash(self.path)


def postgis_connections() -> dict:
    """Sparade PostgreSQL-anslutningar i QGIS (namn -> anslutning)."""
    metadata = QgsProviderRegistry.instance().providerMetadata(PROVIDER)
    return dict(metadata.connections()) if metadata is not None else {}


class PostgisStorage(Storage):
    kind = "postgis"

    def __init__(self, connection_name: str, schema: str, connection=None):
        self.connection_name = connection_name
        self.schema = schema
        self._connection = connection

    @property
    def name(self) -> str:
        return self.schema

    @property
    def connection(self):
        if self._connection is None:
            found = postgis_connections().get(self.connection_name)
            if found is None:
                raise PostgisError(f"Databasanslutningen {self.connection_name} finns inte i QGIS.")
            self._connection = found
        return self._connection

    def _sql(self, sql: str):
        try:
            return self.connection.executeSql(sql)
        except PostgisError:
            raise
        except Exception as exc:  # QgsProviderConnectionException m.fl.
            raise PostgisError(f"Databasen svarade med ett fel: {exc}") from exc

    def read_meta(self) -> dict[str, str]:
        try:
            rows = self._sql(f'SELECT "key", "value" FROM {quote(self.schema)}.{quote(model.META_TABLE)}')
        except PostgisError:
            return {}
        return {row[0]: row[1] for row in rows}

    def upgrade(self) -> bool:
        meta = self.read_meta()
        version = meta.get("schema_version", "")
        if not version.isdigit() or not 3 <= int(version) < model.SCHEMA_VERSION:
            return False
        for statement in postgis_upgrade(self.schema, int(version), int(meta["epsg"])):
            self._sql(statement)
        return True

    def layer_uri(self, layer_def: model.LayerDef, epsg: Optional[int] = None) -> str:
        uri = QgsDataSourceUri(self.connection.uri())
        geometry = "geom" if layer_def.geometry else ""
        uri.setDataSource(self.schema, layer_def.name, geometry, "", "fid")
        if layer_def.geometry:
            if epsg:
                uri.setSrid(str(epsg))
            uri.setWkbType(_WKB[layer_def.geometry])
        return uri.uri(True)

    def _open(self, uri: str, alias: str) -> QgsVectorLayer:  # särskilt för att kunna bytas ut i tester
        return QgsVectorLayer(uri, alias, PROVIDER)

    def make_layer(self, layer_def: model.LayerDef) -> QgsVectorLayer:
        epsg = self.read_meta().get("epsg")
        return self._open(self.layer_uri(layer_def, int(epsg) if epsg else None), layer_def.alias)

    def describe(self) -> str:
        return f"{self.connection_name} · {self.schema}"

    def __eq__(self, other):
        return isinstance(other, PostgisStorage) and (other.connection_name, other.schema) == \
            (self.connection_name, self.schema)

    def __hash__(self):
        return hash((self.connection_name, self.schema))


def as_storage(source) -> Storage:
    """Tar emot en sökväg (GeoPackage) eller ett ``Storage``."""
    return source if isinstance(source, Storage) else GeoPackageStorage(source)


def create_postgis_plan(connection_name: str, schema: str, epsg: int, meta: Optional[dict[str, str]] = None,
                        connection=None) -> PostgisStorage:
    """Skapar ett nytt schema med planens tabeller i databasen. Finns schemat redan avbryts det utan ändringar."""
    if not is_valid_schema(schema):
        raise PostgisError("Schemanamnet får bara innehålla gemener a–z, siffror och understreck och måste börja med "
                           "en bokstav.")
    if epsg not in geopackage.epsg_codes():
        raise ValueError(f"EPSG:{epsg} är inte en tillåten SWEREF 99-projektion (EPSG:3006–3018)")
    storage = PostgisStorage(connection_name, schema, connection)
    if schema in list_schemas(storage.connection):
        raise PostgisError(f"Det finns redan ett schema som heter {schema} i databasen.")
    try:
        storage._sql("SELECT postgis_version()")
    except PostgisError as exc:
        raise PostgisError("Databasen saknar PostGIS (eller anslutningen fungerar inte). "
                           f"Aktivera tillägget med CREATE EXTENSION postgis. {exc}") from exc
    statements = postgis_ddl(schema, epsg, meta)
    try:
        for statement in statements:
            storage._sql(statement)
    except PostgisError:
        try:  # ett halvskapat schema är värre än inget: städa bort det (det är nyskapat av oss)
            storage._sql(f"DROP SCHEMA IF EXISTS {quote(schema)} CASCADE")
        except PostgisError:
            pass
        raise
    return storage


def list_schemas(connection) -> list[str]:
    try:
        return [row[0] for row in connection.executeSql("SELECT schema_name FROM information_schema.schemata")]
    except Exception as exc:
        raise PostgisError(f"Kunde inte läsa databasens scheman: {exc}") from exc


def list_postgis_plans(connection) -> list[str]:
    """Scheman i databasen som innehåller en detaljplan (har pluginets metadatatabell)."""
    try:
        rows = connection.executeSql("SELECT table_schema FROM information_schema.tables WHERE table_name = "
                                     f"{literal(model.META_TABLE)} ORDER BY table_schema")
    except Exception as exc:
        raise PostgisError(f"Kunde inte söka efter detaljplaner i databasen: {exc}") from exc
    return [row[0] for row in rows]
