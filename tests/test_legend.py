"""Teckenförklaringen: innehållet, layoutobjekten och verktyget i layoutläget (kräver QGIS)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS  # noqa: E402

if HAVE_QGIS:
    from qgis.core import (Qgis, QgsLayoutItemGroup, QgsLayoutItemLabel, QgsLayoutItemPolyline, QgsLayoutItemShape,
                           QgsLayoutPoint, QgsLayoutSize, QgsPrintLayout, QgsProject)
    from qgis.PyQt.QtCore import QObject, pyqtSignal
    from qgis.PyQt.QtWidgets import QMainWindow, QMenu, QToolBar
    from rita_detaljplan.core import legend as lg
    from rita_detaljplan.core import legend_layout as ll
    from rita_detaljplan.core import validation
    from rita_detaljplan.gui.layout_legend import LayoutLegendTool
    from rita_detaljplan.gui.legend_settings_dialog import LegendSettingsDialog
    from qgis.core import QgsSettings
    from qgis.PyQt.QtGui import QFont
    from qgis_app import get_app
    from test_export import ExportCase


def use_row(code, text, form="Kvartersmark", farg="Gul", ref=None, **extra):
    return {"tabell": "anvandning_yta", "anvandningsform": form, "beteckning": code, "bestammelseformulering": text,
            "farg": farg, "planbestammelsekatalogreferens": ref or f"use-{code}-{text}", "bestammelsevarde": None, **extra}


def prop_row(text, code=None, form="Kvartersmark", symbol=None, ref=None, table="egenskap_yta", **extra):
    return {"tabell": table, "anvandningsform": form, "beteckning": code, "bestammelseformulering": text,
            "symbol": symbol, "planbestammelsekatalogreferens": ref or f"prop-{text}", "bestammelsevarde": None, **extra}


class FakeCatalog:
    def __init__(self, categories):
        self.categories = categories

    def get(self, ref):
        category = self.categories.get(ref)
        return mock.Mock(kategori=category) if category is not None else None


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class LegendContentTests(unittest.TestCase):
    def test_digits_become_subscripts(self):
        self.assertEqual(lg.subscript("R1"), "R₁")
        self.assertEqual(lg.subscript("utfart12"), "utfart₁₂")
        self.assertEqual(lg.subscript("GATA"), "GATA")
        self.assertEqual(lg.subscript(None), "")

    def test_the_boundary_lines_follow_what_the_plan_contains(self):
        self.assertEqual([e.text for e in lg.boundary_section(True, False).entries], ["Planområdesgräns", "Användningsgräns"])
        self.assertEqual([e.text for e in lg.boundary_section(True, True).entries],
                         ["Planområdesgräns", "Användningsgräns", "Egenskapsgräns"])
        self.assertEqual([e.text for e in lg.boundary_section(True, True, True).entries],
                         ["Planområdesgräns", "Användningsgräns", "Egenskapsgräns", "Sekundär egenskapsgräns"])
        self.assertTrue(all(e.swatch == lg.LINE and e.symbol == e.text for e in lg.boundary_section(True, True, True).entries))
        self.assertTrue(all(e.swatch == lg.LINE and e.symbol == e.text for e in lg.boundary_section(True, True).entries))
        self.assertEqual(lg.boundary_section(True, False).title, "GRÄNSLINJER")

    def test_the_secondary_boundary_is_in_the_legend_only_when_a_provision_uses_it(self):
        rows = [use_row("R2", "Museum"), prop_row("Marken får inte förses med byggnad", "e1")]
        plain = [e.text for e in lg.build(rows)[0].entries]
        self.assertNotIn("Sekundär egenskapsgräns", plain)
        rows[1]["sekundarEgenskapsgrans"] = True
        with_secondary = [e.text for e in lg.build(rows)[0].entries]
        self.assertEqual(with_secondary[-1], "Sekundär egenskapsgräns")

    def test_uses_are_split_by_form_and_sorted_by_letter_and_number(self):
        rows = [use_row("R2", "Museum"), use_row("GATA", "Gata", "Allmän plats", "Ljusgrå"),
                use_row("R1", "Badanläggning"), use_row("C1", "Samlingslokal", farg="Ljusgrå"),
                use_row("VATTEN", "Vatten", "Vattenområde", "Blå")]
        sections = lg.use_sections(rows)
        self.assertEqual([s.title for s in sections], ["ANVÄNDNING AV ALLMÄN PLATS", "ANVÄNDNING AV KVARTERSMARK",
                                                     "ANVÄNDNING AV VATTENOMRÅDE"])
        kvarter = sections[1].entries
        self.assertEqual([e.code for e in kvarter], ["C₁", "R₁", "R₂"])
        self.assertEqual([e.text for e in kvarter], ["Samlingslokal", "Badanläggning", "Museum"])
        self.assertTrue(all(e.swatch == lg.FILL for e in kvarter))
        self.assertEqual(kvarter[1].color, (255, 255, 206), "färgen ur Boverkets färgnamn")
        self.assertEqual(kvarter[0].color, (233, 233, 233))

    def test_the_same_provision_on_several_areas_is_listed_once(self):
        rows = [use_row("R1", "Badanläggning", ref="x"), use_row("R1", "Badanläggning", ref="x")]
        self.assertEqual(len(lg.use_sections(rows)[0].entries), 1)

    def test_an_unknown_colour_gets_the_fallback(self):
        (section,) = lg.use_sections([use_row("X", "Något", farg="Turkos")])
        self.assertEqual(section.entries[0].color, lg.symbology.FALLBACK_FARG)

    def test_properties_are_grouped_by_form_and_category(self):
        catalog = FakeCatalog({"a": "Skydd mot störningar", "b": "Markreservat för allmännyttiga ändamål",
                               "c": "Skydd mot störningar", "d": "Utformning av allmän plats"})
        rows = [prop_row("Skyfallsstråk ska anordnas", "m6", ref="a"),
                prop_row("Markreservat för underjordiska ledningar", "u1", ref="b"),
                prop_row("Friskluftsintag ska vändas bort", "m2", ref="c"),
                prop_row("Fördröjning av dagvatten", "dagvatten1", "Allmän plats", ref="d")]
        sections = lg.property_sections(rows, catalog)
        self.assertEqual([s.title for s in sections], ["EGENSKAPSBESTÄMMELSER FÖR ALLMÄN PLATS",
                                                     "EGENSKAPSBESTÄMMELSER FÖR KVARTERSMARK"])
        groups = sections[1].groups
        self.assertEqual([g.heading for g in groups], ["Markreservat för allmännyttiga ändamål", "Skydd mot störningar"])
        self.assertEqual([e.code for e in groups[1].entries], ["m₂", "m₆"], "sorterade efter beteckning")
        self.assertTrue(all(e.swatch == lg.NONE for e in groups[1].entries))

    def test_patterns_and_lines_get_swatches_and_plain_provisions_do_not(self):
        rows = [prop_row("Marken får inte förses med byggnad.", symbol="Marken får inte förses med byggnad/byggnadsverk"),
                prop_row("Utfart får inte anordnas.", symbol="Utfart får inte finnas", table="egenskap_linje"),
                prop_row("Indelning i fastigheter är …", symbol="Fastighetsindelning"),
                prop_row("Största höjd är 4 m.", "h1")]
        (section,) = lg.property_sections(rows, None)
        kinds = {e.text: e.swatch for e in section.entries}
        self.assertEqual(kinds["Marken får inte förses med byggnad."], lg.PATTERN)
        self.assertEqual(kinds["Utfart får inte anordnas."], lg.LINE)
        self.assertEqual(kinds["Indelning i fastigheter är …"], lg.LINE)
        self.assertEqual(kinds["Största höjd är 4 m."], lg.NONE)
        self.assertEqual(section.groups[0].heading, None, "utan katalog finns inga kategorier")

    def test_property_provisions_for_the_whole_plan_area_get_their_own_section(self):
        (section,) = lg.property_sections([prop_row("Gäller hela planen", form="Planområdet")], None)
        self.assertEqual(section.title, "EGENSKAPSBESTÄMMELSER FÖR PLANOMRÅDET")

    def test_values_are_filled_into_the_text(self):
        row = prop_row("Största höjd är [höjd:decimaltal] meter.", "h1",
                       bestammelsevarde='[{"datatyp":"decimaltal","variabelvarde":"4.0","beskrivning":"höjd"}]')
        (section,) = lg.property_sections([row], None)
        self.assertEqual(section.entries[0].text, "Största höjd är 4.0 meter.")

    def test_the_implementation_time_is_written_in_years_when_it_divides_evenly(self):
        self.assertIn("5 år", lg.implementation_section({"genomforandetid": 60}).note)
        self.assertIn("30 månader", lg.implementation_section({"genomforandetid": 30}).note)
        self.assertIn("fr.o.m. laga kraft datum", lg.implementation_section({"genomforandetid": 60}).note)
        self.assertIn("fr.o.m. 2026-04-22", lg.implementation_section(
            {"genomforandetid": 60, "genomforandetidStartar": "2026-04-22"}).note)
        for missing in ({}, {"genomforandetid": None}, {"genomforandetid": 0}, {"genomforandetid": "x"}):
            self.assertIsNone(lg.implementation_section(missing))

    def test_the_whole_legend_is_in_the_expected_order(self):
        rows = [use_row("R1", "Bad"), prop_row("Text", "a1", ref="p")]
        titles = [s.title for s in lg.build(rows, None, {"genomforandetid": 60})]
        self.assertEqual(titles, ["GRÄNSLINJER", "ANVÄNDNING AV KVARTERSMARK", "EGENSKAPSBESTÄMMELSER FÖR KVARTERSMARK",
                                  "GENOMFÖRANDETID"])
        self.assertIn("Egenskapsgräns", [e.text for e in lg.build(rows)[0].entries])
        self.assertNotIn("Egenskapsgräns", [e.text for e in lg.build([use_row("R1", "Bad")])[0].entries])

    def test_a_plan_without_provisions_still_has_boundary_lines(self):
        sections = lg.build([], None, {})
        self.assertEqual([s.title for s in sections], ["GRÄNSLINJER"])


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class LayoutCase(ExportCase):
    """Teckenförklaring i en tom layout för den färdiga planen i ExportCase."""

    def setUp(self):
        super().setUp()
        self.project = QgsProject.instance()
        self.data = validation.collect(self.project)
        self.decision = self.controller.decision_values()
        self.layout = self.new_layout()

    def new_layout(self, width=841, height=594):
        layout = QgsPrintLayout(self.project)
        layout.initializeDefaults()
        layout.pageCollection().page(0).setPageSize(QgsLayoutSize(width, height, Qgis.LayoutUnit.Millimeters))
        return layout

    def legend(self, rows=None, **kwargs):
        return ll.add_legend(self.layout, self.data.rows if rows is None else rows, self.catalog, self.decision, **kwargs)

    def labels(self):
        return [i for i in self.layout.items() if isinstance(i, QgsLayoutItemLabel)]

    def texts(self):
        return [" ".join(i.text().split()) for i in self.labels()]


class LegendLayoutTests(LayoutCase):
    def test_only_the_legend_is_created_as_one_group(self):
        result = self.legend()
        self.assertIsInstance(result.group, QgsLayoutItemGroup)
        self.assertEqual(len(ll.existing_legends(self.layout)), 1)
        kinds = {type(i).__name__ for i in self.layout.items() if not isinstance(i, QgsLayoutItemGroup)}
        self.assertTrue(kinds <= {"QgsLayoutItemLabel", "QgsLayoutItemShape", "QgsLayoutItemPolyline",
                                  "QgsLayoutItemPage", "QGraphicsRectItem"}, kinds)

    def test_the_texts_are_the_legend_and_nothing_about_the_map_sheet(self):
        joined = "\n".join(self.texts())
        self.assertEqual(joined, "")
        self.legend()
        joined = "\n".join(self.texts())
        for expected in ("PLANBESTÄMMELSER", "GRÄNSLINJER", "Planområdesgräns", "ANVÄNDNING AV KVARTERSMARK"):
            self.assertIn(expected, joined)
        for unwanted in ("UPPLYSNINGAR", "Detaljplan för", "Kv Väktaren", "HANDLING"):
            self.assertNotIn(unwanted, joined)

    def test_the_implementation_time_is_the_last_thing_in_the_legend(self):
        self.legend()
        last = max(self.labels(), key=lambda i: i.sceneBoundingRect().bottom())
        self.assertIn("Genomförandetiden är", last.text())
        title = next(i for i in self.labels() if i.text() == "GENOMFÖRANDETID")
        self.assertLess(title.sceneBoundingRect().bottom(), last.sceneBoundingRect().top() + 0.01)

    def test_a_missing_implementation_time_gives_a_warning_and_no_section(self):
        self.decision = {**self.decision, "genomforandetid": None}
        result = self.legend()
        self.assertNotIn("GENOMFÖRANDETID", "\n".join(self.texts()))
        self.assertTrue(any("Genomförandetid saknas" in w for w in result.warnings), result.warnings)

    def test_the_use_codes_are_written_with_subscripts(self):
        self.legend(rows=[use_row("R1", "Badanläggning"), use_row("R2", "Museum")])
        joined = "\n".join(self.texts())
        self.assertIn("R₁", joined)
        self.assertIn("R₂", joined)

    def test_the_intro_text_can_be_left_out(self):
        self.legend()
        self.assertIn("Följande gäller", "\n".join(self.texts()))
        self.layout = self.new_layout()
        self.legend(style=ll.LegendStyle(intro=False))
        self.assertNotIn("Följande gäller", "\n".join(self.texts()))

    def test_swatches_and_lines_match_the_legend_entries(self):
        rows = [use_row("R1", "Bad"), use_row("R2", "Museum"),
                prop_row("Marken får inte förses med byggnad.", symbol="Marken får inte förses med byggnad/byggnadsverk"),
                prop_row("Utfart får inte anordnas.", symbol="Utfart får inte finnas", table="egenskap_linje")]
        self.legend(rows=rows)
        entries = [e for s in lg.build(rows) for e in s.entries]
        swatches = [e for e in entries if e.swatch in (lg.FILL, lg.PATTERN)]
        lines = [e for e in entries if e.swatch == lg.LINE]
        self.assertEqual(len([i for i in self.layout.items() if isinstance(i, QgsLayoutItemShape)]), len(swatches))
        self.assertEqual(len([i for i in self.layout.items() if isinstance(i, QgsLayoutItemPolyline)]), len(lines))

    def test_the_default_place_is_the_right_edge_of_the_first_page_inside_the_margins(self):
        box = self.legend().group.sceneBoundingRect()
        self.assertGreater(box.left(), 841 / 2)
        self.assertLessEqual(box.right(), 841.01)
        self.assertGreaterEqual(box.top(), 0)
        self.assertLessEqual(box.bottom(), 594.01)

    def test_it_fills_the_given_rectangle(self):
        box = self.legend(rect=(20.0, 30.0, 90.0, 400.0)).group.sceneBoundingRect()
        self.assertGreaterEqual(box.left(), 19.5)
        self.assertLessEqual(box.right(), 110.5)
        self.assertGreaterEqual(box.top(), 29.5)
        self.assertLessEqual(box.bottom(), 430.5)

    def test_a_second_legend_replaces_the_first_one_in_the_same_place(self):
        first = self.legend(rect=(20.0, 30.0, 90.0, 400.0)).group.sceneBoundingRect()
        self.legend()
        (group,) = ll.existing_legends(self.layout)
        box = group.sceneBoundingRect()
        self.assertAlmostEqual(box.left(), first.left(), delta=0.01)
        self.assertAlmostEqual(box.top(), first.top(), delta=0.01)
        self.assertEqual([i.text() for i in self.labels()].count("PLANBESTÄMMELSER"), 1)

    def test_a_normal_legend_stays_in_one_column_at_full_size(self):
        result = self.legend()
        self.assertEqual((result.columns, result.scale), (1, 1.0))

    def test_the_size_follows_the_paper(self):
        self.layout = self.new_layout(297, 210)
        result = self.legend()
        self.assertLess(ll.page_factor(self.layout), 0.4)
        self.assertLessEqual(result.group.sceneBoundingRect().right(), 297.01)

    def test_a_long_legend_is_shrunk_or_split_and_warns(self):
        rows = [prop_row(f"Bestämmelse nummer {i} med en ganska lång text som behöver flera rader", f"a{i}", ref=f"p{i}")
                for i in range(1, 70)]
        result = self.legend(rows=rows, rect=(600.0, 10.0, 110.0, 250.0))
        self.assertTrue(result.scale < 1.0 or result.columns == 2)
        self.assertTrue(any("Teckenförklaringen" in w for w in result.warnings), result.warnings)

    def test_a_far_too_small_area_is_refused(self):
        with self.assertRaises(ll.LegendError):
            self.legend(rect=(10.0, 10.0, 10.0, 10.0))

    def test_text_measuring_grows_with_length_and_size_and_wrapping_respects_the_width(self):
        m = ll.Measure()
        self.assertGreater(m.width("Planbestämmelser", 10), m.width("Plan", 10))
        self.assertAlmostEqual(m.width("Plan", 20), 2 * m.width("Plan", 10), delta=0.05)
        lines = m.wrap("Följande gäller inom områden med nedanstående beteckningar och mer text", 10, 50)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(m.width(line, 10) <= 50 for line in lines))
        self.assertEqual(m.wrap("", 10, 50), [""])



class FakeBar:
    def __init__(self):
        self.messages = []

    def pushMessage(self, title, text, level=None):
        self.messages.append((text, level))


class FakeDesigner:
    """Layoutdesignern: ett huvudfönster med en 'Actions'-verktygsrad och en View-meny."""

    def __init__(self, layout):
        self._layout, self._bar, self._tool_bar = layout, FakeBar(), QToolBar()
        self._window, self._menu = QMainWindow(), QMenu()

    def window(self):
        return self._window

    def viewMenu(self):
        return self._menu

    def buttons(self):
        """Åtgärderna i pluginets egna verktygsfält."""
        bar = self._window.findChild(QToolBar, "DetaljplanLayoutToolBar")
        return bar.actions() if bar is not None else []

    def layout(self):
        return self._layout

    def messageBar(self):
        return self._bar

    def actionsToolbar(self):
        return self._tool_bar


class Signals(QObject):
    opened = pyqtSignal(object)
    closing = pyqtSignal(object)


class FakeIface:
    def __init__(self, designers=()):
        self._signals = Signals()
        self.layoutDesignerOpened = self._signals.opened
        self.layoutDesignerWillBeClosed = self._signals.closing
        self.designers = list(designers)

    def openLayoutDesigners(self):
        return self.designers


class ToolSetup:
    def setUp(self):
        super().setUp()
        self.designer = FakeDesigner(self.layout)
        self.fake = FakeIface()
        self.tool = LayoutLegendTool(self.fake, self.controller, lambda: self.catalog)
        self.tool.attach()
        self.addCleanup(self.tool.detach)

class ToolTests(ToolSetup, LayoutCase):
    def test_a_designer_that_opens_gets_the_button(self):
        self.fake.layoutDesignerOpened.emit(self.designer)
        action = self.designer.buttons()[0]
        self.assertEqual(action.text(), "Teckenförklaring")
        self.assertFalse(action.icon().isNull())

    def test_designers_that_are_already_open_get_the_button_too(self):
        second = FakeDesigner(self.layout)
        tool = LayoutLegendTool(FakeIface([second]), self.controller, lambda: self.catalog)
        tool.attach()
        self.addCleanup(tool.detach)
        self.assertEqual(len(second.buttons()), 2)

    def test_the_button_is_added_once_and_removed_when_the_designer_closes(self):
        self.fake.layoutDesignerOpened.emit(self.designer)
        self.fake.layoutDesignerOpened.emit(self.designer)
        self.assertEqual(len(self.designer.buttons()), 2)
        self.fake.layoutDesignerWillBeClosed.emit(self.designer)
        self.assertEqual(self.designer.buttons(), [])

    def test_the_button_creates_the_legend(self):
        self.fake.layoutDesignerOpened.emit(self.designer)
        self.designer.buttons()[0].trigger()
        self.assertEqual(len(ll.existing_legends(self.layout)), 1)
        text, level = self.designer.messageBar().messages[-1]
        self.assertIn("Skapade teckenförklaringen", text)
        self.assertEqual(level, Qgis.MessageLevel.Success)

    def test_a_selected_item_is_the_area_the_legend_fills(self):
        frame = QgsLayoutItemShape(self.layout)
        frame.attemptMove(QgsLayoutPoint(500, 40, Qgis.LayoutUnit.Millimeters))
        frame.attemptResize(QgsLayoutSize(120, 300, Qgis.LayoutUnit.Millimeters))
        self.layout.addLayoutItem(frame)
        self.layout.setSelectedItem(frame)
        box = self.tool.generate(self.designer).group.sceneBoundingRect()
        self.assertGreaterEqual(box.left(), 499.5)
        self.assertLessEqual(box.right(), 620.5)
        self.assertGreaterEqual(box.top(), 39.5)
        self.assertLessEqual(box.bottom(), 340.5)

    def test_a_selected_legend_is_replaced_where_it_is(self):
        first = self.tool.generate(self.designer).group.sceneBoundingRect()
        self.layout.setSelectedItem(ll.existing_legends(self.layout)[0])
        self.assertIsNone(self.tool.target_rect(self.layout))
        self.tool.generate(self.designer)
        (group,) = ll.existing_legends(self.layout)
        self.assertAlmostEqual(group.sceneBoundingRect().left(), first.left(), delta=0.01)

    def test_warnings_from_the_legend_are_shown(self):
        self.controller.set_decision({**self.controller.decision_values(), "genomforandetid": None})
        self.tool.generate(self.designer)
        text, level = self.designer.messageBar().messages[-1]
        self.assertIn("Genomförandetid saknas", text)
        self.assertEqual(level, Qgis.MessageLevel.Warning)

    def test_without_a_plan_nothing_is_created(self):
        with mock.patch.object(self.controller, "plan_feature", return_value=None):
            self.assertIsNone(self.tool.generate(self.designer))
        self.assertEqual(ll.existing_legends(self.layout), [])
        self.assertEqual(self.designer.messageBar().messages[-1][1], Qgis.MessageLevel.Warning)

    def test_the_buttons_have_their_own_toolbar_that_can_be_closed(self):
        self.fake.layoutDesignerOpened.emit(self.designer)
        bar = self.designer._window.findChild(QToolBar, "DetaljplanLayoutToolBar")
        self.assertIsNotNone(bar)
        self.assertEqual(self.designer.actionsToolbar().actions(), [], "inget läggs i QGIS egen verktygsrad")
        toggle = bar.toggleViewAction()
        self.assertIn(toggle, self.designer.viewMenu().actions())
        self.assertEqual(toggle.text(), "Rita Detaljplan")
        self.assertEqual(bar.windowTitle(), "Rita Detaljplan")
        self.designer._window.show()
        self.addCleanup(self.designer._window.close)
        self.assertTrue(bar.isVisible())
        toggle.trigger()
        self.assertFalse(bar.isVisible())
        toggle.trigger()
        self.assertTrue(bar.isVisible())

    def test_a_closed_toolbar_stays_closed_next_time_a_layout_opens(self):
        self.addCleanup(lambda: QgsSettings().remove("detaljplan_ngp/layout_toolbar_visible"))
        self.fake.layoutDesignerOpened.emit(self.designer)
        self.designer._window.show()
        self.addCleanup(self.designer._window.close)
        self.designer._window.findChild(QToolBar, "DetaljplanLayoutToolBar").toggleViewAction().trigger()
        second = FakeDesigner(self.layout)
        second._window.show()
        self.addCleanup(second._window.close)
        self.fake.layoutDesignerOpened.emit(second)
        self.assertFalse(second._window.findChild(QToolBar, "DetaljplanLayoutToolBar").isVisible())

    def test_closing_the_designer_does_not_count_as_hiding_the_toolbar(self):
        self.addCleanup(lambda: QgsSettings().remove("detaljplan_ngp/layout_toolbar_visible"))
        QgsSettings().remove("detaljplan_ngp/layout_toolbar_visible")
        self.fake.layoutDesignerOpened.emit(self.designer)
        self.designer._window.show()
        self.designer._window.close()
        self.fake.layoutDesignerWillBeClosed.emit(self.designer)
        self.assertTrue(QgsSettings().value("detaljplan_ngp/layout_toolbar_visible", True, type=bool))

    def test_the_toolbar_and_menu_entry_are_removed_when_the_designer_closes(self):
        self.fake.layoutDesignerOpened.emit(self.designer)
        self.fake.layoutDesignerWillBeClosed.emit(self.designer)
        self.assertEqual(self.designer.viewMenu().actions(), [])
        self.assertEqual(self.designer.buttons(), [])

    def test_a_designer_without_a_main_window_falls_back_to_the_actions_toolbar(self):
        class Plain(FakeDesigner):
            def window(self):
                return None

        plain = Plain(self.layout)
        self.fake.layoutDesignerOpened.emit(plain)
        self.assertEqual([a.text() for a in plain.actionsToolbar().actions()],
                         ["Teckenförklaring", "Inställningar för teckenförklaring"])
        self.fake.layoutDesignerWillBeClosed.emit(plain)
        self.assertEqual(plain.actionsToolbar().actions(), [])

    def test_the_main_toolbar_has_no_plankarta_button(self):
        from rita_detaljplan.gui.plan_toolbar import PlanToolBar
        bar = PlanToolBar(self.iface, self.controller, lambda: self.catalog)
        self.addCleanup(bar.deleteLater)
        self.assertNotIn("Plankarta", [a.text() for a in bar.actions()])
        self.assertFalse(hasattr(bar, "act_plankarta"))


class StyleCase(LayoutCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.forget)
        self.forget()

    @staticmethod
    def forget():
        store = QgsSettings()
        for name in ll.LegendStyle.__dataclass_fields__:
            store.remove(ll.KEY_STYLE + name)

    def label(self, text):
        return next(i for i in self.labels() if i.text() == text)


class LegendStyleTests(StyleCase):
    def test_the_defaults_are_what_is_drawn_without_any_settings(self):
        self.assertEqual(ll.LegendStyle.load(), ll.LegendStyle())
        self.legend(rect=(10.0, 10.0, 800.0, 500.0))  # bred yta: inget krymps även om teckensnittet saknas i testmiljön
        heading = self.label("PLANBESTÄMMELSER").textFormat()
        self.assertEqual((heading.size(), heading.font().family()), (30.0, "Arial"))
        self.assertEqual(self.label("GRÄNSLINJER").textFormat().size(), 15.0)

    def test_the_settings_are_saved_and_read_back(self):
        style = ll.LegendStyle(font="Times New Roman", text_size=12.5, swatch_width=20.0, intro=False,
                               scale_with_page=False)
        style.save()
        self.assertEqual(ll.LegendStyle.load(), style)

    def test_unreadable_or_absurd_values_fall_back_to_sensible_ones(self):
        QgsSettings().setValue(ll.KEY_STYLE + "text_size", "skräp")
        QgsSettings().setValue(ll.KEY_STYLE + "swatch_height", -5)
        style = ll.LegendStyle.load()
        self.assertEqual(style.text_size, 10.0)
        self.assertGreater(style.swatch_height, 0)

    def test_font_and_sizes_are_used_in_the_layout(self):
        style = ll.LegendStyle(font="Courier New", heading_size=40.0, title_size=20.0, text_size=14.0)
        self.legend(style=style, rect=(10.0, 10.0, 800.0, 500.0))
        heading = self.label("PLANBESTÄMMELSER").textFormat()
        self.assertEqual((heading.size(), heading.font().family()), (40.0, "Courier New"))
        self.assertEqual(self.label("GRÄNSLINJER").textFormat().size(), 20.0)
        self.assertEqual(self.label("Planområdesgräns").textFormat().size(), 14.0)

    def test_a_larger_text_size_makes_the_legend_taller(self):
        small = self.legend(style=ll.LegendStyle(text_size=8.0)).height
        self.layout = self.new_layout()
        large = self.legend(style=ll.LegendStyle(text_size=14.0)).height
        self.assertGreater(large, small)

    def test_the_swatches_follow_the_chosen_size(self):
        self.legend(rows=[use_row("R1", "Bad")], style=ll.LegendStyle(swatch_width=30.0, swatch_height=9.0))
        (shape,) = [i for i in self.layout.items() if isinstance(i, QgsLayoutItemShape)]
        self.assertAlmostEqual(shape.rect().width(), 30.0, delta=0.01)
        self.assertAlmostEqual(shape.rect().height(), 9.0, delta=0.01)

    def test_the_spacing_settings_move_the_rows_apart(self):
        rows = [use_row("R1", "Bad"), use_row("R2", "Museum")]

        def step(style):
            self.layout = self.new_layout()
            self.legend(rows=rows, style=style)
            texts = sorted((i for i in self.labels() if i.text() in ("Bad", "Museum")),
                           key=lambda i: i.sceneBoundingRect().top())
            return texts[1].sceneBoundingRect().top() - texts[0].sceneBoundingRect().top()

        self.assertGreater(step(ll.LegendStyle(entry_gap=6.0)), step(ll.LegendStyle(entry_gap=1.0)) + 4.0)

    def test_the_group_and_section_gaps_add_height(self):
        rows = [prop_row("A", "a1", ref="pa"), prop_row("B", "b1", ref="pb")]
        base = self.legend(rows=rows).height
        self.layout = self.new_layout()
        self.assertGreater(self.legend(rows=rows, style=ll.LegendStyle(section_gap=12.0)).height, base + 20.0)

    def test_the_page_scaling_can_be_turned_off(self):
        self.layout = self.new_layout(297, 210)
        self.legend()
        scaled = self.label("PLANBESTÄMMELSER").textFormat().size()
        self.layout = self.new_layout(297, 210)
        self.legend(rect=(10.0, 10.0, 200.0, 5000.0), style=ll.LegendStyle(scale_with_page=False))
        fixed = self.label("PLANBESTÄMMELSER").textFormat().size()
        self.assertLess(scaled, 15.0)
        self.assertEqual(fixed, 30.0)

    def test_the_heading_fits_the_default_width_at_full_size_on_every_paper(self):
        from qgis.PyQt.QtGui import QFontMetricsF
        for width, height in ((841, 594), (594, 420), (420, 297), (297, 210)):
            self.layout = self.new_layout(width, height)
            self.legend()
            heading = self.label("PLANBESTÄMMELSER")
            size = heading.textFormat().size()
            needed = ll.Measure().width("PLANBESTÄMMELSER", size, bold=True)
            self.assertLessEqual(needed, heading.rect().width(), f"{width} mm bred sida")

    def test_a_narrow_area_shrinks_the_heading_instead_of_cutting_it(self):
        self.legend(rect=(20.0, 20.0, 60.0, 500.0))
        heading = self.label("PLANBESTÄMMELSER")
        self.assertLess(heading.textFormat().size(), 30.0)
        self.assertLessEqual(ll.Measure().width("PLANBESTÄMMELSER", heading.textFormat().size(), bold=True),
                             heading.rect().width())

    def test_a_long_title_word_is_shrunk_to_fit_the_column(self):
        self.legend(rows=[prop_row("A", "a1", ref="pa")], rect=(20.0, 20.0, 55.0, 500.0))
        for title in ("EGENSKAPSBESTÄMMELSER FÖR", "ANVÄNDNING AV"):
            for label in self.labels():
                if label.text().startswith("EGENSKAPSBESTÄMMELSER"):
                    size = label.textFormat().size()
                    self.assertLessEqual(ll.Measure().width("EGENSKAPSBESTÄMMELSER", size, bold=True),
                                         label.rect().width())

    def test_saved_settings_are_used_by_default(self):
        ll.LegendStyle(heading_size=44.0).save()
        self.legend(rect=(10.0, 10.0, 800.0, 500.0))
        self.assertEqual(self.label("PLANBESTÄMMELSER").textFormat().size(), 44.0)


class PatternSwatchTests(StyleCase):
    """Prick-, ring- och plusmark ska synas i rutan: hela markörer på flera rader, ritade som en egen SVG."""

    ROWS = [prop_row("Under mark", symbol="Marken får endast förses med byggnadsverk under mark", ref="a"),
            prop_row("Komplement", symbol="Marken får endast förses med viss typ av byggnadsverk", ref="b"),
            prop_row("Ingen byggnad", symbol="Marken får inte förses med byggnad/byggnadsverk", ref="c")]

    def pictures(self):
        import base64
        from qgis.core import QgsLayoutItemPicture
        found = []
        for item in self.layout.items():
            if isinstance(item, QgsLayoutItemPicture):
                path = item.picturePath()
                self.assertTrue(path.startswith("base64:"), path[:30])
                found.append((item, base64.b64decode(path[len("base64:"):]).decode("utf-8")))
        return sorted(found, key=lambda pair: pair[0].sceneBoundingRect().top())

    def by_kind(self):
        """(ringar, plustecken, prickar) oavsett i vilken ordning raderna hamnar."""
        svgs = [svg for _, svg in self.pictures()]
        rings = next(v for v in svgs if "<circle" in v and 'fill="none"' in v)
        pluses = next(v for v in svgs if "<path" in v)
        dots = next(v for v in svgs if "<circle" in v and 'fill="none"' not in v)
        return rings, pluses, dots

    def test_each_pattern_mark_gets_a_frame_and_a_picture_with_its_markers(self):
        self.legend(rows=self.ROWS)
        pictures = self.pictures()
        self.assertEqual(len(pictures), 3)
        shapes = [i for i in self.layout.items() if isinstance(i, QgsLayoutItemShape)]
        self.assertEqual(len(shapes), 3, "en ram per mönsterruta")
        for item, _ in pictures:
            self.assertTrue(any(abs(s.sceneBoundingRect().left() - item.sceneBoundingRect().left()) < 0.3
                                and abs(s.sceneBoundingRect().top() - item.sceneBoundingRect().top()) < 0.3
                                for s in shapes), "bilden ligger över sin ram")

    def test_the_rings_pluses_and_dots_are_all_drawn(self):
        self.legend(rows=self.ROWS)
        rings, pluses, dots = self.by_kind()
        self.assertGreaterEqual(rings.count("<circle"), 6)
        self.assertIn('fill="none"', rings)
        self.assertGreaterEqual(pluses.count("<path"), 6)
        self.assertGreaterEqual(dots.count("<circle"), 12)
        self.assertNotIn('fill="none"', dots)

    def test_the_markers_lie_completely_inside_the_swatch(self):
        import re
        self.legend(rows=self.ROWS)
        for item, svg in self.pictures():
            width, height = item.rect().width(), item.rect().height()
            for cx, cy, r in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', svg):
                cx, cy, r = float(cx), float(cy), float(r)
                self.assertGreater(cx - r, 0.0)
                self.assertLess(cx + r, width)
                self.assertGreater(cy - r, 0.0)
                self.assertLess(cy + r, height)
            for x0, y0, x1, y1 in re.findall(r'd="M([\d.]+) ([\d.]+)H([\d.]+)M[\d.]+ [\d.]+V([\d.]+)"', svg):
                self.assertGreater(float(x0), 0.0)
                self.assertLess(float(x1), width)
                self.assertGreater(float(y0), 0.0)
                self.assertLess(float(y1), height)

    def test_the_hairline_ring_gets_a_visible_line_and_the_dot_a_visible_size(self):
        import re
        self.legend(rows=self.ROWS)
        rings, _, dots = self.by_kind()
        self.assertGreaterEqual(float(re.search(r'stroke-width="([\d.]+)"', rings).group(1)), 0.12)
        self.assertGreaterEqual(float(re.search(r' r="([\d.]+)"', dots).group(1)) * 2, 0.5)

    def test_the_grid_is_centred_with_a_shifted_second_row(self):
        points = ll.marker_grid(15.0, 5.6, 3.53, 3.53, 1.76, 0.8)
        xs0 = sorted(x for x, y in points if y == min(p[1] for p in points))
        xs1 = sorted(x for x, y in points if y == max(p[1] for p in points))
        self.assertEqual(len({y for _, y in points}), 2)
        self.assertAlmostEqual(xs1[0] - xs0[0], 1.76, delta=0.01)
        self.assertAlmostEqual(min(p[1] for p in points), 5.6 - max(p[1] for p in points), delta=0.01)
        self.assertAlmostEqual(min(xs0), 15.0 - (max(xs1)), delta=0.01)

    def test_a_tall_swatch_gets_more_rows(self):
        self.legend(rows=self.ROWS, style=ll.LegendStyle(swatch_height=14.0))
        rings = self.by_kind()[0]
        import re
        self.assertGreaterEqual(len({y for y in re.findall(r'cy="([\d.]+)"', rings)}), 4)

    def test_the_pictures_are_part_of_the_legend_group_and_render_in_an_export(self):
        import tempfile
        from qgis.core import QgsLayoutExporter
        from qgis.PyQt.QtGui import QImage
        self.legend(rows=self.ROWS, rect=(20.0, 20.0, 110.0, 200.0))
        self.assertEqual(len(ll.existing_legends(self.layout)), 1)
        path = tempfile.mktemp(suffix=".png")
        self.addCleanup(lambda: __import__("os").path.exists(path) and __import__("os").remove(path))
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 200
        QgsLayoutExporter(self.layout).exportToImage(path, settings)
        image = QImage(path)
        item = self.pictures()[0][0]
        box = item.sceneBoundingRect()
        scale = 200 / 25.4
        dark = 0
        for px in range(int((box.left() + 0.6) * scale), int((box.right() - 0.6) * scale)):
            for py in range(int((box.top() + 0.6) * scale), int((box.bottom() - 0.6) * scale)):
                if image.pixelColor(px, py).red() < 128:
                    dark += 1
        self.assertGreater(dark, 20, "ringarna syns i den exporterade bilden")


class LegendSettingsDialogTests(StyleCase):
    def dialog(self, style=None):
        dialog = LegendSettingsDialog(style if style is not None else ll.LegendStyle())
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_dialog_shows_the_defaults_and_reads_them_back_unchanged(self):
        dialog = self.dialog()
        self.assertEqual(dialog.style(), ll.LegendStyle(font=dialog.font_box.currentFont().family()).clamped())
        self.assertEqual(dialog.fields["text_size"].value(), 10.0)
        self.assertTrue(dialog.intro.isChecked())

    def test_every_setting_can_be_changed_and_is_saved(self):
        dialog = self.dialog()
        dialog.font_box.setCurrentFont(QFont("Courier New"))
        for name, value in (("heading_size", 36.0), ("title_size", 18.0), ("group_size", 13.0), ("text_size", 11.0),
                            ("swatch_width", 18.0), ("swatch_height", 7.0), ("line_length", 20.0), ("text_gap", 3.0),
                            ("entry_gap", 2.0), ("group_gap", 2.5), ("section_gap", 6.0), ("column_gap", 8.0)):
            dialog.fields[name].setValue(value)
        dialog.intro.setChecked(False)
        dialog.scale_with_page.setChecked(False)
        dialog.accept()
        saved = ll.LegendStyle.load()
        self.assertEqual((saved.heading_size, saved.swatch_width, saved.group_gap, saved.column_gap, saved.intro,
                          saved.scale_with_page), (36.0, 18.0, 2.5, 8.0, False, False))
        self.assertEqual(saved.font, dialog.font_box.currentFont().family())

    def test_the_dialog_starts_from_what_was_saved(self):
        ll.LegendStyle(text_size=13.0, intro=False).save()
        dialog = LegendSettingsDialog()
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.fields["text_size"].value(), 13.0)
        self.assertFalse(dialog.intro.isChecked())

    def test_the_reset_button_restores_the_defaults(self):
        dialog = self.dialog(ll.LegendStyle(text_size=20.0, swatch_width=40.0, intro=False))
        dialog.reset.click()
        self.assertEqual(dialog.fields["text_size"].value(), 10.0)
        self.assertEqual(dialog.fields["swatch_width"].value(), 15.0)
        self.assertTrue(dialog.intro.isChecked())

    def test_the_fields_cannot_leave_the_allowed_range(self):
        dialog = self.dialog()
        dialog.fields["text_size"].setValue(9999)
        dialog.fields["swatch_height"].setValue(-3)
        style = dialog.style()
        self.assertLessEqual(style.text_size, 40.0)
        self.assertGreater(style.swatch_height, 0.0)

    def test_cancelling_saves_nothing(self):
        dialog = self.dialog()
        dialog.fields["text_size"].setValue(20.0)
        dialog.reject()
        self.assertEqual(ll.LegendStyle.load().text_size, 10.0)


class SettingsButtonTests(ToolSetup, LayoutCase):
    def test_the_designer_gets_a_settings_button_next_to_the_legend_button(self):
        self.fake.layoutDesignerOpened.emit(self.designer)
        actions = self.designer.buttons()
        self.assertEqual([a.text() for a in actions], ["Teckenförklaring", "Inställningar för teckenförklaring"])
        self.assertFalse(actions[1].icon().isNull())
        self.fake.layoutDesignerWillBeClosed.emit(self.designer)
        self.assertEqual(self.designer.buttons(), [])

    def test_saving_the_settings_rebuilds_an_existing_legend_in_place(self):
        first = self.tool.generate(self.designer).group.sceneBoundingRect()
        with mock.patch.object(self.tool, "_ask_style", return_value=True):
            with mock.patch.object(ll.LegendStyle, "load", return_value=ll.LegendStyle(heading_size=20.0)):
                self.assertTrue(self.tool.configure(self.designer))
        (group,) = ll.existing_legends(self.layout)
        self.assertAlmostEqual(group.sceneBoundingRect().left(), first.left(), delta=0.01)
        self.assertAlmostEqual(group.sceneBoundingRect().top(), first.top(), delta=0.01)
        title = next(i for i in self.layout.items() if isinstance(i, QgsLayoutItemLabel) and i.text() == "PLANBESTÄMMELSER")
        self.assertEqual(title.textFormat().size(), 20.0)

    def test_cancelling_the_settings_leaves_the_legend_alone(self):
        self.tool.generate(self.designer)
        before = len(self.layout.items())
        with mock.patch.object(self.tool, "_ask_style", return_value=False):
            self.assertFalse(self.tool.configure(self.designer))
        self.assertEqual(len(self.layout.items()), before)

    def test_without_an_existing_legend_saving_the_settings_creates_nothing(self):
        with mock.patch.object(self.tool, "_ask_style", return_value=True):
            self.assertTrue(self.tool.configure(self.designer))
        self.assertEqual(ll.existing_legends(self.layout), [])

