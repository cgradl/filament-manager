"""
Background job that polls HA every 30 s to auto-detect Bambu Lab prints.

State machine per printer:
  idle / unknown  ──► printing   → open a new PrintJob
  printing        ──► finish     → close job as success
  printing        ──► failed     → close job as failure
  printing        ──► pause      → track only
  pause/printing  ──► idle       → close job as success
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import PrinterConfig, PrintJob, PrintUsage, Spool
from . import ha_client

log = logging.getLogger(__name__)

_state: dict[int, dict] = {}

_PRINTING_STAGES = {"printing", "auto_bed_leveling", "heatbed_preheating",
                    "scanning_bed_surface", "first_layer_scan", "cooling_filament"}
_FAILED_STAGES   = {"failed", "filament_runout", "front_cover_falling",
                    "nozzle_temp_fail", "bed_temp_fail"}


async def poll_printers() -> None:
    db: Session = SessionLocal()
    try:
        printers = db.query(PrinterConfig).filter(
            PrinterConfig.is_active == True,  # noqa: E712
            PrinterConfig.bambu_source == "ha",
        ).all()
        if not printers:
            return  # no HA-source printers configured — nothing to poll
        for printer in printers:
            await _check_printer(printer, db)
    except Exception as exc:
        log.error("print_monitor poll error: %s", exc)
    finally:
        db.close()


async def _check_printer(printer: PrinterConfig, db: Session) -> None:
    # On first poll after (re)start, recover open job from DB instead of
    # creating a duplicate when the printer is already mid-print.
    if printer.id not in _state:
        open_job = (
            db.query(PrintJob)
            .filter(
                PrintJob.printer_name == printer.name,
                PrintJob.source == "auto",
                PrintJob.finished_at == None,  # noqa: E711
            )
            .order_by(PrintJob.started_at.desc())
            .first()
        )
        if open_job:
            log.info("Recovered open PrintJob #%d for %s after restart", open_job.id, printer.name)
            _state[printer.id] = {"stage": "printing", "job_id": open_job.id}
        else:
            _state[printer.id] = {"stage": "idle", "job_id": None}

    entities = await ha_client.resolve_printer_entity_ids(
        printer.device_slug, printer.sensor_overrides, getattr(printer, "bambu_serial", None)
    )
    stage_raw = await ha_client.get_entity_value(entities["print_stage"])
    if stage_raw is None:
        return

    stage = stage_raw.lower().strip()
    prev = _state.get(printer.id, {"stage": "idle", "job_id": None})

    is_printing  = stage in _PRINTING_STAGES
    was_printing = prev["stage"] in _PRINTING_STAGES

    if is_printing and not was_printing:
        await _on_print_start(printer, entities, db)
    elif not is_printing and was_printing:
        await _on_print_end(printer, db, prev["job_id"], success=stage not in _FAILED_STAGES)

    # Read job_id back from current state — _on_print_start may have just written it
    _state[printer.id] = {"stage": stage, "job_id": _state.get(printer.id, {}).get("job_id")}


async def _on_print_start(printer: PrinterConfig, entities: dict, db: Session) -> None:
    log.info("Print started on %s", printer.name)
    filename = await ha_client.get_entity_value(entities["current_file"]) or ""
    ams_config = ha_client.get_ams_config(
        printer.device_slug, printer.ams_unit_count,
        trays_per_unit=ha_client.get_cached_ams_tray_counts(printer.device_slug),
        ams_device_slug=printer.ams_device_slug,
        ams_overrides=printer.ams_overrides,
    )
    ams_snapshot = await ha_client.get_ams_snapshot(ams_config)

    # Use the gcode filename as the display name; strip common extensions
    display_name = filename
    for ext in (".gcode", ".3mf", ".bgcode"):
        if display_name.lower().endswith(ext):
            display_name = display_name[: -len(ext)]
            break
    if not display_name:
        display_name = f"Print {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    job = PrintJob(
        name=display_name,
        model_name=filename or None,
        started_at=datetime.now(timezone.utc),
        source="auto",
        printer_name=printer.name,
        success=True,
        ams_snapshot_start=ams_snapshot,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _state[printer.id] = {"stage": "printing", "job_id": job.id}
    log.info("Created PrintJob #%d for %s", job.id, printer.name)


async def _on_print_end(
    printer: PrinterConfig, db: Session, job_id: int | None, success: bool,
    extra_fields: dict | None = None,
) -> None:
    log.info("Print ended on %s (success=%s)", printer.name, success)
    if job_id is None:
        _state[printer.id] = {"stage": "idle", "job_id": None}
        return

    job = db.get(PrintJob, job_id)
    if not job:
        _state[printer.id] = {"stage": "idle", "job_id": None}
        return

    now = datetime.now(timezone.utc)
    job.finished_at = now
    job.success = success
    if job.started_at:
        started = job.started_at.replace(tzinfo=timezone.utc) if job.started_at.tzinfo is None else job.started_at
        job.duration_seconds = int((now - started).total_seconds())

    if extra_fields:
        for k, v in extra_fields.items():
            if hasattr(job, k) and v is not None:
                setattr(job, k, v)

    is_cloud = getattr(printer, "bambu_source", "ha") == "cloud" and getattr(printer, "bambu_serial", None)

    if not is_cloud:
        # HA-source printers: delta-based recording as before
        ams_config = ha_client.get_ams_config(
            printer.device_slug, printer.ams_unit_count,
            trays_per_unit=ha_client.get_cached_ams_tray_counts(printer.device_slug),
            ams_device_slug=printer.ams_device_slug,
            ams_overrides=printer.ams_overrides,
        )
        if ams_config and job.ams_snapshot_start:
            ams_now = await ha_client.get_ams_snapshot(ams_config)
            await _record_ams_usage(job, job.ams_snapshot_start, ams_now, db)

    # Commit job close (+ HA delta usages if applicable) FIRST.
    # Cloud prints: no automatic usage recording — user must confirm via LogUsageModal.
    db.commit()
    _state[printer.id] = {"stage": "idle", "job_id": None}
    log.info("Closed PrintJob #%d", job_id)

    # Best-effort post-print data fetch (separate commit — never blocks job close)
    try:
        if is_cloud:
            from . import bambu_cloud_client
            task_data = await bambu_cloud_client.get_task_data_for_serial(printer.bambu_serial)
            weight = task_data.get("weight")
            ams_detail = task_data.get("amsDetailMapping") or []

            if weight is not None:
                job.print_weight_g = weight
                log.info("Cloud: recorded print_weight_g=%.1f for job #%d", weight, job.id)

            # Build suggested_usages from amsDetailMapping (per-tray cloud breakdown)
            if ams_detail:
                suggestions = []
                for entry in ams_detail:
                    idx = entry.get("ams")
                    tray_weight = entry.get("weight")
                    if idx is None or tray_weight is None:
                        continue
                    slot_key = bambu_cloud_client._ams_index_to_slot_key(
                        int(idx), bambu_cloud_client.get_ams_unit_tray_counts(printer.bambu_serial),
                    )
                    if slot_key is None:
                        continue  # external spool — skip
                    color_raw = entry.get("sourceColor") or entry.get("targetColor") or ""
                    color_hex = f"#{color_raw[:6]}" if len(color_raw) >= 6 else None
                    suggestions.append({
                        "ams_slot": slot_key,
                        "grams": round(float(tray_weight), 1),
                        "filament_type": entry.get("filamentType") or entry.get("targetFilamentType") or "",
                        "color": color_hex,
                    })
                if suggestions:
                    job.suggested_usages = suggestions
                    log.info("Cloud: stored %d suggested_usages for job #%d", len(suggestions), job.id)
            elif weight is not None:
                # No per-tray detail — use total weight distributed across tracked trays
                tracked = bambu_cloud_client.get_print_trays(printer.bambu_serial)
                if len(tracked) == 1:
                    idx = next(iter(tracked))
                    slot_key = bambu_cloud_client._ams_index_to_slot_key(
                        idx, bambu_cloud_client.get_ams_unit_tray_counts(printer.bambu_serial),
                    )
                    if slot_key:
                        job.suggested_usages = [{
                            "ams_slot": slot_key,
                            "grams": round(float(weight), 1),
                            "filament_type": "",
                            "color": None,
                        }]
                        log.info("Cloud: stored single-tray suggestion %.1fg on %s for job #%d",
                                 weight, slot_key, job.id)

            if job.print_weight_g is not None or job.suggested_usages is not None:
                db.commit()
        else:
            entities = await ha_client.resolve_printer_entity_ids(
                printer.device_slug, printer.sensor_overrides, getattr(printer, "bambu_serial", None)
            )
            state_data = await ha_client.get_entity_state(entities["print_weight"])
            if state_data is not None:
                weight_str = state_data.get("state")
                if weight_str is not None:
                    try:
                        job.print_weight_g = float(weight_str)
                        log.info("HA: recorded print_weight_g=%.1f for job #%d", job.print_weight_g, job.id)
                    except (TypeError, ValueError):
                        pass

                # Build suggested_usages from per-tray weight attributes
                # ha-bambulab exposes: {"AMS 1 Tray 2": 17.32, "AMS 1 Tray 3": 2.66, ...}
                attrs = state_data.get("attributes", {})
                suggestions = []
                import re as _re
                for attr_key, attr_val in attrs.items():
                    m = _re.match(r"AMS\s+(\d+)\s+Tray\s+(\d+)", str(attr_key))
                    if m and attr_val:
                        try:
                            grams = float(attr_val)
                        except (TypeError, ValueError):
                            continue
                        if grams <= 0:
                            continue
                        slot_key = f"ams{m.group(1)}_tray{m.group(2)}"
                        suggestions.append({
                            "ams_slot": slot_key,
                            "grams": round(grams, 1),
                            "filament_type": "",
                            "color": None,
                        })
                if suggestions:
                    job.suggested_usages = suggestions
                    log.info("HA: stored %d suggested_usages for job #%d", len(suggestions), job.id)

                if job.print_weight_g is not None or job.suggested_usages is not None:
                    db.commit()
    except Exception as exc:
        log.warning("post-print data fetch failed for job #%d: %s", job_id, exc)


async def _record_ams_usage(
    job: PrintJob, snapshot_start: dict, snapshot_end: dict, db: Session
) -> None:
    for slot_key, pct_start in snapshot_start.items():
        pct_end = snapshot_end.get(slot_key)
        if pct_end is None:
            continue
        delta_pct = pct_start - pct_end
        if delta_pct <= 0.5:
            continue
        # Look up by prefixed key first ("PrinterName:ams1_tray2"), fall back to bare key
        # for spools assigned before the prefix was introduced.
        full_slot = f"{job.printer_name}:{slot_key}" if job.printer_name else slot_key
        spool = (
            db.query(Spool).filter(Spool.ams_slot == full_slot, Spool.current_weight_g > 0).first()
            or db.query(Spool).filter(Spool.ams_slot == slot_key, Spool.current_weight_g > 0).first()
        )
        if not spool:
            continue
        grams_used = round(spool.initial_weight_g * delta_pct / 100, 1)
        spool.current_weight_g = max(0, spool.current_weight_g - grams_used)
        db.add(PrintUsage(print_job_id=job.id, spool_id=spool.id,
                          grams_used=grams_used, ams_slot=slot_key))
        log.info("Recorded %.1fg from spool #%d (%s) for job #%d",
                 grams_used, spool.id, slot_key, job.id)


# ── Bambu Cloud MQTT bridge ───────────────────────────────────────────────────

async def on_cloud_print_start(printer_id: int, subtask_name: str, serial: str) -> None:
    """
    Called by bambu_cloud_client when MQTT gcode_state transitions to RUNNING.
    Only acts for printers configured with bambu_source=cloud — HA-source printers
    are tracked by the HA poller; MQTT is connected for Experiments tab only.
    """
    db: Session = SessionLocal()
    try:
        printer = db.get(PrinterConfig, printer_id)
        if not printer:
            return

        # Only drive print tracking via MQTT for cloud-source printers
        if getattr(printer, "bambu_source", "ha") != "cloud":
            return

        # On first MQTT event after (re)start, recover open job from DB instead of
        # creating a duplicate when the printer is already mid-print (the pushall
        # response after MQTT reconnect always delivers the current gcode_state).
        if printer_id not in _state:
            open_job = (
                db.query(PrintJob)
                .filter(
                    PrintJob.printer_name == printer.name,
                    PrintJob.source == "auto",
                    PrintJob.finished_at == None,  # noqa: E711
                )
                .order_by(PrintJob.started_at.desc())
                .first()
            )
            if open_job:
                log.info("Cloud: Recovered open PrintJob #%d for %s after restart", open_job.id, printer.name)
                _state[printer_id] = {"stage": "printing", "job_id": open_job.id}
                return  # already have an open job — do not create a duplicate
            # No open job found — fall through to create a new one

        # Guard: don't open a duplicate job if already tracking one
        prev = _state.get(printer_id, {})
        if prev.get("stage") in _PRINTING_STAGES:
            return

        display_name = subtask_name or ""
        for ext in (".gcode", ".3mf", ".bgcode"):
            if display_name.lower().endswith(ext):
                display_name = display_name[: -len(ext)]
                break
        if not display_name:
            display_name = f"Print {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        from . import bambu_cloud_client
        bambu_cloud_client.reset_print_trays(serial)
        ams_snapshot = bambu_cloud_client.get_ams_snapshot_for_serial(serial)
        status = bambu_cloud_client.get_printer_cloud_status(serial)

        nozzle_d = status.get("nozzle_diameter")
        job = PrintJob(
            name=display_name,
            model_name=subtask_name or None,
            started_at=datetime.now(timezone.utc),
            source="auto",
            printer_name=printer.name,
            success=True,
            ams_snapshot_start=ams_snapshot,
            task_id=str(status["task_id"]) if status.get("task_id") is not None else None,
            project_id=str(status["project_id"]) if status.get("project_id") is not None else None,
            total_layer_num=status.get("total_layer_num"),
            nozzle_diameter=str(nozzle_d) if nozzle_d is not None else None,
            nozzle_type=status.get("nozzle_type"),
            print_type=status.get("print_type"),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        _state[printer_id] = {"stage": "printing", "job_id": job.id}
        log.info("Cloud: Created PrintJob #%d for %s", job.id, printer.name)
    finally:
        db.close()


async def on_cloud_print_end(printer_id: int, success: bool, gcode_state: str) -> None:
    """
    Called by bambu_cloud_client when MQTT gcode_state transitions to FINISH,
    FAILED, or IDLE (with an open job). Only acts for cloud-source printers.
    """
    # Only close an open job — ignore IDLE events when nothing was printing
    prev = _state.get(printer_id, {})
    if prev.get("stage") not in _PRINTING_STAGES:
        return

    db: Session = SessionLocal()
    try:
        printer = db.get(PrinterConfig, printer_id)
        if not printer:
            return

        # Only drive print tracking via MQTT for cloud-source printers
        if getattr(printer, "bambu_source", "ha") != "cloud":
            return

        from . import bambu_cloud_client
        serial = getattr(printer, "bambu_serial", None)
        status = bambu_cloud_client.get_printer_cloud_status(serial) if serial else {}
        extra = {
            "layer_num":       status.get("layer_num"),
            "total_layer_num": status.get("total_layer_num"),
            "error_code":      str(status["mc_print_error_code"]) if not success and status.get("mc_print_error_code") is not None else None,
        }

        job_id = prev.get("job_id")
        try:
            await _on_print_end(printer, db, job_id, success=success, extra_fields=extra)
        except Exception as exc:
            log.error("Cloud: _on_print_end failed for printer %s job #%s: %s", printer.name, job_id, exc)
            # Always reset state — a stuck "printing" state would block all future end events
            _state[printer_id] = {"stage": "idle", "job_id": None}
    finally:
        db.close()
