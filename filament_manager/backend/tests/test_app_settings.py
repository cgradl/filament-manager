"""
Integration tests for /api/settings endpoints.

Covers:
  - GET /version  (mocked config.yaml)
  - Brand spool weights CRUD + 409 duplicate
  - Filament subtypes CRUD + 409 duplicate
  - Filament materials CRUD + 409 duplicate
  - Filament brands CRUD + 409 duplicate
  - Purchase locations CRUD + 409 duplicate
"""
import tempfile
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Version endpoint
# ---------------------------------------------------------------------------

class TestVersion:
    def test_returns_version_string(self, client):
        fake_config = "name: Test\nversion: \"1.2.3\"\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(fake_config)
            tmp_path = f.name

        import app.routers.app_settings as mod
        with patch.object(mod, "_CONFIG", Path(tmp_path)):
            r = client.get("/api/settings/version")

        assert r.status_code == 200
        assert r.json()["version"] == "1.2.3"

    def test_returns_unknown_when_file_missing(self, client):
        import app.routers.app_settings as mod
        with patch.object(mod, "_CONFIG", Path("/nonexistent/config.yaml")):
            r = client.get("/api/settings/version")
        assert r.status_code == 200
        assert r.json()["version"] == "unknown"


# ---------------------------------------------------------------------------
# Brand spool weights
# ---------------------------------------------------------------------------

class TestBrandWeights:
    def test_list_empty(self, client):
        r = client.get("/api/settings/brand-weights")
        assert r.status_code == 200
        assert r.json() == []

    def test_create(self, client):
        r = client.post("/api/settings/brand-weights", json={"brand": "Bambu Lab", "spool_weight_g": 250.0})
        assert r.status_code == 201
        data = r.json()
        assert data["brand"] == "Bambu Lab"
        assert data["spool_weight_g"] == 250.0
        assert data["id"] > 0

    def test_list_after_create(self, client):
        client.post("/api/settings/brand-weights", json={"brand": "Bambu Lab", "spool_weight_g": 250.0})
        client.post("/api/settings/brand-weights", json={"brand": "SUNLU", "spool_weight_g": 225.0})
        result = client.get("/api/settings/brand-weights").json()
        assert len(result) == 2
        brands = [r["brand"] for r in result]
        assert "Bambu Lab" in brands
        assert "SUNLU" in brands

    def test_create_duplicate_returns_409(self, client):
        client.post("/api/settings/brand-weights", json={"brand": "Bambu Lab", "spool_weight_g": 250.0})
        r = client.post("/api/settings/brand-weights", json={"brand": "Bambu Lab", "spool_weight_g": 300.0})
        assert r.status_code == 409

    def test_update(self, client):
        entry_id = client.post("/api/settings/brand-weights", json={"brand": "Bambu Lab", "spool_weight_g": 250.0}).json()["id"]
        r = client.patch(f"/api/settings/brand-weights/{entry_id}", json={"brand": "Bambu Lab", "spool_weight_g": 260.0})
        assert r.status_code == 200
        assert r.json()["spool_weight_g"] == 260.0

    def test_update_nonexistent_returns_404(self, client):
        r = client.patch("/api/settings/brand-weights/9999", json={"brand": "X", "spool_weight_g": 100.0})
        assert r.status_code == 404

    def test_delete(self, client):
        entry_id = client.post("/api/settings/brand-weights", json={"brand": "Bambu Lab", "spool_weight_g": 250.0}).json()["id"]
        r = client.delete(f"/api/settings/brand-weights/{entry_id}")
        assert r.status_code == 204
        assert client.get("/api/settings/brand-weights").json() == []

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/api/settings/brand-weights/9999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Filament subtypes
# ---------------------------------------------------------------------------

class TestSubtypes:
    def test_list_empty(self, client):
        assert client.get("/api/settings/subtypes").json() == []

    def test_create(self, client):
        r = client.post("/api/settings/subtypes", json={"name": "Matte"})
        assert r.status_code == 201
        assert r.json()["name"] == "Matte"

    def test_create_strips_whitespace(self, client):
        r = client.post("/api/settings/subtypes", json={"name": "  Silk  "})
        assert r.json()["name"] == "Silk"

    def test_create_duplicate_returns_409(self, client):
        client.post("/api/settings/subtypes", json={"name": "Matte"})
        r = client.post("/api/settings/subtypes", json={"name": "Matte"})
        assert r.status_code == 409

    def test_update(self, client):
        entry_id = client.post("/api/settings/subtypes", json={"name": "Matte"}).json()["id"]
        r = client.patch(f"/api/settings/subtypes/{entry_id}", json={"name": "Ultra Matte"})
        assert r.status_code == 200
        assert r.json()["name"] == "Ultra Matte"

    def test_update_nonexistent_returns_404(self, client):
        r = client.patch("/api/settings/subtypes/9999", json={"name": "X"})
        assert r.status_code == 404

    def test_delete(self, client):
        entry_id = client.post("/api/settings/subtypes", json={"name": "Matte"}).json()["id"]
        assert client.delete(f"/api/settings/subtypes/{entry_id}").status_code == 204
        assert client.get("/api/settings/subtypes").json() == []

    def test_delete_nonexistent_returns_404(self, client):
        assert client.delete("/api/settings/subtypes/9999").status_code == 404


# ---------------------------------------------------------------------------
# Filament materials
# ---------------------------------------------------------------------------

class TestMaterials:
    def test_list_empty(self, client):
        assert client.get("/api/settings/materials").json() == []

    def test_create(self, client):
        r = client.post("/api/settings/materials", json={"name": "PETG"})
        assert r.status_code == 201
        assert r.json()["name"] == "PETG"

    def test_create_duplicate_returns_409(self, client):
        client.post("/api/settings/materials", json={"name": "PLA"})
        r = client.post("/api/settings/materials", json={"name": "PLA"})
        assert r.status_code == 409

    def test_update(self, client):
        entry_id = client.post("/api/settings/materials", json={"name": "PLA"}).json()["id"]
        r = client.patch(f"/api/settings/materials/{entry_id}", json={"name": "PLA+"})
        assert r.json()["name"] == "PLA+"

    def test_update_nonexistent_returns_404(self, client):
        assert client.patch("/api/settings/materials/9999", json={"name": "X"}).status_code == 404

    def test_delete(self, client):
        entry_id = client.post("/api/settings/materials", json={"name": "ABS"}).json()["id"]
        assert client.delete(f"/api/settings/materials/{entry_id}").status_code == 204

    def test_delete_nonexistent_returns_404(self, client):
        assert client.delete("/api/settings/materials/9999").status_code == 404


# ---------------------------------------------------------------------------
# Filament brands
# ---------------------------------------------------------------------------

class TestBrands:
    def test_list_empty(self, client):
        assert client.get("/api/settings/brands").json() == []

    def test_create(self, client):
        r = client.post("/api/settings/brands", json={"name": "Bambu Lab"})
        assert r.status_code == 201
        assert r.json()["name"] == "Bambu Lab"

    def test_create_duplicate_returns_409(self, client):
        client.post("/api/settings/brands", json={"name": "SUNLU"})
        r = client.post("/api/settings/brands", json={"name": "SUNLU"})
        assert r.status_code == 409

    def test_update(self, client):
        entry_id = client.post("/api/settings/brands", json={"name": "Old Brand"}).json()["id"]
        r = client.patch(f"/api/settings/brands/{entry_id}", json={"name": "New Brand"})
        assert r.json()["name"] == "New Brand"

    def test_update_nonexistent_returns_404(self, client):
        assert client.patch("/api/settings/brands/9999", json={"name": "X"}).status_code == 404

    def test_delete(self, client):
        entry_id = client.post("/api/settings/brands", json={"name": "Jayo"}).json()["id"]
        assert client.delete(f"/api/settings/brands/{entry_id}").status_code == 204

    def test_delete_nonexistent_returns_404(self, client):
        assert client.delete("/api/settings/brands/9999").status_code == 404


# ---------------------------------------------------------------------------
# Purchase locations
# ---------------------------------------------------------------------------

class TestPurchaseLocations:
    def test_list_empty(self, client):
        assert client.get("/api/settings/purchase-locations").json() == []

    def test_create(self, client):
        r = client.post("/api/settings/purchase-locations", json={"name": "Amazon"})
        assert r.status_code == 201
        assert r.json()["name"] == "Amazon"

    def test_create_duplicate_returns_409(self, client):
        client.post("/api/settings/purchase-locations", json={"name": "Amazon"})
        r = client.post("/api/settings/purchase-locations", json={"name": "Amazon"})
        assert r.status_code == 409

    def test_update(self, client):
        entry_id = client.post("/api/settings/purchase-locations", json={"name": "Amazon"}).json()["id"]
        r = client.patch(f"/api/settings/purchase-locations/{entry_id}", json={"name": "Amazon DE"})
        assert r.json()["name"] == "Amazon DE"

    def test_update_nonexistent_returns_404(self, client):
        assert client.patch("/api/settings/purchase-locations/9999", json={"name": "X"}).status_code == 404

    def test_delete(self, client):
        entry_id = client.post("/api/settings/purchase-locations", json={"name": "Amazon"}).json()["id"]
        assert client.delete(f"/api/settings/purchase-locations/{entry_id}").status_code == 204

    def test_delete_nonexistent_returns_404(self, client):
        assert client.delete("/api/settings/purchase-locations/9999").status_code == 404

    def test_list_ordered_by_name(self, client):
        client.post("/api/settings/purchase-locations", json={"name": "Temu"})
        client.post("/api/settings/purchase-locations", json={"name": "Amazon"})
        client.post("/api/settings/purchase-locations", json={"name": "Bambu Lab"})
        names = [r["name"] for r in client.get("/api/settings/purchase-locations").json()]
        assert names == sorted(names)
