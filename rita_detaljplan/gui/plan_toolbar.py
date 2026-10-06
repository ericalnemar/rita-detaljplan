"""Verktygsfältet för planarbetet, längst upp i QGIS. Bara ikoner; texten finns i verktygstipsen.

    [ny plan] [öppna] | [börja rita] [avsluta] | [planens uppgifter] | [planområde] [användning] [egenskapsyta]
    [egenskapslinje] | [tilldela]

Hierarkin styr knapparna: användning kan inte ritas förrän planområdet finns, och egenskap inte förrän en
användning finns. En avstängd knapp förklarar varför i sitt verktygstips. Läget (planområdets storlek, hur stor
del som har en användning, hur många ytor som saknar bestämmelse) visas i QGIS statusrad.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from qgis.core import Qgis, QgsApplication, QgsProject, QgsTask
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapToolCapture, QgsRubberBand
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import QAction, QActionGroup, QFileDialog, QMenu, QMessageBox, QToolBar

from ..controller import HELPER_LAYER, PLAN_LAYER, Candidate, PlanController
from ..core import catalog as cat
from ..core import checkout as co
from ..core import export_ngp, kommuner, settings, validation
from ..core import ngp_client as ngp
from ..core.project import collapse_plan_group, find_plan_group, plan_groups
from .assign_dialog import AssignDialog
from .assign_tool import AssignTool
from .checkout_actions import CheckoutActions
from .bottom_toolbar import BottomToolBar
from .delivery_dialog import DeliveryDialog
from .fill_tool import FillTool
from .ngp_dialog import FILE, UPLOAD, NgpDialog, NgpRequest
from .label_tool import LabelTool
from .messages import push
from .select_tool import SelectTool
from .topology_dialog import TopologyDialog
from .validation_dialog import ValidationDialog

ICONS = Path(__file__).resolve().parent.parent / "icons"

SECONDARY_BUTTON = "egenskap_yta_sekundar"  # ritar i lagret egenskap_yta, men ytorna får sekundär egenskapsgräns
LAYER_OF = {SECONDARY_BUTTON: "egenskap_yta"}  # knapp -> lager, när de inte är samma

# (knapp (oftast lagrets tabell), ikon, verktygstips)
DRAW_BUTTONS = (
    (PLAN_LAYER, "plan.svg", "Rita planområdet (planens yttre gräns)."),
    (cat.USE_LAYER, "use.svg", "Rita användningsområden inom planområdet."),
    ("egenskap_yta", "property.svg", "Rita egenskapsområden inom användningsområdena."),
    (SECONDARY_BUTTON, "property_secondary.svg",
     "Rita sekundära egenskapsområden: avgränsas med sekundär egenskapsgräns (streck och plustecken), som får korsa "
     "vanliga egenskapsgränser, t.ex. ett markreservat som skär genom ett område där höjden regleras."),
    ("egenskap_linje", "line.svg", "Rita egenskapslinjer (utfartsförbud och stängsel) på en användningsyta."),
)
HELPER_BUTTON = (HELPER_LAYER, "helper.svg",
                 "Rita hjälplinjer (konstruktionslinjer som inte följer med till NGP).")
FILL_USE_TIP = "Fyll resten: klicka i den del av planområdet som saknar användning för att fylla den."
FILL_PROPERTY_TIP = "Fyll resten: klicka i den del av ett användningsområde som saknar egenskapsyta för att fylla den."
SELECT_TIP = ("Markera: klicka eller dra en rektangel för att markera ytor och linjer (välj yta om flera ligger "
              "på varandra vid ett klick). Ctrl-klick eller Skift-klick lägger till. Högerklick avmarkerar allt.")
LABEL_TIP = ("Text: klicka eller dra en rektangel för att markera bestämmelsernas texter, dra en markerad text för "
             "att flytta den (även utanför sin yta: en tunn ledlinje visar då vägen dit). Delete återställer till "
             "automatisk placering.")
DELIVER_TIP = ("NGP: kontrollera planen mot Lantmäteriets regler, leverera den till Lantmäteriet (kräver producentbehörighet) "
               "eller spara den som JSON-fil. Inställningarna för leveransen finns också här.")
NO_PLAN = "Öppna eller skapa en detaljplan först."
NEEDS_EDITING = "Börja rita planbestämmelser (pennan) först: verktyget kräver en pågående redigeringssession."
DESELECT_TIP = "Avmarkera alla: ta bort markeringen av alla planytor och linjer."
START_TIP = "Börja rita planbestämmelser: alla planlager öppnas för redigering."
STOP_TIP = "Avsluta redigeringen och spara (eller kasta) ändringarna."
ASSIGN_TIP = "Planbestämmelser: klicka på en yta för att tilldela den en eller flera bestämmelser."
NEW_TIP = "Ny detaljplan…"
OPEN_TIP = "Öppna detaljplan (GeoPackage)…"
TOPOLOGY_TIP = ("Topologikontroll: föreslår att brytpunkter i användnings- och egenskapsytor flyttas till planområdets "
                "eller varandras brytpunkter, stänger små glapp mellan gränser, och visar om hela planområdet har "
                "en användning, om någon redan ritad yta saknar bestämmelse och om kvartersmark saknar "
                "egenskapsområden. Görs på den sparade planen.")
TOPOLOGY_EDITING_TIP = "Topologikontrollen kan inte användas medan redigeringen pågår: avsluta och spara först."
CHECKOUT_TIP = ("Checka ut: lås planen i databasen och redigera en lokal kopia (snabbare). En plan som öppnats från "
                "databasen är skrivskyddad tills den checkats ut.")
CHECKIN_TIP = "Checka in: skriv planen tillbaka till databasen, släpp låset och ta bort den lokala kopian (eller kasta den)."
INFO_TIP = ("Planens uppgifter: kommun, namn, syfte, status, beslut och handlingar, och vad som återstår före "
            "leverans.")
PLANBESKRIVNING_TIP = ("Tagga planbeskrivning: öppnar programmet för att tagga planbeskrivningar med den här planen. Det taggar "
                       "planbeskrivningen (Word) enligt BFS 2020:8, kopplar motiven till planens bestämmelser och kan lägga "
                       "syfte och motiv på planen.")


def icon(name: str) -> QIcon:
    return QIcon(str(ICONS / name))


class PlanToolBar(QToolBar):
    def __init__(self, iface, controller: PlanController, catalog_provider: Callable[[], cat.Catalog],
                 on_new: Optional[Callable[[], None]] = None, on_open: Optional[Callable[[], None]] = None,
                 on_info: Optional[Callable[[], None]] = None, parent=None,
                 on_settings: Optional[Callable[[], None]] = None):
        super().__init__("Rita Detaljplan", parent)
        self.setObjectName("DetaljplanToolBar")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        # QGIS egen ikonstorlek (Inställningar → Alternativ → Allmänt): inte ett fast värde, annars stämmer den
        # inte när användaren har ställt in en annan storlek än standard.
        self.setIconSize(iface.iconSize())
        self.iface = iface
        self._on_settings = on_settings
        self.controller = controller
        self.catalog_provider = catalog_provider
        self.status_text = ""
        self._issue_band = QgsRubberBand(iface.mapCanvas(), Qgis.GeometryType.Polygon)  # "Visa i kartan" för en avvikelse
        self._issue_band.setColor(QColor(179, 38, 30, 90))
        self._issue_band.setStrokeColor(QColor(179, 38, 30))
        self._issue_band.setWidth(2)

        # ny plan och öppna finns alltid tillgängliga; resten hör till en öppen plan
        self.act_new = QAction(icon("new.svg"), NEW_TIP, self)
        self.act_new.setToolTip(NEW_TIP)
        self.act_open = QAction(icon("open.svg"), OPEN_TIP, self)
        self.act_open.setToolTip(OPEN_TIP)
        self.addAction(self.act_new)
        self.addAction(self.act_open)
        self.act_checkout = QAction(icon("checkout.svg"), "Checka ut", self)
        self.act_checkout.setToolTip(CHECKOUT_TIP)
        self.addAction(self.act_checkout)
        self.checkout = CheckoutActions(controller, self._report, self, after=self.refresh)
        self.addSeparator()

        self.act_start = QAction(icon("start.svg"), "Börja rita planbestämmelser", self)
        self.act_stop = QAction(icon("stop.svg"), "Avsluta redigering", self)
        self.act_start.setToolTip(START_TIP)
        self.act_stop.setToolTip(STOP_TIP)
        self.addAction(self.act_start)
        self.addAction(self.act_stop)
        self.act_info = QAction(icon("info.svg"), "Planens uppgifter", self)
        self.act_info.setToolTip(INFO_TIP)
        self.addAction(self.act_info)
        self.act_topology = QAction(icon("topology.svg"), "Topologikontroll", self)
        self.act_topology.setToolTip(TOPOLOGY_TIP)
        self.addAction(self.act_topology)
        self.act_deliver = QAction(icon("deliver.svg"), "Leverera till NGP", self)
        self.act_deliver.setToolTip(DELIVER_TIP)
        self.addAction(self.act_deliver)
        self.act_planbeskrivning = QAction(icon("planbeskrivning.svg"), "Tagga planbeskrivning", self)
        self.act_planbeskrivning.setToolTip(PLANBESKRIVNING_TIP)
        self.addAction(self.act_planbeskrivning)
        self.planbeskrivning_window = None  # programmets fönster, om det är öppet
        self._tasks: list = []
        self.addSeparator()
        # markera/avmarkera alla/text: egna verktyg (inte QGIS egna). Samma knappar läggs till både här och i det
        # andra verktygsfältet (se bottom_toolbar-uppsättningen längre ned) – en QAction kan sitta i flera
        # verktygsfält samtidigt, de visar bara samma ikryssade/aktiva läge oavsett vilken av dem man klickar på.
        self.act_select = QAction(icon("select.svg"), "Markera", self)
        self.act_select.setCheckable(True)
        self.act_select.setToolTip(SELECT_TIP)
        self.act_deselect = QAction(icon("deselect.svg"), "Avmarkera alla", self)
        self.act_deselect.setToolTip(DESELECT_TIP)
        self.act_label = QAction(icon("text.svg"), "Text", self)
        self.act_label.setCheckable(True)
        self.act_label.setToolTip(LABEL_TIP)
        self.addAction(self.act_select)
        self.addAction(self.act_deselect)
        self.addAction(self.act_label)
        self.addSeparator()

        self.draw_group = QActionGroup(self)
        self.draw_group.setExclusive(False)
        self.draw_actions: dict[str, QAction] = {}

        def add_draw_button(table: str, icon_name: str, tip: str):
            action = QAction(icon(icon_name), tip, self)
            action.setCheckable(True)
            action.setToolTip(tip)
            action.setData(tip)
            self.draw_group.addAction(action)
            self.addAction(action)
            self.draw_actions[table] = action

        for button in DRAW_BUTTONS:
            add_draw_button(*button)
        self.addSeparator()

        # fyll användning/egenskap: egna verktyg (inte QGIS egna). Samma knappar läggs till både här och i det
        # andra verktygsfältet (se bottom_toolbar-uppsättningen längre ned), som markera/avmarkera/text ovan.
        self.act_fill_use = QAction(icon("fill_use.svg"), FILL_USE_TIP, self)
        self.act_fill_use.setCheckable(True)
        self.act_fill_use.setToolTip(FILL_USE_TIP)
        self.act_fill_property = QAction(icon("fill_property.svg"), FILL_PROPERTY_TIP, self)
        self.act_fill_property.setCheckable(True)
        self.act_fill_property.setToolTip(FILL_PROPERTY_TIP)
        self.addAction(self.act_fill_use)
        self.addAction(self.act_fill_property)
        add_draw_button(*HELPER_BUTTON)
        self.addSeparator()

        self.act_assign = QAction(icon("assign.svg"), "Planbestämmelser", self)
        self.act_assign.setCheckable(True)
        self.act_assign.setToolTip(ASSIGN_TIP)
        self.addAction(self.act_assign)

        self.assign_tool = AssignTool(iface.mapCanvas(), controller, self.open_assign_dialog, self._report,
                                      on_done=self._deactivate_assign)
        self.fill_tool = FillTool(iface.mapCanvas(), controller, controller.fill_property, self._report,
                                  on_done=self._deactivate_fill)
        self.fill_use_tool = FillTool(iface.mapCanvas(), controller, controller.fill_use_at, self._report,
                                      on_done=self._deactivate_fill_use)
        self.label_tool = LabelTool(iface.mapCanvas(), controller, self._report)
        self.select_tool = SelectTool(iface.mapCanvas(), controller, self.choose_candidate, self._report,
                                      self._after_select)

        self.act_checkout.triggered.connect(lambda _checked=False: self.toggle_checkout())
        for action, callback in ((self.act_new, on_new), (self.act_open, on_open), (self.act_info, on_info)):
            if callback is not None:
                action.triggered.connect(lambda _checked=False, cb=callback: cb())
        self.act_start.triggered.connect(self.start)
        self.act_stop.triggered.connect(self.stop)
        for table, action in self.draw_actions.items():
            action.triggered.connect(lambda checked, t=table: self.draw(t, checked))
        self.draw_actions[SECONDARY_BUTTON].toggled.connect(
            lambda on: setattr(self.controller, "secondary_mode", bool(on)))  # nya egenskapsytor blir sekundära
        self.act_assign.triggered.connect(self.toggle_assign)
        self.act_fill_use.triggered.connect(self.toggle_fill_use)
        self.act_select.triggered.connect(self.toggle_select)
        self.act_deselect.triggered.connect(lambda _checked=False: self.controller.clear_selection())
        self.act_topology.triggered.connect(lambda _checked=False: self.check_topology())
        self.act_deliver.triggered.connect(lambda _checked=False: self.deliver())
        self.act_planbeskrivning.triggered.connect(lambda _checked=False: self.open_planbeskrivning())
        self.act_label.triggered.connect(self.toggle_label)
        self.act_fill_property.triggered.connect(self.toggle_fill_property)
        self.controller.changed.connect(self.refresh)
        QgsProject.instance().layersAdded.connect(self.refresh)  # metod, inte lambda: kopplas bort när verktygsfältet tas bort
        iface.mapCanvas().mapToolSet.connect(self._on_tool_set)

        # parallell/vinkelrätt: exakt samma QAction som knapparna i QGIS egen CAD-panel (Avancerad digitalisering)
        # redan använder – inte en egen ombyggnad. De är växlingsknappar för ett CAD-läge (kräver att snappning är
        # på): aktiverar man läget och för muspekaren över en befintlig linje under ritning låser QGIS själv vinkeln
        # mot den. Vår knapp och panelens egen knapp pekar på samma ``QAction``, så de visar alltid samma
        # ikryssade/aktiva läge, oavsett vilken av dem man klickar på.
        self.act_parallel = self._cad_action("mParallelAction")
        self.act_perpendicular = self._cad_action("mPerpendicularAction")

        # dynamiska rutor (som i AutoCAD): CAD-panelens egen "Floater" visar längd/vinkel som flytande, redigerbara
        # rutor vid muspekaren under ritning (Tab växlar mellan dem, och man skriver rakt in i dem). Ingen egen
        # knapp för den – den ska bara vara på som standard – så den slås på direkt (se _enable_floater).
        self._enable_floater()

        # spårning: exakt samma QAction som knappen i QGIS eget snappningsverktygsfält (en del av huvudfönstret,
        # inte CAD-panelen) – hittad genom att fråga användaren köra `iface.mainWindow().findChildren(QAction)`
        # i QGIS egen Python-konsol, eftersom snappningsverktygsfältet (till skillnad från CAD-panelen) inte går
        # att bygga upp fristående för att undersöka.
        self.act_trace = self._main_window_action("EnableTracingAction")

        # dela objekt/lägg till hål: QGIS egna verktyg (inte ombyggda), precis som flytta/kopiera ovan.
        self.act_split = self.iface.actionSplitFeatures()
        self.act_add_ring = self.iface.actionAddRing()

        # trimma/förläng objekt, slå ihop valda objekt: som spårning, knappar i huvudfönstret (inte CAD-panelen) –
        # hittade genom att fråga användaren köra `iface.mainWindow().findChildren(QAction)` i QGIS egen
        # Python-konsol.
        self.act_trim = self._main_window_action("mActionTrimExtendFeature")
        self.act_merge = self._main_window_action("mActionMergeFeatures")

        # brytpunkter: QGIS eget verktyg för att lägga till/flytta/ta bort brytpunkter, riktat mot det aktiva
        # lagret (samma sorts aktivt-lager-semantik som våra andra verktyg redan bygger på, se _prepare_draw/
        # _after_select) i stället för "alla lager"-varianten.
        self.act_vertex = self.iface.actionVertexToolActiveLayer()

        # en flytande verktygsrad ovanpå kartduken (inte ett dockat fönster) – se bottom_toolbar.py. Den är barn
        # till kartduken, inte till verktygsfältet (den ska ju synas även om verktygsfältet döljs), så den städas
        # inte bort automatiskt av `toolbar.deleteLater()`: koppla städningen till att verktygsfältet förstörs,
        # så den sker överallt (pluginet, tester) utan att varje anropare behöver komma ihåg det – en kvarglömd
        # rad med sitt event-filter kvar på kartduken orsakade krascher längre fram i testsviten (se
        # qgis-plugin-test-pitfalls). Dold som standard: visas bara när en geometri är vald att rita, se refresh.
        self.bottom_toolbar = BottomToolBar(iface.mapCanvas(), iface.iconSize())
        self.bottom_toolbar.add_action(self.act_select)
        self.bottom_toolbar.add_action(self.act_deselect)
        self.bottom_toolbar.add_action(self.act_label)
        self.bottom_toolbar.add_action(self.act_fill_use)
        self.bottom_toolbar.add_action(self.act_fill_property)
        self.bottom_toolbar.add_action(self.act_split)
        self.bottom_toolbar.add_action(self.act_add_ring)
        if self.act_merge is not None:
            self.bottom_toolbar.add_action(self.act_merge)
        if self.act_vertex is not None:
            self.bottom_toolbar.add_action(self.act_vertex)
        if self.act_trim is not None:
            self.bottom_toolbar.add_action(self.act_trim)
        if self.act_trace is not None:
            self.bottom_toolbar.add_action(self.act_trace)
        if self.act_perpendicular is not None:
            self.bottom_toolbar.add_action(self.act_perpendicular)
        if self.act_parallel is not None:
            self.bottom_toolbar.add_action(self.act_parallel)

        canvas_for_cleanup, bottom_toolbar_for_cleanup = iface.mapCanvas(), self.bottom_toolbar

        def _cleanup_bottom_toolbar():
            canvas_for_cleanup.removeEventFilter(bottom_toolbar_for_cleanup)
            # sip.delete (inte deleteLater): den här slotten körs redan som svar på att verktygsfältet förstörs,
            # och en till fördröjd radering här skulle kräva ännu ett varv av händelseloopen för att verkligen ta
            # bort den – vilket QGIS testmiljöns manuella processEvents()-anrop inte alltid ger.
            sip.delete(bottom_toolbar_for_cleanup)

        self.destroyed.connect(_cleanup_bottom_toolbar)

        self.refresh()

    # -- meddelanden ------------------------------------------------------------------
    def _report(self, text: str, warning: bool = False):
        push(self.iface.messageBar(), "Rita Detaljplan", text,
             Qgis.MessageLevel.Warning if warning else Qgis.MessageLevel.Info)

    # -- uppdatera läget --------------------------------------------------------------
    def has_plan(self) -> bool:
        return self.controller.layer(PLAN_LAYER) is not None

    def refresh(self, *_):
        # QGIS egen ikonstorlek läses om varje gång (inte bara vid start): ``iface.iconSize()`` kunde ge ett för
        # litet värde när verktygsfältet byggs i ``initGui()`` (innan QGIS huvudfönster hunnit tillämpa den
        # sparade inställningen på riktigt, t.ex. direkt efter en omstart av QGIS) – ett engångsvärde vid start
        # räckte då inte. Billigt att göra om (Qt gör ingenting om storleken redan stämmer).
        size = self.iface.iconSize()
        self.setIconSize(size)
        self.bottom_toolbar.setIconSize(size)
        has_plan = self.has_plan()
        where = co.state(self.controller.project) if has_plan else co.FILE
        if where == co.DATABASE:
            co.enforce_read_only(self.controller.project)
        self.act_checkout.setVisible(where != co.FILE)
        checked_out = where == co.LOCAL
        self.act_checkout.setText("Checka in" if checked_out else "Checka ut")
        self.act_checkout.setIcon(icon("checkin.svg" if checked_out else "checkout.svg"))
        self.act_checkout.setToolTip(CHECKIN_TIP if checked_out else CHECKOUT_TIP)
        editing = has_plan and self.controller.editing
        if editing:
            # körs om varje gång (inte bara vid start/verktygsbyte, se _on_tool_set): samma sorts omstarts-race
            # som ikonstorleken (se ovan) visade sig gälla CAD-aktiveringen också – enstaka triggerpunkter räckte
            # inte alltid efter en full omstart av QGIS. Billigt och ofarligt att göra om (no-op om redan på).
            self._enable_snapping()
            self._enable_cad()
        self.act_info.setEnabled(has_plan and self.controller.summary().has_plan)
        self.act_info.setToolTip(INFO_TIP if self.act_info.isEnabled() else
                                 (NO_PLAN if not has_plan else "Rita planområdet först."))
        topology_ok = has_plan and self.controller.summary().has_plan and not editing
        self.act_topology.setEnabled(topology_ok)
        self.act_topology.setToolTip(TOPOLOGY_TIP if topology_ok else
                                     (NO_PLAN if not has_plan else "Rita planområdet först."
                                      if not self.controller.summary().has_plan else TOPOLOGY_EDITING_TIP))

        for action, tip in ((self.act_deliver, DELIVER_TIP), (self.act_planbeskrivning, PLANBESKRIVNING_TIP)):
            action.setEnabled(has_plan and self.controller.summary().has_plan)
            action.setToolTip(tip if action.isEnabled() else (NO_PLAN if not has_plan else "Rita planområdet först."))
        for action, tip in ((self.act_select, SELECT_TIP), (self.act_label, LABEL_TIP),
                           (self.act_deselect, DESELECT_TIP)):  # markeringsverktygen
            usable = has_plan and editing
            action.setEnabled(usable)
            action.setToolTip(tip if usable else (NO_PLAN if not has_plan else NEEDS_EDITING))
            if not usable and action.isChecked():
                action.setChecked(False)
                self._unset_assign_tool()

        self.act_start.setEnabled(has_plan and not editing)
        self.act_stop.setEnabled(editing)
        for table, action in self.draw_actions.items():
            ok, reason = self.controller.can_draw(LAYER_OF.get(table, table)) if has_plan else (False, NO_PLAN)
            action.setEnabled(ok)
            action.setToolTip(action.data() if ok else reason)
            if not ok and action.isChecked():
                # blir otillgänglig medan den är aktiv (t.ex. hierarkin ändras mitt i en pågående ritning): stäng
                # av knappen OCH avsluta det riktiga ritverktyget, annars fortsätter QGIS fånga klick i kartan.
                action.setChecked(False)
                self.iface.actionPan().trigger()

        # act_parallel/act_perpendicular/act_trace/act_floater är QGIS egna, delade knappar (se
        # _cad_action/_main_window_action):
        # deras aktiverade läge styrs av QGIS själv, inte av vår redigeringssession – vi ska inte stänga av dem åt QGIS.

        for action, table, tip in ((self.act_fill_use, "anvandning_yta", FILL_USE_TIP),
                                   (self.act_fill_property, "egenskap_yta", FILL_PROPERTY_TIP)):
            ok, reason = self.controller.can_draw(table) if has_plan else (False, NO_PLAN)
            action.setEnabled(ok)
            action.setToolTip(tip if ok else reason)
            if not ok and action.isChecked():
                action.setChecked(False)
                self._unset_assign_tool()

        if not has_plan:
            assign_ok, assign_reason = False, NO_PLAN
        elif not editing:
            assign_ok, assign_reason = False, "Börja rita planbestämmelser först."
        elif not self.controller.summary().has_use:
            assign_ok, assign_reason = False, "Rita planområdet och användningsytor först."
        else:
            assign_ok, assign_reason = True, ASSIGN_TIP
        self.act_assign.setEnabled(assign_ok)
        self.act_assign.setToolTip(assign_reason)
        if not assign_ok and self.act_assign.isChecked():
            self.act_assign.setChecked(False)
            self._unset_assign_tool()
        self._show_status(self._status_text() if has_plan else "")
        self._update_bottom_toolbar_visibility()

    def _update_bottom_toolbar_visibility(self, *_):
        """Den flytande verktygsraden ska synas hela tiden under en redigeringssession – annars är den bara i
        vägen. Anropas i slutet av ``refresh`` (som i sin tur körs varje gång redigeringen startas/avslutas, se
        ``controller.start_editing``/``stop_editing``)."""
        self.bottom_toolbar.setVisible(self.controller.editing)

    def _show_status(self, text: str):
        if text != self.status_text:
            self.status_text = text
            bar = self.iface.statusBarIface()
            if bar is not None:
                bar.showMessage(text, 0)

    def _status_text(self) -> str:
        state = self.controller.summary()
        parts = []
        if len(plan_groups(self.controller.project)) > 1:  # annars onödigt brus: det vanliga är bara en plan
            parts.append(f"Plan: {self._active_plan_name()}")
        if not state.has_plan:
            parts.append("Planområde saknas")
            return "  ·  ".join(parts)
        parts.append(f"Planområde {state.plan_area:,.0f} m²".replace(",", " "))
        parts.append("Användning: " + (f"{state.coverage:.0%} av planområdet" if state.has_use else "saknas"))
        if state.unassigned:
            parts.append(f"{state.unassigned} saknar bestämmelse")
        return "  ·  ".join(parts)

    def _active_plan_name(self) -> str:
        """Den aktiva planens namn – flera planer kan vara laddade samtidigt (se core.project.plan_groups), så
        dialoger som jobbar mot "planen" (planens uppgifter, topologikontroll, NGP-leverans) visar den i sin
        fönstertitel för att det ska gå att se vilken plan man faktiskt jobbar med."""
        group = find_plan_group(self.controller.project)
        return group.name() if group is not None else "ingen plan"

    def _titled(self, dialog):
        """Lägger den aktiva planens namn sist i en dialogs fönstertitel (se ``_active_plan_name``), men bara om
        fler än en plan är laddad – annars är det underförstått vilken plan det gäller."""
        if len(plan_groups(self.controller.project)) > 1:
            dialog.setWindowTitle(f"{dialog.windowTitle()} – {self._active_plan_name()}")
        return dialog

    # -- kommandon --------------------------------------------------------------------
    def toggle_checkout(self):
        """Databasplan: checkar ut planen för redigering, eller (om den redan är utcheckad) checkar in den."""
        if co.state(self.controller.project) == co.LOCAL:
            return self.checkout.check_in()
        return self.checkout.check_out()

    def start(self):
        if not self._choose_plan_to_edit():
            return
        if co.state(self.controller.project) == co.DATABASE and not self.checkout.check_out():
            return  # en plan i en databas redigeras bara i en utcheckad lokal kopia
        if not self.controller.start_editing():
            self._report("Kunde inte öppna alla planlager för redigering.", True)
            return
        self._enable_snapping()
        self._enable_cad()

    def _choose_plan_to_edit(self) -> bool:
        """Är flera planer laddade samtidigt (se ``core.project.plan_groups``) frågar den här vilken som ska bli
        aktiv och alltså redigeras – annars (bara en, eller ingen alls) finns inget att välja. Returnerar False om
        användaren avbryter menyn."""
        groups = plan_groups(self.controller.project)
        if len(groups) <= 1:
            return True
        return self._pick_plan_group(groups) is not None

    def switch_plan(self):
        """Fristående kommando (menyn Rita Detaljplan → Byt aktiv plan…) för att byta aktiv plan utan att starta
        en redigeringssession – t.ex. för att kontrollera eller leverera en annan laddad plan än den man senast
        redigerade. Till skillnad från pennans väljare (``_choose_plan_to_edit``) säger den till om det inte
        finns något att välja, i stället för att bara tyst göra ingenting."""
        groups = plan_groups(self.controller.project)
        if len(groups) <= 1:
            self._report("Ingen plan är laddad." if not groups else "Bara en plan är laddad: inget att byta till.",
                        False)
            return
        chosen = self._pick_plan_group(groups)
        if chosen is not None:
            self._report(f"Bytte aktiv plan till {chosen.name()}.", False)

    def _pick_plan_group(self, groups):
        """Visar en meny med planernas namn och byter till den valda (se ``core.project.activate_plan_group``).
        Returnerar den valda gruppen, eller None om menyn avbröts."""
        menu = QMenu(self)
        actions = {menu.addAction(group.name()): group for group in groups}
        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return None
        group = actions[chosen]
        self.controller.activate_plan(group)
        self.refresh()
        return group

    def _enable_snapping(self):
        """Slår på QGIS egen snappning när redigeringen startar: Parallell/Vinkelrätt/Spårning kräver den för att
        fungera alls ("Snapping must be enabled...", se deras egna verktygstips), men ingen egen knapp för
        snappning behövs i vår panel – den ska bara vara på. Snappning mot korsningar (där två ritade linjer
        korsar utan att dela en nod, t.ex. en egenskapsgräns över en användningsgräns) slås på av samma skäl:
        annars missar man lätt att de möts exakt."""
        project = QgsProject.instance()
        config = project.snappingConfig()
        changed = False
        if not config.enabled():
            config.setEnabled(True)
            changed = True
        if not config.intersectionSnapping():
            config.setIntersectionSnapping(True)
            changed = True
        if changed:
            project.setSnappingConfig(config)

    def _enable_cad(self):
        """Slår på Avancerad digitalisering (CAD-panelen) när redigeringen startar – annars är den avstängd som
        standard och Parallell/Vinkelrätt/Floater fungerar inte förrän man råkar öppna panelen själv.

        Använder den riktiga på/av-knappen (``mEnableAction``, samma som "Enable advanced digitizing tools" i
        panelen) i stället för att bara kalla den underliggande Python-metoden ``dock.enable()`` – precis som med
        Floater visade det sig att bara ``.trigger()`` på den riktiga knappen faktiskt får det att fästa (så länge
        inget ritverktyg är aktivt ännu vet inte ``enable()`` ensam om att verkligen slå på låsningarna). Panelen
        (sidopanelen) döljs INTE här (se docstring-historik i git): ett tidigare försök att skjuta upp ett
        ``dock.hide()`` visade sig ibland hindra att aktiveringen fäster.

        Själva triggningen (``_enable_cad_now``) skjuts upp till nästa varv av händelseloopen
        (``QTimer.singleShot(0, ...)``): anropad direkt synkront, t.ex. från ``_on_tool_set`` när ett nytt
        ritverktyg just blivit aktivt, kunde ``enable_action.trigger()`` köras utan att ``isChecked()`` faktiskt
        ändrades (QGIS hann inte bli klar med sin egen aktivering av det nya ritverktyget än) – bekräftat med
        loggning efter en full omstart av QGIS och datorn, där detta annars kunde göra att Avancerad
        digitalisering aldrig slogs på alls. Samma sorts race som ``dock.hide()`` hade."""
        QTimer.singleShot(0, self._enable_cad_now)

    def _enable_cad_now(self):
        dock = self.iface.cadDockWidget()
        if dock is None:
            return
        enable_action = dock.findChild(QAction, "mEnableAction")
        if enable_action is not None and not enable_action.isChecked():
            enable_action.trigger()
        else:
            dock.enable()

    def _ask_save(self) -> "QMessageBox.StandardButton":
        """Frågan när redigeringen avslutas. Vad som återstår före leverans visas inte här: det står i Planens
        uppgifter och i kontrollen mot NGP."""
        box = QMessageBox(self)
        box.setWindowTitle("Avsluta redigering")
        box.setText("Vill du spara ändringarna i planen?")
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                               | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        return QMessageBox.StandardButton(box.exec())

    def stop(self):
        """Avslutar redigeringen: frågar om ändringarna ska sparas om det finns några."""
        answer = QMessageBox.StandardButton.Save
        if self.controller.has_edits():
            answer = self._ask_save()
            if answer == QMessageBox.StandardButton.Cancel:
                return
        errors = self.controller.stop_editing(answer == QMessageBox.StandardButton.Save)
        self._uncheck_tools()
        if errors:
            self._report("Kunde inte spara: " + " ".join(errors), True)
        elif answer == QMessageBox.StandardButton.Save:
            found = self.controller.validate(self.catalog_provider())
            self._report(f"Sparade planen. Kontroll: {validation.summary(found)}."
                         + (" Kontrollera planen finns i NGP-dialogen." if found else ""),
                         any(i.severity == validation.ERROR for i in found))
        else:
            self._report("Kastade ändringarna.")

    def draw(self, table: str, checked: bool = True):
        if not checked:
            # avaktiverar man den aktiva ritknappen (klickar den igen) ska det faktiska ritverktyget också
            # avslutas – annars fortsätter QGIS eget ritverktyg (actionAddFeature) fånga klick i kartan trots att
            # knappen ser avstängd ut. Pennan (Avsluta ritning) byter till kartans "vanliga" verktyg, vilket
            # avbryter en pågående digitalisering precis som att byta ritverktyg mitt i alltid gör.
            self.iface.actionPan().trigger()
            return
        if self._prepare_draw(table):
            self.iface.actionAddFeature().trigger()

    def _prepare_draw(self, table: str) -> bool:
        """Kontrollerar hierarkin, markerar rätt knapp, gör tabellens lager aktivt och stänger av andra verktyg –
        allt ``draw`` behöver innan det startar själva ritverktyget."""
        ok, reason = self.controller.can_draw(LAYER_OF.get(table, table))
        action = self.draw_actions[table]
        if not ok:
            action.setChecked(False)
            self._report(reason, True)
            return False
        for other, other_action in self.draw_actions.items():
            other_action.setChecked(other == table)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_fill_use()
        self._uncheck_select()
        self._uncheck_label()
        self.iface.setActiveLayer(self.controller.layer(LAYER_OF.get(table, table)))
        QTimer.singleShot(0, lambda: collapse_plan_group(self.controller.project))  # aktivt lager fäller annars ut
        return True

    def _cad_action(self, name: str):
        """Hämtar en av QGIS egna, redan färdiga knappar i CAD-panelen (t.ex. ``mParallelAction``), så att våra
        egna knappar (se ``bottom_toolbar.py``) pekar på exakt samma ``QAction`` i stället för att bygga om dess
        beteende: samma ikon, samma verktygstips, samma ikryssade läge – oavsett var man klickar den."""
        dock = self.iface.cadDockWidget()
        return dock.findChild(QAction, name) if dock is not None else None

    def _main_window_action(self, name: str):
        """Som ``_cad_action``, men för knappar som sitter i själva QGIS huvudfönster (t.ex. Aktivera spårning i
        snappningsverktygsfältet) i stället för i CAD-panelen."""
        window = self.iface.mainWindow()
        return window.findChild(QAction, name) if window is not None else None

    def _enable_floater(self):
        """Slår på CAD-panelens "Floater" som standard (``mFloaterAction``) – de flytande, redigerbara rutorna vid
        muspekaren under ritning, som i AutoCAD – och stänger av XY-koordinaterna i den (``Show XY Coordinates``,
        inget stabilt objektnamn i QGIS: matchar på texten i stället) så bara längd och vinkel visas. Längd och
        vinkel är redan påslagna som QGIS eget förval. Använder ``.trigger()`` i stället för ``setChecked()`` rakt
        av, eftersom det är det som faktiskt kör QGIS egen på/av-logik (visar/döljer rutorna).

        Panelen själv (den dockade sidopanelen, skild från Floater-rutorna på kartan) döljs INTE här längre (se
        _enable_cad för varför) – att slå på Floater råkar visa panelen, men det är bättre än att riskera att
        aktiveringen inte fäster."""
        dock = self.iface.cadDockWidget()
        if dock is None:
            return
        floater = dock.findChild(QAction, "mFloaterAction")
        if floater is not None and not floater.isChecked():
            floater.trigger()
        for action in dock.findChildren(QAction):
            if action.text() == "Show XY Coordinates" and action.isChecked():
                action.trigger()
                break

    def toggle_assign(self, checked: bool):
        if not checked:
            self._unset_assign_tool()
            return
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_fill()
        self._uncheck_fill_use()
        self._uncheck_select()
        self._uncheck_label()
        self.iface.mapCanvas().setMapTool(self.assign_tool)

    def toggle_label(self, checked: bool):
        if not checked:
            self._unset_assign_tool()
            return
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_fill_use()
        self._uncheck_select()
        self.iface.mapCanvas().setMapTool(self.label_tool)

    def toggle_select(self, checked: bool):
        if not checked:
            self._unset_assign_tool()
            return
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_fill_use()
        self._uncheck_label()
        self.iface.mapCanvas().setMapTool(self.select_tool)

    def choose_candidate(self, candidates: list[Candidate]):
        """Meny vid pekaren med ytorna under klicket. Returnerar den valda ytan, eller None om menyn stängs."""
        menu = QMenu(self)
        actions = {}
        for candidate in candidates:
            actions[menu.addAction(candidate.title)] = candidate
        return actions.get(menu.exec(QCursor.pos()))

    def _after_select(self, candidate: Candidate):
        """Gör det markerade lagret aktivt så att redigeringsverktygen (flytta, noder, radera) gäller det."""
        layer = self.controller.layer(candidate.table)
        if layer is not None:
            self.iface.setActiveLayer(layer)
            QTimer.singleShot(0, lambda: collapse_plan_group(self.controller.project))

    def check_topology(self):
        """Öppnar dialogen för topologikontroll: brytpunkter, glapp, om hela planområdet har användning och om
        kvartersmark saknar egenskapsområden. Kan inte användas medan redigeringen pågår. De valda ändringarna (och att
        fylla en saknad användning) startar redigeringen och görs i redigeringsbufferten; de sparas när den avslutas."""
        if self.controller.editing:
            self._report(TOPOLOGY_EDITING_TIP, True)
            return
        def apply(changes):
            if not self.controller.editing:
                self.controller.start_editing()
            return self.controller.apply_topology(changes)

        def fill():
            if not self.controller.editing:
                self.controller.start_editing()
            return self.controller.fill_use()

        dialog = TopologyDialog(self.controller.topology_changes, apply, self._show_item, self.iface.mainWindow(),
                                findings=self.controller.topology_findings, fill_use=fill, controller=self.controller)
        dialog.exec()

    def _show_item(self, item):
        """Markerar och zoomar till ytan ett förslag (``Change``) eller en avvikelse (``Issue``) gäller."""
        self._highlight(item.table, item.fid, getattr(item, "geometry", None))

    def validate(self):
        """Öppnar dialogen med avvikelser mot reglerna."""
        dialog = ValidationDialog(lambda: self.controller.validate(self.catalog_provider()), self._show_issue,
                                  self.iface.mainWindow(), controller=self.controller)
        dialog.exec()

    # -- NGP: spara som fil eller leverera -------------------------------------------------------
    def _build_ngp_request(self) -> NgpRequest:
        """Bygger ögonblicksbilden NgpDialog visar (kommun, kontrollresultat, om en leverans kan återupptas) – för
        den plan som råkar vara aktiv just nu. Anropas igen om man byter aktiv plan inne i dialogen (se
        ``NgpDialog._switch_plan``)."""
        values = self.controller.plan_values()
        kommun = kommuner.by_name(values.get("kommun"))
        found = self.controller.validate(self.catalog_provider())
        errors = sum(1 for i in found if i.severity == validation.ERROR)
        warnings = sum(1 for i in found if i.severity == validation.WARNING)
        last = self.controller.last_delivery()
        resuming = bool(last) and last.get("miljo") == settings.ngp_config().environment
        return NgpRequest(values.get("namn") or "", kommun.namn if kommun else (values.get("kommun") or ""),
                          kommun.kod if kommun else "", errors, warnings, resuming)

    def _ask_ngp(self, request: NgpRequest):
        """Frågar om planen ska levereras till NGP eller sparas som fil. Returnerar UPPLOAD, FILE eller None."""
        dialog = NgpDialog(request, settings.ngp_config, self._on_settings, self.iface.mainWindow(), self.validate,
                           controller=self.controller, request_provider=self._build_ngp_request)
        return dialog.choice() if dialog.exec() else None

    def _ask_export_path(self, default_name: str) -> str:
        home = QgsProject.instance().homePath() or ""
        path, _ = QFileDialog.getSaveFileName(self.iface.mainWindow(), "Spara leverans till NGP",
                                              str(Path(home) / default_name) if home else default_name,
                                              "JSON (*.json)")
        return path

    def save_json(self, errors: int = 0) -> Optional[Path]:
        """Skriver leveransen (JSON, detaljplan 4.1) till en fil. Returnerar sökvägen, eller None om avbrutet."""
        name = (self.controller.plan_values().get("namn") or "detaljplan").strip()
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name).strip("_") or "detaljplan"
        path = self._ask_export_path(f"{safe}.json")
        if not path:
            return None
        try:
            collection = self.controller.export_ngp()
            Path(path).write_text(export_ngp.dumps(collection), encoding="utf-8")
        except (OSError, ValueError) as exc:
            self._report(f"Kunde inte spara: {exc}", True)
            return None
        provisions, geometries = export_ngp.counts(collection)
        self._report(f"Sparade planen som {Path(path).name}: {provisions} bestämmelser med {geometries} geometrier"
                     + (f". Observera {errors} fel som NGP stoppar." if errors else "."), bool(errors))
        return Path(path)

    def _make_client(self, config: "ngp.NgpConfig") -> "ngp.NgpClient":  # kan bytas ut i tester
        return ngp.NgpClient(config)

    def _run_delivery(self, work, done) -> None:
        """Kör ``work(progress)`` i en bakgrundsuppgift och anropar ``done(exception, result)`` i huvudtråden."""
        holder = {}

        def run(task):
            return work(lambda text: task.setDescription(f"Levererar till NGP: {text}"))

        def finished(exception, result=None):
            self._tasks = [t for t in self._tasks if t is not holder.get("task")]
            done(exception, result)

        task = QgsTask.fromFunction("Levererar planen till NGP", run, on_finished=finished)
        holder["task"] = task
        self._tasks.append(task)
        QgsApplication.taskManager().addTask(task)

    def open_planbeskrivning(self):
        """Öppnar programmet Tagga planbeskrivning med den aktiva planen. Är det redan öppet läses planen om (den kan ha
        ändrats) och fönstret visas igen, i stället för att ett till öppnas."""
        from .planbeskrivning_host import open_window
        window = self.planbeskrivning_window
        if window is not None and not sip.isdeleted(window) and window.isVisible():
            window.files.reload_from_host()
            window.showNormal()
            window.raise_()
            window.activateWindow()
            return window
        self.planbeskrivning_window = open_window(self.controller, self.iface.mainWindow())
        return self.planbeskrivning_window

    def close_planbeskrivning(self) -> None:
        """Stänger programmets fönster (när pluginet laddas ur, så att inget fönster med gammal kod blir kvar)."""
        window = self.planbeskrivning_window
        if window is not None and not sip.isdeleted(window):
            window.close()
        self.planbeskrivning_window = None

    def deliver(self) -> bool:
        """Öppnar dialogen för NGP: leverera planen via Uppdatering-API:et (efter bekräftelse) eller spara som fil.
        Dialogen öppnas alltid, även om inställningarna för leverans inte är gjorda (då går filalternativet ändå).
        Man kan byta aktiv plan inne i dialogen (se ``NgpDialog``): allt nedan läses om efter att dialogen stängts,
        så att leveransen gäller den plan som råkar vara aktiv då – inte nödvändigtvis den som var aktiv när
        dialogen öppnades. Returnerar True om en leverans eller en fil skapades/startades."""
        choice = self._ask_ngp(self._build_ngp_request())
        if choice is None:
            return False
        values = self.controller.plan_values()
        kommun = kommuner.by_name(values.get("kommun"))
        found = self.controller.validate(self.catalog_provider())
        errors = sum(1 for i in found if i.severity == validation.ERROR)
        if choice == FILE:
            return self.save_json(errors) is not None
        config = settings.ngp_config()  # kan ha ändrats via knappen Inställningar i dialogen
        problems = ([] if kommun else ["Kommunen är inte angiven i planens uppgifter."]) + config.problems()
        if problems:
            self._report("Leverans till NGP: " + " ".join(problems) + " Öppna Inställningar i NGP-dialogen.", True)
            return False
        last = self.controller.last_delivery()
        resuming = bool(last) and last.get("miljo") == config.environment
        try:
            collection = self.controller.export_ngp()
        except ValueError as exc:
            self._report(f"Leverans till NGP: {exc}", True)
            return False
        client = self._make_client(config)
        existing = last.get("mottagning") if resuming else None
        self._report("Levererar planen till NGP i bakgrunden …", False)

        def work(progress):
            return client.deliver(collection, kommun.kod, existing, progress)

        def done(exception, result=None):
            if exception is not None:
                text = str(exception) if isinstance(exception, ngp.NgpError) else f"{type(exception).__name__}: {exception}"
                self._report(f"Leveransen till NGP misslyckades. {text}", True)
                return
            self.controller.remember_delivery(result.mottagningsid, result.plan_id, config.environment)
            self._report(f"Leveransen till NGP ({config.title}) fick status {result.status.typ}.", not result.ok)
            self._titled(DeliveryDialog(result, config.title,
                                        lambda: client.refresh(result.mottagningsid, result.plan_id),
                                        self.iface.mainWindow())).exec()

        self._run_delivery(work, done)
        return True

    def _show_issue(self, issue):
        """Markerar och zoomar till ytan (eller den exakta delen) avvikelsen gäller."""
        self._highlight(issue.table, issue.fid, issue.geometry)

    def _highlight(self, table, fid, geometry=None) -> None:
        """Visar var en avvikelse eller ett förslag är: en exakt ``geometry`` (t.ex. den del av planområdet som
        saknar användning) ritas som en markering utan att markera någon yta – annars markeras och zoomas ytan
        ``fid`` som vanligt. Gäller det bara en del av en yta ska den delen visas, inte hela ytan (och, när planen
        har flera planområden, rätt del av rätt planområde)."""
        self._issue_band.reset(Qgis.GeometryType.Polygon)
        if geometry is not None and not geometry.isEmpty():
            self._issue_band.setToGeometry(geometry, None)
            box = geometry.boundingBox()
            box.scale(1.3)
            self.iface.mapCanvas().setExtent(box)
            self.iface.mapCanvas().refresh()
            return
        self.controller.select(Candidate(table, fid, ""))
        layer = self.controller.layer(table)
        if layer is not None:
            self.iface.setActiveLayer(layer)
            QTimer.singleShot(0, lambda: collapse_plan_group(self.controller.project))
            self.iface.mapCanvas().zoomToSelected(layer)

    def toggle_fill_use(self, checked: bool):
        if not checked:
            self._unset_assign_tool()
            return
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_select()
        self._uncheck_label()
        self.iface.mapCanvas().setMapTool(self.fill_use_tool)

    def toggle_fill_property(self, checked: bool):
        if not checked:
            self._unset_assign_tool()
            return
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_assign()
        self._uncheck_fill_use()
        self._uncheck_select()
        self._uncheck_label()
        self.iface.mapCanvas().setMapTool(self.fill_tool)

    def open_assign_dialog(self, candidates: list[Candidate], tool: AssignTool):
        """Öppnar dialogen för ytorna under klicket och markerar den valda ytan i kartan medan den är öppen."""
        dialog = AssignDialog(self.controller, self.catalog_provider, candidates, tool.highlight,
                              self.iface.mainWindow())
        dialog.exec()

    # -- verktygsbyten ----------------------------------------------------------------
    def _unset_assign_tool(self):
        self.iface.mapCanvas().unsetMapTool(self.assign_tool)
        self.iface.mapCanvas().unsetMapTool(self.fill_tool)
        self.iface.mapCanvas().unsetMapTool(self.fill_use_tool)
        self.iface.mapCanvas().unsetMapTool(self.select_tool)
        self.iface.mapCanvas().unsetMapTool(self.label_tool)

    def _uncheck_label(self):
        if self.act_label.isChecked():
            self.act_label.setChecked(False)

    def _uncheck_select(self):
        if self.act_select.isChecked():
            self.act_select.setChecked(False)

    def _uncheck_fill(self):
        if self.act_fill_property.isChecked():
            self.act_fill_property.setChecked(False)

    def _uncheck_fill_use(self):
        if self.act_fill_use.isChecked():
            self.act_fill_use.setChecked(False)

    def _deactivate_assign(self):
        """Stänger av tilldelningsverktyget: körs när det använts en gång, så man inte behöver göra det för hand."""
        self._uncheck_assign()
        self._unset_assign_tool()

    def _deactivate_fill(self):
        self._uncheck_fill()
        self._unset_assign_tool()

    def _deactivate_fill_use(self):
        self._uncheck_fill_use()
        self._unset_assign_tool()

    def _uncheck_assign(self):
        if self.act_assign.isChecked():
            self.act_assign.setChecked(False)

    def _uncheck_tools(self):
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_fill_use()
        self._uncheck_select()
        self._uncheck_label()
        self._unset_assign_tool()

    def _on_tool_set(self, tool, _previous=None):
        """När användaren väljer något annat verktyg släpps våra knappar."""
        if isinstance(tool, QgsMapToolCapture):
            # enable() (se _enable_cad) "fäster" bara på riktigt när ett ritverktyg faktiskt är aktivt – att bara
            # slå på det när redigeringen startar (innan något ritverktyg valts) räckte inte i praktiken.
            self._enable_cad()
        if tool in (self.assign_tool, self.fill_tool, self.fill_use_tool, self.select_tool, self.label_tool):
            return
        if tool is None or tool.action() != self.iface.actionAddFeature():
            for action in self.draw_actions.values():
                action.setChecked(False)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_fill_use()
        self._uncheck_select()
        self._uncheck_label()
