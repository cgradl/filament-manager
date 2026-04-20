"""
Compute and push three HA sensor entities on a 5-minute polling loop.
Also exposes `trigger()` so other modules can request an immediate push.

Sensors:
  sensor.filament_manager_pending_usages   – auto prints awaiting usage confirmation
  sensor.filament_manager_low_stock_spools – spools below the configurable threshold
  sensor.filament_manager_ams_unmatched    – AMS trays with filament but no spool assigned
"""
import asyncio
import logging

from .database import SessionLocal
from .models import PrintJob, Spool, UserPreferences

log = logging.getLogger(__name__)

_POLL_INTERVAL = 300   # seconds between periodic pushes
_ENTITY_PENDING   = "sensor.filament_manager_pending_usages"
_ENTITY_LOW_STOCK = "sensor.filament_manager_low_stock_spools"
_ENTITY_UNMATCHED = "sensor.filament_manager_ams_unmatched"

# Last-pushed values; None means "never pushed yet" (always push on first run)
_last: dict[str, int | None] = {
    _ENTITY_PENDING:   None,
    _ENTITY_LOW_STOCK: None,
    _ENTITY_UNMATCHED: None,
}

_trigger_event: asyncio.Event | None = None


def _get_event() -> asyncio.Event:
    global _trigger_event
    if _trigger_event is None:
        _trigger_event = asyncio.Event()
    return _trigger_event


def trigger() -> None:
    """Request an immediate sensor push (fire-and-forget, safe to call from sync code)."""
    try:
        _get_event().set()
    except RuntimeError:
        pass  # no running loop (e.g. tests)


def _compute(db) -> dict[str, tuple[int, dict]]:
    """Return {entity_id: (state_value, attributes)} for all three sensors."""
    from sqlalchemy.orm import joinedload

    prefs = db.get(UserPreferences, 1)
    threshold = (prefs.low_stock_threshold_pct if prefs else None) or 20

    # ── pending usages ────────────────────────────────────────────────────────
    pending_jobs = (
        db.query(PrintJob)
        .filter(
            PrintJob.source == "auto",
            PrintJob.finished_at.isnot(None),
            PrintJob.suggested_usages.isnot(None),
        )
        .options(joinedload(PrintJob.usages))
        .all()
    )
    # A job is "pending" if it has suggested_usages but no confirmed grams yet
    pending = [j for j in pending_jobs if j.total_grams == 0]
    pending_names = [j.name for j in pending]

    # ── low stock ─────────────────────────────────────────────────────────────
    spools = db.query(Spool).all()
    low = [
        s for s in spools
        if s.current_weight_g > 0 and 0 < s.remaining_pct < threshold
    ]
    low_names = [f"{s.brand} {s.material} {s.color_name}".strip() for s in low]

    # ── AMS unmatched ─────────────────────────────────────────────────────────
    from . import bambu_cloud_client
    from .models import PrinterConfig
    unmatched_trays: list[str] = []
    printers = db.query(PrinterConfig).filter(PrinterConfig.is_active == True).all()  # noqa: E712
    for printer in printers:
        if not printer.bambu_serial:
            continue
        ams = bambu_cloud_client.get_ams_detail_for_serial(printer.bambu_serial)
        if not ams:
            continue
        for slot_key, tray_data in ams.items():
            material = tray_data.get("material") or ""
            if not material:
                continue   # empty tray — not an error
            # Check if any spool is assigned to this tray slot
            full_slot = f"{printer.name}:{slot_key}"
            assigned = (
                db.query(Spool)
                .filter(
                    (Spool.ams_slot == full_slot) | (Spool.ams_slot == slot_key)
                )
                .first()
            )
            if assigned is None:
                unmatched_trays.append(f"{printer.name}:{slot_key} ({material})")

    return {
        _ENTITY_PENDING: (
            len(pending),
            {
                "friendly_name": "Filament Manager: Pending Usages",
                "icon": "mdi:scale",
                "unit_of_measurement": "jobs",
                "print_jobs": pending_names,
            },
        ),
        _ENTITY_LOW_STOCK: (
            len(low),
            {
                "friendly_name": "Filament Manager: Low Stock Spools",
                "icon": "mdi:spool",
                "unit_of_measurement": "spools",
                "threshold_pct": threshold,
                "spools": low_names,
            },
        ),
        _ENTITY_UNMATCHED: (
            len(unmatched_trays),
            {
                "friendly_name": "Filament Manager: Unmatched AMS Trays",
                "icon": "mdi:tray-alert",
                "unit_of_measurement": "trays",
                "trays": unmatched_trays,
            },
        ),
    }


async def push_now() -> None:
    """Compute sensor values and push any that have changed since last push."""
    from .ha_client import push_ha_state

    try:
        with SessionLocal() as db:
            values = _compute(db)
    except Exception as exc:
        log.warning("ha_publisher: DB query failed: %s", exc)
        return

    for entity_id, (state, attrs) in values.items():
        if _last[entity_id] == state:
            continue  # unchanged — skip to avoid noisy HA history
        ok = await push_ha_state(entity_id, state, attrs)
        if ok:
            _last[entity_id] = state
            log.debug("ha_publisher: pushed %s = %d", entity_id, state)


async def run_periodic() -> None:
    """Background task: push on startup, then every _POLL_INTERVAL seconds.
    Also wakes up early when trigger() is called."""
    evt = _get_event()
    # Initial push after a short delay (give DB time to finish seeding)
    await asyncio.sleep(10)
    while True:
        await push_now()
        evt.clear()
        try:
            await asyncio.wait_for(evt.wait(), timeout=_POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass  # normal periodic wake-up
        except asyncio.CancelledError:
            break
