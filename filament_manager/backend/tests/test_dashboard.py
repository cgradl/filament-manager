"""
Integration tests for /api/dashboard endpoints.
Verifies that computed aggregates (counts, weights, costs, breakdowns)
match the data in the database.
"""
import pytest
from unittest.mock import AsyncMock, patch
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


def _stats(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    return r.json()


# ---------------------------------------------------------------------------
# Empty database
# ---------------------------------------------------------------------------

class TestEmptyDashboard:
    def test_returns_200(self, client):
        assert client.get("/api/dashboard").status_code == 200

    def test_zero_counts(self, client):
        s = _stats(client)
        assert s["total_spools"] == 0
        assert s["active_spools"] == 0
        assert s["empty_spools"] == 0
        assert s["low_stock_spools"] == 0

    def test_zero_weights(self, client):
        s = _stats(client)
        assert s["total_filament_kg"] == 0.0
        assert s["total_available_kg"] == 0.0
        assert s["total_printed_kg"] == 0.0

    def test_zero_costs(self, client):
        s = _stats(client)
        assert s["total_filament_spent_eur"] == 0.0
        assert s["total_print_cost_eur"] == 0.0
        assert s["total_available_eur"] == 0.0

    def test_empty_lists(self, client):
        s = _stats(client)
        assert s["material_breakdown"] == []
        assert s["price_by_location"] == []
        assert s["recent_prints"] == []
        assert s["low_stock"] == []


# ---------------------------------------------------------------------------
# Spool counts
# ---------------------------------------------------------------------------

class TestSpoolCounts:
    def test_total_spools(self, client):
        _create_spool(client, color_name="Red")
        _create_spool(client, color_name="Blue")
        assert _stats(client)["total_spools"] == 2

    def test_active_vs_empty_spools(self, client):
        _create_spool(client, color_name="Full", initial_weight_g=1000, current_weight_g=500)
        _create_spool(client, color_name="Empty", initial_weight_g=1000, current_weight_g=0)
        s = _stats(client)
        assert s["active_spools"] == 1
        assert s["empty_spools"] == 1

    def test_low_stock_detection(self, client):
        # 15% remaining → low stock (threshold < 20%)
        _create_spool(client, color_name="LowStock", initial_weight_g=1000, current_weight_g=150)
        # 50% remaining → not low stock
        _create_spool(client, color_name="NormalStock", initial_weight_g=1000, current_weight_g=500)
        s = _stats(client)
        assert s["low_stock_spools"] == 1
        assert len(s["low_stock"]) == 1
        assert s["low_stock"][0]["color_name"] == "LowStock"

    def test_empty_spool_not_in_low_stock(self, client):
        _create_spool(client, color_name="Empty", initial_weight_g=1000, current_weight_g=0)
        assert _stats(client)["low_stock_spools"] == 0

    def test_low_stock_sorted_ascending_by_pct(self, client):
        _create_spool(client, color_name="10pct", initial_weight_g=1000, current_weight_g=100)
        _create_spool(client, color_name="5pct", initial_weight_g=1000, current_weight_g=50)
        _create_spool(client, color_name="15pct", initial_weight_g=1000, current_weight_g=150)
        low = _stats(client)["low_stock"]
        pcts = [s["remaining_pct"] for s in low]
        assert pcts == sorted(pcts)


# ---------------------------------------------------------------------------
# Weight totals
# ---------------------------------------------------------------------------

class TestWeightTotals:
    def test_total_filament_kg(self, client):
        _create_spool(client, color_name="A", initial_weight_g=1000, current_weight_g=1000)
        _create_spool(client, color_name="B", initial_weight_g=500, current_weight_g=500)
        assert _stats(client)["total_filament_kg"] == pytest.approx(1.5, abs=0.001)

    def test_total_available_kg_excludes_empty(self, client):
        _create_spool(client, color_name="Full", initial_weight_g=1000, current_weight_g=800)
        _create_spool(client, color_name="Empty", initial_weight_g=1000, current_weight_g=0)
        assert _stats(client)["total_available_kg"] == pytest.approx(0.8, abs=0.001)

    def test_total_printed_kg(self, client):
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=1000)
        _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 200.0}])
        assert _stats(client)["total_printed_kg"] == pytest.approx(0.2, abs=0.001)


# ---------------------------------------------------------------------------
# Cost totals
# ---------------------------------------------------------------------------

class TestCostTotals:
    def test_total_filament_spent(self, client):
        _create_spool(client, color_name="A", purchase_price=20.0)
        _create_spool(client, color_name="B", purchase_price=15.0)
        assert _stats(client)["total_filament_spent_eur"] == pytest.approx(35.0, abs=0.01)

    def test_total_filament_spent_ignores_no_price(self, client):
        _create_spool(client, color_name="Priced", purchase_price=20.0)
        _create_spool(client, color_name="Unpriced", purchase_price=None)
        assert _stats(client)["total_filament_spent_eur"] == pytest.approx(20.0, abs=0.01)

    def test_total_print_cost(self, client):
        # €20/kg spool → €0.02/g; 100g print → €2.00
        spool = _create_spool(client, initial_weight_g=1000, current_weight_g=1000, purchase_price=20.0)
        _create_print(client, usages=[{"spool_id": spool["id"], "grams_used": 100.0}])
        assert _stats(client)["total_print_cost_eur"] == pytest.approx(2.0, abs=0.01)


# ---------------------------------------------------------------------------
# Material breakdown
# ---------------------------------------------------------------------------

class TestMaterialBreakdown:
    def test_groups_by_material(self, client):
        _create_spool(client, material="PLA", color_name="R", initial_weight_g=1000, current_weight_g=800)
        _create_spool(client, material="PLA", color_name="B", initial_weight_g=1000, current_weight_g=600)
        _create_spool(client, material="PETG", color_name="G", initial_weight_g=500, current_weight_g=500)
        breakdown = {m["material"]: m for m in _stats(client)["material_breakdown"]}
        assert breakdown["PLA"]["count"] == 2
        assert breakdown["PETG"]["count"] == 1

    def test_current_kg_aggregated(self, client):
        _create_spool(client, material="PLA", color_name="R", initial_weight_g=1000, current_weight_g=400)
        _create_spool(client, material="PLA", color_name="B", initial_weight_g=1000, current_weight_g=600)
        breakdown = {m["material"]: m for m in _stats(client)["material_breakdown"]}
        assert breakdown["PLA"]["current_kg"] == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# Recent prints
# ---------------------------------------------------------------------------

class TestRecentPrints:
    def test_recent_prints_limited_to_5(self, client):
        for i in range(7):
            _create_print(client, name=f"Print {i}", started_at=f"2024-0{min(i+1,9)}-01T00:00:00")
        assert len(_stats(client)["recent_prints"]) == 5

    def test_recent_prints_most_recent_first(self, client):
        _create_print(client, name="Old", started_at="2024-01-01T00:00:00")
        _create_print(client, name="New", started_at="2024-12-01T00:00:00")
        recent = _stats(client)["recent_prints"]
        assert recent[0]["name"] == "New"


# ---------------------------------------------------------------------------
# HA status endpoint
# ---------------------------------------------------------------------------

class TestHAStatus:
    def test_ha_available(self, client):
        with patch("app.routers.dashboard.ha_client.is_ha_available", new=AsyncMock(return_value=True)):
            r = client.get("/api/dashboard/ha-status")
        assert r.status_code == 200
        assert r.json()["ha_available"] is True

    def test_ha_unavailable(self, client):
        with patch("app.routers.dashboard.ha_client.is_ha_available", new=AsyncMock(return_value=False)):
            r = client.get("/api/dashboard/ha-status")
        assert r.json()["ha_available"] is False
