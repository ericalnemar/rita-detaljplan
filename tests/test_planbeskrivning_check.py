"""Kontroll av planbeskrivningen mot BFS 2020:8 innan den taggas (ren Python, ingen QGIS)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx_case import BODY, make_docx, para, wrap  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning_check as ck  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning_docx as dx  # noqa: E402

R1 = dx.Provision("k1", "R1", "Badanläggning", ("11111111-1111-4111-8111-111111111111",))


def complete(skip=(), motive=True, extra=""):
    """En planbeskrivning med allt som kontrollen kräver. ``skip`` = rubriker (text) som utelämnas helt."""
    parts = [
        ("DETALJPLANENS SYFTE", 1), ("Syfte", 2), ("Detaljplanen syftar till en badanläggning.", 0),
        ("BESKRIVNING AV DETALJPLANEN", 1), ("Hela detaljplanen", 2), ("Planområdet ligger vid Framnäs.", 0),
        ("Genomförandetid", 2), ("Genomförandetiden är tio år.", 0),
        ("Ärendeinformation", 2), ("Planen har samråtts.", 0),
        ("MOTIV TILL DETALJPLANENS REGLERINGAR", 1), ("Motiv till regleringar", 2),
        ("PLANERINGSFÖRUTSÄTTNINGAR", 1), ("Kommunala", 2), ("Översiktsplanen pekar ut området.", 0),
        ("PLANERINGSUNDERLAG", 1), ("Kommunala", 2), ("En planprogramhandling har gjorts.", 0),
        ("GENOMFÖRANDEFRÅGOR", 1), ("Ekonomiska frågor", 2), ("Genomförandet bedöms vara lönsamt.", 0),
    ]
    out, skipping = [], None
    for text, level in parts:
        if level:
            skipping = text in skip
        if skipping:
            continue
        out.append(para(text, f"Rubrik{level}" if level else ""))
        if text == "Motiv till regleringar" and motive:
            out.append(para("R1 Badanläggning") + para("Syftet är att möjliggöra bad."))
    return wrap("".join(out) + extra)


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.folder.cleanup)
        self.dir = Path(self.folder.name)

    def findings(self, body, provisions=(R1,), overrides=None):
        src = make_docx(self.dir / "plan.docx", body)
        return ck.check(dx.analyse(src, list(provisions), overrides))

    def by_severity(self, found, severity):
        return [f for f in found if f.allvarlighet == severity]

    def texts(self, found, severity):
        return [f.text for f in self.by_severity(found, severity)]


class CompleteDocumentTests(Base):
    def test_a_complete_document_has_neither_errors_nor_warnings(self):
        found = self.findings(complete())
        self.assertEqual(ck.counts(found), (0, 0), [f.text for f in found if f.allvarlighet != ck.INFO])

    def test_the_information_lines_say_how_much_is_tagged(self):
        found = self.findings(complete())
        self.assertTrue(any("blir taggade" in f.text for f in self.by_severity(found, ck.INFO)))


class RequiredContentTests(Base):
    def assertMissing(self, skip, text_part, severity, krav_part):
        found = self.findings(complete(skip=skip))
        hit = [f for f in self.by_severity(found, severity) if text_part in f.text]
        self.assertEqual(len(hit), 1, [f.text for f in found])
        self.assertIn(krav_part, hit[0].krav)

    def test_the_purpose_is_required(self):
        self.assertMissing(("DETALJPLANENS SYFTE",), "Detaljplanens syfte saknas", ck.FEL, "2 kap. 1 §")

    def test_scope_and_location_are_required(self):
        self.assertMissing(("Hela detaljplanen",), "omfattning och lokalisering", ck.FEL, "2 kap. 2 §")

    def test_the_implementation_period_is_required(self):
        self.assertMissing(("Genomförandetid",), "Genomförandetiden saknas", ck.FEL, "2 kap. 2 §")

    def test_the_summary_of_planning_documents_is_required(self):
        self.assertMissing(("PLANERINGSUNDERLAG",), "planeringsunderlag saknas", ck.FEL, "2 kap. 13 §")

    def test_case_information_is_a_warning(self):
        self.assertMissing(("Ärendeinformation",), "Ärendeinformationen saknas", ck.VARNING, "2 kap. 14 §")

    def test_implementation_matters_are_a_warning(self):
        self.assertMissing(("GENOMFÖRANDEFRÅGOR",), "Genomförandefrågor saknas", ck.VARNING, "2 kap. 8–9 §§")

    def test_the_economic_assessment_is_asked_for_when_the_implementation_chapter_lacks_it(self):
        body = complete(skip=("GENOMFÖRANDEFRÅGOR",)).replace(
            "<w:sectPr>", para("GENOMFÖRANDEFRÅGOR", "Rubrik1") + para("Tekniska frågor", "Rubrik2")
            + para("Utbyggnad ordnas av kommunen.") + "<w:sectPr>")
        found = self.findings(body)
        self.assertEqual([f.text for f in found if "ekonomiska bedömningen" in f.text],
                         ["Den ekonomiska bedömningen av genomförandet saknas."])
        self.assertFalse(any("Genomförandefrågor saknas" in f.text for f in found))

    def test_how_interests_were_weighed_needs_either_conditions_or_consequences(self):
        found = self.findings(complete(skip=("PLANERINGSFÖRUTSÄTTNINGAR",)))
        self.assertTrue(any("avvägt olika intressen" in f.text for f in self.by_severity(found, ck.VARNING)))
        with_consequences = complete(skip=("PLANERINGSFÖRUTSÄTTNINGAR",)).replace(
            "<w:sectPr>", para("KONSEKVENSER", "Rubrik1") + para("Natur", "Rubrik2") + para("Naturen påverkas lite.")
            + "<w:sectPr>")
        self.assertFalse(any("avvägt" in f.text for f in self.findings(with_consequences)))

    def test_the_findings_come_with_the_most_serious_first(self):
        found = self.findings(complete(skip=("DETALJPLANENS SYFTE", "Ärendeinformation")))
        order = [f.allvarlighet for f in found]
        self.assertEqual(order, sorted(order, key=ck.ORDNING.get))
        self.assertEqual(order[0], ck.FEL)


class UntaggedTextTests(Base):
    def test_text_under_an_unknown_theme_is_an_error_that_names_the_heading(self):
        body = complete().replace(
            "<w:sectPr>", para("HEMLIG RUBRIK", "Rubrik1") + para("Text under okänt tema.") + "<w:sectPr>")
        errors = self.by_severity(self.findings(body), ck.FEL)
        hit = [f for f in errors if "känns inte igen som ett tema" in f.text]
        self.assertEqual([f.var for f in hit], ["HEMLIG RUBRIK"])
        self.assertEqual(hit[0].krav, "3 kap. 2 §")

    def test_text_straight_under_a_theme_heading_has_no_group_and_is_an_error(self):
        body = complete().replace(
            "<w:sectPr>", para("KONSEKVENSER", "Rubrik1") + para("Text direkt under temat.") + "<w:sectPr>")
        errors = self.by_severity(self.findings(body), ck.FEL)
        self.assertTrue(any("saknar grupp" in f.text and f.var == "KONSEKVENSER" for f in errors))

    def test_the_message_for_text_without_a_group_tells_how_to_fix_it_in_the_list(self):
        body = complete().replace(
            "<w:sectPr>", para("KONSEKVENSER", "Rubrik1") + para("Text direkt under temat.") + "<w:sectPr>")
        message = next(f.text for f in self.findings(body) if "saknar grupp" in f.text)
        self.assertIn("Välj grupp för den i listan", message)

    def test_choosing_a_group_for_that_text_removes_the_error(self):
        body = complete().replace(
            "<w:sectPr>", para("KONSEKVENSER", "Rubrik1") + para("Text direkt under temat.") + "<w:sectPr>")
        saved = dx.Overrides(grupp={dx.path_key(("Konsekvenser",)) + "|": "Annat"})
        self.assertFalse(any("saknar grupp" in f.text for f in self.findings(body, overrides=saved)))

    def test_a_saved_choice_for_the_theme_moves_the_problem_on_to_the_missing_group(self):
        body = complete().replace("<w:sectPr>", para("HEMLIG RUBRIK", "Rubrik1") + para("Text.") + "<w:sectPr>")
        before = [f.text for f in self.findings(body)]
        saved = dx.Overrides(tema={dx.path_key(("HEMLIG RUBRIK",)): "Konsekvenser"})
        after = [f.text for f in self.findings(body, overrides=saved)]
        self.assertTrue(any("känns inte igen som ett tema" in t for t in before))
        self.assertFalse(any("känns inte igen som ett tema" in t for t in after))
        self.assertTrue(any("saknar grupp" in t for t in after), "temat är valt men texten saknar fortfarande grupp")

    def test_text_before_the_first_heading_is_reported_as_information_not_as_an_error(self):
        found = self.findings(complete().replace("<w:body>", "<w:body>" + para("Försättsblad")))
        info = [f for f in self.by_severity(found, ck.INFO) if "före första rubriken" in f.text]
        self.assertEqual(len(info), 1)
        self.assertIn("1 avsnitt", info[0].text)
        self.assertEqual(ck.counts(found), (0, 0))

    def test_a_document_without_headings_cannot_be_tagged(self):
        found = self.findings(wrap(para("Bara löpande text utan en enda rubrik.")))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].allvarlighet, ck.FEL)
        self.assertIn("inga rubriker", found[0].text)


class MotiveTests(Base):
    def test_a_provision_without_a_motive_in_the_document_is_an_error_naming_it(self):
        extra = dx.Provision("k2", "X9", "Något helt annat", ("22222222-2222-4222-8222-222222222222",))
        found = self.findings(complete(), (R1, extra))
        errors = self.by_severity(found, ck.FEL)
        self.assertEqual([f.var for f in errors], ["X9 Något helt annat"])
        self.assertIn("2 kap. 3 §", errors[0].krav)

    def test_when_no_motive_at_all_is_found_it_is_one_error_not_one_per_provision(self):
        extra = dx.Provision("k2", "X9", "Något helt annat", ("22222222-2222-4222-8222-222222222222",))
        found = self.findings(complete(motive=False), (R1, extra))
        errors = [f for f in self.by_severity(found, ck.FEL) if "Inga motiv hittades" in f.text]
        self.assertEqual(len(errors), 1)
        self.assertIn("2 bestämmelser", errors[0].text)
        self.assertFalse(any(f.var == "R1 Badanläggning" for f in found))

    def test_the_fixed_motive_of_technical_installations_needs_nothing_in_the_document(self):
        technical = dx.Provision("kt", "", "Tekniska anläggningar", ("33333333-3333-4333-8333-333333333333",), True)
        self.assertEqual(ck.counts(self.findings(complete(), (R1, technical))), (0, 0))

    def test_provisions_the_plan_does_not_deliver_are_not_asked_for(self):
        undelivered = dx.Provision("kx", "Q1", "Utan identitet", ())
        self.assertEqual(ck.counts(self.findings(complete(), (R1, undelivered))), (0, 0))

    def test_a_table_row_that_matches_no_provision_is_a_warning(self):
        found = self.findings(BODY, (R1,))
        warnings = [f for f in self.by_severity(found, ck.VARNING) if "hittar ingen bestämmelse" in f.text]
        self.assertTrue(warnings)
        self.assertIn("z9", " ".join(f.var for f in warnings))

    def test_a_motive_row_with_only_the_provision_text_and_no_motive_is_a_warning(self):
        body = BODY.replace("<w:p><w:r><w:t>Syftet är att möjliggöra bad.</w:t></w:r></w:p>", "")
        found = self.findings(body, (R1,))
        self.assertTrue(any(f.text.startswith("Motivet saknar text") for f in self.by_severity(found, ck.VARNING)))

    def test_a_motive_section_where_nothing_could_be_linked_is_a_warning(self):
        body = wrap(para("MOTIV TILL DETALJPLANENS REGLERINGAR", "Rubrik1") + para("Motiv till regleringar", "Rubrik2")
                    + para("Allmänt resonemang utan att peka ut någon bestämmelse."))
        found = self.findings(body)
        self.assertTrue(any("handlar om motiv" in f.text for f in self.by_severity(found, ck.VARNING)))


class CountsTests(unittest.TestCase):
    def test_counts_errors_and_warnings_separately(self):
        found = [ck.Fynd(ck.FEL, "a"), ck.Fynd(ck.FEL, "b"), ck.Fynd(ck.VARNING, "c"), ck.Fynd(ck.INFO, "d")]
        self.assertEqual(ck.counts(found), (2, 1))

    def test_each_finding_has_a_symbol_for_its_severity(self):
        self.assertEqual([ck.Fynd(s, "x").symbol for s in (ck.FEL, ck.VARNING, ck.INFO)], ["✘", "▲", "ℹ"])


if __name__ == "__main__":
    unittest.main()
