"""Knappen Tagga planbeskrivning: programmet Tagga planbeskrivning öppnas med den aktiva planen, läser dess
bestämmelser och ytor och kan lägga syfte och motiv på planen (kräver QGIS)."""
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS, pump  # noqa: E402

if HAVE_QGIS:
    from qgis.PyQt.QtWidgets import QApplication
    from rita_detaljplan.core import assignments, rows
    from rita_detaljplan.gui.plan_toolbar import ICONS, PlanToolBar
    from rita_detaljplan.gui.planbeskrivning_host import SYFTE_MAX, QgisHost
    from test_export import ExportCase
else:  # pragma: no cover
    ExportCase = unittest.TestCase

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def para(text: str, style: str = "") -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"


def make_docx(path: Path, body: str) -> Path:
    """Ett minimalt Word-dokument med rubrikformat (Rubrik 1 och 2) och ``body`` som brödtext."""
    styles = (f'<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="{W}">'
              '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              + "".join(f'<w:style w:type="paragraph" w:styleId="Rubrik{n}"><w:name w:val="heading {n}"/>'
                        f'<w:pPr><w:outlineLvl w:val="{n - 1}"/></w:pPr></w:style>' for n in (1, 2, 3))
              + "</w:styles>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
                   'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
                   'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName='
                   '"/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.'
                   'document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
                   'openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns='
                   '"http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId5" Type='
                   '"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   '</Relationships>')
        z.writestr("word/styles.xml", styles)
        z.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
                   f'{body}<w:sectPr/></w:body></w:document>')
    return path


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PlanbeskrivningButtonTests(ExportCase):
    def setUp(self):
        super().setUp()
        self.toolbar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(self.toolbar.deleteLater)
        self.addCleanup(self.toolbar.close_planbeskrivning)
        self.host = QgisHost(self.controller)

    def document(self, motives=("Motiv för användningen.", "Motiv för egenskapen.")) -> Path:
        """Planbeskrivning med syfte och motiv i löpande text för planens två första bestämmelser."""
        targets = [t for t in self.controller.provision_targets() if not t["technical"]][:2]
        body = (para("DETALJPLANENS SYFTE", "Rubrik1") + para("Syfte", "Rubrik2")
                + para("Syftet är att möjliggöra industri.")
                + para("MOTIV TILL DETALJPLANENS REGLERINGAR", "Rubrik1") + para("Motiv till reglering", "Rubrik2")
                + "".join(para(t["text"]) + para(text) for t, text in zip(targets, motives)))
        self.targets = targets
        return make_docx(self.dir / "planbeskrivning.docx", body)

    # -- knappen -----------------------------------------------------------------------------
    def test_the_button_sits_in_the_toolbar_and_needs_a_plan_area(self):
        action = self.toolbar.act_planbeskrivning
        self.assertIn(action, self.toolbar.actions())
        self.assertEqual(action.text(), "Tagga planbeskrivning")
        self.assertTrue(action.isEnabled())
        self.assertIn("Tagga planbeskrivning", action.toolTip())
        self.assertNotIn("Planbeskrivning Taggning", action.toolTip())
        from rita_detaljplan.planbeskrivning.pbapp import main as program
        self.assertEqual(program.ICON_FILE.resolve(), (ICONS / "planbeskrivning.svg").resolve(),
                         "programmets ikon är verktygsfältets ikon")
        import xml.etree.ElementTree as ET
        self.assertTrue(ET.parse(ICONS / "planbeskrivning.svg").getroot().tag.endswith("svg"))

    def test_the_window_opens_with_the_active_plan_and_is_reused(self):
        window = self.toolbar.open_planbeskrivning()
        pump()
        self.assertEqual(window.session.plan.identitet, self.controller.plan_identity())
        self.assertEqual(window.session.host.name, "QGIS")
        self.assertIs(self.toolbar.open_planbeskrivning(), window, "ett öppet fönster visas igen")
        self.toolbar.close_planbeskrivning()
        self.assertIsNone(self.toolbar.planbeskrivning_window)

    def test_the_window_does_not_restyle_qgis(self):
        before = QApplication.instance().styleSheet()
        self.toolbar.open_planbeskrivning()
        self.assertEqual(QApplication.instance().styleSheet(), before)

    # -- planen till programmet ------------------------------------------------------------------
    def test_the_plan_has_the_provisions_and_identities_of_the_delivery(self):
        plan, _ = self.host.load_plan()
        self.assertEqual(plan.identitet, self.controller.plan_identity())
        self.assertEqual(plan.namn, "Kv Väktaren")
        targets = {t["key"]: sorted(t["refs"]) for t in self.controller.provision_targets()}
        self.assertEqual({p.key: sorted(p.refs) for p in plan.provisions}, targets)
        self.assertEqual(plan.kinds[plan.provisions[0].key], "anvandning_yta", "användningar först")
        self.assertEqual(plan.motiv[plan.provisions[0].key], "Industri behövs")

    def test_the_map_has_every_area_and_the_plan_border(self):
        plan, karta = self.host.load_plan()
        self.assertEqual(set(karta.layer_of.values()), {"anvandning_yta", "egenskap_yta", "egenskap_linje"})
        self.assertEqual(len(karta.areas), 4, "två användningar, en egenskapsyta och en egenskapslinje")
        self.assertIsNotNone(karta.border)
        use = plan.provisions[0]
        self.assertEqual(len(set(plan.areas[use.key])), 2, "användningen ligger på två ytor")
        self.assertTrue(all(a in karta.areas for a in plan.areas[use.key]))

    def test_a_plan_without_a_plan_area_is_explained(self):
        from rita_detaljplan.planbeskrivning.pbapp import session as ss
        layer = self.controller.layer("detaljplan")
        layer.deleteFeatures(layer.allFeatureIds())
        with self.assertRaisesRegex(ss.SessionError, "planområde"):
            self.host.load_plan()

    # -- syfte och motiv tillbaka till planen -------------------------------------------------------
    def test_purpose_and_motives_are_written_to_the_plan(self):
        key = self.controller.provision_targets()[0]["key"]
        message = self.host.write_back("Ett nytt syfte.", {key: "Ett nytt motiv."})
        self.assertEqual(self.controller.plan_values()["syfte"], "Ett nytt syfte.")
        written = [r["motiv"] for r in assignments.read_rows(self.controller.project)
                   if rows.identity(r) == key]
        self.assertEqual(written, ["Ett nytt motiv."] * len(written))
        self.assertIn("Syftet och 1 motiv lades på planen", message)
        self.assertIn("Planen hade redan samma", self.host.write_back("Ett nytt syfte.", {key: "Ett nytt motiv."}))

    def test_an_empty_text_never_removes_what_the_plan_has(self):
        self.host.write_back("", {})
        self.assertEqual(self.controller.plan_values()["syfte"], "Industri")

    def test_a_purpose_that_is_too_long_is_shortened_and_the_user_is_told(self):
        message = self.host.write_back("x" * (SYFTE_MAX + 10), {})
        self.assertEqual(len(self.controller.plan_values()["syfte"]), SYFTE_MAX)
        self.assertIn("kortades", message)

    def test_the_whole_way_from_the_document_to_the_plan(self):
        window = self.toolbar.open_planbeskrivning()
        window.files.load(docx=self.document())
        self.assertTrue(window.steps.button(2).isEnabled())
        linked = {m.key for m in window.session.analysis.motives}
        self.assertEqual(linked, {t["key"] for t in self.targets})
        window.go(4)
        window.export.write_to_host()
        self.assertIn("lades på planen", window.export.result.text())
        self.assertEqual(self.controller.plan_values()["syfte"], "Syftet är att möjliggöra industri.")
        motives = {rows.identity(r): r["motiv"] for r in assignments.read_rows(self.controller.project)}
        self.assertEqual(motives[self.targets[0]["key"]], "Motiv för användningen.")


class PackageTests(unittest.TestCase):
    """Programmet är en del av pluginets paket: det importerar inget utanför det, och kärnan behöver varken Qt eller
    QGIS (så att den kan köras och testas för sig)."""

    def test_it_imports_nothing_from_outside_the_plugin(self):
        for path in (ROOT / "rita_detaljplan" / "planbeskrivning").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^\s*(from|import) (pbkarna|pbapp)\b", path.name)

    def test_the_core_uses_neither_qt_nor_qgis(self):
        for path in (ROOT / "rita_detaljplan" / "planbeskrivning" / "pbkarna").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^\s*(from|import) (qgis|PyQt\d|PySide\d)\b", path.name)


if __name__ == "__main__":
    unittest.main()
