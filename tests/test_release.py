"""Förutsättningar för att publicera pluginet: metadata, dokumentationens länkar och zip-paketet (utan QGIS)."""
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_zip  # noqa: E402

REPO_URL = "https://github.com/ericalnemar/rita-detaljplan"
MARKDOWN = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "NOTICE.md",
            *(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").glob("*.md"))]


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.meta = build_zip.read_metadata(ROOT)

    def test_the_fields_qgis_and_the_plugin_repository_ask_for_are_filled_in(self):
        for key in ("name", "qgisMinimumVersion", "description", "about", "version", "author", "tags", "homepage",
                    "tracker", "repository", "icon"):
            self.assertTrue(self.meta.get(key), key)

    def test_name_author_and_the_links_point_at_this_project(self):
        self.assertEqual(self.meta["name"], "Rita Detaljplan")
        self.assertEqual(self.meta["author"], "Eric Alnemar")
        self.assertEqual(self.meta["homepage"], REPO_URL)
        self.assertEqual(self.meta["repository"], REPO_URL)
        self.assertEqual(self.meta["tracker"], REPO_URL + "/issues")

    def test_the_version_is_semantic_and_has_a_changelog_entry(self):
        self.assertRegex(self.meta["version"], r"^\d+\.\d+\.\d+$")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{self.meta['version']}]", changelog)

    def test_the_plugin_repository_gets_an_english_description_and_a_contact_address(self):
        for key in ("description", "about"):
            self.assertNotRegex(self.meta[key], "[åäöÅÄÖ]", f"{key} ska vara på engelska")
            self.assertGreater(len(self.meta[key].split()), 5, key)
        self.assertRegex(self.meta["email"], r"^[^@\s]+@[^@\s]+\.[a-z]+$")

    def test_it_targets_qgis_4_and_needs_no_qt6_flag(self):
        self.assertEqual(self.meta["qgisMinimumVersion"], "4.0")
        self.assertEqual(self.meta["qgisMaximumVersion"], "4.99")
        self.assertNotIn("supportsQt6", self.meta, "flaggan är borttagen ur QGIS och behövs inte")

    def test_the_first_release_is_marked_experimental(self):
        self.assertEqual(self.meta["experimental"], "True")

    def test_the_icon_exists(self):
        self.assertTrue((ROOT / "rita_detaljplan" / self.meta["icon"]).exists())

    def test_the_package_has_the_entry_point_qgis_needs(self):
        self.assertIn("def classFactory", (ROOT / "rita_detaljplan" / "__init__.py").read_text(encoding="utf-8"))


class DocumentationTests(unittest.TestCase):
    def test_every_relative_link_in_the_markdown_files_points_at_something_that_exists(self):
        broken = []
        for name in MARKDOWN:
            path = ROOT / name
            text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
            for target in re.findall(r"\]\(([^)\s]+)\)", text):
                if re.match(r"^(https?:|mailto:|#)", target):
                    continue
                if not (path.parent / target.split("#")[0]).exists():
                    broken.append(f"{name}: {target}")
        self.assertEqual(broken, [])

    def test_the_readme_covers_what_a_new_visitor_needs(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for heading in ("## Installera", "## Snabbstart", "## Dokumentation", "## Licens"):
            self.assertIn(heading, readme)
        self.assertIn(REPO_URL + "/releases", readme)
        self.assertIn("Installera från ZIP", readme)

    def test_the_repository_has_the_files_github_looks_for(self):
        for name in ("LICENSE", "README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "NOTICE.md",
                     ".github/ISSUE_TEMPLATE/bug_report.md", ".github/ISSUE_TEMPLATE/feature_request.md"):
            self.assertTrue((ROOT / name).exists(), name)

    def test_no_personal_paths_or_stray_files_are_left_in_the_repository(self):
        self.assertFalse((ROOT / "symbology-style.db").exists())
        for name in MARKDOWN:
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users\\", text, name)
            self.assertNotRegex(text, r"/Users/\w", name)


class ZipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.path = build_zip.build(ROOT, Path(cls.tmp.name))
        with zipfile.ZipFile(cls.path) as archive:
            cls.names = archive.namelist()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_file_is_named_after_the_version(self):
        self.assertEqual(self.path.name, f"rita_detaljplan-{build_zip.version(ROOT)}.zip")

    def test_everything_sits_in_one_folder_named_like_the_package(self):
        self.assertTrue(all(name.startswith("rita_detaljplan/") for name in self.names), self.names[:5])

    def test_the_files_qgis_needs_and_the_licence_are_included(self):
        for name in ("metadata.txt", "__init__.py", "plugin.py", "icon.svg", "LICENSE", "NOTICE.md", "CHANGELOG.md",
                     "data/planbestammelsekatalog.json", "data/kommuner.json", "data/styles/detaljplaner-bfs-2020-6.xml",
                     "icons/legend.svg", "core/checkout.py"):
            self.assertIn(f"rita_detaljplan/{name}", self.names)

    def test_development_files_and_caches_are_left_out(self):
        for name in self.names:
            for unwanted in ("__pycache__", ".pyc", "/tests/", "/spec/", "/tools/", ".git", ".gpkg", ".db"):
                self.assertNotIn(unwanted, name, name)

    def test_every_python_file_in_the_package_is_included(self):
        expected = {p.relative_to(ROOT).as_posix() for p in (ROOT / "rita_detaljplan").rglob("*.py")
                    if "__pycache__" not in p.parts}
        self.assertLessEqual(expected, set(self.names))

    def test_the_same_content_gives_the_same_zip(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as other:
            again = build_zip.build(ROOT, Path(other))
            self.assertEqual(again.read_bytes(), self.path.read_bytes())

    def test_the_zip_is_valid_and_the_metadata_inside_matches(self):
        with zipfile.ZipFile(self.path) as archive:
            self.assertIsNone(archive.testzip())
            inside = archive.read("rita_detaljplan/metadata.txt").decode("utf-8")
        self.assertIn(f"version={build_zip.version(ROOT)}", inside)

    def test_text_files_have_unix_line_endings_like_the_repository(self):
        with zipfile.ZipFile(self.path) as archive:
            for name in archive.namelist():
                if name.endswith((".py", ".md", ".txt", ".json", ".xml", ".svg")):
                    self.assertNotIn(b"\r\n", archive.read(name), name)

    def test_line_endings_are_normalised_but_binary_data_is_left_alone(self):
        self.assertEqual(build_zip.normalized(b"a\r\nb\r\n"), b"a\nb\n")
        self.assertEqual(build_zip.normalized(b"\x89PNG\r\n\x00\x01"), b"\x89PNG\r\n\x00\x01")
        self.assertEqual(build_zip.normalized(b"\xff\xfe\r\n"), b"\xff\xfe\r\n")

    def test_a_bad_version_is_refused(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as fake:
            root = Path(fake)
            (root / "rita_detaljplan").mkdir()
            (root / "rita_detaljplan" / "metadata.txt").write_text("[general]\nversion=abc\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                build_zip.version(root)


if __name__ == "__main__":
    unittest.main()
