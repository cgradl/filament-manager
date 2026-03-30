"""
Pure unit tests for SQLAlchemy model computed properties.
No database or HTTP layer involved.
"""
from datetime import datetime

import pytest

from app.models import PrintJob, PrintUsage, Spool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spool(initial_weight_g=1000.0, current_weight_g=1000.0, purchase_price=None):
    s = Spool()
    s.brand = "TestBrand"
    s.material = "PLA"
    s.color_name = "White"
    s.initial_weight_g = initial_weight_g
    s.current_weight_g = current_weight_g
    s.purchase_price = purchase_price
    return s


def _job(duration_seconds=None):
    j = PrintJob()
    j.name = "Test"
    j.started_at = datetime(2024, 1, 1, 10, 0, 0)
    j.duration_seconds = duration_seconds
    j.usages = []
    return j


def _usage(grams_used, spool=None):
    u = PrintUsage()
    u.grams_used = grams_used
    u.spool = spool
    return u


# ---------------------------------------------------------------------------
# Spool.remaining_pct
# ---------------------------------------------------------------------------

class TestSpoolRemainingPct:
    def test_full_spool(self):
        assert _spool(1000, 1000).remaining_pct == 100.0

    def test_half_spool(self):
        assert _spool(1000, 500).remaining_pct == 50.0

    def test_quarter_spool(self):
        assert _spool(1000, 250).remaining_pct == 25.0

    def test_empty_spool(self):
        assert _spool(1000, 0).remaining_pct == 0.0

    def test_never_negative(self):
        assert _spool(1000, -50).remaining_pct == 0.0

    def test_rounds_to_one_decimal(self):
        # 333g / 1000g = 33.3%
        assert _spool(1000, 333).remaining_pct == 33.3

    def test_500g_spool(self):
        assert _spool(500, 250).remaining_pct == 50.0


# ---------------------------------------------------------------------------
# Spool.price_per_kg
# ---------------------------------------------------------------------------

class TestSpoolPricePerKg:
    def test_1kg_spool(self):
        assert _spool(1000, purchase_price=20.0).price_per_kg == 20.0

    def test_500g_spool(self):
        # €10 for 500 g → €20/kg
        assert _spool(500, purchase_price=10.0).price_per_kg == 20.0

    def test_none_when_no_price(self):
        assert _spool(1000, purchase_price=None).price_per_kg is None

    def test_rounds_to_two_decimals(self):
        # €15 for 1000 g → €15.00/kg (exact)
        assert _spool(1000, purchase_price=15.0).price_per_kg == 15.0

    def test_250g_spool(self):
        # €5 for 250 g → €20/kg
        assert _spool(250, purchase_price=5.0).price_per_kg == 20.0


# ---------------------------------------------------------------------------
# Spool.cost_per_gram
# ---------------------------------------------------------------------------

class TestSpoolCostPerGram:
    def test_1kg_spool_20eur(self):
        # €20 / 1000 g = €0.02/g
        assert _spool(1000, purchase_price=20.0).cost_per_gram == pytest.approx(0.02)

    def test_500g_spool_10eur(self):
        # €10 / 500 g = €0.02/g
        assert _spool(500, purchase_price=10.0).cost_per_gram == pytest.approx(0.02)

    def test_none_when_no_price(self):
        assert _spool(1000, purchase_price=None).cost_per_gram is None


# ---------------------------------------------------------------------------
# PrintJob.total_grams / total_cost / duration_hours
# ---------------------------------------------------------------------------

class TestPrintJobProperties:
    def test_total_grams_no_usages(self):
        assert _job().total_grams == 0.0

    def test_total_grams_single_usage(self):
        j = _job()
        j.usages = [_usage(150.0)]
        assert j.total_grams == 150.0

    def test_total_grams_multiple_usages(self):
        j = _job()
        j.usages = [_usage(100.0), _usage(50.0), _usage(25.5)]
        assert j.total_grams == pytest.approx(175.5)

    def test_total_cost_no_usages(self):
        assert _job().total_cost == 0.0

    def test_total_cost_with_priced_spool(self):
        j = _job()
        spool = _spool(1000, purchase_price=20.0)  # €0.02/g
        j.usages = [_usage(100.0, spool=spool)]
        assert j.total_cost == pytest.approx(2.0)

    def test_total_cost_with_unpriced_spool(self):
        j = _job()
        spool = _spool(1000, purchase_price=None)
        j.usages = [_usage(100.0, spool=spool)]
        assert j.total_cost == 0.0

    def test_total_cost_mixed_spools(self):
        j = _job()
        priced = _spool(1000, purchase_price=20.0)   # €0.02/g
        unpriced = _spool(1000, purchase_price=None)
        j.usages = [_usage(100.0, priced), _usage(50.0, unpriced)]
        assert j.total_cost == pytest.approx(2.0)

    def test_duration_hours_one_hour(self):
        assert _job(duration_seconds=3600).duration_hours == 1.0

    def test_duration_hours_ninety_minutes(self):
        assert _job(duration_seconds=5400).duration_hours == 1.5

    def test_duration_hours_none_when_not_set(self):
        assert _job(duration_seconds=None).duration_hours is None


# ---------------------------------------------------------------------------
# PrintUsage.cost
# ---------------------------------------------------------------------------

class TestPrintUsageCost:
    def test_cost_with_priced_spool(self):
        spool = _spool(1000, purchase_price=20.0)
        u = _usage(100.0, spool=spool)
        assert u.cost == pytest.approx(2.0, abs=1e-4)

    def test_cost_none_when_spool_unpriced(self):
        spool = _spool(1000, purchase_price=None)
        u = _usage(100.0, spool=spool)
        assert u.cost is None

    def test_cost_none_when_no_spool(self):
        u = _usage(100.0, spool=None)
        assert u.cost is None

    def test_cost_proportional_to_grams(self):
        spool = _spool(1000, purchase_price=20.0)
        u1 = _usage(50.0, spool=spool)
        u2 = _usage(200.0, spool=spool)
        assert u2.cost == pytest.approx(u1.cost * 4, rel=1e-4)
