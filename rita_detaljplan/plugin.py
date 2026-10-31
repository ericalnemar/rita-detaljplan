"""Pluginets huvudklass: meny, verktygsfält, panel och kommandon."""
from __future__ import annotations

import json
from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsProject, QgsTask
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QCursor, QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox

from .controller import PlanController
from .core import catalog as cat
from .core.catalog_store import CatalogError, CatalogService
from .core import archive, checkout, example_sheet, example_sheet_layout, importer, legend_layout, storage
from .core import import_ngp as import_ngp_module
from .core.project import (activate_plan_group, collapse_plan_group, create_plan_project, create_postgis_plan_project,
                           find_plan_group, load_plan, plan_groups, remove_plan, restyle)
from .gui.about_dialog import AboutDialog
from .gui.import_dialog import ImportDialog
from .gui.archive_dialog import ArchiveDialog, build_archive
from .gui.messages import push
from .gui.new_plan_dialog import NewPlanDialog
from .gui.layout_legend import LayoutLegendTool
from .gui.plan_info_dialog import PlanInfoDialog
from .gui.plan_toolbar import PlanToolBar
from .gui.postgis_plan_dialog import PostgisPlanDialog
from .gui.settings_dialog import SettingsDialog

MENU = "&Rita Detaljplan"
TITLE = "Rita Detaljplan"
BUNDLED_CATALOG = Path(__file__).parent / "data" / "planbestammelsekatalog.json"
ICONS = Path(__file__).parent / "icons"
BRAND_ICON = Path(__file__).parent / "icon.svg"


class DetaljplanPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions: list[QAction] = []
        self.catalogs: CatalogService | None = None
        self.controller: PlanController | None = None
        self.toolbar: PlanToolBar | None = None
        self.layout_legend: LayoutLegendTool | None = None
        self._tasks: list[QgsTask] = []

    # -- livscykel ----------------------------------------------------------------
    def initGui(self):  # noqa: N802 - namnet krävs av QGIS
        self.controller = PlanController(self._error, self._warn, open_form=self._open_plan_form)
        self.toolbar = PlanToolBar(self.iface, self.controller, self._catalog, self.new_plan, self.open_plan,
                                   self.open_plan_info, self.iface.mainWindow(), on_settings=self.open_settings,
                                   on_archive=self.open_archive, on_import=self.import_geometry)
        self.iface.addToolBar(self.toolbar, Qt.ToolBarArea.TopToolBarArea)
        # det andra verktygsfältet (self.toolbar.bottom_toolbar) läggs till och dockas längst ned av PlanToolBar
        # själv (se dess __init__) – precis som ett vanligt verktygsfält, inget eget addDockWidget-anrop här.
        self.layout_legend = LayoutLegendTool(self.iface, self.controller, self._catalog)
        self.layout_legend.attach()

        self._add_action("Ny detaljplan…", self.new_plan, QIcon(str(ICONS / "new.svg")))  # samma ikon som i verktygsfältet
        self._add_action("Öppna detaljplan (GeoPackage)…", self.open_plan)
        self._add_action("Importera leverans (JSON)…", self.import_plan)
        self._add_action("Importera geometrier…", self.import_geometry)
        self._add_action("Byt aktiv plan…", self.switch_plan)  # flera planer kan vara laddade samtidigt
        self._add_action("Stäng aktiv plan", self.close_plan)
        self.iface.addPluginToMenu(MENU, self._separator())
        tools = self.toolbar.toggleViewAction()
        # samma åtgärd visas i QGIS lista över verktygsfält: den behåller verktygsfältets namn, Rita Detaljplan
        self.iface.addPluginToMenu(MENU, tools)
        self.actions.append(tools)
        more_tools = self.toolbar.bottom_toolbar.toggleViewAction()
        self.iface.addPluginToMenu(MENU, more_tools)
        self.actions.append(more_tools)
        self._add_action("Uppdatera planbestämmelsekatalogen…", self.update_catalog)
        self._add_action("Inställningar för leverans till NGP…", self.open_settings)
        self._add_action("Skapa exempellayout för plankarta…", self.create_example_sheet)
        self.iface.addPluginToMenu(MENU, self._separator())
        self._add_action("Skapa arkivpaket…", lambda _checked=False: self.open_archive())
        self._add_action("Kontrollera arkivpaket…", self.verify_archive)
        self.iface.addPluginToMenu(MENU, self._separator())
        self._add_action("Om Rita Detaljplan…", self.open_about)
        self._brand_menu()

    def unload(self):
        if self.layout_legend is not None:
            self.layout_legend.detach()
            self.layout_legend = None
        if self.controller is not None:
            self.controller.detach()
            self.controller = None
        if self.toolbar is not None:
            self.toolbar.close_planbeskrivning()
            # det andra verktygsfältet (bottom_toolbar) städas automatiskt: se PlanToolBar.__init__, som kopplar
            # det till att verktygsfältet självt förstörs.
            main_window = self.iface.mainWindow()
            if main_window is not None:
                main_window.removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        for action in self.actions:
            self.iface.removePluginMenu(MENU, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()

    def _brand_menu(self):
        """Märket framför Rita Detaljplan i menyn Insticksprogram (QGIS skapar undermenyn utan ikon)."""
        plugin_menu = self.iface.pluginMenu()
        if plugin_menu is None:
            return
        for entry in plugin_menu.actions():
            if entry.menu() is not None and entry.menu().title() == MENU:
                entry.setIcon(QIcon(str(BRAND_ICON)))
                return

    def open_about(self):
        AboutDialog(self.iface.mainWindow()).exec()

    def _separator(self):
        action = QAction(self.iface.mainWindow())
        action.setSeparator(True)
        self.actions.append(action)
        return action

    def _add_action(self, text, callback, icon=None, toolbar=False):
        action = QAction(icon, text, self.iface.mainWindow()) if icon else QAction(text, self.iface.mainWindow())
        action.triggered.connect(callback)
        self.iface.addPluginToMenu(MENU, action)
        if toolbar:
            self.iface.addToolBarIcon(action)
        self.actions.append(action)
        return action

    # -- meddelanden --------------------------------------------------------------
    def _info(self, text):
        push(self.iface.messageBar(), TITLE, text, Qgis.MessageLevel.Success)

    def _warn(self, text):
        push(self.iface.messageBar(), TITLE, text, Qgis.MessageLevel.Warning)

    def _error(self, text):
        push(self.iface.messageBar(), TITLE, text, Qgis.MessageLevel.Critical)

    def _open_plan_form(self, layer, feature):
        """Öppnar planens uppgifter (kommun, namn, syfte, status …) när planområdet ritats första gången."""
        self.open_plan_info()

    def open_plan_info(self):
        if self.controller is None or self.controller.plan_feature() is None:
            self._warn("Rita planområdet först. Planens uppgifter hör till planområdet.")
            return
        PlanInfoDialog(self.controller, self.iface.mainWindow()).exec()

    def choose_sheet_format(self, suggested: tuple[str, str]):
        """Frågar efter pappersformat och riktning; ``suggested`` är förvalt. None om man avbryter."""
        choices = example_sheet.formats()
        labels = [example_sheet.format_label(*choice) for choice in choices]
        label, ok = QInputDialog.getItem(self.iface.mainWindow(), "Skapa exempellayout för plankarta",
                                         "Pappersformat:", labels, choices.index(suggested), False)
        return choices[labels.index(label)] if ok and label in labels else None

    def create_example_sheet(self):
        """Skapar en exempellayout för plankartan (karta, teckenförklaring, norrpil, skalstock och titelruta) med den
        aktiva planen, i det format man väljer, och öppnar den i layoutläget. Den är en utgångspunkt att anpassa, se
        ``core.example_sheet``."""
        if self.controller is None or self.controller.plan_feature() is None:
            self._warn("Rita planområdet först. Exempellayouten visar planen.")
            return None
        try:
            data = self.controller.sheet_data()
            chosen = self.choose_sheet_format(example_sheet.suggested_format(data["bounds"], data["scale"]))
            if chosen is None:
                return None
            paper, orientation = chosen
            result = example_sheet_layout.create(self.controller.project, catalog=self._catalog(), paper=paper,
                                                 orientation=orientation, **data)
        except (legend_layout.LegendError, RuntimeError) as exc:
            self._error(f"Kunde inte skapa exempellayouten: {exc}")
            return None
        self.iface.openLayoutDesigner(result.layout)
        self._info(f"Skapade layouten {result.layout.name()}. Anpassa den efter kommunens grafiska profil och spara den "
                   "som mall med Layout → Spara som mall.")
        if result.warnings:
            self._warn(" ".join(result.warnings))
        return result

    def open_archive(self, parent=None):
        """Samlar planen och dess handlingar i ett arkivpaket med bevarandemetadata (se ``core.archive``). ``parent``:
        fönstret dialogen ska ligga över (NGP-dialogen när den öppnar den, annars QGIS huvudfönster). Returnerar
        paketet, eller None om inget skapades."""
        if self.controller is None or self.controller.plan_feature() is None:
            self._warn("Rita planområdet först. Arkivpaketet gäller en plan.")
            return None
        dialog = ArchiveDialog(self.controller, parent or self.iface.mainWindow())
        if not dialog.exec():
            return None
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            package = build_archive(self.controller, dialog.options())
        except archive.ArchiveError as exc:
            self._error(str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        self._info(f"Arkivpaketet {package.folder.name} är skapat med {len(package.records)} filer i "
                   f"{package.folder.parent}.")
        if package.notes:
            self._warn("Att tänka på: " + " ".join(package.notes))
        return package

    def verify_archive(self):
        """Räknar om kontrollsummorna i ett arkivpaket och visar om något ändrats."""
        home = QgsProject.instance().homePath() or ""
        chosen = QFileDialog.getExistingDirectory(self.iface.mainWindow(), "Välj arkivpaketets mapp", home)
        if not chosen:
            return
        try:
            report = archive.verify_package(Path(chosen))
        except archive.ArchiveError as exc:
            self._warn(str(exc))
            return
        box = QMessageBox(self.iface.mainWindow())
        box.setWindowTitle("Kontrollera arkivpaket")
        box.setIcon(QMessageBox.Icon.Information if report.clean else QMessageBox.Icon.Warning)
        box.setText("Arkivpaketet är oförändrat." if report.clean else "Arkivpaketet skiljer sig från hur det skapades.")
        box.setInformativeText(report.text())
        box.exec()

    def open_settings(self):
        """Inställningar för leverans till NGP."""
        SettingsDialog(self.iface.mainWindow()).exec()

    # -- planer -------------------------------------------------------------------
    def _adopt_as_project_file(self, qgz: Path) -> bool:
        """Om det öppna projektet aldrig sparats (man började t.ex. med ett tomt projekt, möjligen med en
        grundkarta tillagd) sparas det nu som den nya planens egna projektfil – annars skulle bara planens tomma
        "fröprojekt" (skrivet av ``create_plan_project``/``create_postgis_plan_project``) ligga kvar orört på
        disk, medan den riktiga, öppna kartan (med grundkartan också) förblir osparad. Rör inget om projektet
        redan är sparat som något annat, t.ex. när planen läggs till i ett större, befintligt projekt."""
        project = QgsProject.instance()
        if project.fileName():
            return False
        return project.write(str(qgz))

    def new_plan(self):
        dialog = NewPlanDialog(self.iface.mainWindow())
        if not dialog.exec():
            return
        v = dialog.values()
        try:
            if v.kind == "postgis":
                plan_storage, qgz = create_postgis_plan_project(v.directory, v.filnamn, v.connection, v.schema,
                                                                v.plan, v.kommun, v.kommunkod, v.epsg)
            else:
                plan_storage, qgz = create_plan_project(v.directory, v.filnamn, v.kommun, v.kommunkod, v.epsg)
        except FileExistsError:
            self._error(f"Det finns redan en plan med namnet {v.filnamn} i mappen.")
            return
        except storage.PostgisError as exc:
            self._error(f"Kunde inte skapa detaljplanen i databasen: {exc}")
            return
        except (OSError, ValueError) as exc:
            self._error(f"Kunde inte skapa detaljplanen: {exc}")
            return
        # läggs till bredvid en ev. tidigare laddad plan (och blir den aktiva, se load_plan/activate_plan_group) –
        # rör inte andra lager (t.ex. en grundkarta) eller andra laddade planer: byter inte projekt
        load_plan(plan_storage, QgsProject.instance())
        QTimer.singleShot(0, lambda: collapse_plan_group(QgsProject.instance()))
        if self.controller is not None:
            self.controller.attach()
            if v.digitising:
                self.controller.set_digitising(True)
        if self.toolbar is not None:
            self.toolbar.refresh()
            self.toolbar.show()
        if self._adopt_as_project_file(qgz):
            self._info(f"Skapade och sparade {qgz.name} (med den öppna kartans övriga lager). Klicka på pennan i "
                       "verktygsfältet och rita planområdet.")
        else:
            self._info(f"Skapade {qgz.name} och la till planen i den öppna kartan. Klicka på pennan i "
                       "verktygsfältet och rita planområdet.")

    def import_geometry(self):
        """Importerar geometri (utan attribut) från ett annat lager eller en datakälla till planens hjälplager, i
        redigeringsbufferten. Hjälpytor och hjälplinjer får sedan en bestämmelse med Planbestämmelser och blir då
        planobjekt. Returnerar resultatet, eller None om inget importerades."""
        if self.controller is None or self.controller.layer("detaljplan") is None:
            self._warn("Öppna eller skapa en detaljplan först.")
            return None
        if not self.controller.editing:
            self._warn("Börja rita planbestämmelser först (pennan): det importerade läggs i redigeringsbufferten.")
            return None
        targets = {kind: self.controller.layer(table) for kind, table in importer.TARGET_TABLES.items()}
        if any(layer is None for layer in targets.values()):
            self._warn("Planen saknar hjälplagren. Öppna den med Öppna detaljplan (GeoPackage)…, så läggs de till.")
            return None
        group = find_plan_group(self.controller.project)
        own = [node.layer() for node in group.findLayers() if node.layer() is not None] if group is not None else []
        dialog = ImportDialog(self.iface, own, self.iface.mainWindow(), targets["polygon"].crs().postgisSrid() or 3006)
        accepted = dialog.exec()
        source, selected_only = dialog.source(), dialog.selected_only.isChecked()
        dialog.release()
        dialog.deleteLater()
        if not accepted or source is None:
            return None
        result = importer.import_geometries(source, targets, selected_only, self.controller.project)
        root = self.controller.project.layerTreeRoot()
        for kind, count in result.counts.items():
            node = root.findLayer(targets[kind].id())
            if count and node is not None:
                node.setItemVisibilityCheckedParentRecursive(True)
        text = result.text() + (" Spara med Avsluta redigering (disketten) när du är nöjd, eller ångra med Ctrl+Z i "
                                "lagret." if result.total else "")
        (self._info if result.total and not result.invalid else self._warn)(text)
        self.controller._changed()
        return result

    def import_plan(self):
        """Skapar en ny detaljplan och fyller den med en leverans i Lantmäteriets JSON-format (samma form som
        pluginet självt exporterar, se ``core.import_ngp``). Filen kan komma från ett annat verktyg (t.ex. ArcGIS
        Pro) som följer Nationell informationsspecifikation Detaljplan 4.1."""
        path, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Importera leverans", "", "JSON (*.json)")
        if not path:
            return
        try:
            collection = json.loads(Path(path).read_text(encoding="utf-8"))
            plan = import_ngp_module.parse(collection)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, import_ngp_module.ImportError_) as exc:
            self._error(f"Kunde inte läsa filen: {exc}")
            return

        dialog = NewPlanDialog(self.iface.mainWindow())
        dialog.setWindowTitle("Importera leverans – ny detaljplan")
        if plan.attrs.get("kommun"):
            dialog.kommun.set_kommun(plan.attrs["kommun"])
        dialog.planbeteckning.setText(plan.attrs.get("beteckning") or plan.attrs.get("namn") or "")
        if not dialog.exec():
            return
        v = dialog.values()
        try:
            if v.kind == "postgis":
                plan_storage, qgz = create_postgis_plan_project(v.directory, v.filnamn, v.connection, v.schema,
                                                                v.plan, v.kommun, v.kommunkod, v.epsg)
            else:
                plan_storage, qgz = create_plan_project(v.directory, v.filnamn, v.kommun, v.kommunkod, v.epsg)
        except FileExistsError:
            self._error(f"Det finns redan en plan med namnet {v.filnamn} i mappen.")
            return
        except storage.PostgisError as exc:
            self._error(f"Kunde inte skapa detaljplanen i databasen: {exc}")
            return
        except (OSError, ValueError) as exc:
            self._error(f"Kunde inte skapa detaljplanen: {exc}")
            return
        # läggs till bredvid en ev. tidigare laddad plan (och blir den aktiva, se load_plan/activate_plan_group) –
        # rör inte andra lager (t.ex. en grundkarta) eller andra laddade planer: byter inte projekt
        load_plan(plan_storage, QgsProject.instance())
        QTimer.singleShot(0, lambda: collapse_plan_group(QgsProject.instance()))
        if self.controller is not None:
            self.controller.attach()
        if self.toolbar is not None:
            self.toolbar.refresh()
            self.toolbar.show()
        adopted = self._adopt_as_project_file(qgz)
        try:
            summary = self.controller.import_ngp(collection, self._catalog())
        except (import_ngp_module.ImportError_, RuntimeError) as exc:
            self._error(f"Kunde inte importera leveransen: {exc}")
            return
        text = f"Importerade {summary.provisions} bestämmelser på {summary.areas} ytor från {Path(path).name}."
        if adopted:
            text += f" Sparade {qgz.name} (med den öppna kartans övriga lager)."
        if summary.skipped:
            text += f" {summary.skipped} kunde inte tolkas (se varningarna)."
            self._warn(text)
            for warning in summary.warnings:
                self._warn(warning)
        else:
            self._info(text)

    def open_plan(self):
        """Öppnar en plan: från en GeoPackage-fil eller (om det finns databasanslutningar) från en PostGIS-databas."""
        if not storage.postgis_connections():
            self.open_plan_file()
            return
        menu = QMenu(self.iface.mainWindow())
        file_action = menu.addAction("Lokal fil (GeoPackage)…")
        db_action = menu.addAction("PostGIS-databas…")
        chosen = menu.exec(QCursor.pos())
        if chosen is file_action:
            self.open_plan_file()
        elif chosen is db_action:
            self.open_plan_postgis()

    def open_plan_postgis(self):
        dialog = PostgisPlanDialog(self.iface.mainWindow())
        if not dialog.exec():
            return
        connection, schema, plan_id = dialog.selection()
        plan = storage.PostgisStorage(connection, schema, plan_id)
        # läggs till bredvid en ev. tidigare laddad plan och blir den aktiva (se load_plan/activate_plan_group) –
        # är flera planer laddade frågar pennan vilken som ska redigeras.
        try:
            load_plan(plan, QgsProject.instance())
            lock = checkout.read_lock(plan)
        except (ValueError, storage.PostgisError) as exc:
            self._error(str(exc))
            return
        QTimer.singleShot(0, lambda: collapse_plan_group(QgsProject.instance()))
        if self.controller is not None:
            self.controller.attach()
        if self.toolbar is not None:
            self.toolbar.refresh()
        if lock is not None:
            self._warn(f"Laddade planen {schema}, men den är utcheckad av {lock.describe()} och därför skrivskyddad.")
        else:
            self._info(f"Laddade planen {schema} från databasen {connection}. Den är skrivskyddad: klicka på Checka ut "
                       "(eller på pennan) för att redigera en lokal kopia.")

    def open_plan_file(self):
        path, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Öppna detaljplan", "", "GeoPackage (*.gpkg)")
        if not path:
            return
        # läggs till bredvid en ev. tidigare laddad plan och blir den aktiva (se load_plan/activate_plan_group) –
        # är flera planer laddade frågar pennan vilken som ska redigeras.
        try:
            load_plan(path, QgsProject.instance())
        except ValueError as exc:
            self._error(str(exc))
            return
        QTimer.singleShot(0, lambda: collapse_plan_group(QgsProject.instance()))
        if self.controller is not None:
            self.controller.attach()
        self._info(f"Laddade {Path(path).name}")

    def switch_plan(self):
        """Byter aktiv plan: frågar vilken, om fler än en är laddad (se ``PlanToolBar.switch_plan``). Till
        skillnad från pennan startar den ingen redigeringssession – bara för att t.ex. kontrollera eller leverera
        en annan laddad plan."""
        if self.toolbar is not None:
            self.toolbar.switch_plan()

    def close_plan(self):
        """Stänger den aktiva planen: tar bort dess lager ur projektet, men rör inte filen/databasen den kom från
        – den går att öppna igen. Andra laddade planer, om några, ligger kvar och en av dem blir aktiv i stället.
        Frågar om att spara först om det finns en pågående redigeringssession."""
        project = QgsProject.instance()
        if not plan_groups(project):
            self._warn("Ingen plan är laddad.")
            return
        if self.controller is not None and self.controller.editing:
            if self.toolbar is not None:
                self.toolbar.stop()
            if self.controller.editing:
                return  # avbröt frågan om att spara: låt planen vara öppen
        name = find_plan_group(project).name()
        remove_plan(project)
        remaining = plan_groups(project)
        if remaining:
            activate_plan_group(project, remaining[0])
        if self.controller is not None:
            self.controller.attach()
        if self.toolbar is not None:
            self.toolbar.refresh()
        self._info(f"Stängde planen {name}.")

    # -- katalog ------------------------------------------------------------------
    def _catalog(self) -> cat.Catalog:
        if self.catalogs is None:
            cache_dir = Path(QgsApplication.qgisSettingsDirPath()) / "detaljplan_ngp"
            self.catalogs = CatalogService(cache_dir, BUNDLED_CATALOG)
        return self.catalogs.load()

    def update_catalog(self):
        self._catalog()  # skapar tjänsten
        service = self.catalogs

        def run(task):
            return service.update()

        def finished(exception, result=None):
            if exception is not None:
                text = str(exception) if isinstance(exception, CatalogError) else f"{type(exception).__name__}: {exception}"
                self._error(f"Kunde inte uppdatera planbestämmelsekatalogen. {text}")
            else:
                self._info(result.message)
            self._tasks = [t for t in self._tasks if t is not task]

        task = QgsTask.fromFunction("Uppdaterar planbestämmelsekatalogen", run, on_finished=finished)
        self._tasks.append(task)
        QgsApplication.taskManager().addTask(task)
        self._info("Hämtar planbestämmelsekatalogen från Boverket …")
