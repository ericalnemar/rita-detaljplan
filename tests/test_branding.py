"""Märket och identiteten: ikonerna är giltig SVG, bannrarna har texten som konturer, README pekar på riktiga bilder
och Om-dialogen visar rätt uppgifter."""
import re
import struct
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS  # noqa: E402

SVG = "{http://www.w3.org/2000/svg}"
IMAGES = ROOT / "docs" / "images"


class BrandFilesTests(unittest.TestCase):
    """Rena filkontroller, kräver inte QGIS."""

    def test_the_plugin_icon_is_valid_svg_with_the_mark(self):
        path = ROOT / "rita_detaljplan" / "icon.svg"
        root = ET.parse(path).getroot()
        self.assertEqual(root.tag, SVG + "svg")
        self.assertIsNotNone(root.find(f".//{SVG}polyline"))  # märkets linje
        self.assertTrue(root.get("aria-label"))

    def test_the_banners_have_their_text_as_outlines_so_no_font_is_needed(self):
        for name in ("banner-mork.svg", "banner-ljus.svg"):
            root = ET.parse(IMAGES / name).getroot()
            self.assertEqual(root.get("viewBox"), "0 0 1280 640", name)
            self.assertIsNone(root.find(f".//{SVG}text"), name)
            self.assertGreaterEqual(len(root.findall(f".//{SVG}path")), 2, name)

    def test_the_social_preview_is_a_1280_by_640_png(self):
        data = (IMAGES / "social-preview.png").read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (1280, 640))

    def test_the_readme_shows_images_that_exist(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        shown = re.findall(r'(?:src|srcset)="(docs/images/[^"]+)"', readme)
        self.assertTrue(shown, "README ska visa bannern")
        for name in shown:
            self.assertTrue((ROOT / name).exists(), name)


@unittest.skipUnless(HAVE_QGIS, "kräver QGIS")
class AboutDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qgis_app import get_app
        cls.app = get_app()

    def test_it_shows_name_version_author_and_licence_from_the_metadata(self):
        from rita_detaljplan.gui import about_dialog
        meta = about_dialog.metadata()
        dialog = about_dialog.AboutDialog()
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.windowTitle(), "Om Rita Detaljplan")
        self.assertEqual(dialog.name.text(), "Rita Detaljplan")
        self.assertEqual(dialog.version.text(), f"Version {meta['version']}")
        self.assertIn("Eric Alnemar", dialog.credit.text())
        self.assertIn("GPL-2.0-or-later", dialog.credit.text())
        self.assertEqual(dialog.docs.text(), "Dokumentation")

    def test_the_logo_renders_to_a_real_picture(self):
        from rita_detaljplan.gui import about_dialog
        pixmap = about_dialog.logo_pixmap(96)
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.deviceIndependentSize().width(), 96)

    def test_the_documentation_button_opens_the_manual_on_github(self):
        from rita_detaljplan.gui import about_dialog
        dialog = about_dialog.AboutDialog()
        self.addCleanup(dialog.deleteLater)
        with mock.patch.object(about_dialog.QDesktopServices, "openUrl") as open_url:
            dialog.docs.click()
        self.assertEqual(open_url.call_args.args[0].toString(),
                         "https://github.com/ritaplan/rita-detaljplan/blob/main/docs/anvandning.md")

    def test_the_website_button_opens_ritaplan_xyz(self):
        from rita_detaljplan.gui import about_dialog
        dialog = about_dialog.AboutDialog()
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.website.isHidden())
        with mock.patch.object(about_dialog.QDesktopServices, "openUrl") as open_url:
            dialog.website.click()
        self.assertEqual(open_url.call_args.args[0].toString(), "https://ritaplan.xyz")


if __name__ == "__main__":
    unittest.main()
