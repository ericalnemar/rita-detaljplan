"""Dialogen Importera geometrier: välj ett lager (eller lägg till en datakälla på QGIS vanliga sätt) vars geometrier ska
kopieras till hjälplagren. Bara geometrin tas med (se ``core/importer.py``)."""
from __future__ import annotations

from typing import Optional

from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
                                 QVBoxLayout)


INTRO = ("Geometrierna kopieras till Hjälplager, utan attribut: ytor, linjer och punkter var för sig. Ge dem sedan "
         "en bestämmelse med Planbestämmelser, så blir de planobjekt (hjälppunkter kan inte få bestämmelser). "
         "Källan ändras inte och hjälplagren levereras aldrig till NGP.")
KIND_TEXT = {
    QgsWkbTypes.GeometryType.PolygonGeometry: "ytor",
    QgsWkbTypes.GeometryType.LineGeometry: "linjer",
    QgsWkbTypes.GeometryType.PointGeometry: "punkter",
}


class ImportDialog(QDialog):
    def __init__(self, iface, excluded: list, parent=None, epsg: int = 3006):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Importera geometrier")
        self.target = QgsCoordinateReferenceSystem(f"EPSG:{epsg}")
        self.setMinimumWidth(520)

        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        self.layer = QgsMapLayerComboBox()
        self.layer.setFilters(Qgis.LayerFilter.HasGeometry)
        self.layer.setExceptedLayerList(excluded)  # planens egna lager
        self.layer.setAllowEmptyLayer(True, "Välj ett lager…")
        self.layer.layerChanged.connect(lambda *_: self._update())
        self.add_source = QPushButton("Lägg till datakälla…")
        self.add_source.setToolTip("Öppnar QGIS datakällshanterare: filer (GeoPackage, Shape, DXF …), databaser och "
                                   "webbtjänster. Lagret du lägger till väljs här.")
        self.add_source.clicked.connect(self.open_data_source_manager)
        self.add_source.setVisible(self._manager_action() is not None)
        row = QHBoxLayout()
        row.addWidget(self.layer, 1)
        row.addWidget(self.add_source)
        self.selected_only = QCheckBox("Bara markerade objekt")
        self.selected_only.toggled.connect(lambda *_: self._update())
        self.summary = QLabel()
        self.summary.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Lager", row)
        form.addRow("", self.selected_only)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Importera")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addStretch(1)
        layout.addWidget(self.buttons)

        QgsProject.instance().layersAdded.connect(self._layers_added)
        current = iface.activeLayer() if iface is not None and hasattr(iface, "activeLayer") else None
        if isinstance(current, QgsVectorLayer) and current not in excluded and current.isSpatial():
            self.layer.setLayer(current)
        else:
            self.layer.setLayer(None)
        self._update()

    def _manager_action(self):
        return getattr(self.iface, "actionDataSourceManager", lambda: None)() if self.iface is not None else None

    def open_data_source_manager(self) -> None:
        action = self._manager_action()
        if action is not None:
            action.trigger()

    def _layers_added(self, layers) -> None:
        """Ett lager som läggs till medan dialogen är öppen (från datakällshanteraren) väljs direkt."""
        added = [layer for layer in layers if isinstance(layer, QgsVectorLayer) and layer.isSpatial()]
        if added:
            self.layer.setLayer(added[-1])

    def release(self) -> None:
        """Släpper kopplingarna till projektet. Annars kan dialogen (som lever kvar med QGIS fönster som förälder)
        reagera när lager tas bort senare, och QGIS kraschar."""
        self.layer.blockSignals(True)
        try:
            QgsProject.instance().layersAdded.disconnect(self._layers_added)
        except TypeError:
            pass

    def done(self, result: int) -> None:  # noqa: D401 - Qt-namn
        self.release()
        super().done(result)

    def source(self) -> Optional[QgsVectorLayer]:
        layer = self.layer.currentLayer()
        return layer if isinstance(layer, QgsVectorLayer) else None

    def _update(self) -> None:
        layer = self.source()
        selected = layer.selectedFeatureCount() if layer is not None else 0
        self.selected_only.setEnabled(selected > 0)
        self.selected_only.setText(f"Bara markerade objekt ({selected})" if selected else "Bara markerade objekt")
        if selected == 0 and self.selected_only.isChecked():
            self.selected_only.setChecked(False)
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if layer is None:
            self.summary.setText("")
            ok.setEnabled(False)
            return
        count = selected if self.selected_only.isChecked() else layer.featureCount()
        kind = KIND_TEXT.get(QgsWkbTypes.geometryType(layer.wkbType()), "geometrier av blandat slag")
        text = f"{count} objekt ({kind})." if count >= 0 else f"Lagret har {kind}."
        target = self.target
        if layer.crs().isValid() and layer.crs() != target:
            text += (f" Geometrin omvandlas från {layer.crs().userFriendlyIdentifier()} till planens "
                     f"{target.userFriendlyIdentifier()}.")
        elif not layer.crs().isValid():
            text += f" Lagret saknar koordinatsystem: geometrin antas redan vara i planens {target.authid()}."
        self.summary.setText(text)
        ok.setEnabled(count != 0)
