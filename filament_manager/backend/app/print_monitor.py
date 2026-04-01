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
        printers = db.query(PrinterConfig).filter(PrinterConfig.is_active == True).all()  # noqa: E712
        for printer in printers:
            if getattr(printer, "bambu_source", "ha") == "cloud":
                continue  # driven by MQTT, not HA polling
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

    entities = ha_client.get_printer_entity_ids(printer.device_slug, printer.sensor_overrides)
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
    ams_config = ha_client.get_ams_config(printer.device_slug, printer.ams_unit_count,
                                           ams_device_slug=printer.ams_device_slug,
                                           ams_overrides=printer.ams_overrides)
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

    if getattr(printer, "bambu_source", "ha") == "cloud" and getattr(printer, "bambu_serial", None):
        from . import bambu_cloud_client
        ams_now = bambu_cloud_client.get_ams_snapshot_for_serial(printer.bambu_serial)
        if ams_now and job.ams_snapshot_start:
            await _record_ams_usage(job, job.ams_snapshot_start, ams_now, db)
    else:
        ams_config = ha_client.get_ams_config(printer.device_slug, printer.ams_unit_count,
                                               ams_device_slug=printer.ams_device_slug,
                                               ams_overrides=printer.ams_overrides)
        if ams_config and job.ams_snapshot_start:
            ams_now = await ha_client.get_ams_snapshot(ams_config)
            await _record_ams_usage(job, job.ams_snapshot_start, ams_now, db)

    db.commit()
    _state[printer.id] = {"stage": "idle", "job_id": None}
    log.info("Closed PrintJob #%d", job_id)


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
        spool = db.query(Spool).filter(Spool.ams_slot == slot_key, Spool.current_weight_g > 0).first()
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
        await _on_print_end(printer, db, job_id, success=success, extra_fields=extra)
    finally:
        db.close()
