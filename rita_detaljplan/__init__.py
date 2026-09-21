"""Rita Detaljplan – QGIS-plugin för att rita och leverera detaljplaner enligt nationell specifikation."""


def classFactory(iface):  # noqa: N802 - namnet krävs av QGIS
    from .plugin import DetaljplanPlugin

    return DetaljplanPlugin(iface)
