import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plankarta_case import make_larkan  # noqa: E402
from rita_detaljplan.planbeskrivning.pbapp import session as ss  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning_docx as dx  # noqa: E402


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)
        self.files = make_larkan(self.folder)
        self.store = ss.Store.memory()
        self.session = self.open()

    def tearDown(self):
        self.dir.cleanup()

    def open(self) -> ss.Session:
        session = ss.Session(self.store)
        session.load_plankarta(self.files["qgz"])
        session.load_docx(self.files["docx"])
        return session

    def section(self, session, heading):
        return next(s for s in session.analysis.sections if s.path[-1] == heading)

    def motive(self, session, label):
        return next(m for m in session.analysis.motives if m.label == label)

    def test_statuses_of_the_example(self):
        s = self.session
        self.assertEqual(s.status(self.section(s, "Syfte")), ss.AUTO)
        self.assertEqual(s.status(self.section(s, "Hela detaljplanen")), ss.OSAKER)
        self.assertEqual(s.status(self.section(s, "Buller")), ss.EGEN)
        self.assertEqual(s.status(self.section(s, "MEDVERKANDE")), ss.SAKNAS)
        self.assertEqual(s.status(self.section(s, "PLANERINGSFÖRUTSÄTTNINGAR")), ss.RUBRIK)
        self.assertNotIn(self.section(s, "Motiv till reglering"), s.tagged_sections())

    def test_choosing_a_group_is_remembered_for_the_next_time(self):
        s = self.session
        s.set_indelning(self.section(s, "Buller"), "Planeringsförutsättningar", "Hälsa och säkerhet", "Omgivningsbuller")
        buller = self.section(s, "Buller")
        self.assertEqual((buller.indelning.undergrupp, s.status(buller)), ("Omgivningsbuller", ss.GRANSKAD))
        again = self.open()
        self.assertEqual(self.section(again, "Buller").indelning.undergrupp, "Omgivningsbuller")
        self.assertEqual(again.status(self.section(again, "Buller")), ss.GRANSKAD)

    def test_a_skipped_section_is_not_an_error(self):
        s = self.session
        medverkande = self.section(s, "MEDVERKANDE")
        self.assertTrue(any(f.var == "MEDVERKANDE" for f in s.findings()))
        s.skip(medverkande)
        self.assertEqual(s.status(medverkande), ss.HOPPAS)
        self.assertFalse(any(f.var == "MEDVERKANDE" for f in s.findings()))
        self.assertEqual(self.open().status(self.section(self.open(), "MEDVERKANDE")), ss.HOPPAS)

    def test_linking_a_motive_by_hand_survives_a_new_analysis(self):
        s = self.session
        k = self.motive(s, "k")
        self.assertEqual(s.motive_status(k), ss.EJ_KOPPLAT)
        k1 = next(p for p in s.provisions if p.label == "k1")
        s.link(k, k1.key)
        self.assertEqual(s.motive_status(k), ss.KOPPLAT)
        self.assertNotIn(k1, s.provisions_without_motive())
        b = self.motive(s, "B")
        s.link(b, None)
        s.set_indelning(self.section(s, "Buller"), "Planeringsförutsättningar", "Hälsa och säkerhet", "")
        self.assertIsNone(self.motive(s, "B").key, "en borttagen koppling ska inte komma tillbaka av sig själv")
        again = self.open()
        self.assertEqual(self.motive(again, "k").key, k1.key)
        self.assertIsNone(self.motive(again, "B").key)

    def test_the_copies_and_the_exchange_file_are_written(self):
        s = self.session
        s.skip(self.section(s, "MEDVERKANDE"))
        self.assertIn("<Planbeskrivning", s.xml_preview())
        result = s.write_copy(self.folder / "leverans.docx")
        self.assertGreater(result.avsnitt, 10)
        review = s.write_copy(self.folder / "granskning.docx", review=True)
        self.assertEqual(review.kommentarer, result.avsnitt + result.motiv)
        self.assertTrue(s.write_overview(self.folder / "oversikt.csv").read_text(encoding="utf-8-sig").startswith("Bokmärke"))
        data = s.write_exchange(self.folder / "motiv.json")
        self.assertEqual(data["detaljplan"], s.plan.identitet)
        with self.assertRaises(ss.SessionError):
            s.write_copy(self.files["docx"])

    def test_a_section_can_be_found_from_a_finding(self):
        s = self.session
        self.assertEqual(s.section_for("MEDVERKANDE").path, ("MEDVERKANDE",))
        self.assertIsNone(s.section_for(""))

    def test_the_map_has_the_areas_of_each_provision(self):
        s = self.session
        b = next(p for p in s.provisions if p.label == "B")
        self.assertEqual(len([a for a in s.plan.areas[b.key] if a in s.karta.areas]), 3)


if __name__ == "__main__":
    unittest.main()
