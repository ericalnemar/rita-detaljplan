"""Topologikontroll: brytpunkter och små glapp mellan planområde, användningsytor och egenskapsytor.

Analysen föreslår ändringar; ingenting ändras förrän användaren valt vilka som ska göras (``apply_to_geometry``):

  * **Brytpunkter ska sammanfalla.** En brytpunkt i en användningsyta som ligger nära (men inte exakt på) en brytpunkt i
    planområdet flyttas dit, och ligger den nära planområdets gräns flyttas den ända fram till gränsen. Planområdet har
    alltid företräde (planområde > användning > egenskap), i linje med hierarkin på kartan.
  * **Planområdets brytpunkter ska finnas i användningen.** Ligger en av planområdets brytpunkter mot en användningsyta
    som saknar brytpunkt där läggs en till.
  * **Små glapp** mellan användningsytor (och mellan egenskap och användning) stängs: en brytpunkt som ligger inom
    toleransen från en annan ytas gräns, utan att ligga på den, flyttas till den. Mellan ytor i samma lager flyttas den
    senare ytans brytpunkt till den tidigare (så att bara en av dem ändras).

Rena geometriberäkningar (QgsGeometry) utan koppling till lager; kontrollen av att en ändring inte ger en ogiltig
geometri görs när ändringen genomförs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from qgis.core import Qgis, QgsGeometry, QgsPointXY

DEFAULT_TOLERANCE = 0.50  # m: närmare än så räknas ett avstånd som ett glapp/en avvikelse och inte som avsiktligt
EXACT = 1e-6  # m: så nära räknas brytpunkter som sammanfallande

SNAP_VERTEX, SNAP_EDGE, ADD_VERTEX = "brytpunkt", "gräns", "planbrytpunkt"
KIND_TITLES = {SNAP_VERTEX: "Flytta brytpunkt till brytpunkt", SNAP_EDGE: "Stäng glapp mot gräns",
               ADD_VERTEX: "Lägg till planområdets brytpunkt"}
TARGET_TITLES = {"detaljplan": "planområdet", "anvandning_yta": "användningsområde", "egenskap_yta": "egenskapsområde"}
TABLE_TITLES = {"anvandning_yta": "Användningsområde", "egenskap_yta": "Egenskapsområde"}


@dataclass(frozen=True)
class Change:
    """En föreslagen ändring av en yta: flytta en brytpunkt (``old`` → ``new``) eller lägga till en (``old`` är None)."""
    kind: str
    table: str
    fid: int
    old: Optional[tuple]
    new: tuple
    distance: float  # m: hur långt brytpunkten flyttas (0 vid tillägg på gränsen)
    reference: str  # vad den anpassas till: "detaljplan", "anvandning_yta" eller "egenskap_yta"

    @property
    def title(self) -> str:
        return KIND_TITLES[self.kind]

    @property
    def text(self) -> str:
        target = TARGET_TITLES.get(self.reference, self.reference)
        if self.kind == SNAP_VERTEX:
            return f"Flytta brytpunkten {self.distance * 100:.0f} cm till {target}s brytpunkt"
        if self.kind == SNAP_EDGE:
            return f"Stäng glapp på {self.distance * 100:.0f} cm mot {target}s gräns"
        return f"Lägg till en brytpunkt där {target} har en ({self.distance * 100:.0f} cm från ytans kant)"

    @property
    def where(self) -> str:
        return TABLE_TITLES.get(self.table, self.table)


# -- geometrihjälp ----------------------------------------------------------------------------
def _parts(geometry: Optional[QgsGeometry]) -> list[QgsGeometry]:
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return []
    return [part for part in geometry.asGeometryCollection() if not part.isEmpty()]


def vertices(geometry: Optional[QgsGeometry]) -> list[QgsPointXY]:
    """Alla brytpunkter (utan att räkna slutpunkten som är samma som startpunkten i en ring två gånger)."""
    points: list[QgsPointXY] = []
    for part in _parts(geometry):
        if part.type() == Qgis.GeometryType.Polygon:
            rings = part.asPolygon()
            for ring in rings:
                points += ring[:-1]
        elif part.type() == Qgis.GeometryType.Line:
            points += part.asPolyline()
    return points


def _boundary(geometry: Optional[QgsGeometry]) -> Optional[QgsGeometry]:
    parts = _parts(geometry)
    if not parts:
        return None
    lines = [p.convertToType(Qgis.GeometryType.Line) if p.type() == Qgis.GeometryType.Polygon else p for p in parts]
    return QgsGeometry.collectGeometry([l for l in lines if l is not None and not l.isNull()]) if lines else None


def _nearest(points: Iterable[QgsPointXY], target: QgsPointXY) -> tuple[Optional[QgsPointXY], float]:
    best, best_d = None, float("inf")
    for point in points:
        d = point.distance(target)
        if d < best_d:
            best, best_d = point, d
    return best, best_d


def _key(point: QgsPointXY) -> tuple:
    return (round(point.x(), 9), round(point.y(), 9))


# -- analys -------------------------------------------------------------------------------------
@dataclass
class Reference:
    """Det ett lager anpassas till: brytpunkter och gräns hos ytor med högre företräde."""
    name: str
    points: list
    boundary: Optional[QgsGeometry]
    fid: Optional[int] = None


def _references(name: str, geometry: Optional[QgsGeometry], fid: Optional[int] = None) -> Optional[Reference]:
    points = vertices(geometry)
    boundary = _boundary(geometry)
    return Reference(name, points, boundary, fid) if points and boundary is not None else None


def _snap_vertex(vertex: QgsPointXY, refs: list[Reference], tolerance: float):
    """Bästa förslaget för en brytpunkt: närmaste brytpunkt (inom toleransen), annars närmaste punkt på en gräns."""
    if not refs:
        return None
    if any(vertex.distance(p) <= EXACT for r in refs for p in r.points):
        return None  # sammanfaller redan med en brytpunkt
    best = None
    for ref in refs:
        point, d = _nearest(ref.points, vertex)
        if point is not None and d <= tolerance and (best is None or d < best[0]):
            best = (d, SNAP_VERTEX, point, ref)
    if best is not None:
        return best
    for ref in refs:
        if ref.boundary is None:
            continue
        nearest = ref.boundary.nearestPoint(QgsGeometry.fromPointXY(vertex))
        if nearest.isNull():
            continue
        point = nearest.asPoint()
        d = vertex.distance(point)
        if EXACT < d <= tolerance and (best is None or d < best[0]):
            best = (d, SNAP_EDGE, point, ref)
    return best


def analyze(plan: Optional[QgsGeometry], uses: list[tuple], properties: list[tuple],
            tolerance: float = DEFAULT_TOLERANCE) -> list[Change]:
    """Föreslår ändringar. ``uses`` och ``properties`` är listor av ``(fid, geometri)``; ordningen i listan avgör
    vilken av två lika viktiga ytor som anpassar sig till vilken (den senare till den tidigare)."""
    changes: list[Change] = []
    plan_ref = _references("detaljplan", plan)

    ordered_uses = [(fid, g) for fid, g in uses if g is not None and not g.isNull() and not g.isEmpty()]
    for index, (fid, geometry) in enumerate(ordered_uses):
        refs = [plan_ref] if plan_ref else []
        refs += [r for r in (_references("anvandning_yta", g) for _, g in ordered_uses[:index]) if r]
        changes += _vertex_changes("anvandning_yta", fid, geometry, refs, tolerance)
        if plan_ref:
            changes += _added_plan_vertices("anvandning_yta", fid, geometry, plan_ref, tolerance, changes)

    use_refs = [r for r in (_references("anvandning_yta", g) for _, g in ordered_uses) if r]
    for fid, geometry in properties:
        if geometry is None or geometry.isNull() or geometry.isEmpty():
            continue
        refs = ([plan_ref] if plan_ref else []) + use_refs
        changes += _vertex_changes("egenskap_yta", fid, geometry, refs, tolerance)
    return changes


def _vertex_changes(table: str, fid: int, geometry: QgsGeometry, refs: list[Reference], tolerance: float) -> list[Change]:
    found: list[Change] = []
    for vertex in vertices(geometry):
        best = _snap_vertex(vertex, refs, tolerance)
        if best is None:
            continue
        distance, kind, point, ref = best
        found.append(Change(kind, table, fid, _key(vertex), _key(point), distance, ref.name))
    return found


def _added_plan_vertices(table: str, fid: int, geometry: QgsGeometry, plan_ref: Reference, tolerance: float,
                         existing: list[Change]) -> list[Change]:
    """Planområdets brytpunkter som ligger vid ytans gräns men saknas i ytan."""
    boundary = _boundary(geometry)
    if boundary is None:
        return []
    own = vertices(geometry)
    moved_to = {c.new for c in existing if c.fid == fid and c.table == table}
    found = []
    for point in plan_ref.points:
        if _key(point) in moved_to or any(point.distance(v) <= tolerance for v in own):
            continue  # ytan har redan (eller får) en brytpunkt där
        nearest = boundary.nearestPoint(QgsGeometry.fromPointXY(point))
        if nearest.isNull():
            continue
        d = point.distance(nearest.asPoint())
        if d <= tolerance:
            found.append(Change(ADD_VERTEX, table, fid, None, _key(point), d, plan_ref.name))
    return found


# -- genomförande -------------------------------------------------------------------------------
def apply_to_geometry(geometry: QgsGeometry, changes: list[Change]) -> tuple[QgsGeometry, int, int]:
    """Genomför ändringarna på en geometri. Returnerar (ny geometri, antal gjorda, antal hoppade över).

    Brytpunkterna hittas via sina koordinater, så ordningen mellan ändringarna spelar ingen roll. En ändring som
    skulle ge en ogiltig geometri (t.ex. en korsande gräns) hoppas över."""
    current = QgsGeometry(geometry)
    done = skipped = 0
    for change in changes:
        trial = QgsGeometry(current)
        target = QgsPointXY(*change.new)
        if change.old is None:
            _, _, after, _ = _segment(trial, target)
            ok = after >= 0 and trial.insertVertex(target.x(), target.y(), after)
        else:
            _, at, _, _, distance = _closest_vertex(trial, QgsPointXY(*change.old))
            ok = at >= 0 and distance <= 1e-4 and trial.moveVertex(target.x(), target.y(), at)
        if ok and trial.isGeosValid() and not trial.isEmpty():
            current = trial
            done += 1
        else:
            skipped += 1
    return current, done, skipped


def _closest_vertex(geometry: QgsGeometry, point: QgsPointXY):
    found, at, before, after, sqr = geometry.closestVertex(point)
    return found, at, before, after, sqr ** 0.5 if sqr >= 0 else float("inf")


def _segment(geometry: QgsGeometry, point: QgsPointXY):
    sqr, nearest, after, left = geometry.closestSegmentWithContext(point)
    return sqr, nearest, after, left
