"""Regler som binder egenskaper till användning.

En egenskapsbestämmelse hör alltid till en användning:
  * en egenskapsyta ska ligga helt inom användningsyta/-ytor,
  * en egenskapslinje eller -punkt ska ligga på eller inom en användningsyta,
  * användningsformen (allmän plats, kvartersmark, vattenområde) ska stämma med ytans.
Kopplingen sparas i ``reglerarAnvandningsbestammelse`` (som schemat kräver) och fylls i automatiskt.

Toleransen är 10 cm, samma som NGP tillåter för bestämmelsegeometrier i förhållande till planen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qgis.core import Qgis, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsVectorLayer

TOLERANCE = 0.10  # meter
MIN_OVERLAP = 0.01  # m²: mindre överlapp räknas inte som koppling (avrundningsfel i gränser)
_KNOWN_FORMS = ("Kvartersmark", "Allmän plats", "Vattenområde")


@dataclass
class LinkResult:
    use_ids: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def geometry_kind(geometry: QgsGeometry) -> str:
    """"yta", "linje" eller "punkt"."""
    kind = geometry.type()
    if kind == Qgis.GeometryType.Polygon:
        return "yta"
    return "linje" if kind == Qgis.GeometryType.Line else "punkt"


def use_count(use_layer: QgsVectorLayer) -> int:
    return use_layer.featureCount()


def _nearby_uses(use_layer: QgsVectorLayer, geometry: QgsGeometry):
    box = geometry.boundingBox()
    box.grow(TOLERANCE * 2)
    return list(use_layer.getFeatures(QgsFeatureRequest().setFilterRect(box)))


def link_property(geometry: QgsGeometry, use_layer: QgsVectorLayer, anvandningsform: str | None = None) -> LinkResult:
    """Hittar användningsytorna som en egenskapsgeometri hör till, och kontrollerar reglerna ovan."""
    result = LinkResult()
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        result.problems.append("Objektet saknar geometri.")
        return result
    if use_count(use_layer) == 0:
        result.problems.append("Det finns ingen användningsyta än. Rita användningen först.")
        return result

    kind = geometry_kind(geometry)
    linked = []
    for use in _nearby_uses(use_layer, geometry):
        use_geometry = use.geometry()
        if kind == "yta":
            overlap = geometry.intersection(use_geometry)
            if not overlap.isNull() and overlap.area() > MIN_OVERLAP:
                linked.append(use)
        elif use_geometry.distance(geometry) <= TOLERANCE:
            linked.append(use)

    if not linked:
        result.problems.append({
            "yta": "Egenskapsytan ligger inte inom någon användningsyta.",
            "linje": "Egenskapslinjen ligger inte på eller inom någon användningsyta.",
            "punkt": "Egenskapspunkten ligger inte på eller inom någon användningsyta.",
        }[kind])
        return result

    if kind == "yta":
        covered = QgsGeometry.unaryUnion([use.geometry() for use in linked]).buffer(TOLERANCE, 4)
        if not covered.contains(geometry):
            result.problems.append("Egenskapsytan ligger inte helt inom användningsytor. "
                                   "Rita om den så att den ryms inom användningen.")
            return result

    if anvandningsform in _KNOWN_FORMS:
        forms = [use["anvandningsform"] for use in linked if use["anvandningsform"]]
        matching = [form for form in forms if form == anvandningsform]
        wrong = [form for form in forms if form != anvandningsform]
        if (kind == "yta" and wrong) or (kind != "yta" and forms and not matching):
            result.problems.append(f"Bestämmelsen gäller {anvandningsform.lower()} men användningsytan är "
                                   f"{', '.join(sorted(set(wrong))).lower()}.")
            return result

    result.use_ids = [use["objektidentitet"] for use in linked if use["objektidentitet"]]
    return result


# -- hierarki: planområde -> användning -> egenskap ---------------------------------------
@dataclass
class Constrained:
    """Resultat av att tvinga en geometri in i sin förälder (beskärning) och undan syskon (överlapp)."""
    geometry: QgsGeometry | None = None
    notes: list[str] = field(default_factory=list)  # t.ex. "Beskuren mot planområdet."
    problems: list[str] = field(default_factory=list)  # gör att objektet inte kan behållas
    changed: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems


def _only(geometry: QgsGeometry, kind: Qgis.GeometryType) -> QgsGeometry:
    """Behåller bara delar av en viss geometrityp (en beskärning kan ge blandade delar) som multigeometri."""
    if geometry is None or geometry.isNull():
        return QgsGeometry()
    parts = [part for part in geometry.asGeometryCollection() if part.type() == kind and not part.isEmpty()]
    if kind == Qgis.GeometryType.Polygon:
        parts = [part for part in parts if part.area() > MIN_OVERLAP]
    if not parts:
        return QgsGeometry()
    collected = QgsGeometry.collectGeometry(parts)
    collected.convertToMultiType()
    return collected


def _merged(geometries) -> QgsGeometry | None:
    geometries = [g for g in geometries if g is not None and not g.isNull() and not g.isEmpty()]
    return QgsGeometry.unaryUnion(geometries) if geometries else None


def plan_geometry(plan_layer: QgsVectorLayer) -> QgsGeometry | None:
    """Planområdet: alla delytor i planlagret som en geometri (None om planområdet inte är ritat)."""
    return _merged(feature.geometry() for feature in plan_layer.getFeatures())


def use_geometry(use_layer: QgsVectorLayer, exclude_fid: int | None = None) -> QgsGeometry | None:
    return _merged(f.geometry() for f in use_layer.getFeatures() if f.id() != exclude_fid)


def constrain_use(geometry: QgsGeometry, plan: QgsGeometry | None, other_uses: QgsGeometry | None) -> Constrained:
    """En användningsyta ska ligga inom planområdet och får inte överlappa andra användningsytor.

    Det som ligger utanför planområdet eller över en annan användning klipps bort. Ligger hela ytan utanför
    (eller helt inom en annan användning) kan den inte behållas.
    """
    result = Constrained(geometry=geometry)
    if plan is None or plan.isEmpty():
        result.problems.append("Rita planområdet först: användningsytor får bara ligga inom planområdet.")
        return result
    current = geometry
    if not plan.buffer(TOLERANCE, 4).contains(current):
        inside = _only(current.intersection(plan), Qgis.GeometryType.Polygon)
        if inside.isEmpty():
            result.problems.append("Användningsytan ligger utanför planområdet.")
            return result
        result.notes.append("Användningsytan beskars mot planområdet.")
        current = inside
    if other_uses is not None and not other_uses.isEmpty():
        rest = _only(current.difference(other_uses), Qgis.GeometryType.Polygon)
        if rest.isEmpty():
            result.problems.append("Ytan ligger helt inom en annan användningsyta. Användningsytor får inte överlappa.")
            return result
        if current.area() - rest.area() > MIN_OVERLAP:
            result.notes.append("Överlapp med en annan användningsyta klipptes bort.")
            current = rest
    result.changed = current is not geometry
    result.geometry = current
    return result


def constrain_property(geometry: QgsGeometry, uses: QgsGeometry | None) -> Constrained:
    """En egenskap ska ligga inom användningsytorna: ytor och linjer beskärs, punkter kontrolleras."""
    result = Constrained(geometry=geometry)
    if uses is None or uses.isEmpty():
        result.problems.append("Det finns ingen användningsyta än. Rita användningen först.")
        return result
    kind = geometry_kind(geometry)
    padded = uses.buffer(TOLERANCE, 4)
    if kind == "punkt":
        if not padded.intersects(geometry):
            result.problems.append("Egenskapspunkten ligger inte på eller inom någon användningsyta.")
        return result
    if padded.contains(geometry):
        return result
    if kind == "yta":
        clipped = _only(geometry.intersection(uses), Qgis.GeometryType.Polygon)
        message = "Egenskapsytan ligger inte inom någon användningsyta."
    else:
        clipped = _only(geometry.intersection(padded), Qgis.GeometryType.Line)
        message = "Egenskapslinjen ligger inte på eller inom någon användningsyta."
    if clipped.isEmpty():
        result.problems.append(message)
        return result
    result.notes.append("Egenskapen beskars mot användningen.")
    result.geometry = clipped
    result.changed = True
    return result


def remainder(area: QgsGeometry | None, covered: QgsGeometry | None) -> QgsGeometry:
    """Den del av ``area`` som ännu inte täcks av ``covered`` (som yta; tom om inget återstår att fylla)."""
    if area is None or area.isEmpty():
        return QgsGeometry()
    rest = area if covered is None or covered.isEmpty() else area.difference(covered)
    return _only(rest, Qgis.GeometryType.Polygon)


def part_at(geometry: QgsGeometry | None, point: QgsPointXY) -> QgsGeometry:
    """Den sammanhängande delen av en (eventuellt multi-) yta som innehåller punkten. Tom geometri om ingen del gör
    det. Används av "fyll resten"-verktygen så att bara den yta man klickar i fylls, inte hela resten på en gång."""
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return QgsGeometry()
    target = QgsGeometry.fromPointXY(point)
    for part in geometry.asGeometryCollection():
        if part.type() == Qgis.GeometryType.Polygon and not part.isEmpty() and part.contains(target):
            return part
    return QgsGeometry()


def outside_plan(uses: QgsGeometry | None, plan: QgsGeometry | None) -> float:
    """Yta (m²) av användningen som ligger utanför planområdet; används när planområdet ändras."""
    if uses is None or plan is None:
        return 0.0
    return uses.difference(plan.buffer(TOLERANCE, 4)).area()


def coverage(uses: QgsGeometry | None, plan: QgsGeometry | None) -> float:
    """Andel (0–1) av planområdet som har en användningsyta."""
    if plan is None or plan.isEmpty() or plan.area() <= 0:
        return 0.0
    if uses is None:
        return 0.0
    return min(1.0, uses.intersection(plan).area() / plan.area())


def format_links(use_ids: list[str]) -> str:
    """Lagringsformat för ``reglerarAnvandningsbestammelse`` (semikolonseparerade UUID)."""
    return ";".join(use_ids)


def parse_links(text: str | None) -> list[str]:
    return [part for part in (text or "").split(";") if part]
