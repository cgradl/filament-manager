"""
Regression tests for print_monitor.py — the module responsible for
post-print suggestion building and background retry logic.

Every test in this file maps to a real bug that shipped:

  v0.37.2  – _background_fetch_suggestions was missing; Bambu Cloud takes
              15-60 s to finalise amsDetailMapping so immediate fetches
              returned nothing.

  v0.37.3  – suggested_usages was left as null (not []) when no suggestions
              could be built, hiding the Log Usage banner permanently.

  v0.37.3  – Fallback weight estimate called get_print_trays() at retry time
              instead of using the slot-key snapshot captured at print end.
              A new print within the 45-second window reset the cache.
"""
from __future__ import annotations

# Explicitly import so patch() can resolve modules by their dotted path.
import app.bambu_cloud_client  # noqa: F401, E402
import app.ha_publisher        # noqa: F401, E402

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import PrintJob, PrintUsage, Spool, SpoolAudit
from app.print_monitor import (
    _apply_suggested_usages,
    _background_fetch_suggestions,
    _build_suggestions,
)


# ---------------------------------------------------------------------------
# Shared data helpers
# ---------------------------------------------------------------------------

def _make_spool(
    session,
    ams_slot: str | None,
    *,
    current_weight_g: float = 800.0,
    material: str = "PLA",
    color_hex: str = "#FF0000",
) -> Spool:
    spool = Spool(
        brand="TestBrand",
        material=material,
        color_name="Test",
        color_hex=color_hex,
        initial_weight_g=1000.0,
        current_weight_g=current_weight_g,
        ams_slot=ams_slot,
    )
    session.add(spool)
    session.flush()
    return spool


def _make_job(
    session,
    *,
    suggested_usages=None,
    printer_name: str = "Printer",
    print_weight_g: float | None = None,
) -> PrintJob:
    job = PrintJob(
        name="Test Print",
        started_at=datetime.now(timezone.utc),
        source="auto",
        success=True,
        printer_name=printer_name,
        suggested_usages=suggested_usages,
        print_weight_g=print_weight_g,
    )
    session.add(job)
    session.flush()
    return job


# ---------------------------------------------------------------------------
# Canned Bambu Cloud task-data payloads for background-task tests
# ---------------------------------------------------------------------------

_AMS_WITH_DATA = {
    "weight": 50.0,
    "amsDetailMapping": [
        {"ams": 0, "weight": 50.0, "filamentType": "PLA", "sourceColor": "FF0000"},
    ],
    "amsMapping2": [],
}
_AMS_EMPTY = {"weight": 50.0, "amsDetailMapping": [], "amsMapping2": []}
_AMS_NO_DATA = {"weight": None, "amsDetailMapping": [], "amsMapping2": []}


# ---------------------------------------------------------------------------
# Fixture: patch bundle for background-task tests
# ---------------------------------------------------------------------------

@pytest.fixture
def bg_patches(session_factory):
    """
    Patches all external dependencies of _background_fetch_suggestions:

    - SessionLocal → test session factory (same in-memory DB as seeded data)
    - get_task_data_for_serial → AsyncMock (caller sets return_value / side_effect)
    - ha_publisher.trigger → no-op
    - asyncio.sleep → AsyncMock (tests complete instantly, no real 45-second wait)

    Yields (mock_task_data, mock_sleep) for assertion use.
    """
    with (
        patch("app.print_monitor.SessionLocal", session_factory),
        patch("app.bambu_cloud_client.get_task_data_for_serial") as mock_task,
        patch("app.ha_publisher.trigger"),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        yield mock_task, mock_sleep


# ===========================================================================
# Class A — _build_suggestions
# ===========================================================================

class TestBuildSuggestions:
    """
    Unit tests for the pure suggestion-building logic.
    Uses a real in-memory SQLite session; no external mocks required because
    the Bambu Cloud cache (get_ams_unit_tray_counts) returns {} for unknown
    serials, which triggers the standard 4-tray fallback slot resolution.
    """

    SERIAL = "TESTSERIAL"
    PRINTER = "Printer"

    def _call(
        self,
        session,
        job,
        *,
        ams_detail=None,
        ams_mapping2=None,
        weight=None,
        spool_snapshot=None,
        active_slot_keys=None,
    ) -> list[dict]:
        return _build_suggestions(
            job=job,
            db=session,
            ams_detail=ams_detail or [],
            ams_mapping2=ams_mapping2 or [],
            weight=weight,
            spool_snapshot=spool_snapshot or {},
            active_slot_keys=active_slot_keys or set(),
            serial=self.SERIAL,
            printer_name=self.PRINTER,
        )

    # ── amsDetailMapping present ──────────────────────────────────────────

    def test_normal_single_tray(self, session):
        """Standard case: one amsDetailMapping entry → one suggestion."""
        spool = _make_spool(session, f"{self.PRINTER}:ams1_tray1")
        job = _make_job(session)
        snap = {"ams1_tray1": {"spool_id": spool.id, "weight_g": 800.0, "material": "PLA", "color": "#FF0000"}}

        result = self._call(
            session, job,
            ams_detail=[{"ams": 0, "weight": 50.0, "filamentType": "PLA", "sourceColor": "FF0000"}],
            spool_snapshot=snap,
        )

        assert len(result) == 1
        r = result[0]
        assert r["ams_slot"] == "ams1_tray1"
        assert r["grams"] == 50.0
        assert r["spool_id"] == spool.id
        assert r["estimated"] is False
        assert r["swap_index"] is None

    def test_uses_ams_mapping2_for_slot_resolution(self, session):
        """amsMapping2 present → physical slot derived from amsId/slotId, not from flat index."""
        # slicer index 0 maps to amsId=0, slotId=2 → ams1_tray3
        spool = _make_spool(session, f"{self.PRINTER}:ams1_tray3")
        job = _make_job(session)
        snap = {"ams1_tray3": {"spool_id": spool.id, "weight_g": 800.0, "material": "PLA", "color": "#FF0000"}}

        result = self._call(
            session, job,
            ams_detail=[{"ams": 0, "weight": 30.0, "filamentType": "PLA", "sourceColor": "FF0000"}],
            ams_mapping2=[{"amsId": 0, "slotId": 2}],
            spool_snapshot=snap,
        )

        assert len(result) == 1
        assert result[0]["ams_slot"] == "ams1_tray3"
        assert result[0]["spool_id"] == spool.id

    def test_external_spool_skipped(self, session):
        """amsMapping2 entry with amsId=254 (virtual/external spool) → no suggestion."""
        job = _make_job(session)

        result = self._call(
            session, job,
            ams_detail=[{"ams": 0, "weight": 30.0}],
            ams_mapping2=[{"amsId": 254, "slotId": 0}],
        )

        assert result == []

    def test_swap_detected_splits_weight(self, session):
        """
        Spool changed mid-print (runout + manual swap):
        snapshot holds original spool, DB has replacement spool in the same slot.
        Expect two rows for the same slot — original consumed its remaining stock,
        replacement consumed the rest.
        """
        original = _make_spool(session, None, current_weight_g=500.0)      # removed from slot
        replacement = _make_spool(session, f"{self.PRINTER}:ams1_tray1", current_weight_g=900.0)
        job = _make_job(session)
        snap = {"ams1_tray1": {"spool_id": original.id, "weight_g": 500.0, "material": "PLA", "color": "#FF0000"}}

        result = self._call(
            session, job,
            ams_detail=[{"ams": 0, "weight": 600.0, "filamentType": "PLA", "sourceColor": "FF0000"}],
            spool_snapshot=snap,
        )

        assert len(result) == 2
        assert all(r["ams_slot"] == "ams1_tray1" for r in result)
        by_swap = {r["swap_index"]: r for r in result}
        assert by_swap[0]["grams"] == 500.0        # original consumed min(500, 600)
        assert by_swap[0]["spool_id"] == original.id
        assert by_swap[1]["grams"] == 100.0        # remainder = 600 - 500
        assert by_swap[1]["spool_id"] == replacement.id

    def test_auto_switch_splits_weight_across_slots(self, session):
        """
        AMS auto-switched to a backup tray with the same material+color.
        Weight in amsDetailMapping covers both; split by snapshot stock level.
        """
        spool1 = _make_spool(session, f"{self.PRINTER}:ams1_tray1", current_weight_g=50.0)
        spool2 = _make_spool(session, f"{self.PRINTER}:ams1_tray2", current_weight_g=200.0)
        job = _make_job(session)
        snap = {
            "ams1_tray1": {"spool_id": spool1.id, "weight_g": 50.0,  "material": "PLA", "color": "#FF0000"},
            "ams1_tray2": {"spool_id": spool2.id, "weight_g": 200.0, "material": "PLA", "color": "#FF0000"},
        }

        result = self._call(
            session, job,
            ams_detail=[{"ams": 0, "weight": 250.0, "filamentType": "PLA", "sourceColor": "FF0000"}],
            spool_snapshot=snap,
            active_slot_keys={"ams1_tray1", "ams1_tray2"},
        )

        assert len(result) == 2
        by_slot = {r["ams_slot"]: r for r in result}
        assert by_slot["ams1_tray2"]["grams"] == 200.0   # filled from backup first (sorted order)
        assert by_slot["ams1_tray1"]["grams"] == 50.0    # remainder on primary

    # ── amsDetailMapping absent — fallback path ───────────────────────────

    def test_fallback_uses_captured_active_slot_key(self, session):
        """
        No amsDetailMapping but weight + single active_slot_key known:
        creates one suggestion with total weight.
        Regression: old code called get_print_trays() at retry time;
        if a new print had started, the cache was cleared and this returned [].
        """
        spool = _make_spool(session, f"{self.PRINTER}:ams1_tray1")
        job = _make_job(session)
        snap = {"ams1_tray1": {"spool_id": spool.id, "weight_g": 800.0, "material": "PLA", "color": "#FF0000"}}

        result = self._call(
            session, job,
            weight=50.0,
            spool_snapshot=snap,
            active_slot_keys={"ams1_tray1"},
        )

        assert len(result) == 1
        assert result[0]["ams_slot"] == "ams1_tray1"
        assert result[0]["grams"] == 50.0
        assert result[0]["spool_id"] == spool.id

    def test_fallback_equal_split_when_multiple_active_slots(self, session):
        """
        No amsDetailMapping, weight known, two active slots:
        returns equal-split suggestions marked estimated=True so the user can review.
        """
        spool1 = _make_spool(session, f"{self.PRINTER}:ams1_tray1")
        spool2 = _make_spool(session, f"{self.PRINTER}:ams1_tray2")
        job = _make_job(session)
        snap = {
            "ams1_tray1": {"spool_id": spool1.id, "weight_g": 500.0, "material": "PLA", "color": "#FF0000"},
            "ams1_tray2": {"spool_id": spool2.id, "weight_g": 300.0, "material": "PETG", "color": "#00FF00"},
        }

        result = self._call(
            session, job,
            weight=100.0,
            spool_snapshot=snap,
            active_slot_keys={"ams1_tray1", "ams1_tray2"},
        )

        assert len(result) == 2
        slots = {r["ams_slot"] for r in result}
        assert slots == {"ams1_tray1", "ams1_tray2"}
        for r in result:
            assert r["grams"] == 50.0
            assert r["estimated"] is True

    def test_empty_input_returns_empty(self, session):
        """No amsDetailMapping and no weight → nothing to build."""
        job = _make_job(session)
        assert self._call(session, job) == []

    def test_spool_id_none_when_slot_unassigned(self, session):
        """
        amsDetailMapping entry references a slot with no spool in snapshot or DB.
        Suggestion is still produced (user can pick spool manually) with spool_id=None.
        """
        job = _make_job(session)

        result = self._call(
            session, job,
            ams_detail=[{"ams": 0, "weight": 30.0, "filamentType": "PETG"}],
        )

        assert len(result) == 1
        assert result[0]["spool_id"] is None
        assert result[0]["grams"] == 30.0


# ===========================================================================
# Class B — _apply_suggested_usages
# ===========================================================================

class TestApplySuggestedUsages:
    """Unit tests for the deduction step executed by auto-deduct or on user confirm."""

    def test_creates_usage_and_deducts_weight(self, session):
        spool = _make_spool(session, "ams1_tray1", current_weight_g=800.0)
        job = _make_job(session, suggested_usages=[
            {"ams_slot": "ams1_tray1", "grams": 50.0, "spool_id": spool.id},
        ])

        _apply_suggested_usages(job, session)
        session.flush()

        assert spool.current_weight_g == 750.0
        usage = session.query(PrintUsage).filter_by(print_job_id=job.id).first()
        assert usage is not None
        assert usage.grams_used == 50.0
        assert usage.spool_id == spool.id
        audit = session.query(SpoolAudit).filter_by(spool_id=spool.id).first()
        assert audit is not None
        assert audit.delta_g == -50.0
        assert audit.action == "print_auto"

    def test_clears_suggested_usages_after_apply(self, session):
        """After apply, suggested_usages is set to None so the UI banner disappears."""
        spool = _make_spool(session, "ams1_tray1")
        job = _make_job(session, suggested_usages=[
            {"ams_slot": "ams1_tray1", "grams": 20.0, "spool_id": spool.id},
        ])

        _apply_suggested_usages(job, session)

        assert job.suggested_usages is None

    def test_idempotent(self, session):
        """Calling twice must not create a second usage row or double-deduct weight."""
        spool = _make_spool(session, "ams1_tray1", current_weight_g=800.0)
        suggestion = {"ams_slot": "ams1_tray1", "grams": 50.0, "spool_id": spool.id}

        job = _make_job(session, suggested_usages=[suggestion])
        _apply_suggested_usages(job, session)
        session.flush()

        # Expire so job.usages reloads from DB on next access (includes the row
        # we just flushed), then re-arm suggested_usages and call again.
        session.expire(job)
        job.suggested_usages = [suggestion]
        _apply_suggested_usages(job, session)
        session.flush()

        assert session.query(PrintUsage).filter_by(print_job_id=job.id).count() == 1
        assert spool.current_weight_g == 750.0   # deducted exactly once

    def test_skips_zero_grams(self, session):
        spool = _make_spool(session, "ams1_tray1", current_weight_g=800.0)
        job = _make_job(session, suggested_usages=[
            {"ams_slot": "ams1_tray1", "grams": 0.0, "spool_id": spool.id},
        ])

        _apply_suggested_usages(job, session)
        session.flush()

        assert spool.current_weight_g == 800.0
        assert session.query(PrintUsage).filter_by(print_job_id=job.id).count() == 0

    def test_fallback_slot_lookup_when_spool_id_none(self, session):
        """spool_id=None in suggestion → resolved by ams_slot query against DB."""
        spool = _make_spool(session, "ams1_tray1", current_weight_g=800.0)
        job = _make_job(session, suggested_usages=[
            {"ams_slot": "ams1_tray1", "grams": 30.0, "spool_id": None},
        ])

        _apply_suggested_usages(job, session)
        session.flush()

        assert spool.current_weight_g == 770.0
        usage = session.query(PrintUsage).filter_by(print_job_id=job.id).first()
        assert usage is not None
        assert usage.spool_id == spool.id

    def test_skips_missing_spool_without_crash(self, session):
        """spool_id unknown and no spool in slot → skips entry, no exception."""
        job = _make_job(session, suggested_usages=[
            {"ams_slot": "ams9_tray9", "grams": 20.0, "spool_id": 99999},
        ])

        _apply_suggested_usages(job, session)  # must not raise
        session.flush()

        assert session.query(PrintUsage).filter_by(print_job_id=job.id).count() == 0


# ===========================================================================
# Class C — _background_fetch_suggestions (async)
# ===========================================================================

class TestBackgroundFetchSuggestions:
    """
    Async integration tests for the background retry task.

    All three v0.37.x bugs are exercised:
      - timing race  → test_first_attempt_empty_retries
      - banner never showed  → test_both_attempts_empty_stores_empty_list
      - stale MQTT cache in fallback  → covered by TestBuildSuggestions above
    """

    SERIAL = "BGSERIAL"
    PRINTER = "Printer"

    def _snapshot(self, spool_id: int) -> dict:
        return {"ams1_tray1": {
            "spool_id": spool_id, "weight_g": 800.0, "material": "PLA", "color": "#FF0000",
        }}

    async def test_first_attempt_success(self, session, bg_patches):
        """Cloud has amsDetailMapping ready on first call → stored immediately, no sleep."""
        mock_task, mock_sleep = bg_patches
        spool = _make_spool(session, f"{self.PRINTER}:ams1_tray1")
        job = _make_job(session, printer_name=self.PRINTER)
        session.commit()

        mock_task.return_value = _AMS_WITH_DATA

        await _background_fetch_suggestions(
            job_id=job.id, serial=self.SERIAL, auto_deduct=False,
            spool_snapshot=self._snapshot(spool.id),
            active_slot_keys={"ams1_tray1"},
            printer_name=self.PRINTER,
        )

        session.expire(job)
        assert job.suggested_usages is not None
        assert len(job.suggested_usages) == 1
        mock_sleep.assert_not_called()

    async def test_first_attempt_empty_retries_after_45s(self, session, bg_patches):
        """
        Regression: v0.37.2 — Bambu Cloud takes 15-60 s to finalise amsDetailMapping.
        First fetch returns empty; background task must sleep 45 s and retry.
        """
        mock_task, mock_sleep = bg_patches
        spool = _make_spool(session, f"{self.PRINTER}:ams1_tray1")
        job = _make_job(session, printer_name=self.PRINTER)
        session.commit()

        mock_task.side_effect = [_AMS_EMPTY, _AMS_WITH_DATA]

        await _background_fetch_suggestions(
            job_id=job.id, serial=self.SERIAL, auto_deduct=False,
            spool_snapshot=self._snapshot(spool.id),
            active_slot_keys={"ams1_tray1"},
            printer_name=self.PRINTER,
        )

        session.expire(job)
        assert job.suggested_usages is not None
        assert len(job.suggested_usages) == 1
        mock_sleep.assert_called_once_with(45)

    async def test_both_attempts_empty_stores_empty_list(self, session, bg_patches):
        """
        Regression: v0.37.3 — when no suggestions can be built after both attempts,
        suggested_usages must be stored as [] (not left as null) so the frontend
        Log Usage banner appears and the user can log manually.
        """
        mock_task, _ = bg_patches
        job = _make_job(session, printer_name=self.PRINTER)
        session.commit()

        mock_task.return_value = _AMS_NO_DATA   # no weight, no amsDetailMapping

        await _background_fetch_suggestions(
            job_id=job.id, serial=self.SERIAL, auto_deduct=False,
            spool_snapshot={},
            active_slot_keys=set(),
            printer_name=self.PRINTER,
        )

        session.expire(job)
        # [] is not None → frontend shows Log Usage banner
        assert job.suggested_usages == []

    async def test_already_has_suggestions_returns_early(self, session, bg_patches):
        """If suggested_usages is already populated, the cloud is never called."""
        mock_task, _ = bg_patches
        existing = [{"ams_slot": "ams1_tray1", "grams": 10.0}]
        job = _make_job(session, suggested_usages=existing, printer_name=self.PRINTER)
        session.commit()

        await _background_fetch_suggestions(
            job_id=job.id, serial=self.SERIAL, auto_deduct=False,
            spool_snapshot={},
            active_slot_keys=set(),
            printer_name=self.PRINTER,
        )

        mock_task.assert_not_called()
        session.expire(job)
        assert job.suggested_usages == existing   # unchanged

    async def test_auto_deduct_applies_and_clears(self, session, bg_patches):
        """auto_deduct=True → usages applied immediately, suggested_usages cleared to None."""
        mock_task, _ = bg_patches
        spool = _make_spool(session, f"{self.PRINTER}:ams1_tray1", current_weight_g=800.0)
        job = _make_job(session, printer_name=self.PRINTER)
        session.commit()

        mock_task.return_value = _AMS_WITH_DATA

        await _background_fetch_suggestions(
            job_id=job.id, serial=self.SERIAL, auto_deduct=True,
            spool_snapshot=self._snapshot(spool.id),
            active_slot_keys={"ams1_tray1"},
            printer_name=self.PRINTER,
        )

        session.expire_all()
        assert job.suggested_usages is None   # cleared after auto-deduct
        assert spool.current_weight_g == 750.0
        assert session.query(PrintUsage).filter_by(print_job_id=job.id).count() == 1

    async def test_weight_persisted_on_first_attempt_before_retry(self, session, bg_patches):
        """
        When attempt 0 gets weight but empty amsDetailMapping, print_weight_g is
        committed immediately so it survives even if attempt 1 also returns nothing.
        """
        mock_task, _ = bg_patches
        job = _make_job(session, printer_name=self.PRINTER)
        session.commit()

        # First call: has weight, no detail; second call: nothing at all
        mock_task.side_effect = [_AMS_EMPTY, _AMS_NO_DATA]

        await _background_fetch_suggestions(
            job_id=job.id, serial=self.SERIAL, auto_deduct=False,
            spool_snapshot={},
            active_slot_keys=set(),
            printer_name=self.PRINTER,
        )

        session.expire(job)
        assert job.print_weight_g == 50.0   # from _AMS_EMPTY["weight"]
        assert job.suggested_usages == []   # empty but not null


# ===========================================================================
# Class D — seed_active_slot (bambu_cloud_client)
# ===========================================================================

class TestSeedActiveSlot:
    """
    Unit tests for the initial-tray seeding fix.

    Root cause: MQTT pushall delivers tray_now BEFORE gcode_state=RUNNING, so
    reset_print_trays() (called at RUNNING) clears it.  seed_active_slot() re-adds
    the cached tray_now immediately after the reset so the initial slot is always
    captured in active_slot_keys.
    """

    SERIAL = "SEEDSERIAL"

    def test_seed_restores_slot_after_reset(self):
        """seed_active_slot adds the correct slot_key after reset clears it."""
        from app.bambu_cloud_client import (
            get_print_active_slot_keys,
            reset_print_trays,
            seed_active_slot,
        )

        reset_print_trays(self.SERIAL)
        assert get_print_active_slot_keys(self.SERIAL) == set()

        # Index 0 → ams1_tray1 in the standard 4-trays-per-unit layout
        seed_active_slot(self.SERIAL, 0)

        assert get_print_active_slot_keys(self.SERIAL) == {"ams1_tray1"}

    def test_seed_external_index_is_noop(self):
        """External spool index 254 → _ams_index_to_slot_key returns None → no-op."""
        from app.bambu_cloud_client import (
            get_print_active_slot_keys,
            reset_print_trays,
            seed_active_slot,
        )

        reset_print_trays(self.SERIAL)
        seed_active_slot(self.SERIAL, 254)

        assert get_print_active_slot_keys(self.SERIAL) == set()

    def test_seed_second_unit_tray(self):
        """Index 4 → ams2_tray1 (second AMS unit, first slot)."""
        from app.bambu_cloud_client import (
            get_print_active_slot_keys,
            reset_print_trays,
            seed_active_slot,
        )

        reset_print_trays(self.SERIAL)
        seed_active_slot(self.SERIAL, 4)

        assert get_print_active_slot_keys(self.SERIAL) == {"ams2_tray1"}


# ===========================================================================
# Class E — _build_suggestions: uncovered active slots (multi-spool fix)
# ===========================================================================

class TestBuildSuggestionsUncoveredSlots:
    """
    Regression tests for the multi-spool partial-coverage fix.

    Scenario: a 2-spool print where slot A was active at print start (seeded from
    tray_now) but amsDetailMapping only lists slot B (used after the tray switch).
    Before the fix, only slot B got a suggestion.  After the fix, slot A receives
    an estimated suggestion for the remaining weight.
    """

    SERIAL = "UNCOVEREDSERIAL"
    PRINTER = "Printer"

    def _call(self, session, job, **kwargs) -> list[dict]:
        return _build_suggestions(
            job=job,
            db=session,
            ams_detail=kwargs.get("ams_detail", []),
            ams_mapping2=kwargs.get("ams_mapping2", []),
            weight=kwargs.get("weight"),
            spool_snapshot=kwargs.get("spool_snapshot", {}),
            active_slot_keys=kwargs.get("active_slot_keys", set()),
            serial=self.SERIAL,
            printer_name=self.PRINTER,
        )

    def test_uncovered_initial_slot_gets_remaining_weight(self, session):
        """
        amsDetailMapping lists tray2 (60g); tray1 was active at start (not in mapping).
        Total weight = 100g → tray1 must receive 40g as an estimated suggestion.

        Regression: before fix, only tray2 was returned; tray1 was silently dropped.
        """
        spool1 = _make_spool(session, f"{self.PRINTER}:ams1_tray1", material="PLA")
        spool2 = _make_spool(session, f"{self.PRINTER}:ams1_tray2", material="PETG")
        job = _make_job(session)
        snap = {
            "ams1_tray1": {"spool_id": spool1.id, "weight_g": 500.0, "material": "PLA", "color": "#FF0000"},
            "ams1_tray2": {"spool_id": spool2.id, "weight_g": 300.0, "material": "PETG", "color": "#00FF00"},
        }

        # slicer index 1 → ams1_tray2 via flat-index fallback
        result = self._call(
            session, job,
            ams_detail=[{"ams": 1, "weight": 60.0, "filamentType": "PETG", "sourceColor": "00FF00"}],
            weight=100.0,
            spool_snapshot=snap,
            active_slot_keys={"ams1_tray1", "ams1_tray2"},
        )

        assert len(result) == 2
        by_slot = {r["ams_slot"]: r for r in result}

        # tray2: from amsDetailMapping — exact weight, not estimated
        assert by_slot["ams1_tray2"]["grams"] == 60.0
        assert by_slot["ams1_tray2"]["estimated"] is False
        assert by_slot["ams1_tray2"]["spool_id"] == spool2.id

        # tray1: uncovered initial slot — remaining weight, marked estimated
        assert by_slot["ams1_tray1"]["grams"] == 40.0
        assert by_slot["ams1_tray1"]["estimated"] is True
        assert by_slot["ams1_tray1"]["spool_id"] == spool1.id

    def test_no_uncovered_slots_when_all_covered_by_mapping(self, session):
        """When amsDetailMapping covers all active slots, no extra rows are added."""
        # Use different materials so auto-switch logic is not triggered between the two slots.
        spool1 = _make_spool(session, f"{self.PRINTER}:ams1_tray1", material="PLA",  color_hex="#FF0000")
        spool2 = _make_spool(session, f"{self.PRINTER}:ams1_tray2", material="PETG", color_hex="#00FF00")
        job = _make_job(session)
        snap = {
            "ams1_tray1": {"spool_id": spool1.id, "weight_g": 500.0, "material": "PLA",  "color": "#FF0000"},
            "ams1_tray2": {"spool_id": spool2.id, "weight_g": 300.0, "material": "PETG", "color": "#00FF00"},
        }

        result = self._call(
            session, job,
            ams_detail=[
                {"ams": 0, "weight": 40.0, "filamentType": "PLA",  "sourceColor": "FF0000"},
                {"ams": 1, "weight": 60.0, "filamentType": "PETG", "sourceColor": "00FF00"},
            ],
            weight=100.0,
            spool_snapshot=snap,
            active_slot_keys={"ams1_tray1", "ams1_tray2"},
        )

        assert len(result) == 2
        by_slot = {r["ams_slot"]: r for r in result}
        assert by_slot["ams1_tray1"]["grams"] == 40.0
        assert by_slot["ams1_tray2"]["grams"] == 60.0

    def test_uncovered_slots_not_added_when_no_remaining_weight(self, session):
        """
        amsDetailMapping accounts for all the weight → remaining = 0 →
        no estimated entry added for the uncovered active slot.
        """
        spool1 = _make_spool(session, f"{self.PRINTER}:ams1_tray1")
        spool2 = _make_spool(session, f"{self.PRINTER}:ams1_tray2")
        job = _make_job(session)
        snap = {
            "ams1_tray1": {"spool_id": spool1.id, "weight_g": 500.0, "material": "PLA", "color": "#FF0000"},
            "ams1_tray2": {"spool_id": spool2.id, "weight_g": 300.0, "material": "PETG", "color": "#00FF00"},
        }

        # amsDetailMapping reports the full 100g on tray2; tray1 was technically active
        # but consumed nothing (e.g. print switched to tray2 immediately after start)
        result = self._call(
            session, job,
            ams_detail=[{"ams": 1, "weight": 100.0, "filamentType": "PETG", "sourceColor": "00FF00"}],
            weight=100.0,
            spool_snapshot=snap,
            active_slot_keys={"ams1_tray1", "ams1_tray2"},
        )

        assert len(result) == 1
        assert result[0]["ams_slot"] == "ams1_tray2"
        assert result[0]["grams"] == 100.0
