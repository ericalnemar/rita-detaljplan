"""Klickar igenom programmet Tagga planbeskrivning utan att visa fönstret (Qt offscreen): med QGIS egen Qt när testerna
körs i QGIS, annars med PySide6. Hoppas över om ingen av dem finns."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from plan_case import HAVE_QGIS  # noqa: E402

try:
    from rita_detaljplan.planbeskrivning.pbapp.qt.QtWidgets import QApplication
except ImportError:  # pragma: no cover - varken QGIS eller PySide6
    QApplication = None


def get_app():
    if HAVE_QGIS:
        from qgis_app import get_app as qgis_app
        return qgis_app()
    return QApplication.instance() or QApplication([])

from plankarta_case import make_larkan  # noqa: E402


@unittest.skipIf(QApplication is None, "Qt saknas")
class GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        from rita_detaljplan.planbeskrivning.pbapp import session as ss
        from rita_detaljplan.planbeskrivning.pbapp.main import MainWindow
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)
        self.files = make_larkan(self.folder)
        self.window = MainWindow(ss.Session())
        self.window.files.load(docx=self.files["docx"], plankarta=self.files["qgz"])

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.dir.cleanup()

    def index_of(self, heading):
        return next(n for n, s in enumerate(self.window.session.analysis.sections) if s.path[-1] == heading)

    def test_the_window_and_the_heading_are_called_tagga_planbeskrivning(self):
        from rita_detaljplan.planbeskrivning.pbapp.qt.QtWidgets import QLabel
        self.assertEqual(self.window.windowTitle(), "Tagga planbeskrivning")
        brand = [label.text() for label in self.window.findChildren(QLabel) if label.objectName() == "brand"]
        self.assertEqual(brand, ["Tagga planbeskrivning"])

    def test_the_old_name_is_only_kept_as_the_key_for_saved_choices(self):
        from rita_detaljplan.planbeskrivning.pbapp import APP_NAME, SETTINGS_NAME
        self.assertEqual(APP_NAME, "Tagga planbeskrivning")
        self.assertEqual(SETTINGS_NAME, "Planbeskrivning Taggning", "annars försvinner användarens sparade val")

    def test_the_program_uses_the_icon_of_the_toolbar_button(self):
        from rita_detaljplan.planbeskrivning.pbapp import main
        self.assertEqual(main.ICON_FILE.name, "planbeskrivning.svg")
        self.assertEqual(main.ICON_FILE.parent.name, "icons")
        self.assertTrue(main.ICON_FILE.exists())
        self.assertFalse(self.window.windowIcon().isNull())
        image = main.logo_pixmap(64).toImage()
        colours = {image.pixelColor(x, y).name() for x in range(0, image.width(), 2) for y in range(0, image.height(), 2)
                   if image.pixelColor(x, y).alpha() > 200}
        self.assertIn("#0e6a5b", colours, "ikonens gröna etikett syns i logotypen")

    def test_steps_are_locked_until_both_files_are_chosen(self):
        from rita_detaljplan.planbeskrivning.pbapp import session as ss
        from rita_detaljplan.planbeskrivning.pbapp.main import MainWindow
        empty = MainWindow(ss.Session())
        self.assertFalse(empty.steps.button(2).isEnabled())
        empty.go(3)
        self.assertIs(empty.stack.currentWidget(), empty.files)
        self.assertTrue(self.window.steps.button(2).isEnabled())
        empty.deleteLater()

    def test_tagging_a_section_by_hand(self):
        w = self.window
        w.go(2)
        tag = w.tag
        self.assertEqual(w.session.analysis.sections[tag.selected].path[-1], "Hela detaljplanen", "första att granska")
        tag.select(self.index_of("Buller"))
        tag.undergrupp.setCurrentText("Omgivningsbuller")
        tag.apply()
        section = w.session.analysis.sections[self.index_of("Buller")]
        self.assertEqual(section.indelning.undergrupp, "Omgivningsbuller")
        self.assertEqual(w.session.status(section), "granskad")

        tag.select(self.index_of("Hela detaljplanen"))
        tag.approve()
        self.assertEqual(w.session.status(w.session.analysis.sections[self.index_of("Hela detaljplanen")]), "granskad")
        self.assertEqual(w.session.analysis.sections[tag.selected].path[-1], "MEDVERKANDE", "hoppar till nästa")
        tag.toggle_skip()
        self.assertEqual(w.session.status(w.session.analysis.sections[self.index_of("MEDVERKANDE")]), "hoppas")
        tag.set_filter("granska")
        self.assertEqual(tag.outline.item(0).flags(), tag.outline.item(0).flags().__class__(0), "inget kvar att granska")

    def test_linking_a_motive_and_saving_the_copies(self):
        w = self.window
        w.go(3)
        motiv = w.motiv
        k = next(n for n, m in enumerate(w.session.analysis.motives) if m.label == "k")
        self.assertEqual(motiv.selected, k, "första motivet utan bestämmelse är valt")
        k1 = next(n for n, p in enumerate(w.session.provisions) if p.label == "k1")
        motiv._dropped(k, k1)
        self.assertEqual(w.session.analysis.motives[k].key, w.session.provisions[k1].key)
        self.assertEqual(motiv.map.highlighted, set(w.session.plan.areas[w.session.provisions[k1].key]))

        w.go(4)
        self.assertIn("<Planbeskrivning", w.export.xml.toPlainText())
        result = w.session.write_copy(self.folder / "leverans.docx")
        self.assertEqual(result.omatchade_motiv, 0)

    def test_a_finding_opens_the_right_place(self):
        w = self.window
        w.go(4)
        w.export.open_section.emit(self.index_of("MEDVERKANDE"))
        self.assertIs(w.stack.currentWidget(), w.tag)
        self.assertEqual(w.tag.selected, self.index_of("MEDVERKANDE"))
        f1 = next(p for p in w.session.provisions if p.label == "f1")
        w.export.open_provision.emit(f1.key)
        self.assertIs(w.stack.currentWidget(), w.motiv)
        self.assertEqual(w.session.provisions[w.motiv.pinned].label, "f1")


class FakeHost:
    """Ett påhittat värdprogram (som Rita Detaljplan i QGIS) som har planen kv. Lärkan."""
    name = "QGIS"

    def __init__(self, gpkg):
        self.gpkg, self.written, self.loads = gpkg, None, 0

    def load_plan(self):
        from rita_detaljplan.planbeskrivning.pbkarna import geometri as geo
        from rita_detaljplan.planbeskrivning.pbkarna import plankarta as pk
        self.loads += 1
        plan, = pk.read_geopackage(self.gpkg)
        return plan, geo.read_karta(self.gpkg, plan.identitet)

    def write_back(self, purpose, motives):
        self.written = (purpose, motives)
        return f"{len(motives)} motiv lades på planen."


@unittest.skipIf(QApplication is None, "Qt saknas")
class HostTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        from rita_detaljplan.planbeskrivning.pbapp.main import open_in_host
        self.dir = tempfile.TemporaryDirectory()
        self.files = make_larkan(Path(self.dir.name))
        self.host = FakeHost(self.files["gpkg"])
        from rita_detaljplan.planbeskrivning.pbapp.qt.QtCore import Qt
        from rita_detaljplan.planbeskrivning.pbapp import session as ss
        self.window = open_in_host(self.host, store=ss.Store.memory())
        self.window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # tearDown städar själv

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.dir.cleanup()

    def test_the_plan_comes_from_the_host_and_only_the_document_is_chosen(self):
        w = self.window
        self.assertEqual(self.host.loads, 1)
        self.assertEqual(w.session.plan.namn, "Detaljplan för kv. Lärkan")
        self.assertIn("QGIS", w.files.map_path.text())
        self.assertFalse(w.files.example.isVisible())
        self.assertFalse(w.steps.button(2).isEnabled(), "planbeskrivningen saknas än")
        w.files.load(docx=self.files["docx"])
        self.assertTrue(w.steps.button(2).isEnabled())
        w.files.reload_from_host()
        self.assertEqual(self.host.loads, 2)
        self.assertIsNotNone(w.session.analysis, "dokumentet är kvar efter att planen lästs om")

    def test_the_purpose_and_the_motives_are_written_to_the_plan(self):
        w = self.window
        w.files.load(docx=self.files["docx"])
        w.go(4)
        w.export.write_to_host()
        purpose, motives = self.host.written
        self.assertTrue(purpose.startswith("Syftet med detaljplanen"))
        self.assertEqual(len(motives), 9)
        self.assertIn("motiv lades på planen", w.export.result.text())


if __name__ == "__main__":
    unittest.main()
