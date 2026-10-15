"""Skapa arkivpaket och kontrollera ett arkivpaket (se ``core.archive``)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
                                 QLineEdit, QListWidget, QPushButton, QVBoxLayout)

from ..controller import PlanController
from ..core import archive, export_ngp, geopackage, kommuner
from .about_dialog import metadata

DOCUMENT_FILTER = "Dokument (*.pdf *.docx *.odt);;Alla filer (*)"
EDITING_TEXT = ("Planen redigeras just nu. Spara och avsluta redigeringen först, annars kommer inte det du ritat sedan "
                "senast med i paketet.")


def app_info() -> archive.App:
    meta = metadata()
    return archive.App(meta.get("name", "Rita Detaljplan"), meta.get("version", ""), meta.get("homepage", ""))


@dataclass
class ArchiveOptions:
    folder: Path
    geopackage: bool = True
    delivery_file: bool = True
    documents: list[Path] = field(default_factory=list)
    performer: Optional[str] = None


PLAN_FIELDS = ("beteckning", "namn", "status", "datumStatusforandring", "typ", "datumLagakraft", "anvandbarhet")


def plan_metadata(controller: PlanController) -> dict[str, str]:
    """Planens uppgifter till ``detaljplan.xml``: de sökbara attributen ur Detaljplan 4.1 som Boverkets katalog nämner
    (beteckning, namn, status, datum för statusförändring, typ, datum laga kraft, användbarhet) samt kommun och kommunkod.
    Bara det som är ifyllt tas med."""
    feature = controller.plan_feature()
    found: dict[str, str] = {}
    if feature is None:
        return found
    names = feature.fields().names()
    for name in PLAN_FIELDS:
        value = feature[name] if name in names else None
        text = "" if value is None or str(value) in ("NULL", "") else str(value).strip()
        if text:
            found[name] = text
    kommun = kommuner.by_name(controller.plan_values().get("kommun"))
    if kommun is not None:
        found["kommun"], found["kommunkod"] = kommun.namn, kommun.kod
    elif controller.plan_values().get("kommun"):
        found["kommun"] = str(controller.plan_values()["kommun"])
    return found


def build_archive(controller: PlanController, options: ArchiveOptions, app: Optional[archive.App] = None,
                  now: Optional[datetime] = None, progress: Optional[Callable[[str], None]] = None) -> archive.Package:
    """Exporterar det som ska med ur planen (till en tillfällig mapp) och skapar paketet av det och handlingarna."""
    app = app or app_info()
    say = progress or (lambda _text: None)
    name = (controller.plan_values().get("namn") or "detaljplan").strip()
    stem = archive.clean_filename(name, "detaljplan").replace(" ", "_")
    plugin = (app.name, app.version)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        work = Path(temp)
        items: list[archive.Item] = []
        if options.geopackage:
            source = controller.plan_file()
            if source is None:
                raise archive.ArchiveError("Planen ligger i en databas och finns inte som GeoPackage-fil. Ta bort "
                                           "valet för GeoPackage; leveransfilen innehåller hela planen.")
            say("Kopierar planens GeoPackage")
            items.append(archive.Item(geopackage.snapshot(source, work / f"{stem}.gpkg"), creator=plugin))
        if options.delivery_file:
            say("Skapar leveransfilen")
            path = work / f"{stem}.json"
            path.write_text(export_ngp.dumps(controller.export_ngp()), encoding="utf-8")
            items.append(archive.Item(path, creator=plugin))
        items += [archive.Item(Path(path)) for path in options.documents]
        return archive.build_package(options.folder, name, items, app, options.performer or None, now, progress,
                                     plan=plan_metadata(controller))


class ArchiveDialog(QDialog):
    """Frågar vad som ska med i arkivpaketet och var det ska sparas. ``options()`` ger valen när dialogen accepterats."""

    def __init__(self, controller: PlanController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.documents: list[Path] = []
        self.setWindowTitle("Skapa arkivpaket")
        self.setMinimumWidth(560)

        intro = QLabel("Samlar planen och dess handlingar i en mapp och beskriver dem med bevarandemetadata enligt "
                       "Boverkets specifikation (PREMIS), så att de kan sparas för långtidsbevarande. Originalen ändras "
                       "inte. Pluginet gör inga filer till PDF/A: se själv till att plankartan och planbeskrivningen är "
                       "PDF/A och kontrollerade med en PDF/A-validerare.")
        intro.setWordWrap(True)
        values = controller.plan_values()
        self.plan_label = QLabel(f"Plan: {values.get('namn') or 'utan namn'}")

        self.folder = QLineEdit(str(Path(QgsProject.instance().homePath() or Path.home())))
        self.folder.textChanged.connect(self._update)
        self.browse = QPushButton("Välj mapp…")
        self.browse.clicked.connect(self._choose_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Spara paketet i mappen:"))
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.browse)

        self.chk_gpkg = QCheckBox("Planen som GeoPackage-fil")
        self.chk_json = QCheckBox("Leveransfilen (JSON, detaljplan 4.1)")
        self.chk_json.setChecked(True)
        plan_file = controller.plan_file()
        self.chk_gpkg.setChecked(plan_file is not None)
        if plan_file is None:
            self.chk_gpkg.setEnabled(False)
            self.chk_gpkg.setToolTip("Planen ligger i en databas och finns inte som fil.")
        box = QGroupBox("Ur planen")
        QVBoxLayout(box).addWidget(self.chk_gpkg)
        box.layout().addWidget(self.chk_json)

        self.list = QListWidget()
        self.list.setMinimumHeight(70)
        self.list.setMaximumHeight(120)
        self.btn_add = QPushButton("Lägg till filer…")
        self.btn_add.clicked.connect(self._add_documents)
        self.btn_remove = QPushButton("Ta bort")
        self.btn_remove.clicked.connect(self._remove_selected)
        buttons_col = QVBoxLayout()
        buttons_col.addWidget(self.btn_add)
        buttons_col.addWidget(self.btn_remove)
        buttons_col.addStretch(1)
        docs_row = QHBoxLayout()
        docs_row.addWidget(self.list, 1)
        docs_row.addLayout(buttons_col)
        docs = QGroupBox("Handlingar")
        docs_layout = QVBoxLayout(docs)
        docs_layout.addWidget(QLabel("Färdiga filer att lägga med (plankartan och planbeskrivningen som PDF/A):"))
        docs_layout.addLayout(docs_row)

        self.performer = QLineEdit()
        self.performer.setPlaceholderText("valfritt, förs in som den som skapade paketet")
        performer_row = QHBoxLayout()
        performer_row.addWidget(QLabel("Utförd av:"))
        performer_row.addWidget(self.performer, 1)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Skapa paket")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        for check in (self.chk_gpkg, self.chk_json):
            check.toggled.connect(self._update)

        layout = QVBoxLayout(self)
        for widget in (intro, self.plan_label):
            layout.addWidget(widget)
        layout.addLayout(folder_row)
        layout.addWidget(box)
        layout.addWidget(docs)
        layout.addLayout(performer_row)
        layout.addWidget(self.hint)
        layout.addWidget(self.buttons)
        self._update()

    # -- val -----------------------------------------------------------------------------------
    def options(self) -> ArchiveOptions:
        return ArchiveOptions(folder=Path(self.folder.text().strip()), geopackage=self.chk_gpkg.isChecked(),
                              delivery_file=self.chk_json.isChecked(),
                              documents=list(self.documents), performer=self.performer.text().strip() or None)

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Välj mapp för arkivpaketet", self.folder.text())
        if chosen:
            self.folder.setText(chosen)

    def _add_documents(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Välj handlingar", self.folder.text(), DOCUMENT_FILTER)
        self.add_documents([Path(f) for f in files])

    def add_documents(self, paths: list[Path]) -> None:
        for path in paths:
            if path not in self.documents:
                self.documents.append(path)
                self.list.addItem(path.name)
        self._update()

    def _remove_selected(self) -> None:
        for item in self.list.selectedItems():
            row = self.list.row(item)
            self.list.takeItem(row)
            del self.documents[row]
        self._update()

    # -- läget ----------------------------------------------------------------------------------
    def notes(self) -> list[str]:
        """Råd om de tillagda filerna, till exempel att en PDF inte är PDF/A."""
        found = []
        for path in self.documents:
            try:
                found += [f"{path.name}: {note}" for note in archive.sniff_format(path)[2]]
            except OSError:
                found.append(f"{path.name}: filen kan inte läsas.")
        return found

    def problem(self) -> str:
        if self.controller.editing:
            return EDITING_TEXT
        if not Path(self.folder.text().strip()).is_dir():
            return "Välj en mapp som finns."
        o = self.options()
        if not (o.geopackage or o.delivery_file or o.documents):
            return "Välj minst en fil att lägga i paketet."
        return ""

    def _update(self, *_) -> None:
        problem = self.problem()
        self.ok.setEnabled(not problem)
        self.hint.setText("\n".join([problem] if problem else self.notes()))
