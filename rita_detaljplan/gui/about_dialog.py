"""Om Rita Detaljplan: märket, versionen, utvecklaren och en länk till dokumentationen."""
from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QByteArray, QSize, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QFont, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

PLUGIN_DIR = Path(__file__).resolve().parent.parent
LOGO_FILE = PLUGIN_DIR / "icon.svg"
TAGLINE = "Ett QGIS-plugin för att rita detaljplaner."
LICENSE = "GPL-2.0-or-later"


def metadata() -> dict[str, str]:
    """Rader av typen ``nyckel=värde`` ur pluginets metadata.txt."""
    values = {}
    for line in (PLUGIN_DIR / "metadata.txt").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def logo_pixmap(size: int, scale: float = 2.0) -> QPixmap:
    """Märket (pluginikonen) som bild, tillräckligt skarp för skärmar med hög upplösning."""
    renderer = QSvgRenderer(QByteArray(LOGO_FILE.read_bytes()))
    pixmap = QPixmap(QSize(round(size * scale), round(size * scale)))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        meta = metadata()
        self.homepage = meta.get("homepage", "")  # webbsidan
        self.repository = meta.get("repository", "")
        self.setWindowTitle("Om Rita Detaljplan")
        self.setMinimumWidth(460)

        logo = QLabel()
        logo.setPixmap(logo_pixmap(96))
        logo.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.name = QLabel("Rita Detaljplan")
        heading = QFont(self.name.font())
        heading.setPointSizeF(heading.pointSizeF() * 1.8)
        heading.setWeight(QFont.Weight.Medium)
        self.name.setFont(heading)
        self.version = QLabel(f"Version {meta.get('version', '')}")
        self.version.setEnabled(False)  # dämpad färg
        self.tagline = QLabel(TAGLINE)
        self.tagline.setWordWrap(True)
        self.credit = QLabel(f"{meta.get('author', '')} · {LICENSE}")
        self.credit.setEnabled(False)

        text = QVBoxLayout()
        text.setSpacing(6)
        for widget in (self.name, self.version, self.tagline, self.credit):
            text.addWidget(widget)
        text.addStretch(1)
        body = QHBoxLayout()
        body.setSpacing(24)
        body.addWidget(logo)
        body.addLayout(text, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        self.website = self.buttons.addButton("Webbsida", QDialogButtonBox.ButtonRole.ActionRole)
        self.website.setToolTip(self.homepage)
        self.website.clicked.connect(self.open_website)
        self.website.setVisible(bool(self.homepage))
        self.docs = self.buttons.addButton("Dokumentation", QDialogButtonBox.ButtonRole.ActionRole)
        self.docs.clicked.connect(self.open_docs)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(20)
        layout.addLayout(body)
        layout.addWidget(self.buttons)

    def docs_url(self) -> str:
        return f"{self.repository}/blob/main/docs/anvandning.md" if self.repository else ""

    def open_website(self) -> None:
        if self.homepage:
            QDesktopServices.openUrl(QUrl(self.homepage))

    def open_docs(self) -> None:
        if self.repository:
            QDesktopServices.openUrl(QUrl(self.docs_url()))
