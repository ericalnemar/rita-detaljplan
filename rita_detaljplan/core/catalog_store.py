"""Läser, cachar och uppdaterar planbestämmelsekatalogen.

Ordning vid inläsning: cache i QGIS-profilen (om den är hel) -> katalogen som följer med pluginet.
Uppdatering hämtar hela katalogen (inklusive upphörda bestämmelser) från Boverkets öppna API.
Nätverksanropen går via QGIS egen nätverksstack, så proxy och autentisering från QGIS inställningar gäller.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import catalog as cat

CACHE_NAME = "planbestammelsekatalog.json"
TIMEOUT_MS = 180_000

Fetch = Callable[[str], object]  # sökväg (t.ex. "/release") -> tolkad JSON


class CatalogError(RuntimeError):
    """Något gick fel vid hämtning från Boverket. Meddelandet är avsett för användaren."""


@dataclass(frozen=True)
class UpdateResult:
    catalog: cat.Catalog
    updated: bool
    message: str


def qgis_fetch(path: str, feedback=None, base: str = cat.API_BASE) -> object:
    """Hämtar JSON från Boverkets API via QgsBlockingNetworkRequest (får användas från en QgsTask)."""
    from qgis.core import QgsBlockingNetworkRequest
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest

    request = QNetworkRequest(QUrl(base + path))
    request.setRawHeader(b"Accept", b"application/json")
    request.setTransferTimeout(TIMEOUT_MS)
    blocking = QgsBlockingNetworkRequest()
    error = blocking.get(request, True, feedback)
    if error != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise CatalogError(f"Kunde inte nå Boverkets planbestämmelsekatalog: {blocking.errorMessage()}")
    try:
        return json.loads(bytes(blocking.reply().content()).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CatalogError(f"Oväntat svar från Boverket ({path}): {exc}") from exc


class CatalogService:
    def __init__(self, cache_dir: str | Path, bundled_path: str | Path, fetch: Optional[Fetch] = None):
        self.cache_file = Path(cache_dir) / CACHE_NAME
        self.bundled_path = Path(bundled_path)
        self._fetch = fetch or qgis_fetch
        self._catalog: Optional[cat.Catalog] = None

    # -- inläsning ------------------------------------------------------------------
    def load(self, refresh: bool = False) -> cat.Catalog:
        if self._catalog is None or refresh:
            self._catalog = self._load_cache() or cat.Catalog.load(self.bundled_path)
        return self._catalog

    def _load_cache(self) -> Optional[cat.Catalog]:
        if not self.cache_file.exists():
            return None
        try:
            loaded = cat.Catalog.load(self.cache_file)
        except (OSError, ValueError, KeyError, TypeError):
            return None  # trasig cache: använd den medföljande katalogen i stället
        bundled = cat.Catalog.load(self.bundled_path)
        # En nyare medföljande katalog (pluginet uppdaterades) går före en gammal cache.
        return loaded if loaded.release_id >= bundled.release_id else None

    # -- uppdatering ----------------------------------------------------------------
    def latest_release(self) -> dict:
        releases = self._fetch("/release")
        if not isinstance(releases, list):
            raise CatalogError("Oväntat svar från Boverket (releaselistan)")
        try:
            return cat.latest_release(releases)
        except ValueError as exc:
            raise CatalogError(str(exc)) from exc

    def update(self, force: bool = False) -> UpdateResult:
        """Hämtar senaste release om den är nyare, eller om den lokala katalogen saknar upphörda bestämmelser."""
        current = self.load()
        latest = self.latest_release()
        newer = int(latest["id"]) > current.release_id
        if not newer and current.has_historic and not force:
            return UpdateResult(current, False, f"Katalogen är redan aktuell (release {current.release_name}).")

        release = self._fetch(f"/release/full/platt/{latest['id']}")
        try:
            fresh = cat.Catalog.from_api_release(release)
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogError(f"Oväntat innehåll i katalogen från Boverket: {exc}") from exc
        if not len(fresh):
            raise CatalogError("Katalogen från Boverket var tom; behåller den nuvarande.")
        fresh.save(self.cache_file)
        self._catalog = fresh
        what = "Uppdaterade" if newer else "Hämtade hela"
        return UpdateResult(fresh, True, f"{what} planbestämmelsekatalogen: release {fresh.release_name}, "
                                         f"{len(fresh)} bestämmelser.")
