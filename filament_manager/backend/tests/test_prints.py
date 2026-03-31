"""
Integration tests for /api/prints endpoints.
Key behaviours verified:
  - CRUD lifecycle
  - Creating a print decrements spool current_weight_g
  - Deleting a print restores spool current_weight_g
  - Patching usages reverts old weights and applies new ones
  - Pagination (limit / offset)
  - 404 on missing resources
"""
import pytest
from tests.conftest import make_spool_payload, make_print_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_spool(client, **overrides):
    r = client.post("/api/spools", json=make_spool_payload(**overrides))
    assert r.status_code == 201
    return r.json()


def _create_print(client, usages=None, **overrides):
    payload = make_print_payload(usages=usages or [], **overrides)
    r = client.post("/api/prints", json=payload)
    assert r.status_code == 201
    return r.json()


def _get_spool_weight(client, spool_id):
    return client.get(f"/api/spools/{spool_id}").json()["current_weight_g"]


# ---------------------------------------------------------------------------
# GET /api/prints/count
# ---------------------------------------------------------------------------

class TestCountPrints:
    def test_empty_db_returns_zero(self, client):
        r = client.get("/api/prints/count")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_reflects_created_prints(self, client):
        _create_print(client)
        _create_print(client, name="Second")
        assert client.get("/api/prints/count").json()["total"] == 2


# ---------------------------------------------------------------------------
# GET /api/prints
# ---------------------------------------------------------------------------

class TestListPrints:
    def test_empty_returns_list(self, client):
        r = client.get("/api/prints")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_most_recent_first(self, client):
        _create_print(client, started_at="2024-01-01T08:00:00", name="Earlier")
        _create_print(client, started_at="2024-06-01T08:00:00", name="Later")
        results = client.get("/api/prints").json()
        assert results[0]["name"] == "Later"
        assert results[1]["name"] == "Earlier"

    def test_limit_pagination(self, client):
        for i in range(5):
            _create_print(client, name=f"Print {i}")
        r = client.get("/api/prints?limit=3")
        assert len(r.json()) == 3

    def test_offset_pagination(self, client):
        for i in range(5):
            _create_print(client, name=f"Print {i}", started_at=f"2024-0{i+1}-01T00:00:00")
        r = client.get("/api/prints?limit=50&offset=3")
        assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# POST /api/prints
# ---------------------------------------------------------------------------

class TestCreatePrint:
    def test_create_returns_201(self, client):
        r = client.post("/api/prints", json=make_print_payload())
        assert r.status_code == 201

    def test_create_returns_id(self, client):
        data = _create_print(client)
        assert data["id"] > 0

    def test_create_stores_fields(self, client):
        payload = make_print_payload(
            name="My Print",
            started_at="2024-03-15T14:30:00",
            duration_seconds=7200,
            success=True,
            printer_name="My Printer",
        )
        data = client.post("/api/prints", json=payload).json()
        assert data["name"] == "My Print"
        assert data["duration_hours"] == 2.0
        assert data["printer_name"] == "My Printer"
        assert data["success"] is True

    def test_create_without_usages(self, client):
        data = _create_print(client)
        assert data["usages"] == []
        assert data["total_grams"] == 0.0
        assert data["total_cost"] == 0.0

    def test_create_with_usage_decrements_spool(self, client):
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=1000)
        _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 150.0}])
        assert _get_spool_weight(client, spool["id"]) == 850.0

    def test_create_with_multiple_usages(self, client):
        s1 = _create_spool(client, initial_weight_g=1000, current_weight_g=1000, color_name="Red")
        s2 = _create_spool(client, initial_weight_g=500, current_weight_g=500, color_name="Blue")
        _create_print(client, usages=[
            {"spool_id": s1["id"], "grams_used": 100.0},
            {"spool_id": s2["id"], "grams_used": 50.0},
        ])
        assert _get_spool_weight(client, s1["id"]) == 900.0
        assert _get_spool_weight(client, s2["id"]) == 450.0

    def test_create_spool_weight_floored_at_zero(self, client):
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=50)
        _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 200.0}])
        assert _get_spool_weight(client, spool["id"]) == 0.0

    def test_create_with_invalid_spool_returns_404(self, client):
        r = client.post("/api/prints", json=make_print_payload(
            usages=[{"spool_id": 9999, "grams_used": 100.0}]
        ))
        assert r.status_code == 404

    def test_create_usage_computes_total_grams(self, client):
        spool = _create_spool(client, purchase_price=20.0)
        data = _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 100.0}])
        assert data["total_grams"] == pytest.approx(100.0)

    def test_create_usage_computes_total_cost(self, client):
        # €20/kg spool → €0.02/g → 100g = €2.00
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=1000, purchase_price=20.0)
        data = _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 100.0}])
        assert data["total_cost"] == pytest.approx(2.0, abs=0.01)

    def test_create_source_is_manual(self, client):
        data = _create_print(client)
        assert data["source"] == "manual"

    def test_create_missing_name_returns_422(self, client):
        payload = make_print_payload()
        del payload["name"]
        r = client.post("/api/prints", json=payload)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/prints/{id}
# ---------------------------------------------------------------------------

class TestGetPrint:
    def test_get_existing(self, client):
        job_id = _create_print(client)["id"]
        r = client.get(f"/api/prints/{job_id}")
        assert r.status_code == 200
        assert r.json()["id"] == job_id

    def test_get_nonexistent_returns_404(self, client):
        r = client.get("/api/prints/9999")
        assert r.status_code == 404

    def test_get_includes_usages(self, client):
        spool = _create_spool(client)
        job = _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 50.0}])
        data = client.get(f"/api/prints/{job['id']}").json()
        assert len(data["usages"]) == 1
        assert data["usages"][0]["grams_used"] == 50.0


# ---------------------------------------------------------------------------
# PATCH /api/prints/{id}
# ---------------------------------------------------------------------------

class TestUpdatePrint:
    def test_update_name(self, client):
        job_id = _create_print(client)["id"]
        r = client.patch(f"/api/prints/{job_id}", json={"name": "Renamed"})
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_update_nonexistent_returns_404(self, client):
        r = client.patch("/api/prints/9999", json={"name": "X"})
        assert r.status_code == 404

    def test_update_usages_reverts_and_reapplies_weights(self, client):
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=1000)
        job = _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 100.0}])
        # After create: spool = 900g
        assert _get_spool_weight(client, spool["id"]) == 900.0

        # Update usages to 200g
        client.patch(f"/api/prints/{job['id']}", json={
            "usages": [{"spool_id": spool["id"], "grams_used": 200.0}]
        })
        # Should revert 100g then deduct 200g → 800g
        assert _get_spool_weight(client, spool["id"]) == 800.0

    def test_update_clear_usages_restores_spool(self, client):
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=1000)
        job = _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 100.0}])
        assert _get_spool_weight(client, spool["id"]) == 900.0

        client.patch(f"/api/prints/{job['id']}", json={"usages": []})
        assert _get_spool_weight(client, spool["id"]) == 1000.0

    def test_update_without_usages_key_leaves_usages_intact(self, client):
        spool = _create_spool(client)
        job = _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 50.0}])
        # Patch only name — usages should not change
        client.patch(f"/api/prints/{job['id']}", json={"name": "New Name"})
        data = client.get(f"/api/prints/{job['id']}").json()
        assert len(data["usages"]) == 1


# ---------------------------------------------------------------------------
# DELETE /api/prints/{id}
# ---------------------------------------------------------------------------

class TestDeletePrint:
    def test_delete_returns_204(self, client):
        job_id = _create_print(client)["id"]
        r = client.delete(f"/api/prints/{job_id}")
        assert r.status_code == 204

    def test_delete_removes_job(self, client):
        job_id = _create_print(client)["id"]
        client.delete(f"/api/prints/{job_id}")
        assert client.get(f"/api/prints/{job_id}").status_code == 404

    def test_delete_restores_spool_weight(self, client):
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=1000)
        job = _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 150.0}])
        assert _get_spool_weight(client, spool["id"]) == 850.0

        client.delete(f"/api/prints/{job['id']}")
        assert _get_spool_weight(client, spool["id"]) == 1000.0

    def test_delete_spool_weight_capped_at_initial(self, client):
        """Deleting a print never pushes current_weight_g above initial_weight_g."""
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=980)
        job = _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 50.0}])
        # weight = 930g after print
        client.delete(f"/api/prints/{job['id']}")
        # restoring 50g → 980g, not above initial 1000g
        weight = _get_spool_weight(client, spool["id"])
        assert weight <= 1000.0
        assert weight == 980.0

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/api/prints/9999")
        assert r.status_code == 404
