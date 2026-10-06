"""Planens ytor ur GeoPackage-filen, för att kunna rita en enkel karta (var en bestämmelse gäller). Läser GeoPackage-
geometri (GP-huvud + WKB) med ren Python: punkter, linjer och ytor, med eller utan höjd. Bågar stöds inte (hoppas över)."""
from __future__ import annotations

import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

AREA_TABLES = ("anvandning_yta", "egenskap_yta", "egenskap_linje")
PLAN_TABLE = "detaljplan"


@dataclass
class Shape:
    """En geometri som ringar/linjer av (x, y). ``closed`` = ytor (ringar), annars linjer."""
    parts: list = field(default_factory=list)
    closed: bool = True

    def bounds(self) -> Optional[tuple[float, float, float, float]]:
        points = [p for part in self.parts for p in part]
        if not points:
            return None
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass
class Karta:
    """Planområdet och ytorna: ``areas`` är {ytans objektidentitet: Shape}, ``layer_of`` säger vilket lager ytan ligger i."""
    border: Optional[Shape] = None
    areas: dict = field(default_factory=dict)
    layer_of: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)  # ytans objektidentitet -> beteckning (användning), om den finns

    def bounds(self) -> Optional[tuple[float, float, float, float]]:
        boxes = [b for b in [self.border.bounds() if self.border else None]
                 + [s.bounds() for s in self.areas.values()] if b]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


class _Reader:
    def __init__(self, data: bytes, offset: int):
        self.data, self.pos = data, offset

    def read(self, fmt: str):
        values = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += struct.calcsize(fmt)
        return values

    def geometry(self) -> tuple[list, bool]:
        order = "<" if self.read("B")[0] == 1 else ">"
        kind = self.read(order + "I")[0]
        dims = 2
        if kind & 0x80000000:  # EWKB-flaggor
            dims += 1
        if kind & 0x40000000:
            dims += 1
        kind &= 0x0FFFFFFF
        thousands, base = divmod(kind, 1000)
        dims += {0: 0, 1: 1, 2: 1, 3: 2}.get(thousands, 0)

        def points():
            n = self.read(order + "I")[0]
            values = self.read(order + "d" * (n * dims))
            return [(values[i], values[i + 1]) for i in range(0, len(values), dims)]

        if base == 1:
            self.read(order + "d" * dims)
            return [], False
        if base == 2:
            return [points()], False
        if base == 3:
            return [points() for _ in range(self.read(order + "I")[0])], True
        if base in (4, 5, 6, 7):
            parts, closed = [], base in (6,)
            for _ in range(self.read(order + "I")[0]):
                sub, sub_closed = self.geometry()
                parts += sub
                closed = closed or sub_closed
            return parts, closed
        raise ValueError(f"geometritypen {kind} stöds inte")


def parse_gpkg_geometry(blob: Optional[bytes]) -> Optional[Shape]:
    """En GeoPackage-geometri som ``Shape``, eller None om den är tom eller av en typ som inte stöds."""
    if not blob or len(blob) < 8 or blob[:2] != b"GP":
        return None
    flags = blob[3]
    if flags & 0b10000:  # tom geometri
        return None
    envelope = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get((flags >> 1) & 0b111, 0)
    return parse_wkb(blob, 8 + envelope)


def parse_wkb(data: Optional[bytes], offset: int = 0) -> Optional[Shape]:
    """Vanlig WKB (t.ex. ``QgsGeometry.asWkb()`` i QGIS) som ``Shape``, eller None om den inte går att läsa."""
    if not data:
        return None
    try:
        parts, closed = _Reader(bytes(data), offset).geometry()
    except (ValueError, struct.error):
        return None
    return Shape(parts, closed) if parts else None


def _geometry_column(connection: sqlite3.Connection, table: str) -> Optional[str]:
    try:
        row = connection.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?", (table,)).fetchone()
    except sqlite3.Error:
        row = None
    if row:
        return row[0]
    columns = [r[1] for r in connection.execute(f'PRAGMA table_info("{table}")')]
    return next((c for c in ("geom", "geometry", "the_geom") if c in columns), None)


def read_karta(path: str | Path, plan_id: Optional[str] = None) -> Karta:
    """Ytorna (och planområdet) i en GeoPackage från Rita Detaljplan. Saknas geometrin blir kartan tom, inget fel."""
    karta = Karta()
    try:
        connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return karta
    try:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in (PLAN_TABLE, *AREA_TABLES):
            if table not in tables:
                continue
            column = _geometry_column(connection, table)
            if column is None:
                continue
            columns = [r[1] for r in connection.execute(f'PRAGMA table_info("{table}")')]
            label = '"beteckning"' if "beteckning" in columns else "NULL"
            plan_filter = ""
            args: tuple = ()
            if plan_id and table != PLAN_TABLE and "detaljplan" in columns:
                plan_filter, args = ' WHERE "detaljplan" = ? OR "detaljplan" IS NULL', (plan_id,)
            elif plan_id and table == PLAN_TABLE:
                plan_filter, args = ' WHERE "objektidentitet" = ?', (plan_id,)
            for ident, blob, text in connection.execute(
                    f'SELECT "objektidentitet", "{column}", {label} FROM "{table}"{plan_filter}', args):
                shape = parse_gpkg_geometry(blob)
                if shape is None:
                    continue
                if table == PLAN_TABLE:
                    karta.border = karta.border or shape
                elif ident:
                    karta.areas[ident] = shape
                    karta.layer_of[ident] = table
                    if text:
                        karta.labels[ident] = text
    except sqlite3.Error:
        pass
    finally:
        connection.close()
    return karta


def gpkg_blob(parts: list, closed: bool = True, srs: int = 3006) -> bytes:
    """En GeoPackage-geometri (utan omslutande rektangel) av ringar: en yta per ring om ``closed``, annars linjer.
    Används av testerna och exemplet."""
    header = b"GP" + bytes([0, 0b00000001]) + struct.pack("<i", srs)
    if closed:
        body = struct.pack("<BII", 1, 6, len(parts))
        for ring in parts:
            body += struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(ring))
            body += b"".join(struct.pack("<dd", x, y) for x, y in ring)
    else:
        body = struct.pack("<BII", 1, 5, len(parts))
        for line in parts:
            body += struct.pack("<BI", 1, 2) + struct.pack("<I", len(line))
            body += b"".join(struct.pack("<dd", x, y) for x, y in line)
    return header + body
