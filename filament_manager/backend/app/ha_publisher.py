"""
Compute and push three HA sensor entities on a 30-second polling loop.
Also exposes `trigger()` so other modules can request an immediate push.

Sensors:
  sensor.filament_manager_pending_usages   – auto prints awaiting usage confirmation
  sensor.filament_manager_low_stock_spools – spools below the configurable threshold
  sensor.filament_manager_ams_unmatched    – AMS trays with filament but no matching spool (by material + color)

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
_ENTITY_PENDING    = "sensor.filament_manager_pending_usages"
_ENTITY_LOW_STOCK  = "sensor.filament_manager_low_stock_spools"
_ENTITY_UNMATCHED  = "sensor.filament_manager_ams_unmatched"
_ENTITY_LAST_PRINT      = "sensor.filament_manager_last_print"
_ENTITY_TOTAL_SPOOLS    = "sensor.filament_manager_total_spools"
_ENTITY_CONSUMED_SPOOLS = "sensor.filament_manager_consumed_spools"

_trigger_event: asyncio.Event | None = None
_event_loop: asyncio.AbstractEventLoop | None = None


def _get_event() -> asyncio.Event:
    global _trigger_event
    if _trigger_event is None:
        _trigger_event = asyncio.Event()
    return _trigger_event


def trigger() -> None:
    """Request an immediate sensor push (fire-and-forget, safe to call from sync code).

    sync route handlers run in a thread pool, so Event.set() must go through
    call_soon_threadsafe to actually wake the async event loop.
    """
    if _event_loop is not None and _event_loop.is_running():
        _event_loop.call_soon_threadsafe(_get_event().set)
    else:
        try:
            _get_event().set()
        except RuntimeError:
            pass


def _compute(db) -> dict[str, tuple[int, dict]]:
    """Return {entity_id: (state_value, attributes)} for all three sensors."""
    from sqlalchemy.orm import joinedload

    prefs = db.get(UserPreferences, 1)
    threshold = (prefs.low_stock_threshold_pct if prefs else None) or 20

    # ── pending usages ────────────────────────────────────────────────────────
    # Guard against both SQL NULL and JSON text 'null' (stored when none_as_null=False was the default).
    pending_jobs = (
        db.query(PrintJob)
        .filter(
            PrintJob.source == "auto",
            PrintJob.finished_at.isnot(None),
            PrintJob.suggested_usages.isnot(None),
            PrintJob.suggested_usages != "null",
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
    low_names = [f"{s.brand} {s.material} {s.color_name} ({round(s.current_weight_g)}g)".strip() for s in low]

    # ── spool inventory + consumed ───────────────────────────────────────────
    def _count_by_material(spool_list: list) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in spool_list:
            mat = s.material or "Unknown"
            counts[mat] = counts.get(mat, 0) + 1
        return dict(sorted(counts.items()))

    active_spools = [s for s in spools if not s.archived]
    empty_spools  = [s for s in spools if s.current_weight_g == 0]

    # ── AMS unmatched ─────────────────────────────────────────────────────────
    from . import bambu_cloud_client
    from .models import PrinterConfig

    def _normalize_hex(h: str) -> str:
        return h.lstrip("#")[:6].upper()

    def _tray_has_match(material: str, color_hex: str, all_spools: list) -> bool:
        mat = material.lower()
        col = _normalize_hex(color_hex)
        for s in all_spools:
            if s.current_weight_g <= 0:
                continue
            spool_mat = f"{s.material} {s.subtype}".lower() if s.subtype else s.material.lower()
            mat_match = s.material.lower() == mat or spool_mat == mat
            col_match = _normalize_hex(s.color_hex or "") == col
            if mat_match and col_match:
                return True
        return False

    unmatched_trays: list[str] = []
    # order_by(id) keeps slug-collision suffixes deterministic across pushes
    printers = (
        db.query(PrinterConfig)
        .filter(PrinterConfig.is_active == True)  # noqa: E712
        .order_by(PrinterConfig.id)
        .all()
    )
    for printer in printers:
        if not printer.bambu_serial:
            continue
        ams = bambu_cloud_client.get_ams_detail_for_serial(printer.bambu_serial)
        if not ams:
            continue
        for slot_key, tray_data in ams.items():
            material = tray_data.get("material") or ""
            color_hex = tray_data.get("color") or ""
            remain = tray_data.get("remain")
            if not material or not color_hex:
                continue   # empty tray — not an error
            if remain is None or remain < 0:
                continue   # not tracked by AMS
            if remain == 0:
                continue   # empty — nothing to match
            if not _tray_has_match(material, color_hex, spools):
                unmatched_trays.append(f"{printer.name}:{slot_key} ({material})")

    # ── printer status sensors (one per active printer with a serial) ────────
    import re

    def _entity_name(printer_name: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', printer_name.lower().strip()).strip('_')

    _STATE_MAP = {
        "RUNNING": "running",
        "IDLE":    "idle",
        "PAUSE":   "paused",
        "FINISH":  "finished",
        "FAILED":  "failed",
    }

    printer_sensors: dict[str, tuple] = {}
    used_slugs: set[str] = set()
    for printer in printers:
        if not printer.bambu_serial:
            continue
        cache = bambu_cloud_client.get_printer_cloud_status(printer.bambu_serial)
        raw_state = (cache.get("gcode_state") or "").upper()
        state = _STATE_MAP.get(raw_state, "offline")
        # Two printer names can sanitize to the same slug ("P1 S" and "p1-s")
        # — suffix with the printer id so they don't overwrite each other.
        slug = _entity_name(printer.name)
        if slug in used_slugs:
            slug = f"{slug}_{printer.id}"
        used_slugs.add(slug)
        entity_id = f"sensor.filament_manager_printer_{slug}_status"
        printer_sensors[entity_id] = (
            state,
            {
                "friendly_name": f"Filament Manager: {printer.name}",
                "icon": "mdi:printer-3d-nozzle",
                "printer": printer.name,
                "mc_percent": cache.get("mc_percent"),
                "mc_remaining_time": cache.get("mc_remaining_time"),
                "subtask_name": cache.get("subtask_name"),
                "gcode_state": raw_state or None,
            },
        )

    # ── last completed print ──────────────────────────────────────────────────
    from .models import PrintUsage
    last_job = (
        db.query(PrintJob)
        .filter(PrintJob.finished_at.isnot(None))
        .options(joinedload(PrintJob.usages).joinedload(PrintUsage.spool))
        .order_by(PrintJob.finished_at.desc())
        .first()
    )
    if last_job:
        job_grams = round(sum(u.grams_used for u in last_job.usages), 2)
        job_materials = sorted({u.spool.material for u in last_job.usages if u.spool and u.spool.material})
        last_print_state = (last_job.name or "")[:200] or "–"
        last_print_attrs = {
            "friendly_name": "Filament Manager: Last Print",
            "icon": "mdi:printer-3d",
            "printer": last_job.printer_name or "",
            "started_at": last_job.started_at.isoformat() if last_job.started_at else None,
            "finished_at": last_job.finished_at.isoformat() if last_job.finished_at else None,
            "duration_seconds": last_job.duration_seconds,
            "success": last_job.success,
            "total_grams": job_grams,
            "total_cost": round(last_job.total_cost, 4),
            "energy_kwh": last_job.energy_kwh,
            "url": last_job.url,
            "materials": job_materials,
        }
    else:
        last_print_state = "–"
        last_print_attrs = {
            "friendly_name": "Filament Manager: Last Print",
            "icon": "mdi:printer-3d",
        }

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
                "icon": "mdi:printer-3d-nozzle-alert-outline",
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
        _ENTITY_LAST_PRINT: (last_print_state, last_print_attrs),
        _ENTITY_TOTAL_SPOOLS: (
            len(active_spools),
            {
                "friendly_name": "Filament Manager: Total Spools",
                "icon": "mdi:package-variant",
                "unit_of_measurement": "spools",
                "by_material": _count_by_material(active_spools),
            },
        ),
        _ENTITY_CONSUMED_SPOOLS: (
            len(empty_spools),
            {
                "friendly_name": "Filament Manager: Consumed Spools",
                "icon": "mdi:package-variant-remove",
                "unit_of_measurement": "spools",
                "by_material": _count_by_material(empty_spools),
            },
        ),
        **printer_sensors,
    }


# Printer entity ids from the previous push — used to retire sensors whose
# printer was renamed, deactivated, or deleted (they would otherwise linger in
# HA showing their last state until the next HA restart).
_last_printer_entities: set[str] = set()

_PRINTER_ENTITY_PREFIX = "sensor.filament_manager_printer_"


async def push_now() -> None:
    """Compute and push all sensor values to HA; retire vanished printer sensors."""
    global _last_printer_entities
    from .ha_client import push_ha_state, delete_ha_state

    try:
        with SessionLocal() as db:
            values = _compute(db)
    except Exception as exc:
        log.warning("ha_publisher: _compute failed: %s", exc, exc_info=True)
        return

    for entity_id, (state, attrs) in values.items():
        ok = await push_ha_state(entity_id, state, attrs)
        if ok:
            log.info("ha_publisher: pushed %s = %s", entity_id, state)
        else:
            log.warning("ha_publisher: push FAILED for %s (state=%s)", entity_id, state)

    current_printer_entities = {k for k in values if k.startswith(_PRINTER_ENTITY_PREFIX)}
    for stale in _last_printer_entities - current_printer_entities:
        if await delete_ha_state(stale):
            log.info("ha_publisher: removed stale printer sensor %s", stale)
    _last_printer_entities = current_printer_entities


async def run_periodic() -> None:
    """Background task: push on startup, then every 30 seconds.
    Also wakes up early when trigger() is called."""
    global _event_loop
    _event_loop = asyncio.get_event_loop()
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
