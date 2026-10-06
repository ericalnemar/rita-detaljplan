import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plankarta_case import PLAN_ID, make_geopackage, make_larkan, make_project  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import geometri as geo  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import plankarta as pk  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning_check as ck  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning_docx as dx  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import utbyte  # noqa: E402


class GeoPackageTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_the_same_provision_on_several_areas_is_one_provision_with_every_object(self):
        plan, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg"))
        self.assertEqual((plan.identitet, plan.namn, plan.beteckning), (PLAN_ID, "Detaljplan för kv. Lärkan", "1485-P2026/3"))
        self.assertEqual(len(plan.provisions), 12)
        b = next(p for p in plan.provisions if p.label == "B")
        self.assertEqual(len(b.refs), 3)
        self.assertEqual(len(set(b.refs)), 3)
        self.assertEqual(plan.kinds[b.key], "anvandning_yta")

    def test_values_are_filled_into_the_formulation(self):
        plan, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg"))
        texts = {p.label: p.text for p in plan.provisions}
        self.assertEqual(texts["e1"], "Största byggnadsarea är 30 % av fastighetsarean")
        self.assertEqual(texts["h1"], "Högsta nockhöjd är 14,0 meter")

    def test_uses_come_before_properties(self):
        plan, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg"))
        kinds = [plan.kinds[p.key] for p in plan.provisions]
        self.assertEqual(kinds, sorted(kinds, key=lambda k: k != "anvandning_yta"))

    def test_motives_already_on_the_map_are_read(self):
        plan, = pk.read_geopackage(make_geopackage(self.folder / "plan.gpkg", motiv={"B": "Bostäder behövs."}))
        b = next(p for p in plan.provisions if p.label == "B")
        self.assertEqual(plan.motiv[b.key], "Bostäder behövs.")

    def test_a_file_that_is_not_a_plan_is_explained(self):
        other = self.folder / "annat.gpkg"
        other.write_bytes(b"inte en databas" * 100)
        with self.assertRaises(pk.PlankartaError):
            pk.read_geopackage(other)
        with self.assertRaisesRegex(pk.PlankartaError, "finns inte"):
            pk.read_geopackage(self.folder / "saknas.gpkg")


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)
        make_geopackage(self.folder / "kv_Larkan.gpkg")

    def tearDown(self):
        self.dir.cleanup()

    def test_a_qgz_project_points_to_its_geopackage(self):
        project = make_project(self.folder / "plan.qgz", "kv_Larkan.gpkg")
        self.assertEqual(pk.geopackages_in_project(project), [(self.folder / "kv_Larkan.gpkg").resolve()])
        plan, = pk.read_plankarta(project)
        self.assertEqual(plan.identitet, PLAN_ID)

    def test_a_qgs_project_works_too(self):
        plan, = pk.read_plankarta(make_project(self.folder / "plan.qgs", "kv_Larkan.gpkg"))
        self.assertEqual(len(plan.provisions), 12)

    def test_a_plan_in_postgis_is_explained(self):
        project = make_project(self.folder / "plan.qgz", "kv_Larkan.gpkg", provider="postgres")
        with self.assertRaisesRegex(pk.PlankartaError, "PostGIS"):
            pk.read_plankarta(project)

    def test_a_missing_geopackage_is_explained(self):
        project = make_project(self.folder / "plan.qgz", "flyttad.gpkg")
        with self.assertRaisesRegex(pk.PlankartaError, "hittades inte"):
            pk.read_plankarta(project)


class KartaTest(unittest.TestCase):
    def test_the_areas_and_the_plan_border_are_read(self):
        with tempfile.TemporaryDirectory() as folder:
            gpkg = make_geopackage(Path(folder) / "plan.gpkg")
            plan, = pk.read_geopackage(gpkg)
            karta = geo.read_karta(gpkg, plan.identitet)
        self.assertEqual(len(karta.areas), 6)
        self.assertIsNotNone(karta.border)
        x0, y0, x1, y1 = karta.bounds()
        self.assertAlmostEqual(x1 - x0, 288)
        self.assertAlmostEqual(y1 - y0, 188)
        b = next(p for p in plan.provisions if p.label == "B")
        self.assertEqual(sorted(karta.labels[a] for a in plan.areas[b.key]), ["B", "B", "B"])

    def test_a_plan_without_geometry_gives_an_empty_map(self):
        with tempfile.TemporaryDirectory() as folder:
            karta = geo.read_karta(make_geopackage(Path(folder) / "plan.gpkg", geometry=False))
        self.assertEqual((karta.areas, karta.border, karta.bounds()), ({}, None, None))

    def test_z_values_and_big_endian_are_read(self):
        import struct
        ring = [(0, 0, 5), (1, 0, 5), (1, 1, 5), (0, 0, 5)]
        wkb = struct.pack(">BII", 0, 1003, 1) + struct.pack(">I", 4) + b"".join(struct.pack(">ddd", *p) for p in ring)
        shape = geo.parse_gpkg_geometry(b"GP\x00\x00" + struct.pack("<i", 3006) + wkb)
        self.assertEqual(shape.parts, [[(0, 0), (1, 0), (1, 1), (0, 0)]])
        self.assertIsNone(geo.parse_gpkg_geometry(b"inte"))


class ExampleTest(unittest.TestCase):
    """Hela flödet med exemplet kv. Lärkan: läsa plankartan, analysera dokumentet, skriva en leveranskopia."""

    def test_the_example_is_analysed_and_tagged(self):
        with tempfile.TemporaryDirectory() as folder:
            files = make_larkan(Path(folder))
            plan, = pk.read_plankarta(files["qgz"])
            analysis = dx.analyse(files["docx"], plan.provisions)
            matched = {next(p.label for p in plan.provisions if p.key == m.key) for m in analysis.motives if m.key}
            self.assertTrue({"B", "GATA", "PARK", "e1", "h1", "b1", "n1", "r1"} <= matched, matched)
            review = [s for s in analysis.sections if s.status in dx.NEEDS_REVIEW]
            self.assertTrue(review, "exemplet ska ha något att granska")
            result = dx.tag_docx(analysis, Path(folder) / "ut.docx", plan.identitet, "0.1.0",
                                 software="Planbeskrivning Taggning")
            self.assertGreater(result.avsnitt, 10)
            again = dx.analyse(Path(folder) / "ut.docx", plan.provisions)
            self.assertEqual(again.previous.programvara, "Planbeskrivning Taggning")
            self.assertIsInstance(ck.check(analysis), list)

            data = utbyte.build(analysis, plan.identitet, "Planbeskrivning Taggning")
            self.assertTrue(data["syfte"].startswith("Syftet med detaljplanen"))
            by_label = {m["beteckning"]: m for m in data["motiv"]}
            self.assertIn("Lärkvägen förlängs", by_label["GATA"]["motiv"])
            self.assertEqual(len(by_label["B"]["objekt"]), 3)
            back = utbyte.read(utbyte.write(Path(folder) / "motiv.json", data))
            self.assertEqual(back["motiv"], data["motiv"])
            with self.assertRaises(utbyte.UtbyteError):
                utbyte.read(files["gpkg"])


if __name__ == "__main__":
    unittest.main()
