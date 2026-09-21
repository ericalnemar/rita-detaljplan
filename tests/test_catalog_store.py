"""Tester för katalogtjänsten (cache, uppdatering, felhantering). Kräver inte QGIS – nätverket är påhittat."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_detaljplan.core import catalog as cat  # noqa: E402
from rita_detaljplan.core.catalog_store import CACHE_NAME, CatalogError, CatalogService  # noqa: E402

FIXTURE = json.loads((ROOT / "tests" / "data" / "katalog_urval.json").read_text(encoding="utf-8"))


def release(release_id, name):
    return {**FIXTURE, "id": release_id, "namn": name}


class FakeApi:
    """Efterliknar Boverkets API. ``calls`` visar vilka anrop som gjordes."""

    def __init__(self, latest_id=7, latest_name="20251201"):
        self.calls = []
        self.responses = {
            "/release": [
                {"id": latest_id, "namn": latest_name, "publicerad": "2025-12-01T10:39:00", "typ": {"namn": "Juridisk"}},
                {"id": 6, "namn": "20240502", "publicerad": "2024-05-02T06:58:00", "typ": {"namn": "Juridisk"}},
            ],
            f"/release/full/platt/{latest_id}": release(latest_id, latest_name),
        }

    def __call__(self, path):
        self.calls.append(path)
        if path not in self.responses:
            raise CatalogError(f"okänd sökväg {path}")
        return self.responses[path]


class CatalogServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.bundled = self.tmp / "bundled.json"
        cat.Catalog.from_api_release(release(7, "20251201")).only_current().save(self.bundled)
        self.cache_dir = self.tmp / "profil" / "detaljplan_ngp"

    def service(self, fetch=None):
        return CatalogService(self.cache_dir, self.bundled, fetch or FakeApi())

    def test_uses_bundled_catalog_without_cache(self):
        catalog = self.service().load()
        self.assertEqual(catalog.release_id, 7)
        self.assertFalse(catalog.has_historic)

    def test_update_downloads_full_catalog_even_for_same_release_to_get_historic_entries(self):
        api = FakeApi()
        result = self.service(api).update()
        self.assertTrue(result.updated)
        self.assertTrue(result.catalog.has_historic)
        self.assertIn("Hämtade hela", result.message)
        self.assertTrue((self.cache_dir / CACHE_NAME).exists())
        self.assertEqual(api.calls, ["/release", "/release/full/platt/7"])

    def test_new_service_instance_reads_the_cache(self):
        self.service().update()
        fresh = self.service(FakeApi())
        self.assertTrue(fresh.load().has_historic)

    def test_no_download_when_already_current_and_complete(self):
        self.service().update()
        api = FakeApi()
        result = self.service(api).update()
        self.assertFalse(result.updated)
        self.assertEqual(api.calls, ["/release"])
        self.assertIn("redan aktuell", result.message)

    def test_force_downloads_again(self):
        self.service().update()
        api = FakeApi()
        self.assertTrue(self.service(api).update(force=True).updated)

    def test_newer_release_replaces_cache(self):
        self.service().update()
        api = FakeApi(latest_id=8, latest_name="20260601")
        result = self.service(api).update()
        self.assertTrue(result.updated)
        self.assertIn("Uppdaterade", result.message)
        self.assertEqual(self.service(api).load().release_id, 8)

    def test_corrupt_cache_falls_back_to_bundled(self):
        self.cache_dir.mkdir(parents=True)
        (self.cache_dir / CACHE_NAME).write_text("{ inte json", encoding="utf-8")
        self.assertEqual(self.service().load().release_id, 7)
        (self.cache_dir / CACHE_NAME).write_text('{"release_id": 8}', encoding="utf-8")
        self.assertEqual(self.service().load().release_id, 7)

    def test_cache_older_than_bundled_catalog_is_ignored(self):
        cat.Catalog.from_api_release(release(5, "20221101")).save(self.cache_dir / CACHE_NAME)
        self.assertEqual(self.service().load().release_id, 7)

    def test_network_failure_keeps_the_current_catalog(self):
        def offline(path):
            raise CatalogError("Ingen förbindelse")

        service = self.service(offline)
        with self.assertRaises(CatalogError):
            service.update()
        self.assertEqual(service.load().release_id, 7)
        self.assertFalse((self.cache_dir / CACHE_NAME).exists())

    def test_empty_or_malformed_download_is_rejected_and_cache_untouched(self):
        api = FakeApi()
        api.responses["/release/full/platt/7"] = {**release(7, "x"), "bestammelser": []}
        with self.assertRaises(CatalogError):
            self.service(api).update()
        api.responses["/release/full/platt/7"] = {"id": 7}
        with self.assertRaises(CatalogError):
            self.service(api).update()
        api.responses["/release"] = {"fel": "inte en lista"}
        with self.assertRaises(CatalogError):
            self.service(api).update()
        self.assertFalse((self.cache_dir / CACHE_NAME).exists())


if __name__ == "__main__":
    unittest.main()
