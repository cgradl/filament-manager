"""
Background job that tracks Bambu Cloud prints via MQTT callbacks.

State machine per printer (cloud source only):
  idle / unknown  ──► RUNNING  → open a new PrintJob
  RUNNING         ──► FINISH   → close job as success
  RUNNING         ──► FAILED   → close job as failure
  RUNNING         ──► IDLE     → close job as success
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import PrinterConfig, PrintJob, PrintUsage, Spool, SpoolAudit

log = logging.getLogger(__name__)

_state: dict[int, dict] = {}

_PRINTING_STAGES = {"printing", "auto_bed_leveling", "heatbed_preheating",
                    "scanning_bed_surface", "first_layer_scan", "cooling_filament",
                    "RUNNING"}
_FAILED_STAGES   = {"failed", "filament_runout", "front_cover_falling",
                    "nozzle_temp_fail", "bed_temp_fail", "FAILED"}


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

    auto_deduct = getattr(printer, "auto_deduct", False)

    # Commit job close first — captures duration and extra_fields immediately.
    db.commit()
    _state[printer.id] = {"stage": "idle", "job_id": None}
    log.info("Closed PrintJob #%d", job_id)

    from . import ha_publisher
    ha_publisher.trigger()

    # Best-effort post-print data fetch from Bambu Cloud API
    try:
        from . import bambu_cloud_client
        serial = getattr(printer, "bambu_serial", None)
        task_data = await bambu_cloud_client.get_task_data_for_serial(serial) if serial else {}
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
                    int(idx), bambu_cloud_client.get_ams_unit_tray_counts(serial),
                )
                if slot_key is None:
                    continue  # external spool — skip
                color_raw = entry.get("sourceColor") or entry.get("targetColor") or ""
                color_hex = f"#{color_raw[:6]}" if len(color_raw) >= 6 else None
                # Snapshot the spool currently in this slot so the UI shows the
                # correct spool even if the AMS is changed before the user confirms.
                full_slot = f"{job.printer_name}:{slot_key}" if job.printer_name else slot_key
                snap_spool = (
                    db.query(Spool).filter(Spool.ams_slot == full_slot, Spool.current_weight_g > 0).first()
                    or db.query(Spool).filter(Spool.ams_slot == slot_key, Spool.current_weight_g > 0).first()
                )
                suggestions.append({
                    "ams_slot": slot_key,
                    "grams": round(float(tray_weight), 1),
                    "filament_type": entry.get("filamentType") or entry.get("targetFilamentType") or "",
                    "color": color_hex,
                    "spool_id": snap_spool.id if snap_spool else None,
                })
            if suggestions:
                job.suggested_usages = suggestions
                log.info("Cloud: stored %d suggested_usages for job #%d", len(suggestions), job.id)
        elif weight is not None:
            # No per-tray detail — use total weight on the single tracked tray
            tracked = bambu_cloud_client.get_print_trays(serial)
            if len(tracked) == 1:
                idx = next(iter(tracked))
                slot_key = bambu_cloud_client._ams_index_to_slot_key(
                    idx, bambu_cloud_client.get_ams_unit_tray_counts(serial),
                )
                if slot_key:
                    full_slot = f"{job.printer_name}:{slot_key}" if job.printer_name else slot_key
                    snap_spool = (
                        db.query(Spool).filter(Spool.ams_slot == full_slot, Spool.current_weight_g > 0).first()
                        or db.query(Spool).filter(Spool.ams_slot == slot_key, Spool.current_weight_g > 0).first()
                    )
                    job.suggested_usages = [{
                        "ams_slot": slot_key,
                        "grams": round(float(weight), 1),
                        "filament_type": "",
                        "color": None,
                        "spool_id": snap_spool.id if snap_spool else None,
                    }]
                    log.info("Cloud: stored single-tray suggestion %.1fg on %s for job #%d",
                             weight, slot_key, job.id)

        suggestions_count = len(job.suggested_usages) if job.suggested_usages else 0
        if job.suggested_usages and auto_deduct:
            _apply_suggested_usages(job, db)  # clears job.suggested_usages
            log.info("Cloud auto-deduct: applied %d usages for job #%d",
                     suggestions_count, job.id)

        if job.print_weight_g is not None or suggestions_count > 0:
            db.commit()
    except Exception as exc:
        log.warning("post-print data fetch failed for job #%d: %s", job_id, exc)


def _apply_suggested_usages(job: PrintJob, db: Session) -> None:
    """Write PrintUsage rows and update spool weights from job.suggested_usages.

    Skips slots that already have a usage row (idempotent).
    Each suggestion entry may carry a spool_id (set by HA delta path) or
    ams_slot only (cloud path — looks up by slot assignment).
    """
    if not job.suggested_usages:
        return
    existing_slots = {u.ams_slot for u in job.usages}
    for s in job.suggested_usages:
        slot_key = s.get("ams_slot", "")
        if slot_key in existing_slots:
            continue
        grams = float(s.get("grams") or 0)
        if grams <= 0:
            continue
        # Prefer explicit spool_id then fall back to AMS slot lookup
        spool_id = s.get("spool_id")
        if spool_id:
            spool = db.get(Spool, spool_id)
        else:
            full_slot = f"{job.printer_name}:{slot_key}" if job.printer_name else slot_key
            spool = (
                db.query(Spool).filter(Spool.ams_slot == full_slot, Spool.current_weight_g > 0).first()
                or db.query(Spool).filter(Spool.ams_slot == slot_key, Spool.current_weight_g > 0).first()
            )
        if not spool:
            log.warning("auto-deduct: no spool found for slot %s — skipping", slot_key)
            continue
        weight_before = spool.current_weight_g
        spool.current_weight_g = max(0.0, spool.current_weight_g - grams)
        db.add(PrintUsage(
            print_job_id=job.id,
            spool_id=spool.id,
            grams_used=grams,
            ams_slot=slot_key,
        ))
        db.add(SpoolAudit(
            spool_id=spool.id,
            action="print_auto",
            delta_g=-grams,
            weight_before=weight_before,
            weight_after=spool.current_weight_g,
            print_job_id=job.id,
            print_name=job.name,
        ))
        log.info("auto-deduct: %.1fg from spool #%d (%s) for job #%d",
                 grams, spool.id, slot_key, job.id)
    job.suggested_usages = None  # mark as confirmed so the UI yellow icon goes away


# ── Bambu Cloud MQTT bridge ───────────────────────────────────────────────────

async def on_cloud_print_start(printer_id: int, subtask_name: str, serial: str, design_title: str = "", title: str = "") -> None:
    """
    Called by bambu_cloud_client when MQTT gcode_state transitions to RUNNING.
    """
    db: Session = SessionLocal()
    try:
        printer = db.get(PrinterConfig, printer_id)
        if not printer:
            log.warning("Cloud: on_cloud_print_start — no printer found for id=%s", printer_id)
            return

        # On first MQTT event after (re)start, recover open job from DB instead of
        # creating a duplicate when the printer is already mid-print.
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
                # Cross-check: if the new RUNNING message names a different file
                # than the open job, the open job is stale (finished but not closed,
                # e.g. container crashed before FINISH arrived).  Close it and fall
                # through to create the new job.
                stale = (
                    open_job.model_name
                    and subtask_name
                    and open_job.model_name != subtask_name
                )
                if stale:
                    log.info(
                        "Cloud: stale open job #%d (%r) — new print is %r; closing stale job",
                        open_job.id, open_job.model_name, subtask_name,
                    )
                    open_job.finished_at = datetime.now(timezone.utc)
                    if open_job.started_at:
                        started = (
                            open_job.started_at.replace(tzinfo=timezone.utc)
                            if open_job.started_at.tzinfo is None
                            else open_job.started_at
                        )
                        open_job.duration_seconds = int(
                            (open_job.finished_at - started).total_seconds()
                        )
                    db.commit()
                    # Fall through to create the new job
                else:
                    log.info(
                        "Cloud: Recovered open PrintJob #%d for %s after restart",
                        open_job.id, printer.name,
                    )
                    _state[printer_id] = {"stage": "printing", "job_id": open_job.id}
                    return  # already have an open job — do not create a duplicate

        # Guard: don't open a duplicate job if already tracking one
        prev = _state.get(printer_id, {})
        if prev.get("stage") in _PRINTING_STAGES:
            return

        from . import bambu_cloud_client
        bambu_cloud_client.reset_print_trays(serial)
        ams_snapshot = bambu_cloud_client.get_ams_snapshot_for_serial(serial)
        status = bambu_cloud_client.get_printer_cloud_status(serial)

        task_id_str = str(status["task_id"]) if status.get("task_id") is not None else None

        # Fetch start time and designTitle from the cloud task API in one call.
        # - start_time: MQTT pushall lacks the real print start time when the app
        #   was down at print start — the task API has the authoritative value.
        # - design_title: the MQTT pushall delivers fields across multiple messages;
        #   the gcode_state=RUNNING message often arrives before the designTitle
        #   message, so the MQTT cache may not have it yet.
        task_meta = await bambu_cloud_client.get_task_metadata(serial, task_id_str)
        real_started_at = task_meta.get("start_time")
        if real_started_at:
            log.info(
                "Cloud: using task API start time %s for job (task_id=%s)",
                real_started_at.isoformat(), task_id_str,
            )

        # Use cloud designTitle if MQTT cache doesn't have it yet
        if not design_title and task_meta.get("design_title"):
            design_title = task_meta["design_title"]
            log.info("Cloud: using task API designTitle %r for job", design_title)

        # Re-evaluate display name with potentially updated design_title
        if design_title:
            display_name = design_title
        elif title:
            display_name = title
        else:
            display_name = subtask_name
            for ext in (".gcode", ".3mf", ".bgcode"):
                if display_name.lower().endswith(ext):
                    display_name = display_name[: -len(ext)]
                    break
        if not display_name:
            display_name = f"Print {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        nozzle_d = status.get("nozzle_diameter")
        job = PrintJob(
            name=display_name,
            model_name=subtask_name or None,
            design_title=design_title or None,
            started_at=real_started_at or datetime.now(timezone.utc),
            source="auto",
            printer_name=printer.name,
            success=True,
            ams_snapshot_start=ams_snapshot,
            task_id=task_id_str,
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
    except Exception as exc:
        log.error("Cloud: on_cloud_print_start failed for printer_id=%s serial=%s: %s",
                  printer_id, serial, exc, exc_info=True)
    finally:
        db.close()


async def on_cloud_print_end(printer_id: int, success: bool, gcode_state: str) -> None:
    """
    Called by bambu_cloud_client when MQTT gcode_state transitions to FINISH,
    FAILED, or IDLE (with an open job).
    """
    prev = _state.get(printer_id, {})
    if prev.get("stage") not in _PRINTING_STAGES:
        # Not actively tracking a job in memory.  On IDLE/FINISH/FAILED events
        # (which the printer also sends after a restart + pushall), close any
        # stale open job that was left unclosed when the container restarted
        # mid-print.  Without this, the recovery block in on_cloud_print_start
        # would re-attach the next new print to the stale job instead of opening
        # a fresh one.
        if gcode_state in ("IDLE", "FINISH", "FAILED"):
            db: Session = SessionLocal()
            try:
                printer = db.get(PrinterConfig, printer_id)
                if printer:
                    stale = (
                        db.query(PrintJob)
                        .filter(
                            PrintJob.printer_name == printer.name,
                            PrintJob.source == "auto",
                            PrintJob.finished_at == None,  # noqa: E711
                        )
                        .order_by(PrintJob.started_at.desc())
                        .first()
                    )
                    if stale:
                        log.info(
                            "Cloud: closing stale open job #%d for %s "
                            "(gcode_state=%s, not actively tracked)",
                            stale.id, printer.name, gcode_state,
                        )
                        await _on_print_end(
                            printer, db, stale.id,
                            success=(gcode_state != "FAILED"),
                        )
            finally:
                db.close()
        return

    db: Session = SessionLocal()
    try:
        printer = db.get(PrinterConfig, printer_id)
        if not printer:
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
            _state[printer_id] = {"stage": "idle", "job_id": None}
    finally:
        db.close()
