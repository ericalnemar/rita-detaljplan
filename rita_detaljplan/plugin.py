"""Pluginets huvudklass: meny, verktygsfält, panel och kommandon."""
from __future__ import annotations

from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsProject, QgsTask
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QCursor, QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMenu

from .controller import PlanController
from .core import catalog as cat
from .core.catalog_store import CatalogError, CatalogService
from .core import checkout, storage
from .core.project import (collapse_plan_group, create_plan_project, create_postgis_plan_project, load_plan,
                           restyle)
from .gui.new_plan_dialog import NewPlanDialog
from .gui.layout_legend import LayoutLegendTool
from .gui.plan_info_dialog import PlanInfoDialog
from .gui.plan_toolbar import PlanToolBar
from .gui.postgis_plan_dialog import PostgisPlanDialog
from .gui.settings_dialog import SettingsDialog

MENU = "&Rita Detaljplan"
TITLE = "Rita Detaljplan"
BUNDLED_CATALOG = Path(__file__).parent / "data" / "planbestammelsekatalog.json"


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
        icon = QIcon(str(Path(__file__).parent / "icon.svg"))
        self.controller = PlanController(self._error, self._warn, open_form=self._open_plan_form)
        self.toolbar = PlanToolBar(self.iface, self.controller, self._catalog, self.new_plan, self.open_plan,
                                   self.open_plan_info, self.iface.mainWindow(), on_settings=self.open_settings)
        self.iface.addToolBar(self.toolbar, Qt.ToolBarArea.TopToolBarArea)
        self.layout_legend = LayoutLegendTool(self.iface, self.controller, self._catalog)
        self.layout_legend.attach()

        self._add_action("Ny detaljplan…", self.new_plan, icon)  # ikonen finns i verktygsfältet för planarbete
        self._add_action("Öppna detaljplan (GeoPackage)…", self.open_plan)
        self.iface.addPluginToMenu(MENU, self._separator())
        tools = self.toolbar.toggleViewAction()
        tools.setText("Verktygsfält för planarbete")
        self.iface.addPluginToMenu(MENU, tools)
        self.actions.append(tools)
        self._add_action("Uppdatera planbestämmelsekatalogen…", self.update_catalog)
        self._add_action("Inställningar för leverans till NGP…", self.open_settings)

    def unload(self):
        if self.layout_legend is not None:
            self.layout_legend.detach()
            self.layout_legend = None
        if self.controller is not None:
            self.controller.detach()
            self.controller = None
        if self.toolbar is not None:
            main_window = self.iface.mainWindow()
            if main_window is not None:
                main_window.removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        for action in self.actions:
            self.iface.removePluginMenu(MENU, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()

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
        self.iface.messageBar().pushMessage(TITLE, text, level=Qgis.MessageLevel.Success)

    def _warn(self, text):
        self.iface.messageBar().pushMessage(TITLE, text, level=Qgis.MessageLevel.Warning)

    def _error(self, text):
        self.iface.messageBar().pushCritical(TITLE, text)

    def _open_plan_form(self, layer, feature):
        """Öppnar planens uppgifter (kommun, namn, syfte, status …) när planområdet ritats första gången."""
        self.open_plan_info()

    def open_plan_info(self):
        if self.controller is None or self.controller.plan_feature() is None:
            self._warn("Rita planområdet först. Planens uppgifter hör till planområdet.")
            return
        PlanInfoDialog(self.controller, self.iface.mainWindow()).exec()

    def open_settings(self):
        """Inställningar för leverans till NGP."""
        SettingsDialog(self.iface.mainWindow()).exec()

    # -- planer -------------------------------------------------------------------
    def new_plan(self):
        dialog = NewPlanDialog(self.iface.mainWindow())
        if not dialog.exec():
            return
        v = dialog.values()
        try:
            if v.kind == "postgis":
                _, qgz = create_postgis_plan_project(v.directory, v.filnamn, v.connection, v.schema, v.kommun,
                                                     v.kommunkod, v.epsg)
            else:
                _, qgz = create_plan_project(v.directory, v.filnamn, v.kommun, v.kommunkod, v.epsg)
        except FileExistsError:
            self._error(f"Det finns redan en plan med namnet {v.filnamn} i mappen.")
            return
        except storage.PostgisError as exc:
            self._error(f"Kunde inte skapa detaljplanen i databasen: {exc}")
            return
        except (OSError, ValueError) as exc:
            self._error(f"Kunde inte skapa detaljplanen: {exc}")
            return
        self.iface.addProject(str(qgz))
        QTimer.singleShot(0, lambda: collapse_plan_group(QgsProject.instance()))
        if self.controller is not None:
            self.controller.attach()
        if self.toolbar is not None:
            self.toolbar.refresh()
            self.toolbar.show()
        self._info(f"Skapade {qgz.name}. Klicka på pennan i verktygsfältet och rita planområdet.")

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
        connection, schema = dialog.selection()
        plan = storage.PostgisStorage(connection, schema)
        try:
            load_plan(plan, QgsProject.instance())
            lock = checkout.read_lock(plan)
        except (ValueError, storage.PostgisError) as exc:
            self._error(str(exc))
            return
        QTimer.singleShot(0, lambda: collapse_plan_group(QgsProject.instance()))
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
        try:
            load_plan(path, QgsProject.instance())
        except ValueError as exc:
            self._error(str(exc))
            return
        QTimer.singleShot(0, lambda: collapse_plan_group(QgsProject.instance()))
        self._info(f"Laddade {Path(path).name}")

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
