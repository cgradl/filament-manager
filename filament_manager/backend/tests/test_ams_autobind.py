"""
Tests for RFID tag_uid AMS auto-bind (app.ams_autobind) and the assign
endpoint's tag_uid persistence.

The auto-bind logic is exercised against the in-memory DB via the `session`
fixture with `bambu_cloud_client.get_ams_detail_for_serial` monkeypatched to
return a synthetic AMS tray snapshot. The assign endpoint is exercised via the
HTTP `client`.
"""
import pytest
from unittest.mock import patch

from app import ams_autobind, bambu_cloud_client
from app.models import PrinterConfig, Spool
from tests.conftest import make_spool_payload


REAL_TAG = "4767E20300000100"
REAL_TAG_2 = "4767E20300000200"
ZERO_TAG = "0000000000000000"
SERIAL = "01P00A000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_printer(session, name="My Printer", serial=SERIAL, active=True):
    p = PrinterConfig(name=name, bambu_serial=serial, is_active=active, bambu_source="cloud")
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _mk_spool(session, **kw):
    data = make_spool_payload(**kw)
    s = Spool(**data)
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


def _run_autobind(session, detail):
    """Patch the AMS cache + SessionLocal so autobind uses the test DB session."""
    class _Factory:
        def __call__(self):
            return session
    # autobind opens its own SessionLocal() and closes it — patch to hand back
    # the test session and no-op close so assertions can read the same rows.
    orig_close = session.close
    session.close = lambda: None
    try:
        with patch.object(bambu_cloud_client, "get_ams_detail_for_serial", return_value=detail), \
             patch.object(ams_autobind, "SessionLocal", _Factory()), \
             patch("app.ha_publisher.trigger", lambda: None):
            return ams_autobind.autobind_from_ams_cache(SERIAL)
    finally:
        session.close = orig_close


# ---------------------------------------------------------------------------
# _is_real_tag_uid
# ---------------------------------------------------------------------------

class TestIsRealTagUid:
    @pytest.mark.parametrize("val", [None, "", "   ", ZERO_TAG, "000", "0"])
    def test_rejects_empty_and_zeros(self, val):
        assert ams_autobind._is_real_tag_uid(val) is False

    @pytest.mark.parametrize("val", [REAL_TAG, "4767E20300000100", "0000000000000001"])
    def test_accepts_real(self, val):
        assert ams_autobind._is_real_tag_uid(val) is True


# ---------------------------------------------------------------------------
# Exact RFID match ONLY — never guess by material/colour
# ---------------------------------------------------------------------------

class TestExactMatch:
    def test_exact_tag_match_binds(self, session):
        """A spool whose tag_uid was populated (from cloud sync or manual assign)
        binds when that exact RFID appears in a tray."""
        _mk_printer(session)
        spool = _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        spool.tag_uid = REAL_TAG
        session.commit()
        detail = {"ams1_tray1": {"material": "PLA", "color": "#FFFFFF", "tag_uid": REAL_TAG, "remain": 90}}

        changed = _run_autobind(session, detail)

        session.refresh(spool)
        assert changed == 1
        assert spool.ams_slot == "My Printer:ams1_tray1"

    def test_material_color_match_does_NOT_bind(self, session):
        """Regression: a spool matching material+colour but with NO tag_uid must
        NEVER be auto-bound. Material/colour identifies a product, not a physical
        spool — guessing by it stamped the wrong RFID onto records (the bug)."""
        _mk_printer(session)
        spool = _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        detail = {"ams1_tray1": {"material": "PLA", "color": "#FFFFFF", "tag_uid": REAL_TAG, "remain": 90}}

        changed = _run_autobind(session, detail)

        session.refresh(spool)
        assert changed == 0
        assert spool.tag_uid is None
        assert spool.ams_slot is None

    def test_unknown_tag_is_noop(self, session):
        """A real tag matching no spool's tag_uid → nothing happens, no error."""
        _mk_printer(session)
        spool = _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        spool.tag_uid = REAL_TAG_2  # a DIFFERENT physical spool
        session.commit()
        detail = {"ams1_tray1": {"material": "PLA", "color": "#FFFFFF", "tag_uid": REAL_TAG, "remain": 90}}

        changed = _run_autobind(session, detail)

        session.refresh(spool)
        assert changed == 0
        assert spool.ams_slot is None

    def test_zero_tag_is_skipped(self, session):
        """Third-party spool (all-zeros tag) → never auto-bound, even with an
        exact material/colour spool present."""
        _mk_printer(session)
        spool = _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        detail = {"ams1_tray1": {"material": "PLA", "color": "#FFFFFF", "tag_uid": ZERO_TAG, "remain": 90}}

        changed = _run_autobind(session, detail)
        session.refresh(spool)
        assert changed == 0
        assert spool.tag_uid is None
        assert spool.ams_slot is None


# ---------------------------------------------------------------------------
# Deterministic re-bind (tag already known)
# ---------------------------------------------------------------------------

class TestReBind:
    def test_known_tag_rebinds_to_new_slot(self, session):
        _mk_printer(session)
        spool = _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        spool.tag_uid = REAL_TAG
        spool.ams_slot = "My Printer:ams1_tray1"
        session.commit()

        # Same physical spool now loaded in tray 3
        detail = {"ams1_tray3": {"material": "PLA", "color": "#FFFFFF", "tag_uid": REAL_TAG, "remain": 80}}
        changed = _run_autobind(session, detail)

        session.refresh(spool)
        assert changed == 1
        assert spool.ams_slot == "My Printer:ams1_tray3"

    def test_known_tag_same_slot_no_change(self, session):
        _mk_printer(session)
        spool = _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        spool.tag_uid = REAL_TAG
        spool.ams_slot = "My Printer:ams1_tray1"
        session.commit()

        detail = {"ams1_tray1": {"material": "PLA", "color": "#FFFFFF", "tag_uid": REAL_TAG, "remain": 80}}
        changed = _run_autobind(session, detail)
        session.refresh(spool)
        assert changed == 0
        assert spool.ams_slot == "My Printer:ams1_tray1"

    def test_rebind_clears_slot_from_other_spool(self, session):
        """A tag_uid is unique → a second spool wrongly on the slot is cleared."""
        _mk_printer(session)
        bound = _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        bound.tag_uid = REAL_TAG
        session.commit()
        squatter = _mk_spool(session, material="PLA", color_name="Blue", color_hex="#0000FF")
        squatter.ams_slot = "My Printer:ams1_tray5"
        session.commit()

        detail = {"ams1_tray5": {"material": "PLA", "color": "#FFFFFF", "tag_uid": REAL_TAG, "remain": 70}}
        changed = _run_autobind(session, detail)

        session.refresh(bound); session.refresh(squatter)
        assert changed == 1
        assert bound.ams_slot == "My Printer:ams1_tray5"
        assert squatter.ams_slot is None


# ---------------------------------------------------------------------------
# Inactive printer / no data
# ---------------------------------------------------------------------------

class TestGuards:
    def test_inactive_printer_no_bind(self, session):
        _mk_printer(session, active=False)
        spool = _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        detail = {"ams1_tray1": {"material": "PLA", "color": "#FFFFFF", "tag_uid": REAL_TAG, "remain": 90}}
        changed = _run_autobind(session, detail)
        session.refresh(spool)
        assert changed == 0
        assert spool.tag_uid is None

    def test_no_real_tag_short_circuits(self, session):
        _mk_printer(session)
        _mk_spool(session, material="PLA", color_name="White", color_hex="#FFFFFF")
        detail = {"ams1_tray1": {"material": "PLA", "color": "#FFFFFF", "tag_uid": ZERO_TAG}}
        assert _run_autobind(session, detail) == 0


# ---------------------------------------------------------------------------
# Assign endpoint persists tag_uid
# ---------------------------------------------------------------------------

class TestAssignPersistsTagUid:
    def test_assign_stores_tray_tag_uid_on_spool(self, client):
        r = client.post("/api/printers", json={"name": "My Printer", "bambu_serial": SERIAL})
        printer = r.json()
        spool = client.post("/api/spools", json=make_spool_payload()).json()

        detail = {"ams1_tray1": {"material": "PLA", "color": "#FF0000", "tag_uid": REAL_TAG, "remain": 90}}
        with patch("app.bambu_cloud_client.get_ams_detail_for_serial", return_value=detail), \
             patch("app.bambu_cloud_client.register_printer"), \
             patch("app.ha_publisher.trigger"):
            resp = client.post(
                f"/api/printers/{printer['id']}/ams/ams1_tray1/assign",
                json={"spool_id": spool["id"]},
            )
        assert resp.status_code == 200
        got = client.get(f"/api/spools/{spool['id']}").json()
        assert got["ams_slot"] == "My Printer:ams1_tray1"
        assert got["tag_uid"] == REAL_TAG

    def test_assign_ignores_zero_tag(self, client):
        r = client.post("/api/printers", json={"name": "My Printer", "bambu_serial": SERIAL})
        printer = r.json()
        spool = client.post("/api/spools", json=make_spool_payload()).json()

        detail = {"ams1_tray1": {"material": "PLA", "color": "#FF0000", "tag_uid": ZERO_TAG, "remain": 90}}
        with patch("app.bambu_cloud_client.get_ams_detail_for_serial", return_value=detail), \
             patch("app.bambu_cloud_client.register_printer"), \
             patch("app.ha_publisher.trigger"):
            resp = client.post(
                f"/api/printers/{printer['id']}/ams/ams1_tray1/assign",
                json={"spool_id": spool["id"]},
            )
        assert resp.status_code == 200
        got = client.get(f"/api/spools/{spool['id']}").json()
        assert got["tag_uid"] is None


# ---------------------------------------------------------------------------
# Cloud-authoritative AMS slot binding (filament_sync) — the automatic path
# ---------------------------------------------------------------------------

class TestCloudSlotKey:
    @pytest.mark.parametrize("rec,expected", [
        ({"inPrinter": True, "amsId": 1, "slotId": 1}, "ams2_tray2"),      # PETG live sample
        ({"inPrinter": True, "amsId": 128, "slotId": 0}, "ams129_tray1"),  # ABS live sample (AMS-HT)
        ({"inPrinter": True, "amsId": 0, "slotId": 0}, "ams1_tray1"),
        ({"inPrinter": True, "amsId": "2", "slotId": "3"}, "ams3_tray4"),  # numeric strings
        ({"inPrinter": False, "amsId": 1, "slotId": 1}, None),             # not loaded
        ({"amsId": 1, "slotId": 1}, None),                                 # no inPrinter flag
        ({"inPrinter": True, "amsId": 254, "slotId": 0}, None),            # external-spool sentinel
        ({"inPrinter": True, "amsId": 1, "slotId": 255}, None),            # sentinel slot
        ({"inPrinter": True, "amsId": None, "slotId": 1}, None),           # unparseable
        ({"inPrinter": True}, None),                                       # missing ids
    ])
    def test_cloud_ams_slot_key(self, rec, expected):
        from app.routers.filament_sync import _cloud_ams_slot_key
        assert _cloud_ams_slot_key(rec) == expected


class TestCloudSlotBind:
    def test_binds_by_devid_match(self, session):
        from app.routers.filament_sync import _bind_ams_slots_from_cloud
        _mk_printer(session)  # "My Printer", serial SERIAL
        spool = _mk_spool(session, material="PLA")
        spool.bambu_spool_id = "c1"
        session.commit()
        cloud_by_id = {"c1": {"id": "c1", "inPrinter": True, "amsId": 1, "slotId": 1, "devId": SERIAL}}

        _bind_ams_slots_from_cloud(session, cloud_by_id)
        session.commit()
        session.refresh(spool)
        assert spool.ams_slot == "My Printer:ams2_tray2"

    def test_binds_correct_printer_when_multiple(self, session):
        """devId scopes each bind to the owning printer — precise, no guard needed."""
        from app.routers.filament_sync import _bind_ams_slots_from_cloud
        _mk_printer(session, name="Garage", serial="AAA")
        _mk_printer(session, name="Office", serial="BBB")
        spool = _mk_spool(session, material="PLA")
        spool.bambu_spool_id = "c1"
        session.commit()
        # ABS-shaped record (amsId 128 → ams129) loaded on the Office printer
        cloud_by_id = {"c1": {"id": "c1", "inPrinter": True, "amsId": 128, "slotId": 0, "devId": "BBB"}}

        _bind_ams_slots_from_cloud(session, cloud_by_id)
        session.commit()
        session.refresh(spool)
        assert spool.ams_slot == "Office:ams129_tray1"

    def test_skips_untracked_device(self, session):
        """A spool loaded on a printer we don't track is left alone (never guess)."""
        from app.routers.filament_sync import _bind_ams_slots_from_cloud
        _mk_printer(session, serial="AAA")
        spool = _mk_spool(session, material="PLA")
        spool.bambu_spool_id = "c1"
        session.commit()
        cloud_by_id = {"c1": {"id": "c1", "inPrinter": True, "amsId": 1, "slotId": 1, "devId": "UNKNOWN"}}

        _bind_ams_slots_from_cloud(session, cloud_by_id)
        session.commit()
        session.refresh(spool)
        assert spool.ams_slot is None

    def test_not_in_printer_leaves_slot_unset(self, session):
        from app.routers.filament_sync import _bind_ams_slots_from_cloud
        _mk_printer(session)
        spool = _mk_spool(session, material="PLA")
        spool.bambu_spool_id = "c1"
        session.commit()
        cloud_by_id = {"c1": {"id": "c1", "inPrinter": False, "amsId": 1, "slotId": 1, "devId": SERIAL}}

        _bind_ams_slots_from_cloud(session, cloud_by_id)
        session.commit()
        session.refresh(spool)
        assert spool.ams_slot is None

    def test_stale_duplicate_slot_newer_wins(self, session):
        """Bambu leaves inPrinter=true on a swapped-out record → two records claim
        the same slot. Bind the newer (max updatedAt); skip the stale older one.
        (Real collision from prod: ams4_tray3, white current vs blue stale.)"""
        from app.routers.filament_sync import _bind_ams_slots_from_cloud
        _mk_printer(session, name="Garage", serial="DEV1")
        newer = _mk_spool(session, material="PLA", color_hex="#FFFFFF")
        newer.bambu_spool_id = "1827160"
        older = _mk_spool(session, material="PLA", color_hex="#0A2989")
        older.bambu_spool_id = "593855"
        session.commit()
        cloud_by_id = {
            "1827160": {"id": "1827160", "inPrinter": True, "amsId": 3, "slotId": 2,
                        "devId": "DEV1", "updatedAt": 1782177080},  # newer = current
            "593855":  {"id": "593855", "inPrinter": True, "amsId": 3, "slotId": 2,
                        "devId": "DEV1", "updatedAt": 1782162701},  # older = stale
        }

        _bind_ams_slots_from_cloud(session, cloud_by_id)
        session.commit()
        session.refresh(newer); session.refresh(older)
        assert newer.ams_slot == "Garage:ams4_tray3"
        assert older.ams_slot is None


class TestTagUidManualClear:
    """SpoolUpdate now carries tag_uid so a stale/wrong stamp can be cleared or
    corrected via PATCH (previously the field was silently dropped)."""
    def test_patch_sets_and_clears_tag_uid(self, client):
        spool = client.post("/api/spools", json=make_spool_payload()).json()

        r = client.patch(f"/api/spools/{spool['id']}", json={"tag_uid": REAL_TAG})
        assert r.status_code == 200
        assert r.json()["tag_uid"] == REAL_TAG

        r = client.patch(f"/api/spools/{spool['id']}", json={"tag_uid": None})
        assert r.status_code == 200
        assert r.json()["tag_uid"] is None
