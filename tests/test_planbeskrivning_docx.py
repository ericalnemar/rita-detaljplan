"""Tagga en befintlig planbeskrivning (.docx): rubriker -> tema/grupp/undergrupp, motivrader -> bestämmelser och den
taggade kopian (ren Python, ingen QGIS)."""
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx_case import (BODY, STYLES, label_box, make_docx, para, raw_para, run, running_text_body,  # noqa: E402
                       wrap)
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning as pb  # noqa: E402
from rita_detaljplan.planbeskrivning.pbkarna import planbeskrivning_docx as dx  # noqa: E402
from test_planbeskrivning import check_against_xsd  # noqa: E402

PLAN = "12345678-cafe-cafe-cafe-123456789012"
R1A, R1B = "11111111-1111-4111-8111-111111111111", "11111111-1111-4111-8111-111111111112"
NOBUILD = "33333333-3333-4333-8333-333333333333"
PROVISIONS = [dx.Provision("k1", "R1", "Badanläggning", (R1A, R1B)),
              dx.Provision("k2", "", "Marken får inte förses med byggnad", (NOBUILD,))]


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.folder.cleanup)
        self.dir = Path(self.folder.name)
        self.src = make_docx(self.dir / "plan.docx")

    def analyse(self, **kwargs):
        return dx.analyse(self.src, kwargs.pop("provisions", PROVISIONS), **kwargs)

    def section(self, analysis, last):
        return next(s for s in analysis.sections if s.path[-1] == last)

    def tag(self, analysis=None, name="ut.docx"):
        analysis = analysis or self.analyse()
        out = self.dir / name
        return dx.tag_docx(analysis, out, PLAN, "0.1.47"), out


class HeadingTests(unittest.TestCase):
    def test_levels_come_from_the_outline_level_or_the_style_name(self):
        levels = dx.heading_levels(STYLES)
        self.assertEqual((levels["Rubrik1"], levels["Rubrik2"], levels["Rubrik3"]), (1, 2, 3))

    def test_a_style_with_outline_level_9_is_body_text_even_if_based_on_a_heading(self):
        self.assertNotIn("Innehllsfrteckningsrubrik", dx.heading_levels(STYLES))
        self.assertNotIn("Normal", dx.heading_levels(STYLES))


class ResolveTests(unittest.TestCase):
    def resolve(self, *path, overrides=None):
        return dx.resolve(path, overrides or dx.Overrides())

    def test_headings_that_match_the_annex_exactly_ignoring_case_are_accepted(self):
        i = self.resolve("GENOMFÖRANDEFRÅGOR", "Fastighetsrättsliga frågor", "Rättigheter")
        self.assertEqual((i.tema, i.grupp, i.undergrupp, i.status),
                         ("Genomförandefrågor", "Fastighetsrättsliga frågor", "Rättigheter", dx.EXAKT))

    def test_a_close_spelling_is_matched_but_flagged(self):
        i = self.resolve("Beskrivning av detaljplanen", "Hela detaljplanen")
        self.assertEqual((i.grupp, i.status), ("Hela detaljplan", dx.NARA))
        i = self.resolve("Genomförandefrågor", "Tekniska frågor", "Utbyggnad av allmän plats")
        self.assertEqual((i.undergrupp, i.status), ("Utbyggnad allmän plats", dx.NARA))

    def test_your_own_group_or_subgroup_is_kept_and_marked_own(self):
        i = self.resolve("Beskrivning av detaljplanen", "Allmän plats", "Gator")
        self.assertEqual((i.grupp, i.undergrupp, i.status), ("Allmän plats", "Gator", dx.EGEN))

    def test_an_unknown_theme_cannot_be_tagged(self):
        i = self.resolve("HEMLIG RUBRIK", "Något")
        self.assertEqual((i.tema, i.grupp, i.status), (None, None, dx.OKANT))

    def test_a_heading_with_typed_numbering_is_matched(self):
        self.assertEqual(self.resolve("3. Konsekvenser", "2.1 Natur").tema, "Konsekvenser")

    def test_saved_choices_are_used_and_count_as_known(self):
        saved = dx.Overrides(tema={dx.path_key(("Hemlig rubrik",)): "Konsekvenser"},
                             grupp={dx.path_key(("Hemlig rubrik", "Något")): "Natur"})
        i = self.resolve("HEMLIG RUBRIK", "Något", overrides=saved)
        self.assertEqual((i.tema, i.grupp, i.status), ("Konsekvenser", "Natur", dx.SPARAD))

    def test_text_straight_under_a_theme_heading_can_get_a_group_chosen_by_hand(self):
        saved = dx.Overrides(grupp={dx.path_key(("Beskrivning av detaljplanen",)) + "|": "Hela detaljplan"})
        i = self.resolve("BESKRIVNING AV DETALJPLANEN", overrides=saved)
        self.assertEqual((i.tema, i.grupp, i.undergrupp, i.status), ("Beskrivning av detaljplanen", "Hela detaljplan", None, dx.SPARAD))

    def test_without_such_a_choice_text_under_a_theme_heading_has_no_group(self):
        i = self.resolve("BESKRIVNING AV DETALJPLANEN")
        self.assertEqual((i.tema, i.grupp), ("Beskrivning av detaljplanen", None))

    def test_a_choice_for_the_text_under_the_theme_heading_does_not_affect_the_groups_below_it(self):
        saved = dx.Overrides(grupp={dx.path_key(("Beskrivning av detaljplanen",)) + "|": "Annat"})
        self.assertEqual(self.resolve("BESKRIVNING AV DETALJPLANEN", "Genomförandetid", overrides=saved).grupp,
                         "Genomförandetid")

    def test_choices_survive_being_saved_as_text(self):
        saved = dx.Overrides(tema={"a": "b"}, grupp={"a|c": "d"}, undergrupp={"a|c|e": "f"})
        self.assertEqual(dx.Overrides.from_json(saved.to_json()), saved)
        self.assertEqual(dx.Overrides.from_json("trasig {"), dx.Overrides())


class IntroductionTextTests(Base):
    def body(self):
        return wrap(para("BESKRIVNING AV DETALJPLANEN", "Rubrik1") + para("Detta kapitel beskriver planen.")
                    + para("Genomförandetid", "Rubrik2") + para("Tio år."))

    def test_text_straight_under_a_theme_heading_is_not_tagged_until_a_group_is_chosen(self):
        src = make_docx(self.dir / "inledning.docx", self.body())
        analysis = dx.analyse(src, [])
        intro = next(s for s in analysis.sections if s.path == ("BESKRIVNING AV DETALJPLANEN",))
        self.assertTrue(intro.has_content)
        self.assertFalse(intro.taggas)

    def test_once_a_group_is_chosen_the_text_is_tagged_with_it(self):
        src = make_docx(self.dir / "inledning.docx", self.body())
        saved = dx.Overrides(grupp={dx.path_key(("Beskrivning av detaljplanen",)) + "|": "Hela detaljplan"})
        analysis = dx.analyse(src, [], saved)
        out = self.dir / "ut.docx"
        dx.tag_docx(analysis, out, PLAN, "0.1.47")
        with zipfile.ZipFile(out) as z:
            _, items = pb.parse_xml(z.read("customXml/item2.xml").decode("utf-8"))
        self.assertEqual([(i.tema, i.grupp) for i in items],
                         [("Beskrivning av detaljplanen", "Hela detaljplan"),
                          ("Beskrivning av detaljplanen", "Genomförandetid")])


class AnalysisTests(Base):
    def test_every_section_with_content_under_a_known_theme_is_tagged(self):
        analysis = self.analyse()
        tagged = [s.path[-1] for s in analysis.sections if s.taggas]
        self.assertEqual(tagged, ["Syfte", "Hela detaljplanen", "Gator", "Genomförandetid"])

    def test_a_heading_without_content_of_its_own_is_not_tagged(self):
        analysis = self.analyse()
        self.assertFalse(self.section(analysis, "DETALJPLANENS SYFTE").has_content)
        self.assertFalse(self.section(analysis, "Allmän plats").has_content)

    def test_the_table_of_contents_heading_is_not_a_section(self):
        self.assertNotIn("Innehåll", [s.path[-1] for s in self.analyse().sections])

    def test_the_motive_theme_is_not_tagged_as_a_whole_only_its_table_rows(self):
        analysis = self.analyse()
        self.assertFalse(self.section(analysis, "Användning av kvartersmark").taggas)
        self.assertEqual([m.label for m in analysis.motives], ["R1", "", "z9"])

    def test_motive_rows_are_matched_to_provisions_by_designation_or_by_text(self):
        analysis = self.analyse()
        self.assertEqual([m.key for m in analysis.motives], ["k1", "k2", None])

    def test_an_empty_table_row_is_not_a_motive(self):
        self.assertEqual(len(self.analyse().motives), 3)

    def test_an_unknown_theme_has_content_but_cannot_be_tagged(self):
        section = self.section(self.analyse(), "HEMLIG RUBRIK")
        self.assertTrue(section.has_content)
        self.assertFalse(section.taggas)
        self.assertEqual(section.status, dx.OKANT)

    def test_a_file_that_is_not_a_word_document_is_refused(self):
        bad = self.dir / "inte.docx"
        bad.write_text("text", encoding="utf-8")
        with self.assertRaises(dx.DocxError):
            dx.analyse(bad, [])
        empty = self.dir / "tomt.docx"
        with zipfile.ZipFile(empty, "w") as z:
            z.writestr("annat.txt", "x")
        with self.assertRaises(dx.DocxError):
            dx.analyse(empty, [])


TEXT_PROVISIONS = [
    dx.Provision("k1", "R1", "Badanläggning", (R1A, R1B)),
    dx.Provision("k2", "", "Marken får inte förses med byggnad", (NOBUILD,)),
    dx.Provision("k3", "m1", "Byggnaden ska utformas så att vatten kan passera", ("44444444-4444-4444-8444-444444444444",)),
]


class AnchorTests(unittest.TestCase):
    def find(self, text, provisions=TEXT_PROVISIONS):
        hit = dx._find_anchor(text, provisions)
        return (hit[0].key, hit[1]) if hit else None

    def test_a_paragraph_that_is_just_the_designation_or_the_text_points_out_the_provision(self):
        self.assertEqual(self.find("R1"), ("k1", ""))
        self.assertEqual(self.find("Badanläggning"), ("k1", ""))
        self.assertEqual(self.find("badanläggning"), ("k1", ""), "texten spelar skiftläge ingen roll")

    def test_designation_and_text_together_are_both_consumed(self):
        self.assertEqual(self.find("R1 – Badanläggning"), ("k1", ""))
        self.assertEqual(self.find("R1: Badanläggning. Syftet är bad."), ("k1", "Syftet är bad."))

    def test_the_motive_may_follow_in_the_same_paragraph(self):
        self.assertEqual(self.find("Badanläggning: Syftet är att möjliggöra bad."), ("k1", "Syftet är att möjliggöra bad."))
        self.assertEqual(self.find("m1 Byggnaden ska utformas så att vatten kan passera. Det skyddar mot översvämning."),
                         ("k3", "Det skyddar mot översvämning."))

    def test_a_word_that_only_begins_like_the_text_or_the_designation_is_not_an_anchor(self):
        provisions = [dx.Provision("p", "PARK", "Park", ("x",))]
        self.assertIsNone(self.find("Parkering ordnas inom fastigheten.", provisions))
        self.assertIsNone(self.find("Parkeringsplatser", provisions))
        self.assertIsNone(self.find("R10 gäller något annat"), "R1 är inte R10")
        self.assertIsNone(self.find("r1 är något annat"), "beteckningen är skiftlägeskänslig")

    def test_a_long_ordinary_sentence_that_happens_to_start_with_a_designation_is_not_an_anchor(self):
        sentence = "R1 är en av de bestämmelser som diskuterats mest under samrådet och vi har därför valt att beskriva " \
                   "bakgrunden utförligt här innan vi går vidare."
        self.assertGreater(len(sentence), 100)
        self.assertIsNone(self.find(sentence))

    def test_provisions_without_a_delivered_identity_are_never_matched(self):
        self.assertIsNone(self.find("R1", [dx.Provision("k", "R1", "Badanläggning", ())]))

    def test_the_longest_match_wins_when_several_provisions_could_match(self):
        provisions = [dx.Provision("a", "", "Byggnad", ("x",)), dx.Provision("b", "", "Byggnad av trä", ("y",))]
        self.assertEqual(self.find("Byggnad av trä", provisions), ("b", ""))


class RunningTextMotiveTests(Base):
    def setUp(self):
        super().setUp()
        self.src = make_docx(self.dir / "lopande.docx", running_text_body())

    def analyse(self, provisions=TEXT_PROVISIONS):
        return dx.analyse(self.src, provisions)

    def test_motives_are_found_in_headings_short_paragraphs_and_inline_text(self):
        motives = self.analyse().motives
        self.assertEqual([(m.key, m.i_lopande_text) for m in motives], [("k1", True), ("k2", True), ("k3", True)])
        self.assertEqual([m.motiv for m in motives],
                         ["Syftet är att möjliggöra bad.", "Syftet är att behålla gatan fri.\n\nOch dessutom.",
                          "Bestämmelsen syftar till att skydda mot översvämning."])

    def test_text_before_the_first_provision_and_after_the_last_heading_is_not_taken_as_a_motive(self):
        everything = " ".join(m.text for m in self.analyse().motives)
        self.assertNotIn("Här motiveras", everything)
        self.assertNotIn("Text som inte hör till", everything)

    def test_a_block_ends_at_the_next_heading_and_the_next_provision(self):
        motives = self.analyse().motives
        self.assertNotIn("Marken", motives[0].motiv)
        self.assertNotIn("Annat", " ".join(m.text for m in motives))

    def test_the_motives_feed_the_motive_tab_with_text_from_running_text_too(self):
        self.assertEqual(dx.motives_from_document(self.analyse()),
                         {"k1": "Syftet är att möjliggöra bad.",
                          "k2": "Syftet är att behålla gatan fri.\n\nOch dessutom.",
                          "k3": "Bestämmelsen syftar till att skydda mot översvämning."})

    def test_the_tagged_copy_wraps_each_block_in_a_bookmark_and_points_it_at_the_provision(self):
        analysis = self.analyse()
        out = self.dir / "ut.docx"
        result = dx.tag_docx(analysis, out, PLAN, "0.1.47")
        self.assertEqual((result.motiv, result.omatchade_motiv), (3, 0))
        with zipfile.ZipFile(out) as z:
            document = z.read("word/document.xml").decode("utf-8")
            part = z.read("customXml/item2.xml").decode("utf-8")
        ET.fromstring(document.encode("utf-8"))
        _, items = pb.parse_xml(part)
        self.assertEqual([(i.tema, i.grupp) for i in items], [(pb.MOTIV_TEMA, pb.MOTIV_GRUPP)] * 3)
        self.assertEqual([i.referenser() for i in items],
                         [[R1A, R1B], [NOBUILD], ["44444444-4444-4444-8444-444444444444"]])
        check_against_xsd(self, part)
        self.assertRegex(document, r'<w:bookmarkStart w:id="\d+" w:name="pb001"/><w:r><w:t>R1 Badanläggning')
        self.assertRegex(document, r'Och dessutom\.</w:t></w:r><w:bookmarkEnd w:id="\d+"/></w:p>')

    def test_the_document_is_otherwise_unchanged(self):
        out = self.dir / "ut.docx"
        dx.tag_docx(self.analyse(), out, PLAN, "0.1.47")
        with zipfile.ZipFile(out) as z, zipfile.ZipFile(self.src) as o:
            text = z.read("word/document.xml").decode("utf-8")
            original = o.read("word/document.xml")
        stripped = re.sub(r'<w:bookmarkStart w:id="\d+" w:name="pb\d{3}"/>|<w:bookmarkEnd w:id="\d+"/>', "", text)
        self.assertEqual(stripped.encode("utf-8"), original)

    def test_the_overview_says_where_the_motive_sits(self):
        rows = dx.overview(self.analyse())
        self.assertEqual([r.lage for r in rows][:2], ["Planbestämmelse R1 (2 ytor)",
                                                      "Planbestämmelse Marken får inte förses med byggnad"])

    def test_a_provision_already_found_in_a_table_is_not_taken_again_from_the_text(self):
        extra = para("R1 Badanläggning") + para("Text som inte ska tas.")
        body = BODY.replace("</w:tbl>\n<w:p><w:pPr><w:pStyle w:val=\"Rubrik1\"/></w:pPr><w:r><w:t>HEMLIG",
                            "</w:tbl>" + extra + "\n<w:p><w:pPr><w:pStyle w:val=\"Rubrik1\"/></w:pPr><w:r><w:t>HEMLIG")
        src = make_docx(self.dir / "bada.docx", body)
        analysis = dx.analyse(src, PROVISIONS)
        self.assertEqual(len(analysis.motives), 3)
        self.assertFalse(any(m.i_lopande_text for m in analysis.motives))

    def test_no_provision_in_the_plan_means_nothing_is_found(self):
        self.assertEqual(self.analyse(provisions=[]).motives, [])


class UncoveredTests(Base):
    def test_a_motive_section_with_text_but_no_recognised_motive_is_reported(self):
        src = make_docx(self.dir / "ingen.docx", wrap(
            para("MOTIV TILL DETALJPLANENS REGLERINGAR", "Rubrik1") + para("Motiv till regleringar", "Rubrik2")
            + para("Bestämmelserna motiveras i allmänna ordalag här, utan att peka ut någon enskild.")))
        analysis = dx.analyse(src, PROVISIONS)
        self.assertEqual([s.path[-1] for s in analysis.uncovered], ["Motiv till regleringar"])

    def test_a_motive_section_whose_motives_were_recognised_is_not_reported(self):
        self.assertEqual(self.analyse().uncovered, [])

    def test_text_under_a_heading_that_has_motives_below_it_is_not_reported_but_a_leaf_without_motives_is(self):
        src = make_docx(self.dir / "lopande.docx", running_text_body())
        analysis = dx.analyse(src, TEXT_PROVISIONS)
        self.assertEqual([s.path[-1] for s in analysis.uncovered], ["Annat"],
                         "inledningen under 'Motiv till regleringar' har motiv under sig; 'Annat' har bara annan text")

    def test_a_plan_without_a_motive_section_has_nothing_uncovered(self):
        src = make_docx(self.dir / "utan.docx", wrap(para("DETALJPLANENS SYFTE", "Rubrik1") + para("Syfte", "Rubrik2")
                                                       + para("Text.")))
        self.assertEqual(dx.analyse(src, PROVISIONS).uncovered, [])


def places_body() -> str:
    """Avsnitt om en bestämmelse (rubriken är bestämmelsens text) och ett avsnitt om något annat."""
    return wrap(
        para("BESKRIVNING AV DETALJPLANEN", "Rubrik1") + para("Kvartersmark", "Rubrik2")
        + para("Badanläggning", "Rubrik3") + para("Här byggs en badanläggning.")
        + para("Allmänt om kvartersmark", "Rubrik3") + para("Kvartersmarken ligger väster om kanalen.")
        + para("R1", "Rubrik3") + para("Samma bestämmelse igen, nu med beteckningen som rubrik."))


def textbox_body() -> str:
    """Motiv i löpande text där beteckningen är en symbolruta eller ett tabbtecken skiljer den från texten, som i riktiga planbeskrivningar."""
    return wrap(
        para("MOTIV TILL DETALJPLANENS REGLERINGAR", "Rubrik1") + para("Motiv till regleringar", "Rubrik2")
        + raw_para(label_box("PARK") + run(" Park: Användningen Park motiveras med natur."))
        + raw_para(label_box("B") + run("Bostäder: Motivet är nya bostäder."))
        + raw_para(run("plac") + run("1") + "<w:r><w:tab/></w:r>" + run("Byggnadsverk ska placeras minst 5 meter från ledningar."))
        + para("Säkerställer skyddsavstånd.")
        + raw_para(run("Marken får inte förses med byggnad.") + "<w:r><w:br/></w:r>" + run("Bestämmelsen har flera motiv.")))


TEXTBOX_PROVISIONS = [
    dx.Provision("park", "PARK", "Park", ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",)),
    dx.Provision("b", "B", "Bostäder", ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",)),
    dx.Provision("plac1", "plac1", "Byggnadsverk ska placeras minst 5 meter från ledningar.",
                 ("cccccccc-cccc-4ccc-8ccc-ccccccccccc1",)),
    dx.Provision("marken", "", "Marken får inte förses med byggnad.", ("dddddddd-dddd-4ddd-8ddd-ddddddddddd1",)),
]


class TextReadingTests(Base):
    def setUp(self):
        super().setUp()
        self.src = make_docx(self.dir / "ruta.docx", textbox_body())

    def paragraph_texts(self):
        with zipfile.ZipFile(self.src) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        lo, hi = xml.index("<w:body>") + 8, xml.rindex("</w:body>")
        return [" ".join(dx._text(xml, s, e).split()) for name, s, e in dx._spans(xml, lo, hi) if name == "w:p"]

    def test_a_text_box_is_read_once_not_twice(self):
        texts = self.paragraph_texts()
        self.assertEqual(texts[2], "PARK Park: Användningen Park motiveras med natur.", "inte PARKPARK")
        self.assertEqual(texts[3], "B Bostäder: Motivet är nya bostäder.", "inte BBostäder")

    def test_a_tab_and_a_line_break_separate_the_words_around_them(self):
        texts = self.paragraph_texts()
        self.assertEqual(texts[4], "plac1 Byggnadsverk ska placeras minst 5 meter från ledningar.")
        self.assertEqual(texts[6], "Marken får inte förses med byggnad. Bestämmelsen har flera motiv.")

    def test_pieces_of_one_word_stay_together(self):
        self.assertTrue(self.paragraph_texts()[4].startswith("plac1 "), "plac + 1 är ett ord")

    def test_motives_are_found_when_the_designation_is_a_symbol_box_or_separated_by_a_tab_or_a_break(self):
        found = {m.key: m.motiv for m in dx.analyse(self.src, TEXTBOX_PROVISIONS).motives}
        self.assertEqual(found, {
            "park": "Användningen Park motiveras med natur.",
            "b": "Motivet är nya bostäder.",
            "plac1": "Säkerställer skyddsavstånd.",
            "marken": "Bestämmelsen har flera motiv."})

    def test_the_tagged_copy_wraps_those_paragraphs_and_leaves_the_rest_of_the_document_alone(self):
        analysis = dx.analyse(self.src, TEXTBOX_PROVISIONS)
        out = self.dir / "ut.docx"
        result = dx.tag_docx(analysis, out, PLAN, "0.1.47")
        self.assertEqual(result.motiv, 4)
        with zipfile.ZipFile(out) as z, zipfile.ZipFile(self.src) as o:
            text = z.read("word/document.xml").decode("utf-8")
            original = o.read("word/document.xml")
        ET.fromstring(text.encode("utf-8"))
        stripped = re.sub(r'<w:bookmarkStart w:id="\d+" w:name="pb\d{3}"/>|<w:bookmarkEnd w:id="\d+"/>', "", text)
        self.assertEqual(stripped.encode("utf-8"), original)

    def test_a_table_cell_with_a_text_box_label_no_longer_has_a_doubled_label(self):
        cell = ("<w:tc>" + raw_para(label_box("R1")) + "</w:tc><w:tc>" + para("Badanläggning") + para("Syftet är bad.")
                + "</w:tc>")
        body = wrap(para("MOTIV TILL DETALJPLANENS REGLERINGAR", "Rubrik1") + para("Motiv till regleringar", "Rubrik2")
                    + para("Användning", "Rubrik3") + "<w:tbl><w:tr>" + cell + "</w:tr></w:tbl>")
        src = make_docx(self.dir / "tabell.docx", body)
        motives = dx.analyse(src, [dx.Provision("k1", "R1", "Badanläggning", ("e1",))]).motives
        self.assertEqual([(m.label, m.key, m.motiv) for m in motives], [("R1", "k1", "Syftet är bad.")])


class PurposeTests(Base):
    def purpose(self, body):
        src = make_docx(self.dir / "syfte.docx", body)
        return dx.purpose_from_document(dx.analyse(src, []))

    def test_the_purpose_is_the_text_under_the_purpose_heading(self):
        self.assertEqual(self.purpose(BODY), "Detaljplanen syftar till att möjliggöra en badanläggning.")

    def test_every_section_carries_its_own_body_text(self):
        src = make_docx(self.dir / "plan.docx", BODY)
        texts = {s.path[-1]: s.text for s in dx.analyse(src, []).sections}
        self.assertEqual(texts["Syfte"], "Detaljplanen syftar till att möjliggöra en badanläggning.")
        self.assertEqual(texts["Hela detaljplanen"], "Planen omfattar 5 & 6 hektar.", "runs i samma stycke slås ihop")
        self.assertEqual(texts["DETALJPLANENS SYFTE"], "", "en rubrik utan egen text")

    def test_several_paragraphs_and_subheadings_become_one_line(self):
        body = wrap(para("DETALJPLANENS SYFTE", "Rubrik1") + para("Syfte", "Rubrik2") + para("Första stycket.")
                    + para("Andra stycket.") + para("Mer", "Rubrik3") + para("Tredje."))
        self.assertEqual(self.purpose(body), "Första stycket. Andra stycket. Tredje.")

    def test_a_document_without_a_purpose_gives_nothing(self):
        self.assertEqual(self.purpose(wrap(para("KONSEKVENSER", "Rubrik1") + para("Natur", "Rubrik2") + para("Text."))), "")

    def test_text_in_another_group_is_not_taken_for_the_purpose(self):
        body = wrap(para("DETALJPLANENS SYFTE", "Rubrik1") + para("Annat", "Rubrik2") + para("Inte syftet."))
        self.assertEqual(self.purpose(body), "")

    def test_a_close_spelling_of_the_headings_is_accepted(self):
        body = wrap(para("Detaljplanens syfte", "Rubrik1") + para("SYFTE", "Rubrik2") + para("Syftet."))
        self.assertEqual(self.purpose(body), "Syftet.")


class SectionLocationTests(Base):
    def setUp(self):
        super().setUp()
        self.src = make_docx(self.dir / "platser.docx", places_body())

    def analyse(self, provisions=TEXT_PROVISIONS):
        return dx.analyse(self.src, provisions)

    def section(self, analysis, name):
        return next(s for s in analysis.sections if s.path[-1] == name)

    def test_a_heading_that_is_exactly_a_provision_is_linked_to_it_instead_of_the_whole_plan_area(self):
        analysis = self.analyse()
        self.assertEqual(self.section(analysis, "Badanläggning").lage_keys, ["k1"])
        self.assertEqual(self.section(analysis, "R1").lage_keys, ["k1"], "beteckningen duger också")

    def test_other_headings_stay_with_the_whole_plan_area(self):
        analysis = self.analyse()
        self.assertEqual(self.section(analysis, "Allmänt om kvartersmark").lage_keys, [])
        self.assertEqual(self.section(analysis, "Kvartersmark").lage_keys, [])

    def test_a_heading_that_could_mean_two_provisions_is_left_alone(self):
        twice = TEXT_PROVISIONS + [dx.Provision("k9", "", "Badanläggning", ("55555555-5555-4555-8555-555555555555",))]
        self.assertEqual(self.section(self.analyse(twice), "Badanläggning").lage_keys, [])

    def test_a_provision_the_plan_does_not_deliver_is_not_linked(self):
        silent = [dx.Provision("k1", "R1", "Badanläggning", ())]
        self.assertEqual(self.section(self.analyse(silent), "Badanläggning").lage_keys, [])

    def test_the_tagged_copy_points_a_linked_section_at_all_the_areas_of_the_provision(self):
        analysis = self.analyse()
        out = self.dir / "ut.docx"
        dx.tag_docx(analysis, out, PLAN, "0.1.47")
        with zipfile.ZipFile(out) as z:
            part = z.read("customXml/item2.xml").decode("utf-8")
        check_against_xsd(self, part)
        _, items = pb.parse_xml(part)
        by_heading = {r.rubrik.split(" › ")[-1]: i for r, i in zip(dx.overview(analysis), items)}
        linked = by_heading["Badanläggning"]
        self.assertEqual((linked.lage, linked.referenser()), (pb.PLANBESTAMMELSE, [R1A, R1B]))
        self.assertEqual(by_heading["Allmänt om kvartersmark"].lage, pb.PLANOMRADE)
        self.assertNotIn("Kvartersmark", by_heading, "rubriken utan egen text taggas inte")

    def test_the_overview_says_which_provision_a_section_is_linked_to(self):
        rows = {r.rubrik.split(" › ")[-1]: r for r in dx.overview(self.analyse())}
        self.assertEqual(rows["Badanläggning"].lage, "Planbestämmelse R1 (2 ytor)")
        self.assertEqual(rows["Allmänt om kvartersmark"].lage, "Hela planområdet")

    def test_a_choice_made_by_hand_works_the_same_way_and_can_be_undone(self):
        analysis = self.analyse()
        general = self.section(analysis, "Allmänt om kvartersmark")
        general.lage_keys = ["k1", "k2"]
        rows = {r.rubrik.split(" › ")[-1]: r for r in dx.overview(analysis)}
        self.assertEqual(rows["Allmänt om kvartersmark"].lage,
                         "Planbestämmelse R1 (2 ytor), Marken får inte förses med byggnad")
        _, out = self.dir, self.dir / "ut.docx"
        dx.tag_docx(analysis, out, PLAN, "0.1.47")
        with zipfile.ZipFile(out) as z:
            _, items = pb.parse_xml(z.read("customXml/item2.xml").decode("utf-8"))
        wanted = [i for i in items if len(i.referenser()) == 3]
        self.assertEqual(len(wanted), 1)
        general.lage_keys = []
        self.assertEqual({r.rubrik.split(" › ")[-1]: r.lage for r in dx.overview(analysis)}["Allmänt om kvartersmark"],
                         "Hela planområdet")

    def test_the_document_is_still_unchanged_apart_from_the_bookmarks(self):
        out = self.dir / "ut.docx"
        dx.tag_docx(self.analyse(), out, PLAN, "0.1.47")
        with zipfile.ZipFile(out) as z, zipfile.ZipFile(self.src) as o:
            text = z.read("word/document.xml").decode("utf-8")
            original = o.read("word/document.xml")
        stripped = re.sub(r'<w:bookmarkStart w:id="\d+" w:name="pb\d{3}"/>|<w:bookmarkEnd w:id="\d+"/>', "", text)
        self.assertEqual(stripped.encode("utf-8"), original)


def foreign_comment_docs() -> tuple[str, dict]:
    """Ett dokument där någon annan redan kommenterat (id 0), så att granskningskopians kommentarer inte får krocka med den."""
    body = BODY.replace(
        "<w:p><w:r><w:t>Detaljplanen syftar till att möjliggöra en badanläggning.</w:t></w:r></w:p>",
        '<w:p><w:commentRangeStart w:id="0"/><w:r><w:t>Detaljplanen syftar till att möjliggöra en badanläggning.</w:t></w:r>'
        '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>')
    comments = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:comments xmlns:w="' + W_URL + '">'
                '<w:comment w:id="0" w:author="Anna" w:date="2026-01-01T00:00:00Z" w:initials="A"><w:p><w:r><w:t>Kolla syftet</w:t>'
                '</w:r></w:p></w:comment></w:comments>')
    return body, {"word/comments.xml": comments}


W_URL = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class ReviewCopyTests(Base):
    MARKERS = (r'<w:bookmarkStart w:id="\d+" w:name="pb\d{3}"/>|<w:commentRangeStart w:id="\d+"/>'
               r'|<w:commentRangeEnd w:id="\d+"/>|<w:r><w:commentReference w:id="\d+"/></w:r>')

    def review(self, analysis=None, name="granskning.docx"):
        analysis = analysis or self.analyse()
        out = self.dir / name
        return dx.tag_docx(analysis, out, PLAN, "0.1.47", comments=True), out

    def parts(self, path):
        with zipfile.ZipFile(path) as z:
            return {n: z.read(n) for n in z.namelist()}

    def comments(self, path):
        root = ET.fromstring(self.parts(path)["word/comments.xml"])
        return [(c.get(f"{{{W_URL}}}id"), c.get(f"{{{W_URL}}}author"),
                 ["".join(t.text or "" for t in p.iter(f"{{{W_URL}}}t")) for p in c.findall(f"{{{W_URL}}}p")])
                for c in root.findall(f"{{{W_URL}}}comment")]

    def test_every_tag_gets_one_comment_from_the_plugin(self):
        result, out = self.review()
        found = self.comments(out)
        self.assertEqual(result.kommentarer, 6)
        self.assertEqual(len(found), 6)
        self.assertEqual({author for _, author, _ in found}, {"Rita Detaljplan"})
        self.assertEqual(len({ident for ident, _, _ in found}), 6, "unika id")

    def test_a_comment_names_the_bookmark_the_classification_and_the_location(self):
        _, out = self.review()
        found = self.comments(out)
        self.assertEqual(found[0][2], ["pb001 · Detaljplanens syfte › Syfte", "Läge: Hela planområdet"])
        self.assertEqual(found[2][2], ["pb003 · Beskrivning av detaljplanen › Allmän plats › Gator", "Läge: Hela planområdet"])
        self.assertEqual(found[4][2], ["pb005 · Motiv till detaljplanens regleringar › Motiv till reglering",
                                       "Läge: Planbestämmelse R1 (2 ytor)"])

    def test_each_comment_sits_inside_the_bookmark_of_its_tag(self):
        _, out = self.review()
        document = self.parts(out)["word/document.xml"].decode("utf-8")
        ET.fromstring(document.encode("utf-8"))
        for number in range(1, 7):
            pattern = (rf'<w:bookmarkStart w:id="(\d+)" w:name="pb{number:03d}"/><w:commentRangeStart w:id="(\d+)"/>'
                       rf'.*?<w:commentRangeEnd w:id="\2"/><w:r><w:commentReference w:id="\2"/></w:r><w:bookmarkEnd w:id="\1"/>')
            self.assertRegex(document, re.compile(pattern, re.S), f"pb{number:03d}")

    def test_the_document_is_unchanged_apart_from_the_bookmarks_and_the_comment_markers(self):
        _, out = self.review()
        text = self.parts(out)["word/document.xml"].decode("utf-8")
        for ident in re.findall(r'<w:bookmarkStart w:id="(\d+)" w:name="pb\d{3}"/>', text):
            text = text.replace(f'<w:bookmarkEnd w:id="{ident}"/>', "", 1)  # bara våra: dokumentets egna bokmärken finns kvar
        text = re.sub(self.MARKERS, "", text)
        self.assertEqual(text.encode("utf-8"), self.parts(self.src)["word/document.xml"])

    def test_the_package_registers_the_comments_part(self):
        _, out = self.review()
        parts = self.parts(out)
        self.assertIsNone(zipfile.ZipFile(out).testzip())
        self.assertIn(b'Target="comments.xml"', parts["word/_rels/document.xml.rels"])
        self.assertIn(b"relationships/comments", parts["word/_rels/document.xml.rels"])
        self.assertIn(b'PartName="/word/comments.xml"', parts["[Content_Types].xml"])
        before = self.parts(self.src)
        self.assertEqual(sorted(set(parts) - set(before)),
                         ["customXml/_rels/item2.xml.rels", "customXml/item2.xml", "customXml/itemProps2.xml", "word/comments.xml"])

    def test_the_delivery_copy_has_no_comments_at_all(self):
        out = self.dir / "leverans.docx"
        result = dx.tag_docx(self.analyse(), out, PLAN, "0.1.47")
        self.assertEqual(result.kommentarer, 0)
        self.assertNotIn("word/comments.xml", self.parts(out))
        self.assertNotIn("commentRangeStart", self.parts(out)["word/document.xml"].decode("utf-8"))

    def test_the_tagging_is_the_same_in_both_copies(self):
        _, review = self.review()
        delivery = self.dir / "leverans.docx"
        dx.tag_docx(self.analyse(), delivery, PLAN, "0.1.47")
        a, b = (pb.parse_xml(self.parts(p)["customXml/item2.xml"].decode("utf-8"))[1] for p in (review, delivery))
        self.assertEqual(a, b)

    def test_someone_elses_comments_are_kept_and_the_new_ids_do_not_collide_with_them(self):
        body, extra = foreign_comment_docs()
        src = make_docx(self.dir / "annans.docx", body, extra)
        out = self.dir / "granskning.docx"
        dx.tag_docx(dx.analyse(src, PROVISIONS), out, PLAN, "0.1.47", comments=True)
        found = self.comments(out)
        self.assertEqual(found[0], ("0", "Anna", ["Kolla syftet"]))
        ids = [ident for ident, _, _ in found]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(int(i) for i in ids), list(range(len(ids))), "nästa lediga id efter Annas")
        self.assertEqual(sum(1 for _, author, _ in found if author == "Rita Detaljplan"), 6)
        self.assertNotIn(b"Target=\"comments.xml\"", self.parts(out)["word/_rels/document.xml.rels"],
                         "finns kommentarsdelen redan läggs ingen ny relation till")

    def test_a_review_copy_that_is_tagged_again_loses_the_plugins_old_comments_but_not_other_peoples(self):
        body, extra = foreign_comment_docs()
        src = make_docx(self.dir / "annans.docx", body, extra)
        first = self.dir / "granskning1.docx"
        dx.tag_docx(dx.analyse(src, PROVISIONS), first, PLAN, "0.1.47", comments=True)
        again = dx.analyse(first, PROVISIONS)
        delivery = self.dir / "leverans.docx"
        result = dx.tag_docx(again, delivery, PLAN, "0.1.47")
        self.assertEqual(result.kommentarer, 0)
        left = self.comments(delivery)
        self.assertEqual([(i, a) for i, a, _ in left], [("0", "Anna")], "bara Annas kvar")
        document = self.parts(delivery)["word/document.xml"].decode("utf-8")
        self.assertEqual(len(re.findall(r"<w:commentReference ", document)), 1)
        second = self.dir / "granskning2.docx"
        dx.tag_docx(dx.analyse(first, PROVISIONS), second, PLAN, "0.1.47", comments=True)
        mine = [c for c in self.comments(second) if c[1] == "Rita Detaljplan"]
        self.assertEqual(len(mine), 6, "inga dubbletter")

    def test_special_characters_in_a_comment_are_escaped(self):
        odd = [dx.Provision("k1", "A&B", "Badanläggning <ny>", ("11111111-1111-4111-8111-111111111111",))]
        src = make_docx(self.dir / "tecken.docx", wrap(
            para("BESKRIVNING AV DETALJPLANEN", "Rubrik1") + para("Kvartersmark", "Rubrik2")
            + para("A&amp;B", "Rubrik3") + para("Text.")))
        out = self.dir / "granskning.docx"
        dx.tag_docx(dx.analyse(src, odd), out, PLAN, "0.1.47", comments=True)
        raw = self.parts(out)["word/comments.xml"].decode("utf-8")
        ET.fromstring(raw.encode("utf-8"))
        self.assertIn("Läge: Planbestämmelse A&amp;B", raw)

    def test_the_original_is_never_changed(self):
        before = self.src.read_bytes()
        self.review()
        self.assertEqual(self.src.read_bytes(), before)


class TaggedCopyTests(Base):
    def parts(self, path):
        with zipfile.ZipFile(path) as z:
            return {n: z.read(n) for n in z.namelist()}

    def test_only_bookmarks_and_the_xml_part_are_added_nothing_else_is_changed(self):
        result, out = self.tag()
        before, after = self.parts(self.src), self.parts(out)
        changed = sorted(n for n in before if before[n] != after[n])
        self.assertEqual(changed, ["[Content_Types].xml", "word/_rels/document.xml.rels", "word/document.xml"])
        self.assertEqual(sorted(set(after) - set(before)),
                         ["customXml/_rels/item2.xml.rels", "customXml/item2.xml", "customXml/itemProps2.xml"])
        self.assertEqual(before["customXml/item1.xml"], after["customXml/item1.xml"], "bibliografin lämnas orörd")
        self.assertEqual((result.avsnitt, result.motiv, result.omatchade_motiv), (4, 2, 1))

    def test_removing_our_bookmarks_gives_the_original_document_back_byte_for_byte(self):
        _, out = self.tag()
        text = self.parts(out)["word/document.xml"].decode("utf-8")
        stripped = re.sub(r'<w:bookmarkStart w:id="\d+" w:name="pb\d{3}"/>', "", text)
        for ident in re.findall(r'<w:bookmarkStart w:id="(\d+)" w:name="pb\d{3}"/>', text):
            stripped = stripped.replace(f'<w:bookmarkEnd w:id="{ident}"/>', "", 1)
        self.assertEqual(stripped.encode("utf-8"), self.parts(self.src)["word/document.xml"])

    def test_the_document_stays_well_formed_with_unique_bookmark_ids_that_continue_after_existing_ones(self):
        _, out = self.tag()
        text = self.parts(out)["word/document.xml"].decode("utf-8")
        ET.fromstring(text.encode("utf-8"))
        ids = [int(i) for i in re.findall(r'<w:bookmarkStart w:id="(\d+)"', text)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids)[:2], [0, 1], "Words egna bokmärken finns kvar")
        self.assertEqual(min(i for i in ids if i > 1), 2)
        self.assertEqual(len(ids), len(re.findall(r"<w:bookmarkEnd ", text)))
        self.assertIn('mc:Ignorable="w14"', text, "namnrymderna lämnas orörda")

    def test_each_section_is_wrapped_in_a_bookmark_inside_its_first_and_last_paragraph(self):
        _, out = self.tag()
        text = self.parts(out)["word/document.xml"].decode("utf-8")
        heading = re.search(r'<w:pStyle w:val="Rubrik2"/></w:pPr>(<w:bookmarkStart w:id="\d+" w:name="pb\d{3}"/>)', text)
        self.assertIsNotNone(heading, "bokmärket börjar i rubrikstycket, efter styckets egenskaper")
        self.assertRegex(text, r'Gatan är befintlig\.</w:t></w:r><w:bookmarkEnd w:id="\d+"/></w:p>')

    def test_a_motive_row_is_tagged_in_its_second_cell_with_every_identity_of_the_provision(self):
        _, out = self.tag()
        part = self.parts(out)["customXml/item2.xml"].decode("utf-8")
        header, items = pb.parse_xml(part)
        motive = [i for i in items if i.lage == pb.PLANBESTAMMELSE]
        self.assertEqual([i.referenser() for i in motive], [[R1A, R1B], [NOBUILD]])
        self.assertTrue(all((i.tema, i.grupp) == (pb.MOTIV_TEMA, pb.MOTIV_GRUPP) for i in motive))
        document = self.parts(out)["word/document.xml"].decode("utf-8")
        self.assertRegex(document, r'<w:tc><w:p><w:bookmarkStart w:id="\d+" w:name="pb\d{3}"/><w:r><w:t>Badanläggning')

    def test_the_xml_part_follows_the_schema_and_the_rules(self):
        _, out = self.tag()
        part = self.parts(out)["customXml/item2.xml"].decode("utf-8")
        check_against_xsd(self, part)
        header, items = pb.parse_xml(part)
        self.assertEqual(pb.problems(items), [])
        self.assertEqual((header.detaljplan, header.objektversion, header.programvara), (PLAN, 1, "Rita Detaljplan"))
        self.assertEqual([i.identitet for i in items], [f"pb{n:03d}" for n in range(1, 7)])

    def test_the_package_is_valid_and_registers_the_new_part(self):
        _, out = self.tag()
        after = self.parts(out)
        self.assertIsNone(zipfile.ZipFile(out).testzip())
        self.assertIn(b'Target="../customXml/item2.xml"', after["word/_rels/document.xml.rels"])
        self.assertIn(b'Id="rId6"', after["word/_rels/document.xml.rels"], "nästa lediga rId")
        self.assertIn(b'PartName="/customXml/itemProps2.xml"', after["[Content_Types].xml"])
        self.assertIn(b'Target="itemProps2.xml"', after["customXml/_rels/item2.xml.rels"])
        self.assertIn(pb.NAMESPACE.encode("utf-8"), after["customXml/itemProps2.xml"])

    def test_tagging_again_replaces_the_earlier_tags_and_raises_the_version(self):
        first, out = self.tag()
        again = dx.analyse(out, PROVISIONS)
        self.assertEqual(len(again.removed), 6)
        second, out2 = self.tag(again, "ut2.docx")
        before, after = self.parts(out), self.parts(out2)
        self.assertEqual(second.version, 2)
        self.assertNotIn("customXml/item3.xml", after, "samma XML-del skrivs över")
        self.assertEqual(len(re.findall(r'w:name="pb\d{3}"', after["word/document.xml"].decode("utf-8"))), 6)
        ident = lambda parts: pb.parse_xml(parts["customXml/item2.xml"].decode("utf-8"))[0].objektidentitet
        self.assertEqual(ident(before), ident(after))
        self.assertEqual(after["word/document.xml"], before["word/document.xml"].replace(b"", b""))

    def test_an_unmatched_motive_row_is_left_untagged_and_reported(self):
        result, out = self.tag(self.analyse(provisions=[]))
        self.assertEqual((result.motiv, result.omatchade_motiv), (0, 3))

    def test_a_choice_for_an_unknown_heading_tags_it(self):
        analysis = self.analyse()
        analysis.overrides.tema[dx.path_key(("HEMLIG RUBRIK",))] = "Konsekvenser"
        analysis.refresh()
        section = self.section(analysis, "HEMLIG RUBRIK")
        self.assertEqual(section.status, dx.SPARAD)
        self.assertFalse(section.taggas, "en rubrik utan grupp kan inte taggas")

    def test_a_motive_can_be_matched_by_hand(self):
        analysis = self.analyse()
        analysis.motives[2].key = "k1"
        result, _ = self.tag(analysis)
        self.assertEqual(result.motiv, 3)

    def test_the_motive_text_is_what_follows_the_provision_text_in_a_table_row(self):
        analysis = self.analyse()
        self.assertEqual([m.motiv for m in analysis.motives],
                         ["Syftet är att möjliggöra bad.", "Syftet är att behålla gatan fri.", "Motiv."])
        self.assertEqual([m.title for m in analysis.motives][:2],
                         ["Badanläggning", "Marken får inte förses med byggnad"])

    def test_motives_are_fetched_only_for_rows_matched_to_a_provision(self):
        self.assertEqual(dx.motives_from_document(self.analyse()),
                         {"k1": "Syftet är att möjliggöra bad.", "k2": "Syftet är att behålla gatan fri."})
        self.assertEqual(dx.motives_from_document(self.analyse(provisions=[])), {})

    def test_several_paragraphs_of_motive_are_kept_separated_by_a_blank_line(self):
        body = BODY.replace("Syftet är att behålla gatan fri.</w:t></w:r></w:p>",
                            "Syftet är att behålla gatan fri.</w:t></w:r></w:p><w:p/><w:p><w:r><w:t>Och dessutom.</w:t></w:r></w:p>")
        src = make_docx(self.dir / "flera.docx", body)
        found = dx.motives_from_document(dx.analyse(src, PROVISIONS))
        self.assertEqual(found["k2"], "Syftet är att behålla gatan fri.\n\nOch dessutom.")

    def test_a_row_with_only_the_provision_text_gives_no_motive(self):
        body = BODY.replace("<w:p><w:r><w:t>Syftet är att möjliggöra bad.</w:t></w:r></w:p>", "")
        src = make_docx(self.dir / "utan.docx", body)
        self.assertNotIn("k1", dx.motives_from_document(dx.analyse(src, PROVISIONS)))

    def test_the_overview_lists_every_tag_in_document_order_with_where_it_sits(self):
        rows = dx.overview(self.analyse())
        self.assertEqual([r.identitet for r in rows], [f"pb{n:03d}" for n in range(1, 7)])
        self.assertEqual(rows[0], dx.TagRad("pb001", "DETALJPLANENS SYFTE › Syfte", "Detaljplanens syfte", "Syfte", "",
                                            "Hela planområdet"))
        self.assertEqual(rows[2], dx.TagRad("pb003", "BESKRIVNING AV DETALJPLANEN › Allmän plats › Gator",
                                            "Beskrivning av detaljplanen", "Allmän plats", "Gator", "Hela planområdet"))
        self.assertEqual((rows[4].rubrik, rows[4].lage, rows[4].tema, rows[4].grupp),
                         ("Användning av kvartersmark › R1", "Planbestämmelse R1 (2 ytor)", pb.MOTIV_TEMA,
                          pb.MOTIV_GRUPP))
        self.assertEqual(rows[5].lage, "Planbestämmelse Marken får inte förses med byggnad")

    def test_the_overview_matches_the_bookmarks_and_the_xml_part_of_the_copy(self):
        analysis = self.analyse()
        rows = dx.overview(analysis)
        _, out = self.tag(analysis)
        with zipfile.ZipFile(out) as z:
            xml = z.read("customXml/item2.xml").decode("utf-8")
            document = z.read("word/document.xml").decode("utf-8")
        _, items = pb.parse_xml(xml)
        self.assertEqual([r.identitet for r in rows], [i.identitet for i in items])
        self.assertEqual([r.identitet for r in rows], re.findall(r'w:name="(pb\d{3})"', document))

    def test_the_overview_can_be_exported_for_excel(self):
        text = dx.overview_csv(dx.overview(self.analyse()))
        lines = text.split("\r\n")
        self.assertEqual(lines[0], "Bokmärke;Rubrik;Tema;Grupp;Undergrupp;Läge")
        self.assertEqual(lines[1], "pb001;DETALJPLANENS SYFTE › Syfte;Detaljplanens syfte;Syfte;;Hela planområdet")
        self.assertEqual(len([l for l in lines if l]), 7)

    def test_the_original_cannot_be_overwritten(self):
        with self.assertRaises(dx.DocxError):
            dx.tag_docx(self.analyse(), self.src, PLAN, "0.1.47")

    def test_tags_that_break_the_rules_are_not_written(self):
        analysis = self.analyse()
        analysis.provisions = [dx.Provision("k1", "R1", "Badanläggning", ("inte-ett-uuid",))]
        with self.assertRaises(dx.DocxError):
            self.tag(analysis)
        self.assertFalse((self.dir / "ut.docx").exists())


if __name__ == "__main__":
    unittest.main()
