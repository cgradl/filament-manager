"""
Compute and push three HA sensor entities on a 30-second polling loop.
Also exposes `trigger()` so other modules can request an immediate push.

Sensors:
  sensor.filament_manager_pending_usages   – auto prints awaiting usage confirmation
  sensor.filament_manager_low_stock_spools – spools below the configurable threshold
  sensor.filament_manager_ams_unmatched    – AMS trays with filament but no spool assigned

Every push always writes all three sensors so they remain present in HA
after an HA restart (the States API creates entities on first write and they
survive until the next HA restart — the 30-second loop recreates them quickly).
"""
import asyncio
import logging

from .database import SessionLocal
from .models import PrintJob, Spool, UserPreferences

log = logging.getLogger(__name__)

_POLL_INTERVAL = 30    # seconds between periodic pushes
_ENTITY_PENDING   = "sensor.filament_manager_pending_usages"
_ENTITY_LOW_STOCK = "sensor.filament_manager_low_stock_spools"
_ENTITY_UNMATCHED = "sensor.filament_manager_ams_unmatched"

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
    """Compute and push all three sensor values to HA."""
    from .ha_client import push_ha_state

    try:
        with SessionLocal() as db:
            values = _compute(db)
    except Exception as exc:
        log.warning("ha_publisher: DB query failed: %s", exc)
        return

    for entity_id, (state, attrs) in values.items():
        await push_ha_state(entity_id, state, attrs)
        log.debug("ha_publisher: pushed %s = %d", entity_id, state)


async def run_periodic() -> None:
    """Background task: push on startup, then every 30 seconds.
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


async def run_ha_event_listener() -> None:
    """Subscribe to HA's homeassistant_started WebSocket event.

    Pushes all three sensors immediately when HA restarts so they are
    recreated without any polling delay.  Reconnects automatically if
    the WebSocket drops.
    """
    import json
    import os

    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        log.debug("ha_publisher: no SUPERVISOR_TOKEN — HA restart listener disabled")
        return

    try:
        import websockets  # type: ignore[import]
    except ImportError:
        log.warning("ha_publisher: websockets package not installed — HA restart listener disabled")
        return

    uri = "ws://supervisor/core/websocket"

    while True:
        try:
            async with websockets.connect(uri) as ws:
                # HA WebSocket auth handshake
                first = json.loads(await ws.recv())
                if first.get("type") == "auth_required":
                    await ws.send(json.dumps({"type": "auth", "access_token": token}))
                    result = json.loads(await ws.recv())
                    if result.get("type") != "auth_ok":
                        log.warning("ha_publisher: WS auth failed (%s) — retry in 60s", result.get("type"))
                        await asyncio.sleep(60)
                        continue

                await ws.send(json.dumps({
                    "id": 1,
                    "type": "subscribe_events",
                    "event_type": "homeassistant_started",
                }))
                await ws.recv()  # subscription confirmation
                log.info("ha_publisher: subscribed to homeassistant_started events")

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "event":
                        log.info("ha_publisher: homeassistant_started received — pushing sensors immediately")
                        await push_now()

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.debug("ha_publisher: WS listener error (%s) — reconnecting in 60s", exc)
            await asyncio.sleep(60)
