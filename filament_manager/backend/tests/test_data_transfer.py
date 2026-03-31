"""
Integration tests for /api/data/export and /api/data/import endpoints.

Key behaviours:
  - Export serialises all tables into a versioned JSON bundle
  - Import merges additively (no deletes)
  - Import remaps spool IDs in print usages so cross-DB references stay valid
  - Duplicate settings entries are skipped on import
  - Duplicate printer configs (by device_slug) are skipped
  - Version mismatch returns 400
  - Full round-trip: export then re-import produces consistent data
"""
import pytest
from tests.conftest import make_spool_payload, make_print_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_spool(client, **kw):
    r = client.post("/api/spools", json=make_spool_payload(**kw))
    assert r.status_code == 201
    return r.json()


def _create_print(client, usages=None, **kw):
    r = client.post("/api/prints", json=make_print_payload(usages=usages or [], **kw))
    assert r.status_code == 201
    return r.json()


def _export(client):
    r = client.get("/api/data/export")
    assert r.status_code == 200
    return r.json()


def _import(client, bundle):
    r = client.post("/api/data/import", json=bundle)
    return r


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_returns_200(self, client):
        assert client.get("/api/data/export").status_code == 200

    def test_bundle_has_version(self, client):
        bundle = _export(client)
        assert bundle["version"] == 1

    def test_bundle_has_exported_at(self, client):
        bundle = _export(client)
        assert "exported_at" in bundle

    def test_empty_db_export(self, client):
        bundle = _export(client)
        assert bundle["spools"] == []
        assert bundle["print_jobs"] == []
        assert bundle["printer_configs"] == []

    def test_export_includes_spools(self, client):
        _create_spool(client, brand="SUNLU", color_name="Blue")
        bundle = _export(client)
        assert len(bundle["spools"]) == 1
        assert bundle["spools"][0]["brand"] == "SUNLU"

    def test_export_includes_print_jobs(self, client):
        _create_print(client, name="My Print")
        bundle = _export(client)
        assert len(bundle["print_jobs"]) == 1
        assert bundle["print_jobs"][0]["name"] == "My Print"

    def test_export_includes_usages_under_jobs(self, client):
        spool = _create_spool(client)
        _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 75.0}])
        bundle = _export(client)
        assert len(bundle["print_jobs"][0]["usages"]) == 1
        assert bundle["print_jobs"][0]["usages"][0]["grams_used"] == 75.0

    def test_export_preserves_spool_id(self, client):
        spool = _create_spool(client)
        bundle = _export(client)
        assert bundle["spools"][0]["id"] == spool["id"]

    def test_export_settings_keys_present(self, client):
        bundle = _export(client)
        s = bundle["settings"]
        assert "materials" in s
        assert "subtypes" in s
        assert "brands" in s
        assert "purchase_locations" in s
        assert "brand_weights" in s

    def test_content_disposition_header(self, client):
        r = client.get("/api/data/export")
        assert "content-disposition" in r.headers
        assert "filament_manager_export.json" in r.headers["content-disposition"]


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _minimal_bundle(**overrides):
    bundle = {
        "version": 1,
        "spools": [],
        "print_jobs": [],
        "printer_configs": [],
        "settings": {},
    }
    bundle.update(overrides)
    return bundle


class TestImport:
    def test_empty_bundle_returns_ok(self, client):
        r = _import(client, _minimal_bundle())
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_wrong_version_returns_400(self, client):
        r = _import(client, _minimal_bundle(version=99))
        assert r.status_code == 400

    def test_import_spools(self, client):
        bundle = _minimal_bundle(spools=[{
            "id": 1,
            "brand": "Jayo",
            "material": "PLA",
            "color_name": "Green",
            "initial_weight_g": 1000.0,
            "current_weight_g": 800.0,
        }])
        r = _import(client, bundle)
        assert r.json()["imported"]["spools"] == 1

        spools = client.get("/api/spools").json()
        assert len(spools) == 1
        assert spools[0]["brand"] == "Jayo"

    def test_import_remaps_spool_ids_in_usages(self, client):
        """
        The old DB had spool id=1. After import the spool gets a new id.
        The print usage should reference the new id, not the old one.
        """
        bundle = _minimal_bundle(
            spools=[{
                "id": 1,
                "brand": "Bambu Lab",
                "material": "PLA",
                "color_name": "Red",
                "initial_weight_g": 1000.0,
                "current_weight_g": 850.0,
            }],
            print_jobs=[{
                "id": 1,
                "name": "Remapped Print",
                "started_at": "2024-01-01T10:00:00",
                "success": True,
                "usages": [{"spool_id": 1, "grams_used": 150.0}],
            }],
        )
        _import(client, bundle)

        # Get the newly assigned spool id
        new_spool_id = client.get("/api/spools").json()[0]["id"]

        prints = client.get("/api/prints").json()
        assert len(prints) == 1
        assert prints[0]["usages"][0]["spool"]["id"] == new_spool_id

    def test_import_skips_usage_when_spool_not_in_bundle(self, client):
        """Usage referencing a spool_id not in the bundle is silently dropped."""
        bundle = _minimal_bundle(
            spools=[],
            print_jobs=[{
                "id": 1,
                "name": "Orphan Usage",
                "started_at": "2024-01-01T10:00:00",
                "success": True,
                "usages": [{"spool_id": 42, "grams_used": 100.0}],
            }],
        )
        r = _import(client, bundle)
        assert r.json()["ok"] is True
        assert r.json()["imported"]["print_usages"] == 0
        assert r.json()["imported"]["print_jobs"] == 1

    def test_import_settings_materials(self, client):
        bundle = _minimal_bundle(settings={"materials": ["ABS", "PETG", "PLA"]})
        r = _import(client, bundle)
        assert r.json()["imported"]["materials"] == 3
        names = [m["name"] for m in client.get("/api/settings/materials").json()]
        assert sorted(names) == ["ABS", "PETG", "PLA"]

    def test_import_skips_duplicate_materials(self, client):
        # Pre-populate
        client.post("/api/settings/materials", json={"name": "PLA"})
        bundle = _minimal_bundle(settings={"materials": ["PLA", "PETG"]})
        r = _import(client, bundle)
        # Only PETG is new
        assert r.json()["imported"]["materials"] == 1

    def test_import_brand_weights(self, client):
        bundle = _minimal_bundle(settings={"brand_weights": [
            {"brand": "Bambu Lab", "spool_weight_g": 250.0},
        ]})
        r = _import(client, bundle)
        assert r.json()["imported"]["brand_weights"] == 1

    def test_import_skips_duplicate_printer_config(self, client):
        # Pre-create a printer
        client.post("/api/printers", json={"name": "My Printer", "device_slug": "my_printer"})
        bundle = _minimal_bundle(printer_configs=[
            {"name": "My Printer", "device_slug": "my_printer"},
        ])
        r = _import(client, bundle)
        assert r.json()["imported"]["printer_configs"] == 0

    def test_import_additive_does_not_delete_existing(self, client):
        _create_spool(client, brand="ExistingSpool", color_name="Yellow")
        bundle = _minimal_bundle(spools=[{
            "id": 99,
            "brand": "NewSpool",
            "material": "PLA",
            "color_name": "Green",
            "initial_weight_g": 1000.0,
            "current_weight_g": 1000.0,
        }])
        _import(client, bundle)
        spools = client.get("/api/spools").json()
        brands = {s["brand"] for s in spools}
        assert "ExistingSpool" in brands
        assert "NewSpool" in brands

    def test_import_import_count_returned(self, client):
        bundle = _minimal_bundle(
            spools=[{
                "id": 1, "brand": "X", "material": "PLA",
                "color_name": "R", "initial_weight_g": 1000.0, "current_weight_g": 1000.0
            }],
            print_jobs=[{
                "id": 1, "name": "P", "started_at": "2024-01-01T00:00:00",
                "success": True,
                "usages": [{"spool_id": 1, "grams_used": 10.0}],
            }],
        )
        stats = _import(client, bundle).json()["imported"]
        assert stats["spools"] == 1
        assert stats["print_jobs"] == 1
        assert stats["print_usages"] == 1


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_export_and_reimport_spools(self, client):
        _create_spool(client, brand="Bambu Lab", material="PLA", color_name="Red",
                      initial_weight_g=1000.0, current_weight_g=750.0, purchase_price=19.99)
        _create_spool(client, brand="SUNLU", material="PETG", color_name="Blue",
                      initial_weight_g=800.0, current_weight_g=800.0)

        bundle = _export(client)

        # Delete and re-import (simulates migration to new instance)
        spool_ids = [s["id"] for s in client.get("/api/spools").json()]
        for sid in spool_ids:
            client.delete(f"/api/spools/{sid}")

        _import(client, bundle)
        spools = client.get("/api/spools").json()
        assert len(spools) == 2
        brands = {s["brand"] for s in spools}
        assert brands == {"Bambu Lab", "SUNLU"}

    def test_export_and_reimport_preserves_usage_association(self, client):
        spool = _create_spool(client, brand="Bambu Lab", color_name="White")
        _create_print(client, name="BenchyPrint",
                      usages=[{"spool_id": spool["id"], "grams_used": 42.0}])

        bundle = _export(client)

        # Wipe DB and re-import
        client.delete(f"/api/prints/{client.get('/api/prints').json()[0]['id']}")
        client.delete(f"/api/spools/{spool['id']}")

        _import(client, bundle)

        prints = client.get("/api/prints").json()
        assert len(prints) == 1
        assert len(prints[0]["usages"]) == 1
        assert prints[0]["usages"][0]["grams_used"] == 42.0
        assert prints[0]["usages"][0]["spool"] is not None
