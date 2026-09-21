"""Gemensamma hjälpmedel för tester som behöver en riktig plan i QGIS."""
import json
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from qgis.core import QgsExpressionContext, QgsExpressionContextUtils, QgsGeometry, QgsProject, QgsVectorLayerUtils
    from qgis.PyQt.QtCore import QCoreApplication
    from qgis_app import get_app
    HAVE_QGIS = True
except ImportError:  # kördes utanför QGIS
    HAVE_QGIS = False

if HAVE_QGIS:
    from rita_detaljplan.core import bestammelse as bm
    from rita_detaljplan.core import catalog as cat
    from rita_detaljplan.core.project import create_plan_project, load_plan

FIXTURE = json.loads((ROOT / "tests" / "data" / "katalog_urval.json").read_text(encoding="utf-8"))

# Geometrier i en plan som är 100 x 100 m
PLAN = "MultiPolygon(((0 0, 100 0, 100 100, 0 100, 0 0)))"
LEFT = "MultiPolygon(((0 0, 50 0, 50 100, 0 100, 0 0)))"
RIGHT = "MultiPolygon(((50 0, 100 0, 100 100, 50 100, 50 0)))"
INSIDE = "MultiPolygon(((10 10, 40 10, 40 40, 10 40, 10 10)))"
FAR_AWAY = "MultiPolygon(((500 500, 520 500, 520 520, 500 520, 500 500)))"
LINE_ON_EDGE = "MultiLineString(((0 50, 0 80)))"
LINE_INSIDE = "MultiLineString(((20 20, 20 60)))"
LINE_FAR = "MultiLineString(((500 500, 500 520)))"
POINT_ON_EDGE = "MultiPoint((50 50))"
POINT_FAR = "MultiPoint((300 300))"


def pick(catalog, kod=None, layer=None, symbol=None, contains=None, form=None, variables=None):
    """Första pågående, levererbara bestämmelsen i katalogen som uppfyller villkoren."""
    for e in catalog.entries:
        if not e.deliverable or e.tolkning or not e.is_current:
            continue
        if kod and e.kod != kod:
            continue
        if layer and e.layer_name != layer:
            continue
        if symbol and not e.symbol.startswith(symbol):
            continue
        if contains and contains not in e.formulering:
            continue
        if form and e.anvandningsform != form:
            continue
        if variables is not None and bool(e.variables) != variables:
            continue
        return e
    raise LookupError((kod, layer, symbol, contains, form, variables))


def filled(e, number="5"):
    """Värden för en bestämmelse: tal för decimaler (enhet/värdetyp förifyllda eller "antal"/"max"), text för text."""
    values = []
    for item in bm.default_values(e):
        if item.variable.datatype == "decimaltal":
            values.append(bm.VariableValue(item.variable, number, item.vardetyp or "max", item.enhet or "antal"))
        else:
            values.append(bm.VariableValue(item.variable, "text"))
    return values


def pump(seconds=0.0):
    """Kör Qt:s händelseslinga (QTimer.singleShot(0) i pluginet körs här)."""
    end = time.time() + seconds
    QCoreApplication.processEvents()
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PlanCase(unittest.TestCase):
    """Skapar en ny plan i globala projektet inför varje test, med alla planlager redigerbara."""

    @classmethod
    def setUpClass(cls):
        cls.app = get_app()
        cls.catalog = cat.Catalog.from_api_release(FIXTURE)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(QgsProject.instance().clear)
        self.dir = Path(self._tmp.name)
        QgsProject.instance().clear()
        self.gpkg, _ = create_plan_project(self.dir, "plan", "Eskilstuna", "0482", 3006)
        self.layers = load_plan(self.gpkg, QgsProject.instance())
        for layer in self.layers.values():
            if layer.isSpatial():
                layer.startEditing()

    def add(self, table, wkt=None, **attrs):
        """Lägger ett objekt direkt i ett lager (styrenheten reagerar om den finns)."""
        layer = self.layers[table]
        if not layer.isEditable():
            layer.startEditing()
        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        geometry = QgsGeometry.fromWkt(wkt) if wkt else QgsGeometry()
        indexed = {layer.fields().indexOf(name): value for name, value in attrs.items()}
        feature = QgsVectorLayerUtils.createFeature(layer, geometry, indexed, context)
        self.assertTrue(layer.addFeature(feature))
        return feature

    def features(self, table):
        return list(self.layers[table].getFeatures())

    def area(self, table):
        return sum(f.geometry().area() for f in self.features(table))
