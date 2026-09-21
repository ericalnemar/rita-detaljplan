"""Symbologi för planlagren, byggd på stilbiblioteket "Detaljplaner (Bfs 2020:6)" (CC0, se data/styles).

Hierarkin i kartan: planområdesgräns > användningsgräns > egenskapsgräns. Där gränslinjer sammanfaller ritas bara
den högsta: varje lager ritar sin kantlinje med en geometrigenerator som tar bort de delar som redan ritas av ett
högre lager (och de delar som delas med en annan yta i samma lager, så att en gemensam kant ritas en gång).
Lagerordningen (se ``model.LAYERS``) ligger i samma ordning. Användningslagret ritas med blandningsläget
Multiplicera, så att egenskapsytornas mönster (t.ex. prickmark) syns under användningens färg.

  * Användningsytor färgas efter Boverkets färgnamn (Gul, Blågrå, …).
  * Egenskapsytor är genomskinliga; bestämmelser med symbol i Boverkets katalog (t.ex. prickmark) får mönstret.
  * Egenskapslinjer (utfartsförbud, stängsel) får sina symboler.
  * Ytor och objekt som ännu saknar bestämmelse ritas med ett tydligt snedstreck, så att man ser vad som återstår.
  * Beteckningen (t.ex. R1, e2) skrivs ut som etikett.

Katalogens färgnamn saknar färgkoder; ``FARGER`` avgör vilken färg varje namn får och kan justeras.
"""
from __future__ import annotations

from pathlib import Path

from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsFillSymbol,
    QgsFontMarkerSymbolLayer,
    QgsGeometryGeneratorSymbolLayer,
    QgsLinePatternFillSymbolLayer,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointPatternFillSymbolLayer,
    QgsProperty,
    QgsRendererCategory,
    QgsSimpleFillSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsStyle,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter

STYLE_FILE = Path(__file__).resolve().parent.parent / "data" / "styles" / "detaljplaner-bfs-2020-6.xml"

# Boverkets färgnamn -> färg. Hämtade ur färgskalan "Användningsområden" i stilbiblioteket.
FARGER: dict[str, tuple[int, int, int]] = {
    "Gul": (255, 255, 206),
    "Brun": (218, 191, 140),
    "Beige": (255, 203, 131),
    "Orange": (255, 128, 64),
    "Röd": (250, 75, 60),
    "Rosa": (255, 188, 225),
    "Lila": (209, 182, 225),
    "Blå": (165, 218, 251),
    "Blågrå": (182, 204, 225),
    "Grön": (178, 236, 64),
    "Ljusgrön": (222, 255, 206),
    "Grå": (217, 217, 217),
    "Ljusgrå": (233, 233, 233),
}
FALLBACK_FARG = (245, 245, 245)
UNASSIGNED = "ej tilldelad"  # klassvärde för objekt som ännu saknar bestämmelse
UNASSIGNED_COLOR = (220, 90, 40)

# Uttryck som ger klassen för varje objekt: "ej tilldelad" så länge bestämmelse saknas.
_USE_CLASS = f"CASE WHEN coalesce(\"bestammelser\", 0) = 0 THEN '{UNASSIGNED}' ELSE coalesce(\"farg\", '') END"
_SYMBOL_CLASS = (f"CASE WHEN coalesce(\"bestammelser\", 0) = 0 THEN '{UNASSIGNED}' "
                 "ELSE coalesce(\"symbol\", '') END")

# Boverkets symbolnamn -> symbol i stilbiblioteket, när namnen skiljer sig åt.
SYMBOL_ALIAS = {
    "Marken får inte förses med byggnad/byggnadsverk":
        "Marken får inte förses med byggnadsverk eller viss typ av byggnadsverk",
}
AREA_SYMBOLS = (
    "Marken får endast förses med byggnadsverk under mark",
    "Marken får endast förses med viss typ av byggnadsverk",
    "Marken får inte förses med byggnad/byggnadsverk",
)
LINE_SYMBOLS = ("Utfart får inte finnas", "Stängsel ska finnas")
# Symboler som ritas som linje längs ytans kant i stället för som fyllning (indelning i fastigheter, Boverket)
OUTLINE_SYMBOLS = ("Fastighetsindelning",)

def load_style(path: Path = STYLE_FILE) -> QgsStyle:
    style = QgsStyle()
    if not style.importXml(str(path)):
        raise ValueError(f"Kunde inte läsa stilbiblioteket {path}")
    return style


def _tidy(symbol):
    """Gör en symbol stabil på kartan och i utskrift.

    * Utan klippning mot kartrutan: annars räknas mönstrets utgångspunkt och streckens fas om från den synliga delen, så
      prick- och plusmark och streckade linjer "hoppar" när man panorerar eller zoomar.
    * Punktmönster (prickmark, plusmark, ringprickad mark) klipps inte mot ytans form: en markör ritas hel om dess
      mittpunkt ligger inom ytan, så inga halva prickar, ringar eller plustecken syns längs kanterna."""
    if symbol is None:
        return symbol
    symbol.setClipFeaturesToExtent(False)
    for layer in symbol.symbolLayers():
        if isinstance(layer, QgsPointPatternFillSymbolLayer):
            layer.setClipMode(Qgis.MarkerClipMode.CentroidWithin)
        inner = layer.subSymbol() if hasattr(layer, "subSymbol") else None
        if inner is not None:
            _tidy(inner)
    return symbol


def _plus_marker(size_pt: float = 3.6, width_pt: float = 0.45):
    """Ett plustecken som vanlig markör (ingen typsnittsberoende glyf): ser likadant ut på alla datorer och i PDF."""
    marker = QgsSimpleMarkerSymbolLayer(Qgis.MarkerShape.Cross, size_pt, 0.0, Qgis.ScaleMethod.ScaleDiameter,
                                        QColor(0, 0, 0), QColor(0, 0, 0))
    marker.setSizeUnit(Qgis.RenderUnit.Points)
    marker.setStrokeWidth(width_pt)
    marker.setStrokeWidthUnit(Qgis.RenderUnit.Points)
    return marker


def _robust_pattern(symbol):
    """Byter typsnittsmarkörer med plustecken (plusmark) mot en riktig kryssmarkör. Typsnittet i stilbiblioteket
    (Noto Sans) finns inte på alla datorer och ger då fel tecken eller rutor."""
    for layer in symbol.symbolLayers():
        inner = layer.subSymbol() if isinstance(layer, QgsPointPatternFillSymbolLayer) else None
        if inner is None:
            continue
        for index, marker in enumerate(inner.symbolLayers()):
            if isinstance(marker, QgsFontMarkerSymbolLayer) and marker.character().strip() == "+":
                inner.changeSymbolLayer(index, _plus_marker())
    return symbol


def _symbol(style: QgsStyle, name: str):
    return style.symbol(SYMBOL_ALIAS.get(name, name))


def _outline_from(style: QgsStyle, name: str):
    """Ett linjesymbolskikt ur stilbiblioteket, att lägga som kant på en yta."""
    line = style.symbol(name)
    return line.symbolLayer(0).clone() if line is not None and line.symbolLayerCount() else None


COINCIDENCE_TOLERANCE = 0.05  # meter: kantlinjer närmare än så räknas som sammanfallande
_EMPTY = "geom_from_wkt('GEOMETRYCOLLECTION EMPTY')"


def hierarchical_boundary(layers: dict[str, QgsVectorLayer], own_table: str, higher_tables: tuple[str, ...]) -> str:
    """Uttryck för kantlinjen av en yta utan det som redan ritas av högre lager eller av en annan yta i samma lager.

    Delade kanter inom lagret ritas av ytan med lägst ``objektidentitet``, så att de inte ritas två gånger."""
    hidden = [f"coalesce(boundary(aggregate('{layers[table].id()}', 'collect', $geometry)), {_EMPTY})"
              for table in higher_tables if table in layers]
    hidden.append(f"coalesce(boundary(aggregate('{layers[own_table].id()}', 'collect', $geometry, "
                  f"filter:=\"objektidentitet\" < attribute(@parent, 'objektidentitet'))), {_EMPTY})")
    # Toleransen följer planens storlek så att en mycket liten plan (nära origo, några meter) inte får hela kanter
    # bortdöljda; för en vanlig plan blir den COINCIDENCE_TOLERANCE.
    plan = layers.get("detaljplan")
    if plan is not None:
        tolerance = (f"min({COINCIDENCE_TOLERANCE}, max(0.000001, 0.0005 * "
                     f"sqrt(coalesce(aggregate('{plan.id()}', 'sum', $area), 1000000))))")
    else:
        tolerance = str(COINCIDENCE_TOLERANCE)
    return (f"difference(boundary($geometry), buffer(collect_geometries({', '.join(hidden)}), {tolerance}))")


def _generated_outline(style: QgsStyle, symbol_name: str, expression: str):
    """Ett linjeskikt som ritar ``expression`` (en linjegeometri) med en linjesymbol ur stilbiblioteket."""
    line = style.symbol(symbol_name)
    if line is None:
        return None
    generator = QgsGeometryGeneratorSymbolLayer.create({"geometryModifier": expression, "SymbolType": "Line"})
    generator.setSubSymbol(_tidy(line.clone()))
    return generator


def _fill(color: tuple[int, int, int] | None, outline=None) -> QgsFillSymbol:
    """Fyllning (eller genomskinlig) utan penna; kantlinjen är ett linjeskikt (``outline``) från stilbiblioteket."""
    symbol = QgsFillSymbol()
    symbol.deleteSymbolLayer(0)
    base = QgsSimpleFillSymbolLayer(QColor(*color) if color else QColor(0, 0, 0, 0))
    base.setStrokeStyle(Qt.PenStyle.NoPen)
    symbol.appendSymbolLayer(base)
    if outline is not None:
        symbol.appendSymbolLayer(outline)
    return _tidy(symbol)


def _hatched(color: tuple[int, int, int], background: tuple[int, int, int] | None = None, outline=None) -> QgsFillSymbol:
    """Snedstreck: markerar ytor som ännu saknar bestämmelse."""
    symbol = _fill(background, None)
    hatch = QgsLinePatternFillSymbolLayer()
    hatch.setLineAngle(45)
    hatch.setDistance(2.2)
    hatch.setColor(QColor(*color))
    hatch.setLineWidth(0.3)
    symbol.appendSymbolLayer(hatch)
    if outline is not None:
        symbol.appendSymbolLayer(outline)
    return _tidy(symbol)


SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉"
# Siffror i beteckningar ritas nedsänkta (e₁, R₂). Lagrat värde (e1) ändras inte, bara visningen.
_SUBSCRIPT_EXPRESSION = (
    "array_to_string(array_foreach(string_to_array(coalesce(\"beteckning\", ''), ''), "
    f"if(@element >= '0' and @element <= '9', substr('{SUBSCRIPT_DIGITS}', to_int(@element) + 1, 1), @element)), '')")


USE_TEXT_MM = 6.0  # användningsbestämmelsens textstorlek (mm på papper i referensskalan)
PROPERTY_TEXT_MM = 3.5  # egenskapsbestämmelsernas: tydligt mindre än användningens
LABEL_GAP_MM = 0.4


def _move_by_fields(settings: QgsPalLayerSettings) -> None:
    """Texten placeras automatiskt, men på det läge användaren flyttat den till om ``label_x``/``label_y`` är satta."""
    props = settings.dataDefinedProperties()
    props.setProperty(QgsPalLayerSettings.Property.PositionX, QgsProperty.fromField("label_x"))
    props.setProperty(QgsPalLayerSettings.Property.PositionY, QgsProperty.fromField("label_y"))
    for prop, value in ((QgsPalLayerSettings.Property.Hali, "Center"), (QgsPalLayerSettings.Property.Vali, "Half")):
        props.setProperty(prop, QgsProperty.fromExpression(
            f"CASE WHEN \"label_x\" IS NULL OR \"label_y\" IS NULL THEN NULL ELSE '{value}' END"))
    settings.setDataDefinedProperties(props)


def _labeling(reference_scale: float = 1000, *, bold: bool = True, is_use: bool = False,
              is_line: bool = False) -> QgsVectorLayerSimpleLabeling:
    """Etikett för beteckningen. Storleken är fast i referensskalan (angiven i meter i kartan), så texten blir
    inte orimligt stor eller liten när man zoomar. Användningens etikett ligger mitt i ytan, tvingas in i ytan och
    visas alltid; egenskapernas är mindre och placeras nedanför användningens."""
    per_mm = reference_scale / 1000.0  # meter i kartan per mm på papper
    size_mm = USE_TEXT_MM if is_use else PROPERTY_TEXT_MM
    settings = QgsPalLayerSettings()
    settings.fieldName = _SUBSCRIPT_EXPRESSION
    settings.isExpression = True
    settings.enabled = True
    font = QFont()
    font.setBold(bold)
    fmt = QgsTextFormat()
    fmt.setFont(font)
    fmt.setSizeUnit(Qgis.RenderUnit.MapUnits)
    fmt.setSize(size_mm * per_mm)
    fmt.buffer().setEnabled(True)
    fmt.buffer().setSizeUnit(Qgis.RenderUnit.MapUnits)
    fmt.buffer().setSize(0.25 * per_mm)
    fmt.buffer().setColor(QColor(255, 255, 255))
    settings.setFormat(fmt)
    _move_by_fields(settings)
    if is_line:
        settings.placement = Qgis.LabelPlacement.Line
        settings.priority = 3
        settings.obstacleSettings().setIsObstacle(False)
        return QgsVectorLayerSimpleLabeling(settings)
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.centroidInside = True  # punkten tvingas in i ytan även för konkava och smala former
    settings.centroidWhole = True
    if is_use:
        settings.displayAll = True  # visas även när något annat ligger i vägen
        settings.priority = 10
        settings.zIndex = 10.0
    else:
        # nedanför användningens etikett: överkanten hamnar en halv användningstext (plus lucka) under punkten
        settings.quadOffset = QgsPalLayerSettings.QuadrantBelow
        settings.offsetUnits = Qgis.RenderUnit.MapUnits
        settings.yOffset = (USE_TEXT_MM / 2 + LABEL_GAP_MM) * per_mm
        settings.displayAll = True
        settings.priority = 3
        settings.obstacleSettings().setIsObstacle(False)  # egenskapsytan får inte trycka undan användningens etikett
    return QgsVectorLayerSimpleLabeling(settings)


def _apply_labels(layer: QgsVectorLayer, reference_scale: float, **kwargs) -> None:
    layer.setLabeling(_labeling(reference_scale, **kwargs))
    layer.setLabelsEnabled(True)


def _set_renderer(layer: QgsVectorLayer, renderer, reference_scale: float) -> None:
    """Sätter renderaren med en fast referensskala: linjebredder och symbolstorlekar (mm) gäller vid den skalan."""
    if reference_scale:
        renderer.setReferenceScale(reference_scale)
    layer.setRenderer(renderer)


# -- lager ------------------------------------------------------------------------------
def style_plan_area(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                    reference_scale: float = 1000) -> None:
    """Planområdet: ingen fyllning, bara planområdesgränsen (överst i hierarkin, ritas hel)."""
    _set_renderer(layer, QgsSingleSymbolRenderer(_fill(None, _outline_from(style, "Planområdesgräns"))), reference_scale)


def style_use(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
              reference_scale: float = 1000) -> None:
    expression = hierarchical_boundary(layers, "anvandning_yta", ("detaljplan",))

    def outline():
        return _generated_outline(style, "Användningsgräns", expression)

    categories = [QgsRendererCategory(name, _fill(rgb, outline()), name) for name, rgb in FARGER.items()]
    categories.append(QgsRendererCategory(UNASSIGNED, _hatched(UNASSIGNED_COLOR, (250, 250, 250), outline()),
                                          "Saknar bestämmelse"))
    categories.append(QgsRendererCategory("", _fill(FALLBACK_FARG, outline()), "Övriga"))
    _set_renderer(layer, QgsCategorizedSymbolRenderer(_USE_CLASS, categories), reference_scale)
    layer.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)  # egenskapsytornas mönster syns igenom
    _apply_labels(layer, reference_scale, is_use=True)


def style_property_area(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                        reference_scale: float = 1000) -> None:
    expression = hierarchical_boundary(layers, "egenskap_yta", ("detaljplan", "anvandning_yta"))

    def outline():
        return _generated_outline(style, "Egenskapsgräns", expression)

    categories = []
    for name in AREA_SYMBOLS:
        pattern = _symbol(style, name)
        if pattern is not None:
            symbol = _robust_pattern(pattern.clone())
            if outline() is not None:
                symbol.appendSymbolLayer(outline())
            categories.append(QgsRendererCategory(name, _tidy(symbol), name))
    for name in OUTLINE_SYMBOLS:  # t.ex. indelning i fastigheter: ingen fyllning, kanten ritas med symbolens linje
        line = _generated_outline(style, name, expression)
        if line is not None:
            categories.append(QgsRendererCategory(name, _fill(None, line), name))
    categories.append(QgsRendererCategory(UNASSIGNED, _hatched(UNASSIGNED_COLOR, None, outline()), "Saknar bestämmelse"))
    categories.append(QgsRendererCategory("", _fill(None, outline()), "Övriga egenskaper"))
    _set_renderer(layer, QgsCategorizedSymbolRenderer(_SYMBOL_CLASS, categories), reference_scale)
    _apply_labels(layer, reference_scale, bold=False)


def style_property_line(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                        reference_scale: float = 1000) -> None:
    categories = []
    for name in LINE_SYMBOLS:
        symbol = _symbol(style, name)
        if symbol is not None:
            categories.append(QgsRendererCategory(name, _tidy(symbol.clone()), name))
    categories.append(QgsRendererCategory(UNASSIGNED, _tidy(QgsLineSymbol.createSimple(
        {"color": "220,90,40", "width": "0.6", "line_style": "dash"})), "Saknar bestämmelse"))
    categories.append(QgsRendererCategory("", _tidy(QgsLineSymbol.createSimple({"color": "0,0,0", "width": "0.5"})),
                                          "Övriga"))
    _set_renderer(layer, QgsCategorizedSymbolRenderer(_SYMBOL_CLASS, categories), reference_scale)
    _apply_labels(layer, reference_scale, bold=False, is_line=True)


def style_helper_line(layer: QgsVectorLayer, style: QgsStyle, layers: dict[str, QgsVectorLayer],
                      reference_scale: float = 1000) -> None:
    """Hjälplinjer: tunn, streckad blå linje som tydligt skiljer sig från plangeometrin."""
    _set_renderer(layer, QgsSingleSymbolRenderer(_tidy(QgsLineSymbol.createSimple(
        {"color": "0,150,200", "width": "0.25", "line_style": "dash"}))), reference_scale)
    layer.setLabelsEnabled(False)


_STYLERS = {
    "hjalplinje": style_helper_line,
    "detaljplan": style_plan_area,
    "anvandning_yta": style_use,
    "egenskap_yta": style_property_area,
    "egenskap_linje": style_property_line,
}


def apply_symbology(layers: dict[str, QgsVectorLayer], style: QgsStyle | None = None,
                    reference_scale: float = 1000) -> None:
    """Sätter symbologi och etiketter på planens lager (tabellnamn -> lager)."""
    style = style or load_style()
    for table, styler in _STYLERS.items():
        if table in layers:
            styler(layers[table], style, layers, reference_scale)
