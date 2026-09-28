"""Var planen lagras: en lokal GeoPackage eller en plan i ett delat schema i en PostGIS-databas.

Båda lagringssätten har samma tabeller (se :mod:`model`). ``load_plan`` och resten av pluginet arbetar mot
``Storage`` och behöver inte veta vilket det är. Ett PostGIS-schema delas av alla planer som lagts i det (databas-
anslutningen är en av QGIS sparade PostgreSQL-anslutningar, så inloggningen sköts av QGIS): varje tabell har en
``plan``-kolumn som skiljer planernas rader åt, och varje QGIS-lager är tabellen filtrerad på just den planens
identifierare (``PostgisStorage.plan_id``). Det innebär att alla planer i samma schema delar koordinatsystem (SRID:et
sitter i geometrikolumnens definition, som är gemensam för schemat) – behövs flera SWEREF 99-zoner får de olika
scheman. Schemat och tabellerna skapas bara första gången (``CREATE ... IF NOT EXISTS``); en ny plan i ett schema
som redan finns lägger bara till sina rader.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from qgis.core import Qgis, QgsDataSourceUri, QgsProviderRegistry, QgsVectorLayer

from . import geopackage, model

PROVIDER = "postgres"
SCHEMA_TABLE = "dp_schema"  # en rad per schema-övergripande nyckel (schema_version, epsg) – delas av alla planer
_SCHEMA_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_TRANSLITERATE = str.maketrans({"å": "a", "ä": "a", "ö": "o", "é": "e", "ü": "u"})

_SQL_TYPES = {model.TEXT: "text", model.INT: "integer", model.REAL: "double precision", model.DATE: "date",
              model.DATETIME: "timestamp", model.BOOL: "boolean"}
_WKB = {"MultiPolygon": Qgis.WkbType.MultiPolygon, "MultiLineString": Qgis.WkbType.MultiLineString}


class PostgisError(RuntimeError):
    """Något gick fel mot databasen. Meddelandet är avsett för användaren."""


def _execute(connection, sql: str):
    try:
        return connection.executeSql(sql)
    except PostgisError:
        raise
    except Exception as exc:  # QgsProviderConnectionException m.fl.
        raise PostgisError(f"Databasen svarade med ett fel: {exc}") from exc


# -- namn och SQL (rena funktioner) ---------------------------------------------------------
def schema_name(text: str) -> str:
    """Gör fri text (plannamn eller planbeteckning) till ett giltigt schema- eller plan-id: gemener, a–z, siffror
    och understreck, börjar med en bokstav."""
    name = re.sub(r"[^a-z0-9_]+", "_", (text or "").strip().lower().translate(_TRANSLITERATE)).strip("_")
    if name and not name[0].isalpha():
        name = "dp_" + name
    return name[:63]


def _is_valid_identifier(name: str) -> bool:
    return bool(_SCHEMA_RE.match(name or ""))


def is_valid_schema(name: str) -> bool:
    return _is_valid_identifier(name) and name not in ("public", "information_schema") \
        and not name.startswith("pg_")


def is_valid_plan_id(name: str) -> bool:
    return _is_valid_identifier(name)


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _column(field: model.FieldDef) -> str:
    return f"{quote(field.name)} {_SQL_TYPES[field.type]}"


def _table_ddl(schema: str, layer_def: model.LayerDef, epsg: int) -> list[str]:
    columns = ['"fid" serial PRIMARY KEY', '"plan" text NOT NULL']
    if layer_def.geometry:
        columns.append(f'"geom" geometry({layer_def.geometry}, {int(epsg)})')
    columns += [_column(field) for field in layer_def.fields]
    table = f"{quote(schema)}.{quote(layer_def.name)}"
    statements = [f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(columns)})"]
    statements.append(f"CREATE INDEX IF NOT EXISTS {quote(layer_def.name + '_plan_idx')} ON {table} (\"plan\")")
    if layer_def.geometry:
        statements.append(f"CREATE INDEX IF NOT EXISTS {quote(layer_def.name + '_geom_idx')} ON {table} "
                          f"USING gist (\"geom\")")
    statements.append(f"COMMENT ON TABLE {table} IS {literal(layer_def.alias)}")
    return statements


def _meta_table_ddl(schema: str) -> list[str]:
    """Metadatatabellen (en rad per plan och nyckel, t.ex. namn/syfte/status): delas av alla planer i schemat."""
    table = f"{quote(schema)}.{quote(model.META_TABLE)}"
    return [
        f'CREATE TABLE IF NOT EXISTS {table} ("fid" serial PRIMARY KEY, "plan" text NOT NULL, "key" text NOT NULL, '
        '"value" text)',
        f"CREATE UNIQUE INDEX IF NOT EXISTS {quote(model.META_TABLE + '_plan_key_idx')} ON {table} "
        '("plan", "key")',
    ]


def _schema_table_ddl(schema: str) -> list[str]:
    """Schemats egna (icke plan-specifika) nycklar: schema_version och epsg, gemensamma för alla planer i schemat."""
    table = f"{quote(schema)}.{quote(SCHEMA_TABLE)}"
    return [f'CREATE TABLE IF NOT EXISTS {table} ("key" text PRIMARY KEY, "value" text)']


def ensure_schema(schema: str, epsg: int) -> list[str]:
    """SQL som skapar det delade schemat med alla tabeller (samma som GeoPackage-planens), om de inte redan finns.
    Körs vid varje ny plan: är schemat redan där (från en tidigare plan) blir det en no-op."""
    statements = [f"CREATE SCHEMA IF NOT EXISTS {quote(schema)}"]
    statements += _schema_table_ddl(schema)
    for layer_def in model.LAYERS:
        statements += _table_ddl(schema, layer_def, epsg)
    statements += _meta_table_ddl(schema)
    return statements


def postgis_upgrade(schema: str, version: int, epsg: int) -> list[str]:
    """SQL som uppgraderar ett schema från schemaversion ``version`` till nuvarande (gäller alla planer i schemat,
    eftersom tabellerna delas)."""
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
    statements.append(f"UPDATE {quote(schema)}.{quote(SCHEMA_TABLE)} SET \"value\" = "
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

    def __init__(self, connection_name: str, schema: str, plan_id: str, connection=None):
        self.connection_name = connection_name
        self.schema = schema
        self.plan_id = plan_id
        self._connection = connection

    @property
    def name(self) -> str:
        return self.plan_id

    @property
    def connection(self):
        if self._connection is None:
            found = postgis_connections().get(self.connection_name)
            if found is None:
                raise PostgisError(f"Databasanslutningen {self.connection_name} finns inte i QGIS.")
            self._connection = found
        return self._connection

    def _sql(self, sql: str):
        return _execute(self.connection, sql)

    def _read_schema_meta(self) -> dict[str, str]:
        """Schemats egna nycklar (schema_version, epsg): gemensamma för alla planer i schemat."""
        try:
            rows = self._sql(f'SELECT "key", "value" FROM {quote(self.schema)}.{quote(SCHEMA_TABLE)}')
        except PostgisError:
            return {}
        return {row[0]: row[1] for row in rows}

    def read_meta(self) -> dict[str, str]:
        try:
            rows = self._sql(f'SELECT "key", "value" FROM {quote(self.schema)}.{quote(model.META_TABLE)} '
                             f'WHERE "plan" = {literal(self.plan_id)}')
        except PostgisError:
            return {}
        meta = {row[0]: row[1] for row in rows}
        if meta:  # bara en riktig plan (annars ska t.ex. load_plan se en tom meta och neka)
            meta.update(self._read_schema_meta())
        return meta

    def upgrade(self) -> bool:
        schema_meta = self._read_schema_meta()
        version = schema_meta.get("schema_version", "")
        if not version.isdigit() or not 3 <= int(version) < model.SCHEMA_VERSION:
            return False
        for statement in postgis_upgrade(self.schema, int(version), int(schema_meta["epsg"])):
            self._sql(statement)
        return True

    def layer_uri(self, layer_def: model.LayerDef, epsg: Optional[int] = None) -> str:
        uri = QgsDataSourceUri(self.connection.uri())
        geometry = "geom" if layer_def.geometry else ""
        uri.setDataSource(self.schema, layer_def.name, geometry, f'"plan" = {literal(self.plan_id)}', "fid")
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
        return f"{self.connection_name} · {self.schema} · {self.plan_id}"

    def __eq__(self, other):
        return isinstance(other, PostgisStorage) and (other.connection_name, other.schema, other.plan_id) == \
            (self.connection_name, self.schema, self.plan_id)

    def __hash__(self):
        return hash((self.connection_name, self.schema, self.plan_id))


def as_storage(source) -> Storage:
    """Tar emot en sökväg (GeoPackage) eller ett ``Storage``."""
    return source if isinstance(source, Storage) else GeoPackageStorage(source)


def create_postgis_plan(connection_name: str, schema: str, plan_id: str, epsg: int,
                        meta: Optional[dict[str, str]] = None, connection=None) -> PostgisStorage:
    """Lägger till en ny plan i ett schema i databasen: skapar schemat med alla tabeller om det inte redan finns
    (annars återanvänds det, och måste ha samma koordinatsystem), och avbryter utan ändringar om planidentifieraren
    redan finns i schemat."""
    if not is_valid_schema(schema):
        raise PostgisError("Schemanamnet får bara innehålla gemener a–z, siffror och understreck och måste börja med "
                           "en bokstav.")
    if not is_valid_plan_id(plan_id):
        raise PostgisError("Planidentifieraren får bara innehålla gemener a–z, siffror och understreck och måste "
                           "börja med en bokstav.")
    if epsg not in geopackage.epsg_codes():
        raise ValueError(f"EPSG:{epsg} är inte en tillåten SWEREF 99-projektion (EPSG:3006–3018)")
    plan = PostgisStorage(connection_name, schema, plan_id, connection)
    try:
        plan._sql("SELECT postgis_version()")
    except PostgisError as exc:
        raise PostgisError("Databasen saknar PostGIS (eller anslutningen fungerar inte). "
                           f"Aktivera tillägget med CREATE EXTENSION postgis. {exc}") from exc
    existing = plan._read_schema_meta()
    if existing:  # schemat finns redan (från en tidigare plan): återanvänd det, men kräv samma koordinatsystem
        existing_epsg = int(existing.get("epsg", epsg))
        if existing_epsg != int(epsg):
            raise PostgisError(f"Schemat {schema} finns redan, med koordinatsystem EPSG:{existing_epsg}. Alla "
                               f"planer i samma schema måste dela koordinatsystem: välj EPSG:{existing_epsg}, eller "
                               "ett annat schema.")
        version = existing.get("schema_version", "")
        if version.isdigit() and int(version) < model.SCHEMA_VERSION:
            for statement in postgis_upgrade(schema, int(version), existing_epsg):
                plan._sql(statement)
        if plan_exists(plan.connection, schema, plan_id):  # bara meningsfullt att fråga om schemat redan fanns
            raise PostgisError(f"Det finns redan en plan med identifieraren {plan_id} i schemat {schema}.")
    statements = ensure_schema(schema, epsg)
    try:
        for statement in statements:
            plan._sql(statement)
    except PostgisError:
        if not existing:  # schemat var nyskapat av oss: ett halvskapat schema är värre än inget, städa bort det
            try:
                plan._sql(f"DROP SCHEMA IF EXISTS {quote(schema)} CASCADE")
            except PostgisError:
                pass
        raise
    values = {"schema_version": str(model.SCHEMA_VERSION), "epsg": str(int(epsg))} if not existing else {}
    if values:
        inserts = ", ".join(f"({literal(k)}, {literal(v)})" for k, v in values.items())
        plan._sql(f'INSERT INTO {quote(schema)}.{quote(SCHEMA_TABLE)} ("key", "value") VALUES {inserts}')
    plan_values = {"spec_version": model.SPEC_VERSION, **(meta or {})}
    inserts = ", ".join(f"({literal(plan_id)}, {literal(k)}, {literal(v)})" for k, v in plan_values.items())
    plan._sql(f'INSERT INTO {quote(schema)}.{quote(model.META_TABLE)} ("plan", "key", "value") VALUES {inserts}')
    return plan


def list_schemas(connection) -> list[str]:
    return [row[0] for row in _execute(connection, "SELECT schema_name FROM information_schema.schemata")]


def list_plugin_schemas(connection) -> list[str]:
    """Scheman i databasen som pluginet delar mellan planer (har tabellen ``dp_schema``)."""
    rows = _execute(connection, "SELECT table_schema FROM information_schema.tables WHERE table_name = "
                                f"{literal(SCHEMA_TABLE)} ORDER BY table_schema")
    return [row[0] for row in rows]


def list_plans_in_schema(connection, schema: str) -> list[str]:
    """Planidentifierarna för planerna (skapade med pluginet) i ett schema."""
    rows = _execute(connection, f'SELECT DISTINCT "plan" FROM {quote(schema)}.{quote(model.META_TABLE)} '
                                'ORDER BY "plan"')
    return [row[0] for row in rows]


def plan_exists(connection, schema: str, plan_id: str) -> bool:
    rows = _execute(connection, f'SELECT 1 FROM {quote(schema)}.{quote(model.META_TABLE)} '
                                f'WHERE "plan" = {literal(plan_id)} LIMIT 1')
    return bool(rows)
