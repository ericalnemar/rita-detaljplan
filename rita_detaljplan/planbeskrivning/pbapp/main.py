"""Huvudfönstret: toppfält med stegen och en sida per steg."""
from __future__ import annotations

import sys
from pathlib import Path

from .qt.QtCore import QByteArray, QSettings, QSize, Qt
from .qt.QtGui import QIcon, QPainter, QPixmap
from .qt.QtSvg import QSvgRenderer
from .qt.QtWidgets import QApplication, QButtonGroup, QFrame, QMainWindow, QStackedWidget, QWidget

from . import APP_NAME, SETTINGS_NAME, VERSION
from . import session as ss
from . import theme
from .pages import ExportPage, FilesPage, MotivPage, TagPage
from .widgets import Toast, box, button, label

ICON_FILE = Path(__file__).resolve().parents[2] / "icons" / "planbeskrivning.svg"  # samma ikon som knappen i verktygsfältet

STEPS = ("Filer", "Taggning", "Motiv", "Kontroll och export")


def logo_pixmap(size: int = 28) -> QPixmap:
    """Programmets ikon: verktygsfältets ikon för Tagga planbeskrivning (``rita_detaljplan/icons/planbeskrivning.svg``)."""
    renderer = QSvgRenderer(QByteArray(ICON_FILE.read_bytes()))
    pixmap = QPixmap(QSize(size, size) * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


def settings_store() -> ss.Store:
    settings = QSettings("Planbeskrivning", SETTINGS_NAME)

    def get(key):
        value = settings.value(key)
        return str(value) if value is not None else None

    return ss.Store(get, lambda key, value: settings.setValue(key, value))


class MainWindow(QMainWindow):
    def __init__(self, session: ss.Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setStyleSheet(theme.load())  # bara det här fönstret, inte hela applikationen (QGIS)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(logo_pixmap(64)))
        self.resize(1380, 880)
        self.toast = Toast(self)

        logo = label()
        logo.setPixmap(logo_pixmap())
        brand = box("h", logo, box("v", label(APP_NAME, "brand"), label("Taggning enligt BFS 2020:8", "brandSub"),
                                   spacing=0), spacing=10)
        self.steps = QButtonGroup(self)
        self.steps.setExclusive(True)
        steps = box("h", spacing=4)
        for n, name in enumerate(STEPS, 1):
            b = button(f"{n}   {name}")
            b.setObjectName("step")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, n=n: self.go(n))
            self.steps.addButton(b, n)
            steps.addWidget(b)
        self.file_hint = label("", "fileHint")
        version = label(f"v{VERSION}", "hint")
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setLayout(box("h", brand, 24, steps, None, self.file_hint, 12, version, margins=(16, 10, 16, 10)))

        self.files = FilesPage(session, self.show_toast)
        self.tag = TagPage(session, self.show_toast)
        self.motiv = MotivPage(session, self.show_toast)
        self.export = ExportPage(session, self.show_toast)
        self.stack = QStackedWidget()
        for page in (self.files, self.tag, self.motiv, self.export):
            self.stack.addWidget(page)
        self.files.loaded.connect(self._loaded)
        self.files.proceed.connect(lambda: self.go(2))
        self.tag.go.connect(self.go)
        self.export.open_section.connect(self._open_section)
        self.export.open_provision.connect(self._open_provision)
        self.export.open_motive.connect(self._open_motive)

        central = QWidget()
        central.setLayout(box("v", bar, self.stack, spacing=0))
        self.setCentralWidget(central)
        self.go(1)

    def show_toast(self, text: str) -> None:
        self.toast.show_text(text)

    def _loaded(self) -> None:
        s = self.session
        parts = [p for p in (s.docx.name if s.docx else "", s.plan.rubrik if s.plan else "") if p]
        self.file_hint.setText("   ·   ".join(parts))
        self._enable_steps()

    def _enable_steps(self) -> None:
        ready = self.session.ready and self.session.plan is not None
        for n in (2, 3, 4):
            self.steps.button(n).setEnabled(ready)

    def go(self, step: int) -> None:
        if step > 1 and not (self.session.ready and self.session.plan is not None):
            step = 1
        self.steps.button(step).setChecked(True)
        page = (self.files, self.tag, self.motiv, self.export)[step - 1]
        page.refresh()
        self.stack.setCurrentWidget(page)
        self._enable_steps()
        if step == 2:
            self.tag.setFocus()

    def _open_section(self, index: int) -> None:
        self.go(2)
        self.tag.filter = "alla"
        self.tag.refresh()
        self.tag.select(index, scroll=True)

    def _open_provision(self, key) -> None:
        self.go(3)
        self.motiv.focus_provision(key)

    def _open_motive(self, index: int) -> None:
        self.go(3)
        self.motiv.select_motive(index)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.move((self.width() - self.toast.width()) // 2, self.height() - self.toast.height() - 24)


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName("Planbeskrivning")
    app = QApplication(argv)
    app.setStyle("Fusion")
    window = MainWindow(ss.Session(settings_store()))
    files = argv[1:]
    if files:
        docx = next((f for f in files if f.lower().endswith(".docx")), None)
        plankarta = next((f for f in files if f.lower().endswith((".qgz", ".qgs", ".gpkg"))), None)
        window.files.load(docx=docx, plankarta=plankarta)
    window.show()
    return app.exec()


def open_in_host(host: ss.Host, parent=None, store: ss.Store | None = None) -> MainWindow:
    """Öppnar programmet inuti ett annat program (Rita Detaljplan i QGIS) med värdens aktiva plan förvald. Fönstret
    är ett eget fönster (inte modalt), så att man kan arbeta i QGIS samtidigt."""
    window = MainWindow(ss.Session(store or settings_store(), host), parent)
    window.setWindowFlag(Qt.WindowType.Window, True)
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    window.files.reload_from_host()
    window.show()
    window.raise_()
    window.activateWindow()
    return window
