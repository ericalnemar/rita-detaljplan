"""Checka ut och checka in en plan som ligger i PostGIS.

Att rita direkt mot en databas över nätet blir segt: kartan ritas om och reglerna läser om planens ytor efter varje
ändring, och varje läsning kostar en nätverksfördröjning. Därför arbetar man mot en tillfällig lokal kopia:

* **Checka ut** låser planen i databasen (en rad i planens metadatatabell), kopierar alla tabeller till en lokal
  GeoPackage och pekar om planens lager i projektet dit. Ritandet går sedan lika snabbt som mot en fil.
* **Checka in** skriver tillbaka hela planen i databasen i en enda transaktion (allt eller inget, och bara om låset
  fortfarande är ditt), släpper låset, pekar tillbaka lagren mot databasen och tar bort den lokala kopian.
* **Kasta utcheckningen** släpper låset och tar bort kopian utan att skriva något till databasen.

Så länge planen är utcheckad kan ingen annan checka ut den, och en plan som öppnas direkt från databasen är
skrivskyddad: allt som ändras utan utcheckning skulle annars skrivas över vid nästa incheckning.

Låset är en rad ``checkout`` i ``dp_meta`` med JSON (nyckel, vem, dator, sedan när). Den lokala kopian har samma nyckel
i sin egen ``dp_meta``, så en utcheckning som avbröts (kraschat QGIS, avstängd dator) kan tas upp igen.
"""
from __future__ import annotations

import getpass
import json
import platform
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from qgis.core import (NULL, QgsApplication, QgsDataProvider, QgsDataSourceUri, QgsFeature, QgsProject,
                       QgsVectorLayer)
from qgis.PyQt.QtCore import QDate, QDateTime, Qt

from . import geopackage, model, storage
from .project import DB_SCOPE, find_layer
from .storage import PostgisError, PostgisStorage, literal, quote

SCOPE = DB_SCOPE
LOCK_KEY = "checkout"
LOCAL_KEYS = ("checkout_token", "checkout_connection", "checkout_schema", "checkout_since")
BATCH = 200  # rader per INSERT

DATABASE, LOCAL, FILE = "database", "local", "file"  # var planen ligger just nu
DB_PROVIDER = storage.PROVIDER  # dataleverantören för databasens lager (byts ut i tester)


def _is_db_layer(layer) -> bool:
    return layer.providerType() == DB_PROVIDER


class CheckoutError(RuntimeError):
    """Något gick fel vid utcheckning eller incheckning. Meddelandet är avsett för användaren."""


@dataclass(frozen=True)
class Lock:
    token: str
    user: str
    host: str
    since: str

    def describe(self) -> str:
        return f"{self.user} på {self.host} sedan {self.since.replace('T', ' ')}"

    def to_json(self) -> str:
        return json.dumps({"token": self.token, "user": self.user, "host": self.host, "since": self.since})

    @classmethod
    def from_json(cls, text: str) -> Optional["Lock"]:
        try:
            data = json.loads(text)
            return cls(str(data["token"]), str(data.get("user", "")), str(data.get("host", "")), str(data.get("since", "")))
        except (ValueError, KeyError, TypeError):
            return None


class LockedError(CheckoutError):
    """Planen är redan utcheckad av någon annan (eller av dig på en annan dator)."""

    def __init__(self, lock: Optional[Lock]):
        self.lock = lock
        who = lock.describe() if lock is not None else "någon annan"
        super().__init__(f"Planen är utcheckad av {who}. Bara en kan redigera planen åt gången.")


# -- låset i databasen -------------------------------------------------------------------------------
def _meta_table(schema: str) -> str:
    return f"{quote(schema)}.{quote(model.META_TABLE)}"


def _token_pattern(token: str) -> str:
    """LIKE-mönster som hittar låsraden med nyckeln. (Ingen JSON-cast: andra rader i ``dp_meta`` är inte JSON och
    databasen kan välja att läsa dem före filtret på nyckeln.)"""
    if not token.isalnum():
        raise ValueError("ogiltig låsnyckel")
    return literal(f'%"token": "{token}"%')


def read_lock(plan: PostgisStorage) -> Optional[Lock]:
    text = plan.read_meta().get(LOCK_KEY)
    return Lock.from_json(text) if text else None


def new_lock() -> Lock:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - saknas t.ex. i vissa tjänstemiljöer
        user = "okänd"
    return Lock(uuid.uuid4().hex, user, platform.node() or "okänd dator", datetime.now().isoformat(timespec="seconds"))


def acquire_lock(plan: PostgisStorage) -> Lock:
    """Låser planen. Kastar ``LockedError`` om den redan är låst. Låsningen är atomär: tabellen låses medan raden läggs in."""
    lock = new_lock()
    meta = _meta_table(plan.schema)
    plan._sql(f"DO $dp$ BEGIN LOCK TABLE {meta} IN EXCLUSIVE MODE; "
              f"IF NOT EXISTS (SELECT 1 FROM {meta} WHERE \"key\" = {literal(LOCK_KEY)}) THEN "
              f"INSERT INTO {meta} (\"key\", \"value\") VALUES ({literal(LOCK_KEY)}, {literal(lock.to_json())}); "
              f"END IF; END $dp$")
    current = read_lock(plan)
    if current is None or current.token != lock.token:
        raise LockedError(current)
    return lock


def release_lock(plan: PostgisStorage, token: str) -> None:
    """Släpper låset om det fortfarande är ditt."""
    plan._sql(f"DELETE FROM {_meta_table(plan.schema)} WHERE \"key\" = {literal(LOCK_KEY)} "
              f"AND \"value\" LIKE {_token_pattern(token)}")


def break_lock(plan: PostgisStorage) -> None:
    """Tar bort låset oavsett vems det är. Den som hade planen utcheckad kan då inte längre checka in den."""
    plan._sql(f"DELETE FROM {_meta_table(plan.schema)} WHERE \"key\" = {literal(LOCK_KEY)}")


# -- var planen ligger ------------------------------------------------------------------------------------
def _read(project: QgsProject, key: str) -> str:
    return project.readEntry(SCOPE, key)[0]


def _write(project: QgsProject, key: str, value: str) -> None:
    project.writeEntry(SCOPE, key, value)


def remember_source(project: QgsProject, plan: PostgisStorage) -> None:
    _write(project, "connection", plan.connection_name)
    _write(project, "schema", plan.schema)


def db_source(project: QgsProject) -> Optional[PostgisStorage]:
    """Planens plats i databasen: sparad i projektet, annars utläst ur lagrens adress och matchad mot QGIS anslutningar."""
    connection, schema = _read(project, "connection"), _read(project, "schema")
    if connection and schema:
        return PostgisStorage(connection, schema)
    layer = find_layer(project, "detaljplan")
    if layer is None or not _is_db_layer(layer):
        return None
    uri = QgsDataSourceUri(layer.source())
    for name, known in storage.postgis_connections().items():
        other = QgsDataSourceUri(known.uri())
        if (other.host(), other.port(), other.database()) == (uri.host(), uri.port(), uri.database()):
            return PostgisStorage(name, uri.schema())
    return None


def local_path(project: QgsProject) -> Optional[Path]:
    text = _read(project, "checkout_path")
    return Path(text) if text else None


def state(project: QgsProject) -> str:
    """``DATABASE`` (planen läses direkt från databasen), ``LOCAL`` (utcheckad) eller ``FILE`` (vanlig GeoPackage)."""
    layer = find_layer(project, "detaljplan")
    if layer is None:
        return FILE
    if _is_db_layer(layer):
        return DATABASE
    return LOCAL if local_path(project) is not None and _read(project, "checkout_token") else FILE


def checkouts_dir() -> Path:
    return Path(QgsApplication.qgisSettingsDirPath()) / "detaljplan_ngp" / "checkouts"


def copy_path(plan: PostgisStorage, lock: Lock, directory: Optional[Path] = None) -> Path:
    return (directory or checkouts_dir()) / f"{plan.connection_name}_{plan.schema}_{lock.token[:8]}.gpkg".replace("/", "_")


# -- lager: peka om mellan databasen och den lokala kopian ------------------------------------------------------
def _switch(project: QgsProject, source_for, provider: str) -> None:
    """Pekar om alla planlager. Lagren behåller sina id, sin stil, sina formulär och relationer."""
    changed = []
    for layer_def in model.LAYERS:
        layer = find_layer(project, layer_def.name)
        if layer is None:
            continue
        if layer.isEditable():
            raise CheckoutError("Avsluta redigeringen (spara eller kasta ändringarna) först.")
        layer.setDataSource(source_for(layer_def), layer.name(), provider, QgsDataProvider.ProviderOptions())
        changed.append(layer)
        if not layer.isValid():
            raise CheckoutError(f"Kunde inte öppna tabellen {layer_def.name} på den nya platsen.")
    for layer in changed:
        layer.triggerRepaint()


def _to_database(project: QgsProject, plan: PostgisStorage) -> None:
    epsg = plan.read_meta().get("epsg")
    _switch(project, lambda layer_def: plan.layer_uri(layer_def, int(epsg) if epsg else None), DB_PROVIDER)
    for layer_def in model.LAYERS:
        layer = find_layer(project, layer_def.name)
        if layer is not None:
            layer.setReadOnly(True)  # bara en utcheckad plan får ändras


def _to_copy(project: QgsProject, path: Path) -> None:
    _switch(project, lambda layer_def: f"{path.as_posix()}|layername={layer_def.name}", "ogr")
    for layer_def in model.LAYERS:
        layer = find_layer(project, layer_def.name)
        if layer is not None:
            layer.setReadOnly(False)


def enforce_read_only(project: QgsProject) -> None:
    """Se till att en plan som läses direkt från databasen är skrivskyddad (även projekt skapade av äldre versioner)."""
    if state(project) != DATABASE:
        return
    for layer_def in model.LAYERS:
        layer = find_layer(project, layer_def.name)
        if layer is not None and not layer.readOnly() and not layer.isEditable():
            layer.setReadOnly(True)


# -- kopiera data ----------------------------------------------------------------------------------------------------
def _copy_layer(source: QgsVectorLayer, target: QgsVectorLayer) -> int:
    fields = target.fields()
    positions = [(index, source.fields().indexOf(field.name())) for index, field in enumerate(fields)]
    features = []
    for old in source.getFeatures():
        new = QgsFeature(fields)
        new.setGeometry(old.geometry())
        for target_index, source_index in positions:
            if source_index >= 0:
                new.setAttribute(target_index, old.attribute(source_index))
        features.append(new)
    if features:
        ok, _ = target.dataProvider().addFeatures(features)
        if not ok:
            raise CheckoutError(f"Kunde inte skriva tabellen {target.name()} i den lokala kopian.")
    return len(features)


def download(plan: PostgisStorage, path: Path, lock: Lock) -> Path:
    """Kopierar planens alla tabeller från databasen till en ny GeoPackage."""
    meta = plan.read_meta()
    extra = {k: v for k, v in meta.items() if k not in ("schema_version", "spec_version", "epsg", LOCK_KEY)}
    extra.update({"checkout_token": lock.token, "checkout_connection": plan.connection_name,
                  "checkout_schema": plan.schema, "checkout_since": lock.since})
    path.parent.mkdir(parents=True, exist_ok=True)
    geopackage.create_geopackage(path, int(meta["epsg"]), extra)
    local = storage.GeoPackageStorage(path)
    for layer_def in model.LAYERS:
        source = plan.make_layer(layer_def)
        if not source.isValid():
            raise CheckoutError(f"Kunde inte läsa tabellen {layer_def.name} i databasen.")
        target = local.make_layer(layer_def)
        _copy_layer(source, target)
        if target.featureCount() != source.featureCount():
            raise CheckoutError(f"Kopian av {layer_def.name} blev inte komplett.")
    return path


def local_copies(plan: PostgisStorage, directory: Optional[Path] = None) -> list[tuple[Path, dict]]:
    """Lokala kopior på den här datorn som hör till planen, med sin metadata."""
    found = []
    folder = directory or checkouts_dir()
    for path in sorted(folder.glob("*.gpkg")) if folder.exists() else []:
        try:
            meta = geopackage.read_meta(path)
        except Exception:  # noqa: BLE001 - trasig fil
            continue
        if meta.get("checkout_connection") == plan.connection_name and meta.get("checkout_schema") == plan.schema:
            found.append((path, meta))
    return found


def resumable_copy(plan: PostgisStorage, directory: Optional[Path] = None) -> Optional[tuple[Path, Lock]]:
    """En avbruten utcheckning som går att fortsätta: lokal kopia vars lås fortfarande är ditt."""
    lock = read_lock(plan)
    if lock is None:
        return None
    for path, meta in local_copies(plan, directory):
        if meta.get("checkout_token") == lock.token:
            return path, lock
    return None


# -- checka ut ------------------------------------------------------------------------------------------------------------
def check_out(project: QgsProject, directory: Optional[Path] = None) -> Path:
    """Låser planen och gör en lokal kopia som planens lager pekar mot. Returnerar kopians sökväg."""
    if state(project) != DATABASE:
        raise CheckoutError("Planen ligger inte i en databas.")
    plan = db_source(project)
    if plan is None:
        raise CheckoutError("Hittar inte databasanslutningen för planen bland QGIS sparade anslutningar.")
    if any((find_layer(project, d.name) is not None and find_layer(project, d.name).isEditable()) for d in model.LAYERS):
        raise CheckoutError("Avsluta redigeringen (spara eller kasta ändringarna) först.")
    try:
        lock = acquire_lock(plan)
    except PostgisError as exc:
        raise CheckoutError(str(exc)) from exc
    path = copy_path(plan, lock, directory)
    try:
        download(plan, path, lock)
        _to_copy(project, path)
    except Exception as exc:
        _cleanup_after_failed_checkout(project, plan, lock, path)
        if isinstance(exc, (CheckoutError, PostgisError)):
            raise CheckoutError(f"Kunde inte checka ut planen: {exc}") from exc
        raise
    _write(project, "checkout_path", str(path))
    _write(project, "checkout_token", lock.token)
    remember_source(project, plan)
    return path


def resume(project: QgsProject, path: Path, lock: Lock) -> Path:
    """Tar upp en avbruten utcheckning: pekar lagren mot den lokala kopian igen."""
    plan = db_source(project)
    if plan is None:
        raise CheckoutError("Hittar inte databasanslutningen för planen bland QGIS sparade anslutningar.")
    _to_copy(project, path)
    _write(project, "checkout_path", str(path))
    _write(project, "checkout_token", lock.token)
    remember_source(project, plan)
    return path


def _cleanup_after_failed_checkout(project, plan, lock, path) -> None:
    try:
        _to_database(project, plan)
    except Exception:  # noqa: BLE001 - städningen får inte dölja det ursprungliga felet
        pass
    try:
        release_lock(plan, lock.token)
    except Exception:  # noqa: BLE001
        pass
    _remove(path)


def _remove(path: Path) -> bool:
    """Tar bort kopian (och SQLites hjälpfiler). Returnerar False om något inte gick att ta bort."""
    clean = True
    for suffix in ("", "-wal", "-shm", "-journal"):
        target = Path(str(path) + suffix)
        try:
            if target.exists():
                target.unlink()
        except OSError:
            clean = False
    return clean


# -- checka in ----------------------------------------------------------------------------------------------------------------
def sql_value(value, kind: str) -> str:
    """En cell som SQL-literal för kolumntypen ``kind`` (se ``model``)."""
    if value is None or value is NULL or (hasattr(value, "isNull") and value.isNull()):
        return "NULL"
    if kind == model.BOOL:
        return "true" if value in (True, 1, "1", "true", "True") else "false"
    if kind == model.INT:
        return str(int(value))
    if kind == model.REAL:
        return repr(float(value))
    if isinstance(value, QDateTime):
        return literal(value.toString("yyyy-MM-dd HH:mm:ss")) if value.isValid() else "NULL"
    if isinstance(value, QDate):
        return literal(value.toString("yyyy-MM-dd")) if value.isValid() else "NULL"
    if isinstance(value, datetime):
        return literal(value.strftime("%Y-%m-%d %H:%M:%S"))
    if isinstance(value, date):
        return literal(value.isoformat())
    return literal(value)


def read_rows(layer: QgsVectorLayer, layer_def: model.LayerDef) -> list[dict]:
    """Lagrets rader som ``{kolumn: värde}``: ``fid``, ``geom`` (WKT eller None) och tabellens fält."""
    rows = []
    for feature in layer.getFeatures():
        row = {"fid": feature.id() if layer.fields().indexOf("fid") < 0 else feature.attribute("fid")}
        if layer_def.geometry:
            geometry = feature.geometry()
            row["geom"] = None if geometry is None or geometry.isNull() or geometry.isEmpty() else geometry.asWkt(6)
        for field in layer_def.fields:
            row[field.name] = feature.attribute(field.name) if layer.fields().indexOf(field.name) >= 0 else None
        rows.append(row)
    return rows


def checkin_sql(schema: str, epsg: int, token: str, tables: list[tuple[model.LayerDef, list[dict]]]) -> str:
    """Ett enda SQL-block (``DO``) som i en transaktion kontrollerar att låset är ditt, ersätter innehållet i alla
    planens tabeller med de lokala raderna och släpper låset. Går något fel rullas allt tillbaka."""
    meta = _meta_table(schema)
    parts = [f"IF NOT EXISTS (SELECT 1 FROM {meta} WHERE \"key\" = {literal(LOCK_KEY)} "
             f"AND \"value\" LIKE {_token_pattern(token)}) THEN "
             "RAISE EXCEPTION 'Låset på planen tillhör inte längre dig. Planen har inte checkats in.'; END IF;"]
    for layer_def, rows in tables:
        table = f"{quote(schema)}.{quote(layer_def.name)}"
        parts.append(f"DELETE FROM {table};")
        columns = ["fid"] + (["geom"] if layer_def.geometry else []) + [f.name for f in layer_def.fields]
        column_list = ", ".join(quote(c) for c in columns)
        for start in range(0, len(rows), BATCH):
            values = []
            for row in rows[start:start + BATCH]:
                cells = [str(int(row["fid"]))]
                if layer_def.geometry:
                    wkt = row.get("geom")
                    cells.append("NULL" if wkt is None else f"ST_Multi(ST_GeomFromText({literal(wkt)}, {int(epsg)}))")
                cells += [sql_value(row.get(f.name), f.type) for f in layer_def.fields]
                values.append("(" + ", ".join(cells) + ")")
            parts.append(f"INSERT INTO {table} ({column_list}) VALUES {', '.join(values)};")
        parts.append(f"PERFORM setval(pg_get_serial_sequence({literal(table)}, 'fid'), "
                     f"COALESCE((SELECT MAX(\"fid\") FROM {table}), 1));")
    parts.append(f"DELETE FROM {meta} WHERE \"key\" = {literal(LOCK_KEY)};")
    body = " ".join(parts)
    tag, n = "dp", 0
    while f"${tag}$" in body:  # dollarcitatet får inte förekomma i innehållet
        n += 1
        tag = f"dp{n}"
    return f"DO ${tag}$ BEGIN {body} END ${tag}$"


def check_in(project: QgsProject) -> tuple[Path, bool]:
    """Skriver planen till databasen, släpper låset, pekar tillbaka lagren och tar bort den lokala kopian.

    Returnerar kopians sökväg och om den kunde tas bort. Vid fel ändras ingenting: låset och kopian finns kvar."""
    if state(project) != LOCAL:
        raise CheckoutError("Planen är inte utcheckad.")
    plan, path, token = db_source(project), local_path(project), _read(project, "checkout_token")
    if plan is None:
        raise CheckoutError("Hittar inte databasanslutningen för planen bland QGIS sparade anslutningar.")
    layers = {d.name: find_layer(project, d.name) for d in model.LAYERS}
    if any(layer is None or layer.isEditable() for layer in layers.values()):
        raise CheckoutError("Avsluta redigeringen (spara eller kasta ändringarna) först.")
    epsg = int(plan.read_meta().get("epsg") or geopackage.read_meta(path).get("epsg"))
    tables = [(d, read_rows(layers[d.name], d)) for d in model.LAYERS]
    try:
        plan._sql(checkin_sql(plan.schema, epsg, token, tables))
    except PostgisError as exc:
        raise CheckoutError(f"Kunde inte checka in planen: {exc}") from exc
    _to_database(project, plan)
    for key in ("checkout_path", "checkout_token"):
        _write(project, key, "")
    return path, _remove(path)


def discard(project: QgsProject) -> tuple[Path, bool]:
    """Släpper låset och tar bort den lokala kopian utan att skriva något till databasen."""
    if state(project) != LOCAL:
        raise CheckoutError("Planen är inte utcheckad.")
    plan, path, token = db_source(project), local_path(project), _read(project, "checkout_token")
    if plan is None:
        raise CheckoutError("Hittar inte databasanslutningen för planen bland QGIS sparade anslutningar.")
    if any(find_layer(project, d.name) is not None and find_layer(project, d.name).isEditable() for d in model.LAYERS):
        raise CheckoutError("Avsluta redigeringen (spara eller kasta ändringarna) först.")
    try:
        release_lock(plan, token)
    except PostgisError as exc:
        raise CheckoutError(f"Kunde inte släppa låset i databasen: {exc}") from exc
    _to_database(project, plan)
    for key in ("checkout_path", "checkout_token"):
        _write(project, key, "")
    return path, _remove(path)
