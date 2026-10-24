"""Importera geometri från en annan datakälla till planens hjälplager.

Bara geometrin tas med, inga attribut: ytor hamnar i ``hjalpyta``, linjer i ``hjalplinje`` och punkter i ``hjalppunkt`` och
får sedan en bestämmelse med verktyget Planbestämmelser (då blir de planobjekt). Geometrin omvandlas till planens
koordinatsystem (SWEREF 99), kurvor delas upp i raka segment och höjd- och M-värden tas bort. Ett objekt med flera slags
delar (en geometrisamling) delas upp efter slag; multipunkter blir en punkt per del. Objekten läggs i redigeringsbufferten
och sparas med Spara (eller ångras med QGIS Ångra). Hjälplagren levereras aldrig till NGP."""
from __future__ import annotations

from dataclasses import dataclass, field

from qgis.core import (Qgis, QgsCoordinateTransform, QgsExpressionContext, QgsExpressionContextUtils,
                       QgsFeatureRequest, QgsGeometry, QgsProject, QgsVectorLayer, QgsVectorLayerUtils, QgsWkbTypes)

KINDS = ("polygon", "line", "point")
TARGET_TABLES = {"polygon": "hjalpyta", "line": "hjalplinje", "point": "hjalppunkt"}
_KIND = {
    QgsWkbTypes.GeometryType.PolygonGeometry: "polygon",
    QgsWkbTypes.GeometryType.LineGeometry: "line",
    QgsWkbTypes.GeometryType.PointGeometry: "point",
}
_WORDS = {"polygon": ("yta", "ytor"), "line": ("linje", "linjer"), "point": ("punkt", "punkter")}


@dataclass
class ImportResult:
    counts: dict[str, int] = field(default_factory=lambda: {kind: 0 for kind in KINDS})
    skipped: int = 0  # objekt utan geometri eller som inte kunde omvandlas
    invalid: int = 0  # importerade men ogiltiga geometrier (till exempel ytor som korsar sig själva)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def text(self) -> str:
        parts = [f"{n} {_WORDS[k][0] if n == 1 else _WORDS[k][1]}" for k, n in self.counts.items() if n]
        text = (", ".join(parts) if parts else "Inga geometrier") + " importerades till Hjälplager."
        if self.skipped:
            text += f" {self.skipped} objekt saknade geometri eller kunde inte omvandlas och hoppades över."
        if self.invalid:
            text += f" {self.invalid} geometrier är ogiltiga (till exempel ytor som korsar sig själva); kontrollera dem."
        return text


def clean_parts(geometry: QgsGeometry) -> list[tuple[str, QgsGeometry]]:
    """(slag, geometri) för en geometri utan kurvor, höjd- och M-värden, uppdelad efter slag. Punkter blir en per del."""
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return []
    geometry = QgsGeometry(geometry)  # kopia: källans objekt ändras inte
    abstract = geometry.get()
    if QgsWkbTypes.isCurvedType(geometry.wkbType()):
        geometry = QgsGeometry(abstract.segmentize())
        abstract = geometry.get()
    abstract.dropZValue()
    abstract.dropMValue()
    if QgsWkbTypes.flatType(geometry.wkbType()) == Qgis.WkbType.GeometryCollection:
        pieces = geometry.asGeometryCollection()
    else:
        pieces = [geometry]
    found: list[tuple[str, QgsGeometry]] = []
    grouped: dict[str, list[QgsGeometry]] = {}
    for piece in pieces:
        kind = _KIND.get(QgsWkbTypes.geometryType(piece.wkbType()))
        if kind is None or piece.isEmpty():
            continue
        if kind == "point":
            found += [("point", QgsGeometry(part)) for part in piece.asGeometryCollection()] if piece.isMultipart() \
                else [("point", piece)]
        else:
            grouped.setdefault(kind, []).append(piece)
    for kind, items in grouped.items():
        combined = QgsGeometry.collectGeometry(items) if len(items) > 1 else items[0]
        combined.convertToMultiType()
        found.append((kind, combined))
    return found


def _feature(layer: QgsVectorLayer, geometry: QgsGeometry):
    geometry = QgsGeometry(geometry)
    geometry.convertToMultiType()  # lagren är multilager
    context = QgsExpressionContext()
    context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    return QgsVectorLayerUtils.createFeature(layer, geometry, {}, context)


def import_geometries(source: QgsVectorLayer, targets: dict[str, QgsVectorLayer], selected_only: bool = False,
                      project: QgsProject | None = None) -> ImportResult:
    """Kopierar källans geometrier (inga attribut) till hjälplagren, i redigeringsbufferten. ``targets``: slag
    (``polygon``, ``line``, ``point``) -> lager."""
    project = project or QgsProject.instance()
    result = ImportResult()
    crs = next(iter(targets.values())).crs()  # planens koordinatsystem
    transform = QgsCoordinateTransform(source.crs(), crs, project) if source.crs().isValid() and source.crs() != crs \
        else None
    request = QgsFeatureRequest().setNoAttributes()
    if selected_only:
        request.setFilterFids(source.selectedFeatureIds())
    new: dict[str, list] = {kind: [] for kind in targets}
    for feature in source.getFeatures(request):
        geometry = QgsGeometry(feature.geometry())
        if transform is not None and not geometry.isNull():
            try:
                if geometry.transform(transform) != 0:
                    result.skipped += 1
                    continue
            except Exception:  # QgsCsException: punkter utanför koordinatsystemets område
                result.skipped += 1
                continue
        parts = clean_parts(geometry)
        if not parts:
            result.skipped += 1
            continue
        for kind, part in parts:
            target = targets.get(kind)
            if target is None:
                result.skipped += 1
                continue
            if not part.isGeosValid():
                result.invalid += 1
            new[kind].append(_feature(target, part))
    for kind, features in new.items():
        if not features:
            continue
        target = targets[kind]
        if not target.isEditable():
            target.startEditing()
        target.beginEditCommand(f"Importera geometri från {source.name()}")
        ok = target.addFeatures(features)
        target.endEditCommand()
        if ok:
            result.counts[kind] += len(features)
        else:
            result.skipped += len(features)
    return result
