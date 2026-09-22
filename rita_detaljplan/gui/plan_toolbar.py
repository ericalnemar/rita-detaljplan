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

from qgis.core import QgsApplication, QgsProject, QgsTask
from qgis.PyQt.QtCore import QSize, Qt, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import QAction, QActionGroup, QFileDialog, QMenu, QMessageBox, QToolBar

from ..controller import HELPER_LAYER, PLAN_LAYER, Candidate, PlanController
from ..core import catalog as cat
from ..core import checkout as co
from ..core import export_ngp, kommuner, settings, validation
from ..core import ngp_client as ngp
from ..core.project import collapse_plan_group
from .assign_dialog import AssignDialog
from .assign_tool import AssignTool
from .checkout_actions import CheckoutActions
from .delivery_dialog import DeliveryDialog
from .fill_tool import FillTool
from .ngp_dialog import FILE, UPLOAD, NgpDialog, NgpRequest
from .label_tool import LabelTool
from .select_tool import SelectTool
from .topology_dialog import TopologyDialog
from .validation_dialog import ValidationDialog

ICONS = Path(__file__).resolve().parent.parent / "icons"

# (tabell, ikon, verktygstips)
DRAW_BUTTONS = (
    (PLAN_LAYER, "plan.svg", "Rita planområdet (planens yttre gräns)."),
    (cat.USE_LAYER, "use.svg", "Rita användningsområden inom planområdet."),
    ("egenskap_yta", "property.svg", "Rita egenskapsområden inom användningsområdena."),
    ("egenskap_linje", "line.svg", "Rita egenskapslinjer (utfartsförbud och stängsel) på en användningsyta."),
)
HELPER_BUTTON = (HELPER_LAYER, "helper.svg",
                 "Rita hjälplinjer (konstruktionslinjer som inte följer med till NGP).")
FILL_USE_TIP = "Fyll resten av planområdet med en användningsyta (det som ännu saknar användning)."
FILL_PROPERTY_TIP = "Fyll resten av ett användningsområde med en egenskapsyta: klicka i användningsområdet."
DESELECT_TIP = "Avmarkera alla: ta bort markeringen av alla planytor och linjer."
SELECT_TIP = "Markera: klicka i planen för att markera en yta eller linje (välj yta om flera ligger på varandra)."
LABEL_TIP = ("Text: klicka eller dra en rektangel för att markera bestämmelsernas texter, dra en markerad text för "
             "att flytta den. Delete återställer till automatisk placering.")
DELIVER_TIP = ("NGP: kontrollera planen mot Lantmäteriets regler, leverera den till Lantmäteriet (kräver producentbehörighet) "
               "eller spara den som JSON-fil. Inställningarna för leveransen finns också här.")
NO_PLAN = "Öppna eller skapa en detaljplan först."
START_TIP = "Börja rita planbestämmelser: alla planlager öppnas för redigering."
STOP_TIP = "Avsluta redigeringen och spara (eller kasta) ändringarna."
ASSIGN_TIP = "Planbestämmelser: klicka på en yta för att tilldela den en eller flera bestämmelser."
NEW_TIP = "Ny detaljplan…"
OPEN_TIP = "Öppna detaljplan (GeoPackage)…"
TOPOLOGY_TIP = ("Topologikontroll: föreslår att brytpunkter i användnings- och egenskapsytor flyttas till planområdets "
                "eller varandras brytpunkter, stänger små glapp mellan gränser, och visar om hela planområdet har "
                "en användning (med en knapp för att fylla det som saknas).")
CHECKOUT_TIP = ("Checka ut: lås planen i databasen och redigera en lokal kopia (snabbare). En plan som öppnats från "
                "databasen är skrivskyddad tills den checkats ut.")
CHECKIN_TIP = "Checka in: skriv planen tillbaka till databasen, släpp låset och ta bort den lokala kopian (eller kasta den)."
INFO_TIP = ("Planens uppgifter: kommun, namn, syfte, status, beslut och handlingar, och vad som återstår före "
            "leverans.")


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
        self.setIconSize(QSize(28, 28))
        self.iface = iface
        self._on_settings = on_settings
        self.controller = controller
        self.catalog_provider = catalog_provider
        self.status_text = ""

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
        self._tasks: list = []
        self.addSeparator()
        self.act_select = QAction(icon("select.svg"), "Markera", self)
        self.act_select.setCheckable(True)
        self.act_select.setToolTip(SELECT_TIP)
        self.addAction(self.act_select)
        self.act_deselect = QAction(icon("deselect.svg"), "Avmarkera alla", self)
        self.act_deselect.setToolTip(DESELECT_TIP)
        self.addAction(self.act_deselect)
        self.act_label = QAction(icon("text.svg"), "Text", self)
        self.act_label.setCheckable(True)
        self.act_label.setToolTip(LABEL_TIP)
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

        self.act_fill_use = QAction(icon("fill_use.svg"), FILL_USE_TIP, self)
        self.act_fill_use.setToolTip(FILL_USE_TIP)
        self.act_fill_property = QAction(icon("fill_property.svg"), FILL_PROPERTY_TIP, self)
        self.act_fill_property.setCheckable(True)
        self.act_fill_property.setToolTip(FILL_PROPERTY_TIP)
        self.addAction(self.act_fill_use)
        self.addAction(self.act_fill_property)
        self.addSeparator()
        add_draw_button(*HELPER_BUTTON)
        self.addSeparator()

        self.act_assign = QAction(icon("assign.svg"), "Planbestämmelser", self)
        self.act_assign.setCheckable(True)
        self.act_assign.setToolTip(ASSIGN_TIP)
        self.addAction(self.act_assign)

        self.assign_tool = AssignTool(iface.mapCanvas(), controller, self.open_assign_dialog, self._report)
        self.fill_tool = FillTool(iface.mapCanvas(), controller, self._report)
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
        self.act_assign.triggered.connect(self.toggle_assign)
        self.act_fill_use.triggered.connect(self.fill_use)
        self.act_select.triggered.connect(self.toggle_select)
        self.act_deselect.triggered.connect(lambda _checked=False: self.controller.clear_selection())
        self.act_topology.triggered.connect(lambda _checked=False: self.check_topology())
        self.act_deliver.triggered.connect(lambda _checked=False: self.deliver())
        self.act_label.triggered.connect(self.toggle_label)
        self.act_fill_property.triggered.connect(self.toggle_fill_property)
        self.controller.changed.connect(self.refresh)
        QgsProject.instance().layersAdded.connect(self.refresh)  # metod, inte lambda: kopplas bort när verktygsfältet tas bort
        iface.mapCanvas().mapToolSet.connect(self._on_tool_set)
        self.refresh()

    # -- meddelanden ------------------------------------------------------------------
    def _report(self, text: str, warning: bool = False):
        bar = self.iface.messageBar()
        (bar.pushWarning if warning else bar.pushInfo)("Rita Detaljplan", text)

    # -- uppdatera läget --------------------------------------------------------------
    def has_plan(self) -> bool:
        return self.controller.layer(PLAN_LAYER) is not None

    def refresh(self, *_):
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
        self.act_info.setEnabled(has_plan and self.controller.summary().has_plan)
        self.act_info.setToolTip(INFO_TIP if self.act_info.isEnabled() else
                                 (NO_PLAN if not has_plan else "Rita planområdet först."))
        self.act_topology.setEnabled(has_plan and self.controller.summary().has_plan)
        self.act_topology.setToolTip(TOPOLOGY_TIP if self.act_topology.isEnabled() else
                                     (NO_PLAN if not has_plan else "Rita planområdet först."))

        for action, tip in ((self.act_deliver, DELIVER_TIP),):
            action.setEnabled(has_plan and self.controller.summary().has_plan)
            action.setToolTip(tip if action.isEnabled() else (NO_PLAN if not has_plan else "Rita planområdet först."))
        self.act_select.setEnabled(has_plan)
        self.act_deselect.setEnabled(has_plan)
        self.act_deselect.setToolTip(DESELECT_TIP if has_plan else NO_PLAN)
        self.act_select.setToolTip(SELECT_TIP if has_plan else NO_PLAN)
        if not has_plan and self.act_select.isChecked():
            self.act_select.setChecked(False)
            self._unset_assign_tool()

        self.act_label.setEnabled(has_plan)
        self.act_label.setToolTip(LABEL_TIP if has_plan else NO_PLAN)
        if not has_plan and self.act_label.isChecked():
            self.act_label.setChecked(False)
            self._unset_assign_tool()

        self.act_start.setEnabled(has_plan and not editing)
        self.act_stop.setEnabled(editing)
        for table, action in self.draw_actions.items():
            ok, reason = self.controller.can_draw(table) if has_plan else (False, NO_PLAN)
            action.setEnabled(ok)
            action.setToolTip(action.data() if ok else reason)

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

    def _show_status(self, text: str):
        if text != self.status_text:
            self.status_text = text
            bar = self.iface.statusBarIface()
            if bar is not None:
                bar.showMessage(text, 0)

    def _status_text(self) -> str:
        state = self.controller.summary()
        if not state.has_plan:
            return "Planområde saknas"
        parts = [f"Planområde {state.plan_area:,.0f} m²".replace(",", " ")]
        parts.append("Användning: " + (f"{state.coverage:.0%} av planområdet" if state.has_use else "saknas"))
        if state.unassigned:
            parts.append(f"{state.unassigned} saknar bestämmelse")
        return "  ·  ".join(parts)

    # -- kommandon --------------------------------------------------------------------
    def toggle_checkout(self):
        """Databasplan: checkar ut planen för redigering, eller (om den redan är utcheckad) checkar in den."""
        if co.state(self.controller.project) == co.LOCAL:
            return self.checkout.check_in()
        return self.checkout.check_out()

    def start(self):
        if co.state(self.controller.project) == co.DATABASE and not self.checkout.check_out():
            return  # en plan i en databas redigeras bara i en utcheckad lokal kopia
        if not self.controller.start_editing():
            self._report("Kunde inte öppna alla planlager för redigering.", True)

    def _ask_save(self, missing: Optional[list[str]] = None) -> "QMessageBox.StandardButton":
        box = QMessageBox(self)
        box.setWindowTitle("Avsluta redigering")
        box.setText("Vill du spara ändringarna i planen?")
        if missing:
            lines = "\n".join(f"  ✘ {text}" for text in missing)
            box.setInformativeText(
                "Du kan spara nu och fylla i resten senare. Innan planen kan levereras till NGP saknas:\n\n"
                f"{lines}\n\nPlanens uppgifter fyller du i med ikonen med kryssrutan.")
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                               | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        return QMessageBox.StandardButton(box.exec())

    def stop(self):
        """Avslutar redigeringen: frågar om ändringarna ska sparas om det finns några."""
        answer = QMessageBox.StandardButton.Save
        if self.controller.has_edits():
            gaps = [req.text for req in self.controller.requirements() if not req.ok]
            answer = self._ask_save(gaps)
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
            return
        ok, reason = self.controller.can_draw(table)
        action = self.draw_actions[table]
        if not ok:
            action.setChecked(False)
            self._report(reason, True)
            return
        for other, other_action in self.draw_actions.items():
            other_action.setChecked(other == table)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_select()
        self._uncheck_label()
        self.iface.setActiveLayer(self.controller.layer(table))
        QTimer.singleShot(0, lambda: collapse_plan_group(self.controller.project))  # aktivt lager fäller annars ut
        self.iface.actionAddFeature().trigger()

    def toggle_assign(self, checked: bool):
        if not checked:
            self._unset_assign_tool()
            return
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_fill()
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
        """Öppnar dialogen för topologikontroll: brytpunkter, glapp och om hela planområdet har användning. De valda
        ändringarna (och att fylla en saknad användning) görs i redigeringsbufferten (redigeringen startas om den
        inte redan pågår) och sparas när redigeringen avslutas."""
        def apply(changes):
            if not self.controller.editing:
                self.controller.start_editing()
            return self.controller.apply_topology(changes)

        def fill():
            if not self.controller.editing:
                self.controller.start_editing()
            return self.controller.fill_use()

        dialog = TopologyDialog(self.controller.topology_changes, apply, self._show_change, self.iface.mainWindow(),
                                missing_use=self.controller.missing_use_area, fill_use=fill)
        dialog.exec()

    def _show_change(self, change):
        """Markerar och zoomar till ytan ett förslag gäller."""
        from ..controller import Candidate
        self.controller.select(Candidate(change.table, change.fid, ""))
        layer = self.controller.layer(change.table)
        if layer is not None:
            self.iface.setActiveLayer(layer)
            QTimer.singleShot(0, lambda: collapse_plan_group(self.controller.project))
            self.iface.mapCanvas().zoomToSelected(layer)

    def validate(self):
        """Öppnar dialogen med avvikelser mot reglerna."""
        dialog = ValidationDialog(lambda: self.controller.validate(self.catalog_provider()), self._show_issue,
                                  self.iface.mainWindow())
        dialog.exec()

    # -- NGP: spara som fil eller leverera -------------------------------------------------------
    def _ask_ngp(self, request: NgpRequest):
        """Frågar om planen ska levereras till NGP eller sparas som fil. Returnerar UPPLOAD, FILE eller None."""
        dialog = NgpDialog(request, settings.ngp_config, self._on_settings, self.iface.mainWindow(), self.validate)
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

    def deliver(self) -> bool:
        """Öppnar dialogen för NGP: leverera planen via Uppdatering-API:et (efter bekräftelse) eller spara som fil.
        Dialogen öppnas alltid, även om inställningarna för leverans inte är gjorda (då går filalternativet ändå).
        Returnerar True om en leverans eller en fil skapades/startades."""
        values = self.controller.plan_values()
        kommun = kommuner.by_name(values.get("kommun"))
        found = self.controller.validate(self.catalog_provider())
        errors = sum(1 for i in found if i.severity == validation.ERROR)
        warnings = sum(1 for i in found if i.severity == validation.WARNING)
        last = self.controller.last_delivery()
        config = settings.ngp_config()
        resuming = bool(last) and last.get("miljo") == config.environment
        request = NgpRequest(values.get("namn") or "", kommun.namn if kommun else (values.get("kommun") or ""),
                             kommun.kod if kommun else "", errors, warnings, resuming)
        choice = self._ask_ngp(request)
        if choice == FILE:
            return self.save_json(errors) is not None
        if choice != UPLOAD:
            return False
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
            DeliveryDialog(result, config.title, lambda: client.refresh(result.mottagningsid, result.plan_id),
                           self.iface.mainWindow()).exec()

        self._run_delivery(work, done)
        return True

    def _show_issue(self, issue):
        """Markerar och zoomar till ytan avvikelsen gäller."""
        self.controller.show_issue(issue)
        layer = self.controller.layer(issue.table)
        if layer is not None:
            self.iface.setActiveLayer(layer)
            QTimer.singleShot(0, lambda: collapse_plan_group(self.controller.project))
            self.iface.mapCanvas().zoomToSelected(layer)

    def fill_use(self, _checked=False):
        result = self.controller.fill_use()
        self._report(result.message, not result.ok)

    def toggle_fill_property(self, checked: bool):
        if not checked:
            self._unset_assign_tool()
            return
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_assign()
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

    def _uncheck_assign(self):
        if self.act_assign.isChecked():
            self.act_assign.setChecked(False)

    def _uncheck_tools(self):
        for action in self.draw_actions.values():
            action.setChecked(False)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_select()
        self._uncheck_label()
        self._unset_assign_tool()

    def _on_tool_set(self, tool, _previous=None):
        """När användaren väljer något annat verktyg släpps våra knappar."""
        if tool in (self.assign_tool, self.fill_tool, self.select_tool, self.label_tool):
            return
        if tool is None or tool.action() != self.iface.actionAddFeature():
            for action in self.draw_actions.values():
                action.setChecked(False)
        self._uncheck_assign()
        self._uncheck_fill()
        self._uncheck_select()
        self._uncheck_label()
