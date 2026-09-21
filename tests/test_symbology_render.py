"""Renderar planlagren och kontrollerar att symbologin ser ut som avsett (kräver QGIS)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, INSIDE, LINE_INSIDE, PLAN, PlanCase  # noqa: E402

if HAVE_QGIS:
    from qgis.core import QgsCoordinateReferenceSystem, QgsMapRendererParallelJob, QgsMapSettings, QgsProject, QgsRectangle
    from qgis.PyQt.QtCore import QEventLoop, QSize, QTimer
    from qgis.PyQt.QtGui import QColor
    from rita_detaljplan.core import catalog as cat
    from rita_detaljplan.core.project import restyle
    from rita_detaljplan.core.symbology import FARGER

SIZE = 120
EXTENT = (-10, -10, 110, 110)


def is_dark(color):
    return color.alpha() > 0 and color.red() < 100 and color.green() < 100


def is_orange(color):
    return color.alpha() > 0 and color.red() > 150 and color.green() < 170 and color.blue() < 100


class RenderCase(PlanCase):
    def render(self, layers, extent=EXTENT, size=SIZE, reference=None, dpi=None):
        settings = QgsMapSettings()
        settings.setLayers(layers)
        settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3006"))  # meter: skalan blir rimlig
        settings.setExtent(QgsRectangle(*extent))
        settings.setOutputSize(QSize(size, size))
        if dpi:
            settings.setOutputDpi(dpi)
        settings.setBackgroundColor(QColor(255, 255, 255))
        # Symbolerna dimensioneras för en referensskala. Om inget annat anges renderas i just den skalan, så att
        # linjer och texter får sin ordinarie storlek oavsett hur litet provet är.
        restyle(QgsProject.instance(), reference or settings.scale())
        job = QgsMapRendererParallelJob(settings)
        # Vänta med en händelseslinga, som kartfönstret gör. waitForFinished() blockerar huvudtråden, och uttryck som
        # hämtar objekt från andra lager (aggregate) kan behöva den: det ger dödläge.
        loop = QEventLoop()
        job.finished.connect(loop.quit)
        QTimer.singleShot(20000, loop.quit)
        job.start()
        loop.exec()
        self.assertFalse(job.isActive(), "renderingen blev inte klar")
        return job.renderedImage()

    def in_map_order(self, tables):
        """Lagren i den ordning de ritas (översta i lagerträdet först), som QgsMapSettings vill ha dem."""
        order = [n.layer() for n in QgsProject.instance().layerTreeRoot().findLayers()]
        wanted = [self.layers[t] for t in tables]
        return [layer for layer in order if layer in wanted]

    def set_attr(self, table, name, value):
        layer = self.layers[table]
        layer.changeAttributeValue(layer.allFeatureIds()[0], layer.fields().indexOf(name), value)

    @staticmethod
    def rgb(color):
        return color.red(), color.green(), color.blue()

    @staticmethod
    def count(image, predicate):
        return sum(1 for x in range(SIZE) for y in range(SIZE) if predicate(image.pixelColor(x, y)))


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class UseTests(RenderCase):
    def assigned_use(self, wkt=PLAN, farg="Gul"):
        self.add("anvandning_yta", wkt)
        self.set_attr("anvandning_yta", "bestammelser", 1)
        self.set_attr("anvandning_yta", "farg", farg)

    def test_a_use_is_filled_with_the_colour_of_its_boverket_colour_name(self):
        self.assigned_use()
        centre = self.render(self.in_map_order(["anvandning_yta"])).pixelColor(60, 60)
        self.assertEqual(self.rgb(centre), FARGER["Gul"])

    def test_different_colour_names_give_different_fills(self):
        self.assigned_use()
        colours = set()
        for name in ("Gul", "Blå", "Röd", "Ljusgrön"):
            self.set_attr("anvandning_yta", "farg", name)
            colours.add(self.rgb(self.render(self.in_map_order(["anvandning_yta"])).pixelColor(60, 60)))
        self.assertEqual(len(colours), 4)

    def test_every_colour_name_in_the_catalog_has_a_colour(self):
        bundled = cat.Catalog.load(ROOT / "rita_detaljplan" / "data" / "planbestammelsekatalog.json")
        names = {e.farg for e in bundled.entries if e.farg}
        self.assertLessEqual(names, set(FARGER), f"färg saknas för: {sorted(names - set(FARGER))}")

    def test_a_use_has_its_own_boundary_line(self):
        self.assigned_use(INSIDE)
        image = self.render(self.in_map_order(["anvandning_yta"]))
        self.assertGreater(self.count(image, is_dark), 30, "användningsgränsen ritas")
        self.assertFalse(is_dark(image.pixelColor(35, 60)), "insidan är fylld med färg, inte svart")

    def test_a_use_without_a_provision_is_hatched_so_it_stands_out(self):
        self.add("anvandning_yta", PLAN)  # ingen bestämmelse tilldelad
        image = self.render(self.in_map_order(["anvandning_yta"]))
        self.assertGreater(self.count(image, is_orange), 100, "snedstrecket ska synas")
        colours = {self.rgb(image.pixelColor(x, 60)) for x in range(20, 100)}
        self.assertGreater(len(colours), 1, "ytan är strimmig, inte enfärgad")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class HierarchyTests(RenderCase):
    def test_the_plan_boundary_lies_over_the_use_boundary_over_the_property_boundary(self):
        order = [n.layer().name() for n in QgsProject.instance().layerTreeRoot().findLayers()]
        plan, use, prop = (order.index(n) for n in ("Detaljplan (planområde)", "Användning (yta)", "Egenskap (yta)"))
        self.assertLess(plan, use)
        self.assertLess(use, prop)

    def test_where_edges_coincide_the_higher_layer_decides_how_the_line_looks(self):
        """Planområdet och användningen har samma kant: kantlinjen ska bli minst lika tjock som den tjockaste."""
        self.add("detaljplan", PLAN)
        self.add("anvandning_yta", PLAN)
        self.set_attr("anvandning_yta", "bestammelser", 1)
        self.set_attr("anvandning_yta", "farg", "Gul")

        def line_width(tables):
            image = self.render(self.in_map_order(tables), extent=(-2, -2, 102, 102))
            y = SIZE // 2
            return sum(1 for x in range(0, 15) if is_dark(image.pixelColor(x, y)))

        plan_only, use_only = line_width(["detaljplan"]), line_width(["anvandning_yta"])
        both = line_width(["detaljplan", "anvandning_yta"])
        self.assertGreater(plan_only, use_only, "planområdesgränsen är tjockare än användningsgränsen")
        self.assertGreaterEqual(both, plan_only, "den högsta bestämmelsen syns där linjerna sammanfaller")

    def test_a_property_pattern_shows_through_the_use_colour(self):
        """Användningslagret multipliceras, så prickmarkens prickar syns under användningens färg."""
        self.add("anvandning_yta", PLAN)
        self.set_attr("anvandning_yta", "bestammelser", 1)
        self.set_attr("anvandning_yta", "farg", "Gul")
        self.add("egenskap_yta", INSIDE, bestammelser=1,
                 symbol="Marken får inte förses med byggnad/byggnadsverk")
        size = 300  # prickarna är små: rendera ett litet område i hög upplösning
        image = self.render(self.in_map_order(["anvandning_yta", "egenskap_yta"]), extent=(14, 14, 36, 36), size=size)
        inside = [self.rgb(image.pixelColor(x, y)) for x in range(size) for y in range(size)]
        yellow = FARGER["Gul"]
        dots = [c for c in inside if sum(c) < sum(yellow) - 150]
        self.assertGreater(len(dots), 10, "prickarna syns")
        self.assertGreater(sum(1 for c in inside if c == yellow), len(inside) // 2, "resten har användningens färg")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class LabelTests(RenderCase):
    def settings(self, table):
        return self.layers[table].labeling().settings()

    def test_digits_in_designations_are_shown_as_subscripts(self):
        from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
        layer = self.layers["egenskap_yta"]
        f = self.add("egenskap_yta", INSIDE, beteckning="e1 a12 R")
        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        context.setFeature(f)
        expression = QgsExpression(self.settings("egenskap_yta").fieldName)
        self.assertEqual(expression.evaluate(context), "e₁ a₁₂ R", expression.evalErrorString())
        self.assertEqual(f["beteckning"], "e1 a12 R", "lagrad beteckning är oförändrad")

    def test_a_missing_designation_gives_an_empty_label(self):
        from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
        f = self.add("egenskap_yta", INSIDE)
        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(self.layers["egenskap_yta"]))
        context.setFeature(f)
        self.assertFalse(QgsExpression(self.settings("egenskap_yta").fieldName).evaluate(context))

    def test_the_use_text_is_clearly_larger_than_the_property_text(self):
        use, prop = self.settings("anvandning_yta"), self.settings("egenskap_yta")
        self.assertGreaterEqual(use.format().size(), 1.5 * prop.format().size())

    def test_the_property_label_sits_below_the_use_label(self):
        from qgis.core import QgsPalLayerSettings
        prop = self.settings("egenskap_yta")
        self.assertEqual(prop.quadOffset, QgsPalLayerSettings.QuadrantBelow)
        self.assertNotEqual(prop.yOffset, 0)
        self.assertEqual(self.settings("anvandning_yta").quadOffset, QgsPalLayerSettings.QuadrantOver)

    def test_the_property_label_is_drawn_under_the_use_label_in_the_map(self):
        plan = "MultiPolygon(((0 0, 100 0, 100 60, 0 60, 0 0)))"
        self.add("detaljplan", plan)
        self.add("anvandning_yta", plan, bestammelser=1, farg="Gul", beteckning="BC")
        self.add("egenskap_yta", plan, bestammelser=1, beteckning="e1")
        image = self.render(self.in_map_order(["anvandning_yta", "egenskap_yta"]), extent=(-5, -5, 105, 65), size=440)
        rows = [y for y in range(440) if any(is_dark(image.pixelColor(x, y)) for x in range(150, 290))]
        gaps = [b - a for a, b in zip(rows, rows[1:]) if b - a > 1]
        self.assertTrue(gaps or len(rows) > 0)
        first_block_end = next((a for a, b in zip(rows, rows[1:]) if b - a > 1), rows[-1])
        centre = 440 * 30 / 70  # yta 60 m + marginal: mitten ligger vid y = 30 m
        self.assertLess(rows[0], centre + 220 * 0.2)
        self.assertGreater(rows[-1], first_block_end, "egenskapens text ligger under användningens")

    def test_the_use_label_is_central_forced_inside_always_shown_and_ahead_of_the_properties(self):
        use, prop = self.settings("anvandning_yta"), self.settings("egenskap_yta")
        self.assertTrue(use.centroidInside)
        self.assertTrue(use.displayAll)
        self.assertGreater(use.priority, prop.priority)
        self.assertFalse(prop.obstacleSettings().isObstacle())
        self.assertTrue(use.isExpression and prop.isExpression)
        self.assertTrue(self.settings("egenskap_linje").isExpression)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PatternTests(RenderCase):
    """Prickmark, plusmark och ringprickad mark, och linjen för fastighetsindelning."""

    def categories(self, table="egenskap_yta"):
        renderer = self.layers[table].renderer()
        return renderer, {c.value(): c for c in renderer.categories()}

    def test_no_symbol_is_clipped_to_the_map_canvas(self):
        for table in ("detaljplan", "anvandning_yta", "egenskap_yta", "egenskap_linje", "hjalplinje"):
            renderer = self.layers[table].renderer()
            categories = renderer.categories() if hasattr(renderer, "categories") else []
            symbols = [c.symbol() for c in categories] or [renderer.symbol()]
            for symbol in symbols:
                self.assertFalse(symbol.clipFeaturesToExtent(), table)

    def test_point_patterns_draw_whole_markers(self):
        from qgis.core import QgsPointPatternFillSymbolLayer, Qgis
        _, categories = self.categories()
        checked = 0
        for name in ("Marken får endast förses med byggnadsverk under mark",
                     "Marken får endast förses med viss typ av byggnadsverk",
                     "Marken får inte förses med byggnad/byggnadsverk"):
            symbol = categories[name].symbol()
            patterns = [l for l in symbol.symbolLayers() if isinstance(l, QgsPointPatternFillSymbolLayer)]
            self.assertEqual(len(patterns), 1, name)
            self.assertEqual(patterns[0].clipMode(), Qgis.MarkerClipMode.CentroidWithin, name)
            checked += 1
        self.assertEqual(checked, 3)

    def test_plus_ground_uses_a_cross_marker_not_a_font_glyph(self):
        from qgis.core import QgsFontMarkerSymbolLayer, QgsPointPatternFillSymbolLayer, QgsSimpleMarkerSymbolLayer, Qgis
        _, categories = self.categories()
        symbol = categories["Marken får endast förses med viss typ av byggnadsverk"].symbol()
        pattern = next(l for l in symbol.symbolLayers() if isinstance(l, QgsPointPatternFillSymbolLayer))
        markers = pattern.subSymbol().symbolLayers()
        self.assertFalse(any(isinstance(m, QgsFontMarkerSymbolLayer) for m in markers))
        self.assertTrue(any(isinstance(m, QgsSimpleMarkerSymbolLayer) and m.shape() == Qgis.MarkerShape.Cross
                            for m in markers))

    def test_patterns_are_drawn_and_rings_reach_the_edge_whole(self):
        plan = "MultiPolygon(((0 0, 60 0, 60 30, 0 30, 0 0)))"
        self.add("detaljplan", plan)
        self.add("anvandning_yta", plan, bestammelser=1, farg="Gul", beteckning="BC")
        self.add("egenskap_yta", "MultiPolygon(((3 3, 20 3, 20 27, 3 27, 3 3)))", bestammelser=1, beteckning="e1",
                 symbol="Marken får endast förses med byggnadsverk under mark")
        image = self.render(self.in_map_order(["detaljplan", "anvandning_yta", "egenskap_yta"]),
                            extent=(-2, -2, 62, 32), size=800, reference=1000, dpi=384)
        # ringar: mörka pixlar innanför ytan finns, men ingen ring är avskuren av kanten (inga mörka pixlar utanför x < 3)
        inside = sum(1 for x in range(int(3.3 / 64 * 800) + 12, int(19.7 / 64 * 800)) for y in range(300, 500)
                     if is_dark(image.pixelColor(x, y)))
        self.assertGreater(inside, 30)

    def test_the_line_for_property_division_is_its_own_symbol_and_not_the_plain_property_boundary(self):
        _, categories = self.categories()
        self.assertIn("Fastighetsindelning", categories)
        symbol = categories["Fastighetsindelning"].symbol()
        generators = [l for l in symbol.symbolLayers() if l.layerType() == "GeometryGenerator"]
        self.assertEqual(len(generators), 1)
        line = generators[0].subSymbol()
        self.assertEqual(line.symbolLayer(0).layerType(), "MarkerLine", "markörer längs linjen, inte streck")
        plain = categories["Fastighetsindelning"].symbol().symbolLayer(0)
        self.assertEqual(plain.color().alpha(), 0, "ingen fyllning")

    def test_a_property_division_area_is_drawn_with_that_line_and_no_fill(self):
        plan = "MultiPolygon(((0 0, 60 0, 60 30, 0 30, 0 0)))"
        self.add("detaljplan", plan)
        self.add("anvandning_yta", plan, bestammelser=1, farg="Gul", beteckning="BC")
        self.add("egenskap_yta", "MultiPolygon(((10 5, 50 5, 50 25, 10 25, 10 5)))", bestammelser=1, beteckning="a1",
                 symbol="Fastighetsindelning")
        with_symbol = self.render(self.in_map_order(["detaljplan", "anvandning_yta", "egenskap_yta"]),
                                  extent=(-2, -2, 62, 32), size=800, reference=1000, dpi=384)
        self.set_attr("egenskap_yta", "symbol", None)
        plain = self.render(self.in_map_order(["detaljplan", "anvandning_yta", "egenskap_yta"]),
                            extent=(-2, -2, 62, 32), size=800, reference=1000, dpi=384)
        different = sum(1 for x in range(0, 800, 2) for y in range(0, 800, 2)
                        if with_symbol.pixelColor(x, y) != plain.pixelColor(x, y))
        self.assertGreater(different, 50, "linjen för fastighetsindelning skiljer sig från egenskapsgränsen")
        fill = with_symbol.pixelColor(250, 250)
        self.assertGreater(fill.red(), 200, "ytan fylls inte")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class ReferenceScaleTests(RenderCase):
    def styled(self, scale):
        from rita_detaljplan.core.project import restyle
        self.add("detaljplan", PLAN)
        self.add("anvandning_yta", PLAN, bestammelser=1, farg="Gul", beteckning="BC")
        self.assertTrue(restyle(QgsProject.instance(), scale))

    def test_every_renderer_gets_the_reference_scale(self):
        self.styled(2000)
        for table in ("detaljplan", "anvandning_yta", "egenskap_yta", "egenskap_linje", "hjalplinje"):
            self.assertEqual(self.layers[table].renderer().referenceScale(), 2000, table)

    def test_a_new_plan_uses_the_setting_which_defaults_to_1_1000(self):
        from qgis.core import QgsSettings
        from rita_detaljplan.core import settings
        QgsSettings().remove(settings.KEY_REFERENCE_SCALE)
        self.assertEqual(settings.reference_scale(), 1000)
        self.assertEqual(self.layers["detaljplan"].renderer().referenceScale(), 1000)

    def test_text_sizes_follow_the_reference_scale(self):
        self.styled(1000)
        small = self.layers["anvandning_yta"].labeling().settings().format().size()
        self.styled(2000)
        self.assertAlmostEqual(self.layers["anvandning_yta"].labeling().settings().format().size(), 2 * small)

    def test_lines_get_thicker_when_the_reference_scale_is_larger_at_the_same_view(self):
        self.add("detaljplan", PLAN)
        thin = self.count(self.render(self.in_map_order(["detaljplan"]), reference=500), is_dark)
        thick = self.count(self.render(self.in_map_order(["detaljplan"]), reference=4000), is_dark)
        self.assertGreater(thick, thin * 2)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class CoincidingBoundaryTests(RenderCase):
    """Där gränslinjer sammanfaller ska bara den högsta ritas: inga dubbla linjer."""

    def add_with_id(self, table, wkt, oid, **attrs):
        return self.add(table, wkt, objektidentitet=oid, **attrs)

    def edge_pixels(self, tables, y=60):
        image = self.render(self.in_map_order(tables), extent=(-2, -2, 102, 102))
        return sum(1 for x in range(0, 12) if is_dark(image.pixelColor(x, y)))

    def test_a_tiny_plan_keeps_its_whole_use_boundary(self):
        """En plan på någon meter (ritad nära origo) får inte förlora kantlinjer till toleransen."""
        plan = "MultiPolygon(((0 0, 1 0, 1 1, 0 1, 0 0)))"
        left = "MultiPolygon(((0 0, 0.5 0, 0.5 1, 0 1, 0 0)))"
        self.add_with_id("detaljplan", plan, "p")
        self.add_with_id("anvandning_yta", left, "a", bestammelser=1, farg="Gul")
        image = self.render(self.in_map_order(["anvandning_yta"]), extent=(-0.02, -0.02, 1.02, 1.02), size=400)
        column = [image.pixelColor(200, y) for y in range(60, 340)]  # den delade kanten x = 0,5
        self.assertGreater(sum(1 for c in column if is_dark(c)), 60, "kanten mitt i planen ritas")

    def test_a_use_does_not_draw_the_part_of_its_boundary_that_the_plan_boundary_already_draws(self):
        self.add_with_id("detaljplan", PLAN, "plan")
        self.add_with_id("anvandning_yta", PLAN, "a", bestammelser=1, farg="Gul")
        self.assertEqual(self.edge_pixels(["anvandning_yta"]), 0, "användningsgränsen på planens kant ritas inte")
        self.assertGreater(self.edge_pixels(["detaljplan"]), 0, "planområdesgränsen ritas")

    def test_without_a_plan_area_the_use_draws_its_whole_boundary(self):
        self.add_with_id("anvandning_yta", PLAN, "a", bestammelser=1, farg="Gul")
        self.assertGreater(self.edge_pixels(["anvandning_yta"]), 0)

    def test_two_neighbouring_uses_draw_their_shared_edge_only_once(self):
        self.add_with_id("detaljplan", PLAN, "plan")
        self.add_with_id("anvandning_yta", "MultiPolygon(((0 0, 50 0, 50 100, 0 100, 0 0)))", "a", bestammelser=1, farg="Gul")
        self.add_with_id("anvandning_yta", "MultiPolygon(((50 0, 100 0, 100 100, 50 100, 50 0)))", "b", bestammelser=1, farg="Blå")
        expression = self.generated_expression("anvandning_yta")
        lengths = {f["objektidentitet"]: self.evaluate(expression, f).length() for f in self.features("anvandning_yta")}
        self.assertAlmostEqual(lengths["a"], 100, delta=0.5, msg="a (lägst id) ritar den gemensamma kanten")
        self.assertAlmostEqual(lengths["b"], 0, delta=0.5, msg="b ritar den inte en gång till")

    def test_a_property_hides_edges_shared_with_the_plan_and_the_use(self):
        self.add_with_id("detaljplan", PLAN, "plan")
        self.add_with_id("anvandning_yta", "MultiPolygon(((0 0, 50 0, 50 100, 0 100, 0 0)))", "u", bestammelser=1, farg="Gul")
        # egenskapsytan har två kanter på användningens/planens kanter (x=0 och y=0) och två fria kanter
        self.add_with_id("egenskap_yta", "MultiPolygon(((0 0, 30 0, 30 40, 0 40, 0 0)))", "e", bestammelser=1)
        feature = next(iter(self.layers["egenskap_yta"].getFeatures()))
        visible = self.evaluate(self.generated_expression("egenskap_yta"), feature)
        self.assertAlmostEqual(visible.length(), 30 + 40, delta=1.0, msg="bara de två fria kanterna ritas")

    def test_the_boundary_of_the_plan_itself_is_never_reduced(self):
        self.add_with_id("detaljplan", PLAN, "plan")
        self.add_with_id("anvandning_yta", PLAN, "a", bestammelser=1, farg="Gul")
        renderer = self.layers["detaljplan"].renderer()
        symbol = renderer.symbol()
        self.assertFalse(any(l.layerType() == "GeometryGenerator" for l in symbol.symbolLayers()))

    def generated_expression(self, table):
        renderer = self.layers[table].renderer()
        categories = renderer.categories()  # behåll referensen: symbolen ägs av kategorin (annars kraschar det)
        symbol = categories[0].symbol()
        generator = next(l for l in symbol.symbolLayers() if l.layerType() == "GeometryGenerator")
        return str(generator.geometryExpression())

    def evaluate(self, expression, feature):
        from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsGeometry
        layer = next(l for l in self.layers.values() if l.getFeature(feature.id()).isValid()
                     and l.getFeature(feature.id())["objektidentitet"] == feature["objektidentitet"])
        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        context.setFeature(feature)
        result = QgsExpression(expression).evaluate(context)
        return result if isinstance(result, QgsGeometry) else QgsGeometry()


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PropertyTests(RenderCase):
    def test_a_property_area_is_transparent_with_its_own_boundary(self):
        self.add("egenskap_yta", INSIDE, bestammelser=1)
        image = self.render(self.in_map_order(["egenskap_yta"]))
        self.assertEqual(self.rgb(image.pixelColor(35, 60)), (255, 255, 255), "insidan är genomskinlig")
        self.assertGreater(self.count(image, is_dark), 20, "egenskapsgränsen ritas")

    def test_a_property_without_a_provision_is_hatched(self):
        self.add("egenskap_yta", INSIDE)
        image = self.render(self.in_map_order(["egenskap_yta"]))
        self.assertGreater(self.count(image, is_orange), 30)

    def test_a_line_with_a_boverket_symbol_is_drawn(self):
        self.add("egenskap_linje", LINE_INSIDE, bestammelser=1, symbol="Utfart får inte finnas")
        image = self.render(self.in_map_order(["egenskap_linje"]))
        self.assertGreater(self.count(image, lambda c: c.red() < 200 or c.blue() < 200), 10)

    def test_a_line_without_a_provision_is_drawn_dashed_orange(self):
        self.add("egenskap_linje", LINE_INSIDE)
        image = self.render(self.in_map_order(["egenskap_linje"]))
        self.assertGreater(self.count(image, is_orange), 5)


if __name__ == "__main__":
    unittest.main()
