"""Programmets fyra steg: Filer, Taggning, Motiv och Kontroll och export."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Optional

from .qt.QtCore import QMimeData, QSize, Qt, QUrl, Signal
from .qt.QtGui import QColor, QDesktopServices, QDrag, QIcon, QPainter, QPixmap
from .qt.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFrame, QGridLayout, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QProgressBar, QRadioButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ..pbkarna import planbeskrivning as pb
from ..pbkarna import planbeskrivning_check as ck
from ..pbkarna import planbeskrivning_docx as dx
from ..pbkarna import plankarta as pk

from . import session as ss
from . import theme
from .widgets import Card, MapView, Pill, TagChip, box, button, frame, label, restyle

# exemplet kv. Lärkan ligger i repots mapp exempel/ (skapas med tools/skapa_exempel.py); det följer inte med zip-filen
EXEMPEL = Path(__file__).resolve().parents[3] / "exempel"
MOTIV_MIME = "application/x-planbeskrivning-motiv"


def short(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def scrolled(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setFrameShape(QFrame.Shape.NoFrame)
    return area


def provision_name(provision: dx.Provision) -> str:
    return f"{provision.label}  {provision.text}".strip() if provision.label else provision.text


class Facts(QWidget):
    """Några uppgifter i rad: liten grå rubrik och värdet under."""

    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(2)

    def set(self, items: list[tuple[str, str]]) -> None:
        while self.grid.count():
            self.grid.takeAt(0).widget().deleteLater()
        for column, (name, value) in enumerate(items):
            self.grid.addWidget(label(name, "hint"), 0, column)
            value_label = label(value, "factValue")
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.grid.addWidget(value_label, 1, column)
        self.grid.setColumnStretch(len(items), 1)


# -- steg 1 ---------------------------------------------------------------------------------------------
class FilesPage(QWidget):
    loaded = Signal()
    proceed = Signal()

    def __init__(self, session: ss.Session, toast):
        super().__init__()
        self.session, self.toast = session, toast
        self.setObjectName("page")
        self.setAcceptDrops(True)

        self.doc_name, self.doc_path, self.doc_facts = label("Ingen fil vald", "fileName"), label("", "hint"), Facts()
        self.map_name, self.map_path, self.map_facts = label("Ingen fil vald", "fileName"), label("", "hint"), Facts()
        self.doc_frame = frame("chosen", box("h", box("v", self.doc_name, self.doc_path, spacing=2), None,
                                             self._choose_button(self.choose_docx), margins=(12, 10, 12, 10)))
        host = session.host
        if host is not None:
            map_button = button(f"Läs om från {host.name}", "small",
                                f"Hämta planens bestämmelser från {host.name} igen, t.ex. efter att du ändrat i planen.")
            map_button.clicked.connect(self.reload_from_host)
        else:
            map_button = self._choose_button(self.choose_plankarta)
        self.map_frame = frame("chosen", box("h", box("v", self.map_name, self.map_path, spacing=2), None,
                                             map_button, margins=(12, 10, 12, 10)))
        self.plan_combo = QComboBox()
        self.plan_combo.activated.connect(self._plan_chosen)
        self.plan_row = QWidget()
        self.plan_row.setLayout(box("h", label("Plan:", "muted"), self.plan_combo, None))
        self.plan_row.hide()

        doc_panel = frame("panel", box(
            "v", self._head("Planbeskrivning", "Word-dokument (.docx). Originalet ändras aldrig."),
            self.doc_frame, self.doc_facts, None, spacing=14, margins=(20, 20, 20, 20)))
        map_panel = frame("panel", box(
            "v", self._head("Plankarta", f"Den aktiva planen i {host.name}." if host is not None else
                            "QGIS-projekt (.qgz, .qgs) eller GeoPackage (.gpkg) från Rita Detaljplan."),
            self.map_frame, self.plan_row, self.map_facts, None, spacing=14, margins=(20, 20, 20, 20)))

        self.go = button("Fortsätt till taggning  →", "primary")
        self.go.clicked.connect(self.proceed.emit)
        self.example = button("Öppna exemplet kv. Lärkan", "ghost",
                              "En påhittad plan med planbeskrivning, för att prova programmet.")
        self.example.clicked.connect(self.open_example)
        self.example.setVisible(host is None and (EXEMPEL / "Planbeskrivning_kv_Larkan.docx").exists())
        self.recent = button("", "ghost")
        self.recent.clicked.connect(self.open_recent)
        self.error = label("", "error", wrap=True)
        self.error.hide()

        column = QWidget()
        column.setMaximumWidth(1040)
        files = QGridLayout()
        files.setSpacing(16)
        files.addWidget(doc_panel, 0, 0)
        files.addWidget(map_panel, 0, 1)
        column.setLayout(box(
            "v", label("NY TAGGNING", "eyebrow"),
            label("Välj planbeskrivning" if host is not None else "Välj planbeskrivning och plankarta", "h1"),
            label("Programmet läser Word-filen och plankartans bestämmelser, föreslår taggar för varje avsnitt och hjälper "
                  "dig koppla motiven till rätt bestämmelse. Allt sker på den här datorn.", "lead", wrap=True),
            12, files, self.error, box("h", self.go, self.example, self.recent, None),
            label("Du kan också dra filen hit." if host is not None else "Du kan också dra filerna hit.", "hint"), None,
            spacing=10, margins=(16, 36, 16, 36)))
        outer = QWidget()
        outer.setLayout(box("h", None, column, None))
        self.setLayout(box("v", scrolled(outer)))
        self.refresh()

    def _head(self, title: str, sub: str) -> QWidget:
        widget = QWidget()
        widget.setLayout(box("v", label(title, "h2"), label(sub, "muted", wrap=True), spacing=2))
        return widget

    def _choose_button(self, slot) -> QWidget:
        widget = button("Välj…", "small")
        widget.clicked.connect(slot)
        return widget

    # -- val av filer --
    def _start_dir(self) -> str:
        for path in (self.session.docx, self.session.plankarta):
            if path:
                return str(path.parent)
        return self.session.store.get("senast/mapp") or ""

    def choose_docx(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Välj planbeskrivning", self._start_dir(), "Word-dokument (*.docx)")
        if path:
            self.load(docx=path)

    def choose_plankarta(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Välj plankarta", self._start_dir(),
                                              "Plan från Rita Detaljplan (*.qgz *.qgs *.gpkg);;Alla filer (*)")
        if path:
            self.load(plankarta=path)

    def load(self, docx=None, plankarta=None) -> None:
        self.error.hide()
        try:
            if plankarta:
                self.session.load_plankarta(plankarta)
                self.session.store.put("senast/plankarta", str(plankarta))
                self.session.store.put("senast/mapp", str(Path(plankarta).parent))
            if docx:
                self.session.load_docx(docx)
                self.session.store.put("senast/docx", str(docx))
                self.session.store.put("senast/mapp", str(Path(docx).parent))
        except (ss.SessionError, pk.PlankartaError) as exc:
            self.error.setText(str(exc))
            self.error.show()
        self.refresh()
        self.loaded.emit()

    def reload_from_host(self) -> None:
        self.error.hide()
        try:
            self.session.load_from_host()
        except (ss.SessionError, pk.PlankartaError) as exc:
            self.error.setText(str(exc))
            self.error.show()
        self.refresh()
        self.loaded.emit()

    def _plan_chosen(self, index: int) -> None:
        try:
            self.session.choose_plan(index)
        except ss.SessionError as exc:
            self.error.setText(str(exc))
            self.error.show()
        self.refresh()
        self.loaded.emit()

    def open_example(self) -> None:
        self.load(docx=EXEMPEL / "Planbeskrivning_kv_Larkan.docx", plankarta=EXEMPEL / "Detaljplan_kv_Larkan.qgz")

    def _recent(self) -> tuple[Optional[str], Optional[str]]:
        docx, plankarta = self.session.store.get("senast/docx"), self.session.store.get("senast/plankarta")
        if self.session.host is not None:
            plankarta = None
        return (docx if docx and Path(docx).exists() else None, plankarta if plankarta and Path(plankarta).exists() else None)

    def open_recent(self) -> None:
        docx, plankarta = self._recent()
        self.load(docx=docx, plankarta=plankarta)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        docx = next((p for p in paths if p.suffix.lower() == ".docx"), None)
        plankarta = next((p for p in paths if p.suffix.lower() in (".qgz", ".qgs", ".gpkg")), None)
        if self.session.host is not None:
            plankarta = None  # planen kommer från värdprogrammet
        if docx or plankarta:
            self.load(docx=docx, plankarta=plankarta)
        else:
            self.toast("Dra hit en planbeskrivning (.docx) eller en plankarta (.qgz, .qgs, .gpkg).")

    def refresh(self) -> None:
        s = self.session
        for frame_, name, path_label, path in ((self.doc_frame, self.doc_name, self.doc_path, s.docx),
                                               (self.map_frame, self.map_name, self.map_path, s.plankarta)):
            name.setText(path.name if path else "Ingen fil vald")
            path_label.setText(str(path.parent) if path else "Välj en fil eller dra den hit")
            frame_.setProperty("empty", path is None)
            restyle(frame_)
        if s.host is not None:
            self.map_name.setText(s.plan.rubrik if s.plan else "Ingen plan")
            self.map_path.setText(f"Aktiv plan i {s.host.name}")
            self.map_frame.setProperty("empty", s.plan is None)
            restyle(self.map_frame)
        if s.analysis is not None:
            a = s.analysis
            previous = f"Version {a.previous.objektversion} ({a.previous.programvara or 'okänt program'})" \
                if a.previous else "Inga"
            self.doc_facts.set([("Rubriker", str(len(a.sections))),
                                ("Avsnitt med text", str(len(s.tagged_sections()))),
                                ("Motiv", str(len(a.motives))), ("Tidigare taggning", previous)])
        else:
            self.doc_facts.set([])
        self.plan_combo.clear()
        self.plan_combo.addItems([p.rubrik for p in s.plans])
        if s.plan in s.plans:
            self.plan_combo.setCurrentIndex(s.plans.index(s.plan))
        self.plan_row.setVisible(len(s.plans) > 1)
        if s.plan is not None:
            areas = len(s.karta.areas) if s.karta else 0
            self.map_facts.set([("Plan", s.plan.namn or "–"), ("Beteckning", s.plan.beteckning or "–"),
                                ("Bestämmelser", str(len(s.plan.provisions))),
                                ("Ytor på kartan", str(areas) if areas else "Ingen geometri")])
        else:
            self.map_facts.set([])
        self.go.setEnabled(s.ready and s.plan is not None)
        self.go.setToolTip("" if self.go.isEnabled() else "Välj både planbeskrivning och plankarta.")
        docx, plankarta = self._recent()
        show_recent = bool(docx or plankarta) and s.docx is None and (s.plankarta is None or s.host is not None)
        self.recent.setVisible(show_recent)
        if show_recent:
            self.recent.setText("Öppna senaste: " + " + ".join(Path(p).name for p in (docx, plankarta) if p))


# -- steg 2 ---------------------------------------------------------------------------------------------
class SectionCard(Card):
    def __init__(self, page: "TagPage", index: int, section: dx.Avsnitt):
        self.page, self.index, self.section = page, index, section
        status = page.session.status(section)
        super().__init__(clickable=status not in (ss.RUBRIK, ss.MOTIV))
        self.chip, self.pill = TagChip(), Pill()
        level = len(section.path)
        self.heading = label(section.path[-1], "docHeading", wrap=True)
        self.heading.setProperty("level", str(level))
        rows = [box("h", self.chip, self.pill, None)] if self._clickable else []
        rows.append(self.heading)
        if self._clickable and section.text:
            rows.append(label(short(section.text, 700), "docText", wrap=True))
        self.motive_note = None
        if status == ss.MOTIV and page.is_first_motive(index):
            self.motive_note = label("", "muted", wrap=True)
            go = button("Koppla motiv  →", "small")
            go.clicked.connect(lambda: page.go.emit(3))
            rows.append(box("h", self.motive_note, go, None))
        self.setLayout(box("v", *rows, spacing=4, margins=(14, 8 if self._clickable else 2, 14, 8)))
        self.clicked.connect(lambda: page.select(index, scroll=False))
        self.refresh()

    def refresh(self) -> None:
        session, section = self.page.session, self.section
        status = session.status(section)
        i = section.indelning
        if self._clickable:
            self.chip.set(i.tema, i.grupp, i.undergrupp)
            self.pill.set(status)
            self.set_accent(theme.C["line"] if status == ss.HOPPAS else theme.tema_color(i.tema))
        if self.motive_note is not None:
            motives = session.analysis.motives
            linked = sum(1 for m in motives if session.provision(m.key))
            self.motive_note.setText(f"{len(motives)} motiv hittades under den här rubriken, {linked} är kopplade till en "
                                     "bestämmelse. Kopplingen görs i steg 3.")


class ProvisionDialog(QDialog):
    """Välj vilka bestämmelser ett avsnitt gäller (läget)."""

    def __init__(self, provisions: list, chosen: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Avsnittet gäller")
        self.provisions = [p for p in provisions if p.refs]
        self.list = QListWidget()
        for provision in self.provisions:
            item = QListWidgetItem(provision_name(provision))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if provision.key in chosen else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.setLayout(box("v", label("Kryssa i de bestämmelser texten handlar om. Inga kryss = hela planområdet.", "muted",
                                      wrap=True), self.list, buttons, margins=(16, 16, 16, 16)))
        self.resize(520, 480)

    def selected(self) -> list:
        return [p.key for n, p in enumerate(self.provisions)
                if self.list.item(n).checkState() == Qt.CheckState.Checked]


class TagPage(QWidget):
    go = Signal(int)
    changed = Signal()

    FILTERS = (("alla", "Alla"), ("granska", "Att granska"), (ss.GRANSKAD, "Granskade"), (ss.HOPPAS, "Taggas inte"))

    def __init__(self, session: ss.Session, toast):
        super().__init__()
        self.session, self.toast = session, toast
        self.setObjectName("page")
        self.selected: Optional[int] = None
        self.filter = "alla"
        self.cards: dict[int, SectionCard] = {}
        self._built_for = None
        self._loading = False

        # vänster: avsnitt
        self.filter_buttons = QButtonGroup(self)
        filters = box("h", spacing=6)
        for key, text in self.FILTERS:
            b = button(text, "filter")
            b.setCheckable(True)
            b.setChecked(key == self.filter)
            b.clicked.connect(lambda _=False, k=key: self.set_filter(k))
            self.filter_buttons.addButton(b)
            filters.addWidget(b)
        filters.addStretch(1)
        self.outline = QListWidget()
        self.outline.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.outline.itemClicked.connect(lambda item: self.select(item.data(Qt.ItemDataRole.UserRole), scroll=True))
        self.summary = label("", "hint", wrap=True)
        left = frame("sideLeft", box("v", label("Avsnitt", "h2"), filters, self.summary, self.outline,
                                     spacing=10, margins=(12, 14, 6, 6)))

        # mitten: dokumentet
        self.doc_layout = QVBoxLayout()
        self.doc_layout.setSpacing(6)
        self.doc_title, self.doc_sub = label("", "docTitle", wrap=True), label("", "hint")
        page = frame("docPage", box("v", self.doc_title, self.doc_sub, 12, self.doc_layout, None,
                                    margins=(48, 40, 48, 48)))
        page.setMaximumWidth(820)
        holder = QWidget()
        holder.setLayout(box("h", None, page, None, margins=(16, 20, 16, 40)))
        self.doc_scroll = scrolled(holder)

        # höger: inställningar för valt avsnitt
        self.insp_heading, self.insp_pill = label("", "h3", wrap=True), Pill()
        self.why = label("", wrap=True)
        why_frame = frame("why", box("v", label("VARFÖR", "eyebrow"), self.why, spacing=4, margins=(12, 10, 12, 10)))
        self.tema, self.grupp, self.undergrupp = QComboBox(), QComboBox(), QComboBox()
        for combo in (self.grupp, self.undergrupp):
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.lineEdit().editingFinished.connect(self.apply)
            combo.activated.connect(self.apply)
        self.tema.addItem("Välj tema…", "")
        for tema in pb.temas():
            if tema != pb.MOTIV_TEMA:
                self.tema.addItem(tema, tema)
        self.tema.activated.connect(self._tema_chosen)
        self.lage_all = QRadioButton("Hela planområdet")
        self.lage_some = QRadioButton("Vissa planbestämmelser")
        self.lage_all.toggled.connect(self._lage_toggled)
        self.lage_text = label("", "hint", wrap=True)
        self.lage_button = button("Välj bestämmelser…", "small")
        self.lage_button.clicked.connect(self.choose_lage)
        self.approve_button = button("Godkänn", "primary")
        self.approve_button.clicked.connect(self.approve)
        self.skip_button = button("Tagga inte")
        self.skip_button.clicked.connect(self.toggle_skip)
        self.next_button = button("Nästa att granska  →", "ghost")
        self.next_button.clicked.connect(lambda: self.next_to_review(quiet=False))
        self.inspector = QWidget()
        self.inspector.setLayout(box(
            "v", label("VALT AVSNITT", "eyebrow"), self.insp_heading, box("h", self.insp_pill, None), why_frame,
            label("Tema", "muted"), self.tema, label("Grupp", "muted"), self.grupp,
            label("Undergrupp", "muted"), self.undergrupp, 6, label("Läge: vad texten gäller", "muted"),
            self.lage_all, self.lage_some, box("h", self.lage_text, self.lage_button), 8,
            box("h", self.approve_button, self.skip_button, None), self.next_button,
            label("Tangenter: J och K bläddrar, Enter godkänner.", "hint", wrap=True), None,
            spacing=6, margins=(16, 16, 16, 16)))
        self.empty_inspector = label("Välj ett avsnitt i listan eller i texten.", "muted", wrap=True)
        self.empty_inspector.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right = frame("sideRight", box("v", scrolled(self.inspector), self.empty_inspector))

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.doc_scroll)
        splitter.addWidget(right)
        splitter.setSizes([280, 760, 360])
        splitter.setChildrenCollapsible(False)
        self.setLayout(box("v", splitter))

    # -- bygga upp ----------------------------------------------------------------------------------
    def is_first_motive(self, index: int) -> bool:
        sections = self.session.analysis.sections
        return sections[index].indelning.tema == pb.MOTIV_TEMA and (
            index == 0 or sections[index - 1].indelning.tema != pb.MOTIV_TEMA)

    def refresh(self) -> None:
        analysis = self.session.analysis
        if analysis is None:
            return
        if self._built_for is not analysis:
            self._build(analysis)
        for card in self.cards.values():
            card.refresh()
        self._fill_outline()
        if self.selected is None or self.selected >= len(analysis.sections):
            first = next((n for n, s in enumerate(analysis.sections)
                          if self.session.status(s) in ss.NEEDS_LOOK), None)
            first = first if first is not None else next(
                (n for n, s in enumerate(analysis.sections) if s in self.session.tagged_sections()), None)
            self.select(first, scroll=True) if first is not None else self._show_inspector()
        else:
            self._show_inspector()

    def _build(self, analysis: dx.Analys) -> None:
        while self.doc_layout.count():
            item = self.doc_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards = {}
        for n, section in enumerate(analysis.sections):
            card = SectionCard(self, n, section)
            self.cards[n] = card
            self.doc_layout.addWidget(card)
        plan = self.session.plan
        self.doc_title.setText(plan.namn if plan and plan.namn else (self.session.docx.stem if self.session.docx else ""))
        self.doc_sub.setText(self.session.docx.name if self.session.docx else "")
        self._built_for = analysis
        self.selected = None

    def _fill_outline(self) -> None:
        session = self.session
        counts = session.counts()
        review = sum(counts[s] for s in ss.NEEDS_LOOK)
        totals = {"alla": len(session.tagged_sections()), "granska": review,
                  ss.GRANSKAD: counts[ss.GRANSKAD], ss.HOPPAS: counts[ss.HOPPAS]}
        for b, (key, text) in zip(self.filter_buttons.buttons(), self.FILTERS):
            b.setText(f"{text}  {totals[key]}")
        tagged = counts[ss.AUTO] + counts[ss.EGEN] + counts[ss.GRANSKAD] + counts[ss.OSAKER]
        self.summary.setText(f"{tagged} av {totals['alla']} avsnitt får en tagg. "
                             + (f"{review} behöver granskas." if review else "Inget behöver granskas."))
        self.outline.clear()
        for n, section in enumerate(session.analysis.sections):
            status = session.status(section)
            if status in (ss.RUBRIK, ss.MOTIV) or not self._visible(status):
                continue
            item = QListWidgetItem(_dot_icon(QColor(theme.status_color(status))),
                                   ("   " * (len(section.path) - 1)) + section.path[-1])
            item.setData(Qt.ItemDataRole.UserRole, n)
            item.setToolTip(" › ".join(section.path) + f"\n{ss.STATUS_TEXT[status]}")
            item.setSizeHint(QSize(0, 30))
            self.outline.addItem(item)
            if n == self.selected:
                item.setSelected(True)
                self.outline.setCurrentItem(item)
        if not self.outline.count():
            empty = QListWidgetItem("Inga avsnitt i det här urvalet.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.outline.addItem(empty)

    def _visible(self, status: str) -> bool:
        if self.filter == "alla":
            return True
        if self.filter == "granska":
            return status in ss.NEEDS_LOOK
        return status == self.filter

    def set_filter(self, key: str) -> None:
        self.filter = key
        self._fill_outline()

    # -- välja ---------------------------------------------------------------------------------------
    def select(self, index: Optional[int], scroll: bool = False) -> None:
        if index is None or index not in self.cards or not self.cards[index]._clickable:
            return
        if self.selected in self.cards:
            self.cards[self.selected].set_selected(False)
        self.selected = index
        card = self.cards[index]
        card.set_selected(True)
        if scroll:
            self.doc_scroll.ensureWidgetVisible(card, 0, 120)
        for row in range(self.outline.count()):
            item = self.outline.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == index:
                self.outline.setCurrentItem(item)
                self.outline.scrollToItem(item)
                break
        else:
            self.outline.clearSelection()
        self._show_inspector()
        self.setFocus()

    def current(self) -> Optional[dx.Avsnitt]:
        if self.session.analysis is None or self.selected is None:
            return None
        return self.session.analysis.sections[self.selected]

    def _show_inspector(self) -> None:
        section = self.current()
        self.inspector.setVisible(section is not None)
        self.empty_inspector.setVisible(section is None)
        if section is None:
            return
        self._loading = True
        session, i = self.session, section.indelning
        status = session.status(section)
        self.insp_heading.setText(" › ".join(section.path))
        self.insp_pill.set(status)
        self.why.setText(session.why(section))
        self.tema.setCurrentIndex(max(0, self.tema.findData(i.tema or "")))
        self._fill_groups(i.tema)
        self.grupp.setCurrentText(i.grupp or "")
        self._fill_subgroups(i.tema, i.grupp)
        self.undergrupp.setCurrentText(i.undergrupp or "")
        self.undergrupp.setEnabled(len(section.path) >= 3)
        self.undergrupp.setToolTip("" if len(section.path) >= 3 else
                                   "Undergrupp kräver en tredje rubriknivå i dokumentet (Rubrik 3).")
        chosen = [p for p in session.provisions if p.key in section.lage_keys and p.refs]
        self.lage_all.setChecked(not chosen)
        self.lage_some.setChecked(bool(chosen))
        self.lage_text.setText(", ".join(p.label or short(p.text, 30) for p in chosen) if chosen else "")
        self.lage_button.setEnabled(bool(session.provisions))
        self.approve_button.setEnabled(status in (ss.AUTO, ss.EGEN, ss.OSAKER))
        self.skip_button.setText("Tagga igen" if status == ss.HOPPAS else "Tagga inte")
        self._loading = False

    def _fill_groups(self, tema) -> None:
        self.grupp.clear()
        self.grupp.addItems(pb.grupper(tema))

    def _fill_subgroups(self, tema, grupp) -> None:
        self.undergrupp.clear()
        self.undergrupp.addItem("")
        self.undergrupp.addItems(pb.undergrupper(tema, grupp))

    # -- ändra -----------------------------------------------------------------------------------------
    def _tema_chosen(self, _index: int) -> None:
        if self._loading:
            return
        tema = self.tema.currentData()
        if not tema:
            return
        current = self.grupp.currentText()
        self._fill_groups(tema)
        groups = pb.grupper(tema)
        section = self.current()
        own = section is not None and len(section.path) >= 2 and current and pb.canonical(current, groups) is None
        self.grupp.setCurrentText(pb.canonical(current, groups) or (current if own else (groups[0] if groups else "")))
        self.apply()

    def apply(self, *_) -> None:
        section = self.current()
        if self._loading or section is None:
            return
        tema = self.tema.currentData() or ""
        grupp, undergrupp = self.grupp.currentText().strip(), self.undergrupp.currentText().strip()
        i = section.indelning
        if (tema, grupp, undergrupp) == (i.tema or "", i.grupp or "", i.undergrupp or "") and \
                self.session.status(section) != ss.HOPPAS:
            return
        if not tema:
            return
        self.session.set_indelning(section, tema, grupp, undergrupp)
        self._after_change("Sparat. Samma val används för rubriken nästa gång.")

    def approve(self) -> None:
        section = self.current()
        if section is None or not self.approve_button.isEnabled():
            return
        self.session.approve(section)
        self._after_change(f"Godkänt: {section.path[-1]}")
        self.next_to_review(quiet=True)

    def toggle_skip(self) -> None:
        section = self.current()
        if section is None:
            return
        skip = self.session.status(section) != ss.HOPPAS
        self.session.skip(section, skip)
        self._after_change(f"\"{section.path[-1]}\" taggas inte." if skip else f"\"{section.path[-1]}\" taggas igen.")

    def _lage_toggled(self, whole: bool) -> None:
        section = self.current()
        if self._loading or section is None:
            return
        if whole and section.lage_keys:
            self.session.set_lage(section, [])
            self._after_change("Avsnittet gäller hela planområdet.")
        elif not whole and not section.lage_keys:
            self.choose_lage()

    def choose_lage(self) -> None:
        section = self.current()
        if section is None:
            return
        dialog = ProvisionDialog(self.session.provisions, section.lage_keys, self)
        if dialog.exec():
            self.session.set_lage(section, dialog.selected())
            self._after_change("Läget är sparat.")
        else:
            self._show_inspector()

    def _after_change(self, message: str) -> None:
        for card in self.cards.values():
            card.refresh()
        self._fill_outline()
        self._show_inspector()
        self.changed.emit()
        if message:
            self.toast(message)

    def next_to_review(self, quiet: bool = False) -> None:
        sections = self.session.analysis.sections if self.session.analysis else []
        start = (self.selected or 0) + 1
        order = list(range(start, len(sections))) + list(range(0, start))
        found = next((n for n in order if self.session.status(sections[n]) in ss.NEEDS_LOOK), None)
        if found is not None:
            self.select(found, scroll=True)
        elif not quiet:
            self.toast("Inga fler avsnitt att granska.")

    def step(self, delta: int) -> None:
        visible = [self.outline.item(r).data(Qt.ItemDataRole.UserRole) for r in range(self.outline.count())]
        visible = [v for v in visible if v is not None]
        if not visible:
            return
        if self.selected in visible:
            target = visible[(visible.index(self.selected) + delta) % len(visible)]
        else:
            target = visible[0]
        self.select(target, scroll=True)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_J:
            self.step(1)
        elif key == Qt.Key.Key_K:
            self.step(-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.approve()
        else:
            super().keyPressEvent(event)


def _dot_icon(color: QColor) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(2, 2, 8, 8)
    painter.end()
    return QIcon(pixmap)


# -- steg 3 ---------------------------------------------------------------------------------------------
class MotiveCard(Card):
    def __init__(self, page: "MotivPage", index: int, motive: dx.Motiv):
        super().__init__()
        self.page, self.index, self.motive = page, index, motive
        title = " – ".join(p for p in (motive.label, short(motive.title, 90)) if p)
        self.pill = Pill()
        self.link_text = label("", rich=True)
        self.unlink = button("×", "ghost", "Ta bort kopplingen")
        self.unlink.setFixedWidth(30)
        self.unlink.clicked.connect(lambda: page.link(self.index, None))
        where = label(" › ".join(motive.path[1:]) or " › ".join(motive.path), "hint")
        rows = [box("h", label(title, "docHeading", wrap=True), self.pill), where]
        if motive.motiv.strip():
            rows.append(label(short(motive.motiv, 420), "docText", wrap=True))
        rows.append(box("h", self.link_text, self.unlink, None))
        self.setLayout(box("v", *rows, spacing=5, margins=(14, 10, 14, 10)))
        self.clicked.connect(lambda: page.select_motive(index))
        self._drag_start = None
        self.refresh()

    def refresh(self) -> None:
        session = self.page.session
        status = session.motive_status(self.motive)
        provision = session.provision(self.motive.key)
        names = {ss.KOPPLAT_AUTO: ("auto", "Automatiskt kopplat"), ss.KOPPLAT: ("granskad", "Kopplat"),
                 ss.EJ_KOPPLAT: ("saknas", "Saknar bestämmelse")}
        pill_status, text = names[status]
        self.pill.set(pill_status, text)
        c = theme.C
        if provision is not None:
            self.link_text.setText(
                f'<span style="font-family:Consolas; font-weight:700">{html.escape(provision.label or "")}</span> '
                f'{html.escape(short(provision.text, 70))}'
                + (f' <span style="color:{c["muted"]}">· {len(provision.refs)} ytor</span>' if len(provision.refs) > 1 else ""))
            self.link_text.setStyleSheet(f"QLabel {{ background: {c['accent_soft']}; border: 1px solid {c['accent']}; "
                                         "border-radius: 6px; padding: 3px 8px; }")
        else:
            self.link_text.setText("Välj bestämmelse i listan till höger, eller dra motivet dit.")
            self.link_text.setStyleSheet(f"QLabel {{ color: {c['bad']}; }}")
        self.unlink.setVisible(provision is not None)
        self.set_accent(c["accent"] if provision is not None else c["bad"])

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        data = QMimeData()
        data.setData(MOTIV_MIME, str(self.index).encode())
        data.setText(self.motive.label or self.motive.title)
        drag.setMimeData(data)
        drag.setPixmap(self.grab().scaledToWidth(min(self.width(), 320), Qt.TransformationMode.SmoothTransformation))
        self._drag_start = None
        drag.exec(Qt.DropAction.LinkAction | Qt.DropAction.CopyAction)


class ProvisionList(QListWidget):
    dropped = Signal(int, int)  # motivets index, bestämmelsens index
    hovered = Signal(object)  # bestämmelsens index eller None

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setMouseTracking(True)
        self.itemEntered.connect(lambda item: self.hovered.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hovered.emit(None)
        super().leaveEvent(event)

    def _index_at(self, event):
        item = self.itemAt(event.position().toPoint())
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(MOTIV_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event)
        if event.mimeData().hasFormat(MOTIV_MIME) and index is not None:
            item = self.itemAt(event.position().toPoint())
            self.setCurrentItem(item)
            self.hovered.emit(index)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event)
        if event.mimeData().hasFormat(MOTIV_MIME) and index is not None:
            self.dropped.emit(int(bytes(event.mimeData().data(MOTIV_MIME)).decode()), index)
            event.acceptProposedAction()


class MotivPage(QWidget):
    changed = Signal()

    def __init__(self, session: ss.Session, toast):
        super().__init__()
        self.session, self.toast = session, toast
        self.setObjectName("page")
        self.selected: Optional[int] = None
        self.pinned: Optional[int] = None
        self.cards: dict[int, MotiveCard] = {}
        self._built_for = None

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(160)
        self.progress_text = label("", "muted")
        head = box("h", box("v", label("Koppla motiv till planbestämmelser", "h2"),
                            label("Klicka på ett motiv och sedan på en bestämmelse till höger, eller dra motivet till "
                                  "bestämmelsen. Klicka på samma bestämmelse igen för att ta bort kopplingen.", "hint",
                                  wrap=True), spacing=2),
                   box("h", self.progress, self.progress_text), margins=(20, 16, 20, 12), spacing=24)
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(10)
        holder = QWidget()
        holder.setLayout(box("v", self.list_layout, None, margins=(20, 4, 20, 40)))
        self.scroll = scrolled(holder)
        left = QWidget()
        left.setLayout(box("v", head, self.scroll, spacing=0))

        self.map = MapView()
        self.map_hint = label("Peka på en bestämmelse för att se var den gäller.", "hint", wrap=True)
        self.map_box = QWidget()
        self.map_box.setLayout(box("v", label("PLANKARTA", "eyebrow"), self.map, self.map_hint, spacing=6))
        self.provisions = ProvisionList()
        self.provisions.itemClicked.connect(self._provision_clicked)
        self.provisions.dropped.connect(self._dropped)
        self.provisions.hovered.connect(self._hovered)
        right = frame("sideRight", box("v", self.map_box, label("BESTÄMMELSER I PLANEN", "eyebrow"), self.provisions,
                                       spacing=8, margins=(14, 14, 10, 10)))
        right.setMinimumWidth(360)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([820, 440])
        splitter.setChildrenCollapsible(False)
        self.setLayout(box("v", splitter))

    def refresh(self) -> None:
        analysis = self.session.analysis
        if analysis is None:
            return
        if self._built_for is not analysis:
            self._build(analysis)
        for card in self.cards.values():
            card.refresh()
            card.set_selected(card.index == self.selected)
        self._fill_provisions()
        needed = [p for p in self.session.provisions if p.refs and not p.technical]
        missing = len(self.session.provisions_without_motive())
        self.progress.setMaximum(max(1, len(needed)))
        self.progress.setValue(len(needed) - missing)
        self.progress_text.setText(f"{len(needed) - missing} av {len(needed)} bestämmelser har motiv")
        self.map_box.setVisible(self.map.has_content())

    def _build(self, analysis: dx.Analys) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards = {}
        for n, motive in enumerate(analysis.motives):
            card = MotiveCard(self, n, motive)
            self.cards[n] = card
            self.list_layout.addWidget(card)
        if not analysis.motives:
            self.list_layout.addWidget(label(
                "Inga motiv hittades i planbeskrivningen. Motiven ska stå under rubriken \"Motiv till detaljplanens "
                "regleringar\", i en tabell eller i löpande text som börjar med bestämmelsens beteckning (t.ex. \"e1\").",
                "muted", wrap=True))
        for section in analysis.uncovered:
            warning = Card(theme.C["warn"], clickable=False)
            warning.setLayout(box("v", label(" › ".join(section.path), "docHeading", wrap=True),
                                  label("Avsnittet handlar om motiv, men ingen bestämmelse kunde kopplas till texten. "
                                        "Skriv bestämmelsens beteckning eller text först i stycket, eller använd en "
                                        "tabell.", "muted", wrap=True), margins=(14, 8, 14, 8)))
            self.list_layout.addWidget(warning)
        self.map.set_karta(self.session.karta)
        self._built_for = analysis
        self.selected = next((n for n, m in enumerate(analysis.motives)
                              if self.session.motive_status(m) == ss.EJ_KOPPLAT), 0 if analysis.motives else None)
        self.pinned = None

    def _fill_provisions(self) -> None:
        session = self.session
        selected_key = session.analysis.motives[self.selected].key if self.selected is not None else None
        self.provisions.clear()
        last_kind = None
        for n, provision in enumerate(session.provisions):
            kind = session.plan.kinds.get(provision.key, "")
            if kind != last_kind:
                head = QListWidgetItem(pk.KIND_NAMES.get(kind, "Övrigt").upper())
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                self.provisions.addItem(head)
                last_kind = kind
            count = len(session.motives_for(provision.key))
            state = ("fast motiv" if provision.technical else
                     ("✓ valt motiv" if provision.key == selected_key and selected_key is not None else
                      (f"✓ {count} motiv" if count else "saknar motiv")))
            item = QListWidgetItem(f"{provision.label or '–'}\t{short(provision.text, 60)}\n\t{state}"
                                   + (f" · {len(provision.refs)} ytor" if len(provision.refs) > 1 else ""))
            item.setData(Qt.ItemDataRole.UserRole, n)
            item.setToolTip(provision_name(provision))
            if not count and not provision.technical:
                item.setForeground(QColor(theme.C["warn"]))
            if provision.key == selected_key and selected_key is not None:
                item.setBackground(QColor(theme.C["accent_soft"]))
            self.provisions.addItem(item)
            if n == self.pinned:
                self.provisions.setCurrentItem(item)

    def select_motive(self, index: int) -> None:
        self.selected = index
        motive = self.session.analysis.motives[index]
        key = motive.key
        self.pinned = next((n for n, p in enumerate(self.session.provisions) if p.key == key), None)
        self.refresh()
        self._highlight(self.pinned)

    def _provision_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        self.pinned = index
        if self.selected is not None:
            motive = self.session.analysis.motives[self.selected]
            provision = self.session.provisions[index]
            self.link(self.selected, None if motive.key == provision.key else provision.key)
        else:
            self._highlight(index)

    def _dropped(self, motive_index: int, provision_index: int) -> None:
        self.selected, self.pinned = motive_index, provision_index
        self.link(motive_index, self.session.provisions[provision_index].key)

    def link(self, motive_index: int, key) -> None:
        motive = self.session.analysis.motives[motive_index]
        self.session.link(motive, key)
        provision = self.session.provision(key)
        name = motive.label or short(motive.title, 40)
        self.toast(f"\"{name}\" kopplat till {provision.label or short(provision.text, 40)}" if provision
                   else f"Kopplingen för \"{name}\" är borttagen.")
        self.refresh()
        self._highlight(self.pinned)
        self.changed.emit()

    def _hovered(self, index) -> None:
        self._highlight(index if index is not None else self.pinned)

    def _highlight(self, index) -> None:
        session = self.session
        if index is None or session.plan is None or not 0 <= index < len(session.provisions):
            self.map.highlight(())
            self.map_hint.setText("Peka på en bestämmelse för att se var den gäller.")
            return
        provision = session.provisions[index]
        self.map.highlight(session.plan.areas.get(provision.key, ()))
        self.map_hint.setText(provision_name(provision))

    def focus_provision(self, key) -> None:
        self.pinned = next((n for n, p in enumerate(self.session.provisions) if p.key == key), None)
        self.selected = None
        self.refresh()
        self._highlight(self.pinned)


# -- steg 4 ---------------------------------------------------------------------------------------------
class ExportPage(QWidget):
    open_section = Signal(int)
    open_provision = Signal(object)
    open_motive = Signal(int)

    def __init__(self, session: ss.Session, toast):
        super().__init__()
        self.session, self.toast = session, toast
        self.setObjectName("page")
        self.check_summary = label("", "muted", wrap=True)
        self.findings_layout = QVBoxLayout()
        self.findings_layout.setSpacing(0)
        checks = frame("panel", box("v", self.findings_layout, margins=(0, 4, 0, 4)))
        self.result = label("", wrap=True, rich=True)
        self.result.setOpenExternalLinks(False)
        self.result.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl.fromLocalFile(url)))
        self.result.hide()
        exports = box("v", spacing=10)
        self.delivery = self._export_row(exports, "Leveranskopia", "Word-fil med bokmärken och XML-del, utan kommentarer. "
                                         "Den här lämnas in.", "Spara…", self.save_delivery, primary=True)
        self._export_row(exports, "Granskningskopia", "Samma text med en kommentar per avsnitt som visar taggen. För dig "
                         "och kollegor som granskar i Word.", "Spara…", self.save_review)
        if session.host is not None:
            self._export_row(exports, f"Till planen i {session.host.name}",
                             "Lägger syftet och motiven ur planbeskrivningen på planen och dess bestämmelser (de ersätter "
                             "det som stod). Spara planen som vanligt efteråt.", "Importera till planen",
                             self.write_to_host)
        else:
            self._export_row(exports, "Till Rita Detaljplan", "Syfte och motiv per bestämmelse, så att pluginet kan "
                             "läsa in dem på plankartan.", "Exportera…", self.save_exchange)
        self._export_row(exports, "Översikt över taggarna", "Tabell (CSV) som öppnas i Excel: bokmärke, rubrik, tema, "
                         "grupp, undergrupp och läge.", "Spara…", self.save_overview)
        export_panel = frame("panel", box("v", label("Spara och exportera", "h2"), exports, self.result,
                                          spacing=12, margins=(16, 16, 16, 16)))
        left = QWidget()
        left.setLayout(box("v", label("Kontroll", "h2"), self.check_summary, checks, 8, export_panel, None,
                           spacing=8, margins=(20, 20, 10, 20)))
        self.xml = QPlainTextEdit()
        self.xml.setObjectName("xml")
        self.xml.setReadOnly(True)
        self.xml.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        copy = button("Kopiera", "small")
        copy.clicked.connect(self._copy)
        right = frame("panel", box("v", box("h", box("v", label("XML-del som läggs i Word-filen", "h2"),
                                                       label("customXML enligt Planbeskrivning 2.0. Uppdateras när du "
                                                             "ändrar något.", "hint", wrap=True), spacing=2), None, copy),
                                   self.xml, spacing=10, margins=(16, 16, 16, 16)))
        holder = QWidget()
        holder.setLayout(box("v", right, margins=(10, 20, 20, 20)))
        splitter = QSplitter()
        splitter.addWidget(scrolled(left))
        splitter.addWidget(holder)
        splitter.setSizes([640, 620])
        splitter.setChildrenCollapsible(False)
        self.setLayout(box("v", splitter))

    def _export_row(self, layout, title, text, action, slot, primary=False):
        b = button(action, "primary" if primary else "small")
        b.clicked.connect(slot)
        row = QFrame()
        row.setObjectName("chosen")
        row.setLayout(box("h", box("v", label(title, "fileName"), label(text, "hint", wrap=True), spacing=2), b,
                          spacing=12, margins=(12, 10, 12, 10)))
        layout.addWidget(row)
        return b

    def refresh(self) -> None:
        session = self.session
        if session.analysis is None:
            return
        while self.findings_layout.count():
            item = self.findings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        findings = session.findings()
        errors, warnings = ck.counts(findings)
        self.check_summary.setText(
            f"{errors} fel och {warnings} varningar mot BFS 2020:8 och Lantmäteriets regler." if errors or warnings
            else "Inga fel eller varningar. Leveranskopian kan sparas.")
        for n, finding in enumerate(findings):
            self.findings_layout.addWidget(self._finding_row(finding, first=n == 0))
        self.xml.setPlainText(session.xml_preview())

    def _finding_row(self, finding: ck.Fynd, first: bool) -> QWidget:
        c = theme.C
        color = {ck.FEL: c["bad"], ck.VARNING: c["warn"], ck.INFO: c["info"]}[finding.allvarlighet]
        icon = label({ck.FEL: "×", ck.VARNING: "!", ck.INFO: "i"}[finding.allvarlighet])
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(22, 22)
        icon.setStyleSheet(f"QLabel {{ background: {theme.mix(color, .16)}; color: {color}; border-radius: 11px; "
                           "font-weight: 700; }")
        details = " · ".join(p for p in (finding.var, finding.krav) if p)
        texts = box("v", label(finding.text, wrap=True), label(details, "hint", wrap=True) if details else None, spacing=2)
        action = self._action_for(finding)
        row = QFrame()
        row.setStyleSheet("" if first else f"QFrame {{ border-top: 1px solid {c['line2']}; }} QLabel {{ border: 0; }}")
        items = [icon, texts]
        if action is not None:
            go = button("Gå till", "small")
            go.clicked.connect(action)
            items.append(go)
        layout = box("h", *items, spacing=10, margins=(14, 10, 14, 10))
        layout.setAlignment(icon, Qt.AlignmentFlag.AlignTop)
        row.setLayout(layout)
        return row

    def _action_for(self, finding: ck.Fynd):
        session = self.session
        section = session.section_for(finding.var)
        if section is not None:
            index = session.analysis.sections.index(section)
            if session.status(section) == ss.MOTIV:
                return None
            return lambda: self.open_section.emit(index)
        provision = next((p for p in session.provisions if f"{p.label} {p.text}".strip() == finding.var), None)
        if provision is not None:
            return lambda: self.open_provision.emit(provision.key)
        for n, motive in enumerate(session.analysis.motives):
            name = motive.label or motive.title[:60]
            if finding.var in (name, f"{name} ({' › '.join(motive.path[-1:])})"):
                return lambda n=n: self.open_motive.emit(n)
        return None

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.xml.toPlainText())
        self.toast("XML-delen är kopierad.")

    def _ask_path(self, title: str, suffix: str, extension: str, pattern: str) -> Optional[Path]:
        path, _ = QFileDialog.getSaveFileName(self, title, str(self.session.default_name(suffix, extension)), pattern)
        return Path(path) if path else None

    def _done(self, path: Path, text: str) -> None:
        folder = html.escape(str(path.parent))
        self.result.setText(f"{html.escape(text)}<br><a href=\"{html.escape(str(path))}\">Öppna filen</a> · "
                            f"<a href=\"{folder}\">Öppna mappen</a>")
        self.result.show()
        self.toast(text)

    def _fail(self, exc: Exception) -> None:
        self.result.setText(f'<span style="color:{theme.C["bad"]}">{html.escape(str(exc))}</span>')
        self.result.show()

    def save_delivery(self) -> None:
        errors, _ = ck.counts(self.session.findings())
        if errors and QMessageBox.question(
                self, "Spara leveranskopia", f"Kontrollen visar {errors} fel. Vill du spara leveranskopian ändå?") \
                != QMessageBox.StandardButton.Yes:
            return
        path = self._ask_path("Spara leveranskopia", "_leverans", ".docx", "Word-dokument (*.docx)")
        if path:
            try:
                result = self.session.write_copy(path)
            except ss.SessionError as exc:
                return self._fail(exc)
            self._done(path, f"Sparade {path.name}: {result.avsnitt} avsnitt och {result.motiv} motiv är taggade "
                             f"(version {result.version}).")

    def save_review(self) -> None:
        path = self._ask_path("Spara granskningskopia", "_granskning", ".docx", "Word-dokument (*.docx)")
        if path:
            try:
                result = self.session.write_copy(path, review=True)
            except ss.SessionError as exc:
                return self._fail(exc)
            self._done(path, f"Sparade {path.name} med {result.kommentarer} kommentarer. Lämna inte in den här kopian.")

    def write_to_host(self) -> None:
        try:
            message = self.session.write_back()
        except ss.SessionError as exc:
            return self._fail(exc)
        self.result.setText(html.escape(message))
        self.result.show()
        self.toast(message)

    def save_exchange(self) -> None:
        path = self._ask_path("Exportera till Rita Detaljplan", "_motiv", ".json", "Utbytesfil (*.json)")
        if path:
            try:
                data = self.session.write_exchange(path)
            except ss.SessionError as exc:
                return self._fail(exc)
            self._done(path, f"Exporterade syftet och {len(data['motiv'])} motiv till {path.name}.")

    def save_overview(self) -> None:
        path = self._ask_path("Spara översikt", "_taggar", ".csv", "Tabell (*.csv)")
        if path:
            try:
                self.session.write_overview(path)
            except OSError as exc:
                return self._fail(exc)
            self._done(path, f"Sparade översikten {path.name}.")
