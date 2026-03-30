"""
Integration tests for /api/printers endpoints.

HA client calls (get_all_entities, get_entity_value, is_ha_available) are
mocked so tests run without a real Home Assistant instance.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.conftest import make_spool_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PRINTER_PAYLOAD = {
    "name": "Bambu H2S",
    "device_slug": "h2s",
    "ams_unit_count": 1,
    "is_active": True,
}


def _create_printer(client, **overrides):
    payload = dict(PRINTER_PAYLOAD)
    payload.update(overrides)
    r = client.post("/api/printers", json=payload)
    assert r.status_code == 201
    return r.json()


def _create_spool(client, **kw):
    r = client.post("/api/spools", json=make_spool_payload(**kw))
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# GET /api/printers
# ---------------------------------------------------------------------------

class TestListPrinters:
    def test_empty_returns_list(self, client):
        r = client.get("/api/printers")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_created_printers(self, client):
        _create_printer(client)
        r = client.get("/api/printers")
        assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# POST /api/printers
# ---------------------------------------------------------------------------

class TestCreatePrinter:
    def test_returns_201(self, client):
        r = client.post("/api/printers", json=PRINTER_PAYLOAD)
        assert r.status_code == 201

    def test_stores_fields(self, client):
        data = _create_printer(client)
        assert data["name"] == "Bambu H2S"
        assert data["device_slug"] == "h2s"
        assert data["ams_unit_count"] == 1
        assert data["is_active"] is True
        assert data["id"] > 0

    def test_optional_ams_device_slug(self, client):
        data = _create_printer(client, ams_device_slug="h2s_ams")
        assert data["ams_device_slug"] == "h2s_ams"

    def test_missing_required_field_returns_422(self, client):
        r = client.post("/api/printers", json={"name": "X"})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/printers/{id}
# ---------------------------------------------------------------------------

class TestGetPrinter:
    def test_get_existing(self, client):
        printer_id = _create_printer(client)["id"]
        r = client.get(f"/api/printers/{printer_id}")
        assert r.status_code == 200
        assert r.json()["id"] == printer_id

    def test_get_nonexistent_returns_404(self, client):
        assert client.get("/api/printers/9999").status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/printers/{id}
# ---------------------------------------------------------------------------

class TestUpdatePrinter:
    def test_update_name(self, client):
        printer_id = _create_printer(client)["id"]
        r = client.patch(f"/api/printers/{printer_id}", json={
            "name": "New Name",
            "device_slug": "h2s",
        })
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_update_ams_unit_count(self, client):
        printer_id = _create_printer(client)["id"]
        r = client.patch(f"/api/printers/{printer_id}", json={
            "name": "Bambu H2S",
            "device_slug": "h2s",
            "ams_unit_count": 2,
        })
        assert r.json()["ams_unit_count"] == 2

    def test_update_nonexistent_returns_404(self, client):
        r = client.patch("/api/printers/9999", json=PRINTER_PAYLOAD)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/printers/{id}
# ---------------------------------------------------------------------------

class TestDeletePrinter:
    def test_delete_returns_204(self, client):
        printer_id = _create_printer(client)["id"]
        assert client.delete(f"/api/printers/{printer_id}").status_code == 204

    def test_delete_removes_printer(self, client):
        printer_id = _create_printer(client)["id"]
        client.delete(f"/api/printers/{printer_id}")
        assert client.get(f"/api/printers/{printer_id}").status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        assert client.delete("/api/printers/9999").status_code == 404


# ---------------------------------------------------------------------------
# GET /api/printers/{id}/status  (mocked HA)
# ---------------------------------------------------------------------------

class TestPrinterStatus:
    def test_returns_status_dict(self, client):
        printer_id = _create_printer(client)["id"]

        async def fake_get_entity_value(entity_id):
            return "idle"

        with patch("app.routers.printers.ha_client.get_entity_value", side_effect=fake_get_entity_value):
            r = client.get(f"/api/printers/{printer_id}/status")

        assert r.status_code == 200
        data = r.json()
        assert "print_stage" in data

    def test_status_nonexistent_printer_returns_404(self, client):
        r = client.get("/api/printers/9999/status")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/printers/discover  (mocked HA)
# ---------------------------------------------------------------------------

class TestDiscoverPrinter:
    def _mock_entities(self):
        return [
            {"entity_id": "sensor.h2s_current_stage", "state": "idle", "attributes": {}},
            {"entity_id": "sensor.h2s_print_progress", "state": "0", "attributes": {}},
            {"entity_id": "sensor.h2s_gcode_file", "state": "", "attributes": {}},
        ]

    def test_discover_returns_slug(self, client):
        with patch("app.routers.printers.ha_client.get_all_entities",
                   new=AsyncMock(return_value=self._mock_entities())):
            r = client.get("/api/printers/discover?device=H2S")
        assert r.status_code == 200
        assert r.json()["slug"] == "h2s"

    def test_discover_finds_printer_entities(self, client):
        with patch("app.routers.printers.ha_client.get_all_entities",
                   new=AsyncMock(return_value=self._mock_entities())):
            r = client.get("/api/printers/discover?device=H2S")
        entities = r.json()["printer_entities"]
        assert entities["print_stage"]["found"] is True
        assert entities["print_stage"]["entity_id"] == "sensor.h2s_current_stage"

    def test_discover_unknown_device_shows_not_found(self, client):
        with patch("app.routers.printers.ha_client.get_all_entities",
                   new=AsyncMock(return_value=[])):
            r = client.get("/api/printers/discover?device=UnknownPrinter")
        assert r.status_code == 200
        for entity_info in r.json()["printer_entities"].values():
            assert entity_info["found"] is False


# ---------------------------------------------------------------------------
# POST /api/printers/{id}/ams/{slot_key}/assign
# ---------------------------------------------------------------------------

class TestAssignAMSTray:
    def test_assign_spool_to_tray(self, client):
        printer = _create_printer(client)
        spool = _create_spool(client)

        r = client.post(
            f"/api/printers/{printer['id']}/ams/ams1_tray1/assign",
            json={"spool_id": spool["id"]},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        spool_data = client.get(f"/api/spools/{spool['id']}").json()
        assert spool_data["ams_slot"] == "ams1_tray1"

    def test_unassign_spool_from_tray(self, client):
        printer = _create_printer(client)
        spool = _create_spool(client)

        # Assign first
        client.post(
            f"/api/printers/{printer['id']}/ams/ams1_tray1/assign",
            json={"spool_id": spool["id"]},
        )
        # Then unassign
        r = client.post(
            f"/api/printers/{printer['id']}/ams/ams1_tray1/assign",
            json={"spool_id": None},
        )
        assert r.status_code == 200
        spool_data = client.get(f"/api/spools/{spool['id']}").json()
        assert spool_data["ams_slot"] is None

    def test_reassign_clears_previous_spool(self, client):
        printer = _create_printer(client)
        spool1 = _create_spool(client, color_name="Red")
        spool2 = _create_spool(client, color_name="Blue")

        client.post(f"/api/printers/{printer['id']}/ams/ams1_tray1/assign",
                    json={"spool_id": spool1["id"]})
        client.post(f"/api/printers/{printer['id']}/ams/ams1_tray1/assign",
                    json={"spool_id": spool2["id"]})

        # spool1 should be unassigned
        assert client.get(f"/api/spools/{spool1['id']}").json()["ams_slot"] is None
        # spool2 should be assigned
        assert client.get(f"/api/spools/{spool2['id']}").json()["ams_slot"] == "ams1_tray1"

    def test_assign_invalid_printer_returns_404(self, client):
        spool = _create_spool(client)
        r = client.post(
            "/api/printers/9999/ams/ams1_tray1/assign",
            json={"spool_id": spool["id"]},
        )
        assert r.status_code == 404

    def test_assign_invalid_spool_returns_404(self, client):
        printer = _create_printer(client)
        r = client.post(
            f"/api/printers/{printer['id']}/ams/ams1_tray1/assign",
            json={"spool_id": 9999},
        )
        assert r.status_code == 404
