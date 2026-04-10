"""
Bambu Lab Cloud REST endpoints.

POST /api/bambu-cloud/login           — start login (triggers 2FA email)
POST /api/bambu-cloud/verify          — submit 2FA code, complete login
GET  /api/bambu-cloud/status          — current connection state
DELETE /api/bambu-cloud/logout        — disconnect + delete credentials
GET  /api/bambu-cloud/devices         — list cloud-bound printers
POST /api/bambu-cloud/import-prints   — import historical print jobs from cloud task API
"""
from datetime import datetime

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import bambu_cloud_client
from ..database import get_db

router = APIRouter(prefix="/api/bambu-cloud", tags=["bambu-cloud"])


class LoginIn(BaseModel):
    email: str
    password: str
    region: str = "us"


class VerifyIn(BaseModel):
    code: str


@router.post("/login")
async def login(body: LoginIn) -> dict:
    """Initiate login. Always returns {requires_2fa: true} — a code is sent by email."""
    return await bambu_cloud_client.begin_login(body.email, body.password, body.region)


@router.post("/verify")
async def verify(body: VerifyIn) -> dict:
    """Submit the 2FA code received by email to complete login."""
    await bambu_cloud_client.verify_2fa(body.code)
    return {"ok": True}


@router.get("/status")
def get_status() -> dict:
    """Returns current cloud connection state. Always safe to poll."""
    return bambu_cloud_client.get_status()


@router.delete("/logout", status_code=204)
async def logout() -> None:
    """Disconnect MQTT and delete stored credentials."""
    await bambu_cloud_client.logout()


@router.get("/devices")
def get_devices() -> list[dict]:
    """List printers bound to the Bambu Lab account."""
    return bambu_cloud_client.get_devices()


@router.post("/cancel-2fa", status_code=204)
async def cancel_2fa() -> None:
    """Cancel a pending 2FA flow without logging out or deleting credentials."""
    bambu_cloud_client.cancel_pending_2fa()


@router.get("/printer/{serial}/status")
def get_printer_status_by_serial(serial: str) -> dict:
    """Return last MQTT status for a device serial (always from cloud cache)."""
    raw = bambu_cloud_client.get_printer_cloud_status(serial)
    tray_now = raw.get("tray_now")
    active_tray = None
    if tray_now is not None:
        try:
            slot = int(tray_now)
            active_tray = f"T{slot + 1}" if slot >= 0 else None
        except (ValueError, TypeError):
            pass
    return {
        "print_stage":    raw.get("gcode_state"),
        "print_progress": str(raw["mc_percent"]) if raw.get("mc_percent") is not None else None,
        "remaining_time": str(raw["mc_remaining_time"]) if raw.get("mc_remaining_time") is not None else None,
        "nozzle_temp":    str(raw["nozzle_temper"]) if raw.get("nozzle_temper") is not None else None,
        "bed_temp":       str(raw["bed_temper"]) if raw.get("bed_temper") is not None else None,
        "current_file":   raw.get("subtask_name"),
        "active_tray":    active_tray,
    }


@router.get("/printer/{serial}/ams")
def get_ams_by_serial(serial: str) -> list[dict]:
    """Return AMS tray detail for a device serial (always from cloud MQTT cache)."""
    detail = bambu_cloud_client.get_ams_detail_for_serial(serial)
    return [
        {
            "slot_key":     slot_key,
            "ha_material":  td.get("material"),
            "ha_color_hex": td.get("color"),
            "ha_remaining": str(td["remain"]) if "remain" in td else None,
            "remain_flag":  td.get("remain_flag"),  # 0/None = reliable, 1 = rough estimate
        }
        for slot_key, td in sorted(detail.items())
    ]


@router.get("/debug")
def get_debug() -> dict:
    """Diagnostic snapshot: MQTT client state, cache contents, token validity."""
    return bambu_cloud_client.get_debug_info()


@router.get("/printer/{serial}/tasks-raw")
async def get_tasks_raw(serial: str) -> dict:
    """Return the raw Bambu Cloud task list for a single device (all pages) as-is."""
    import asyncio, requests as _requests
    creds = bambu_cloud_client._load_credentials()
    if not creds or not creds.get("token"):
        return {"serial": serial, "total": 0, "tasks": []}
    token = creds["token"]
    tasks: list[dict] = []
    limit = 50
    offset = 0
    loop = asyncio.get_event_loop()
    while True:
        def _fetch(o=offset):
            resp = _requests.get(
                "https://api.bambulab.com/v1/user-service/my/tasks",
                params={"deviceId": serial, "limit": limit, "offset": o},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        data = await loop.run_in_executor(None, _fetch)
        hits = data.get("hits") or []
        tasks.extend(hits)
        total = int(data.get("total") or 0)
        offset += len(hits)
        if not hits or offset >= total:
            break
    return {"serial": serial, "total": len(tasks), "tasks": tasks}


@router.post("/reconnect")
async def force_reconnect() -> dict:
    """Force restart of all MQTT connections using saved credentials."""
    try:
        await bambu_cloud_client.reconnect()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _parse_task_time(value) -> datetime | None:
    """Parse a Bambu Cloud task timestamp (Unix seconds int/float or ISO string)."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(float(value))
        s = str(value).strip()
        if s.isdigit():
            return datetime.utcfromtimestamp(float(s))
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


@router.post("/import-prints")
async def import_cloud_prints(db: Session = Depends(get_db)) -> dict:
    """Import historical print jobs from the Bambu Cloud task API.

    Deduplicates by task_id — jobs already tracked in real time are skipped.
    Per-tray usage data is stored as suggested_usages so the user can assign
    to spools via the Log Usage modal.
    """
    from ..models import PrintJob, PrintUsage, PrinterConfig

    creds = bambu_cloud_client._load_credentials()
    if not creds or not creds.get("token"):
        raise HTTPException(400, "Not connected to Bambu Cloud")

    # serial → printer name (cloud printers only)
    cloud_printers: dict[str, str] = {
        p.bambu_serial: p.name
        for p in db.query(PrinterConfig).filter(
            PrinterConfig.bambu_serial.isnot(None),
            PrinterConfig.bambu_source == "cloud",
        ).all()
        if p.bambu_serial
    }

    tasks = await bambu_cloud_client.get_all_tasks()

    # Pre-load existing task_ids for fast dedup
    existing_task_ids: set[str] = {
        r[0] for r in db.query(PrintJob.task_id).filter(PrintJob.task_id.isnot(None)).all()
    }

    imported = 0
    skipped = 0
    total = len(tasks)

    for task in tasks:
        task_id_raw = task.get("id")
        task_id = str(task_id_raw) if task_id_raw is not None else None

        if task_id and task_id in existing_task_ids:
            skipped += 1
            continue

        started_at = _parse_task_time(task.get("startTime"))
        if not started_at:
            skipped += 1
            continue

        finished_at = _parse_task_time(task.get("endTime"))

        duration_seconds = None
        if finished_at and started_at:
            delta = (finished_at - started_at).total_seconds()
            if delta > 0:
                duration_seconds = int(delta)

        serial = str(task.get("deviceId", ""))
        printer_name = cloud_printers.get(serial)

        name = task.get("designTitle") or task.get("title") or "Imported print"
        weight = task.get("weight")
        # Bambu Cloud: status 4 = FINISH (success), 5 = FAILED
        success = task.get("status") != 5

        # Parse amsDetailMapping — build both PrintUsage rows and suggested_usages hints
        suggestions: list[dict] = []
        usage_entries: list[dict] = []
        for entry in (task.get("amsDetailMapping") or []):
            idx = entry.get("ams")
            tray_weight = entry.get("weight")
            if idx is None or tray_weight is None:
                continue
            unit = int(idx) // 4 + 1
            tray = int(idx) % 4 + 1
            slot_key = f"ams{unit}_tray{tray}"
            color_raw = entry.get("sourceColor") or entry.get("targetColor") or ""
            color_hex = f"#{color_raw[:6]}" if len(color_raw) >= 6 else None
            grams = round(float(tray_weight), 1)
            suggestions.append({
                "ams_slot": slot_key,
                "grams": grams,
                "filament_type": entry.get("filamentType") or entry.get("targetFilamentType") or "",
                "color": color_hex,
            })
            usage_entries.append({"ams_slot": slot_key, "grams": grams})

        job = PrintJob(
            name=name,
            model_name=name,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            success=success,
            printer_name=printer_name,
            source="cloud",
            ams_snapshot_start={},
            task_id=task_id,
            print_weight_g=float(weight) if weight is not None else None,
            suggested_usages=suggestions if suggestions else None,
        )
        db.add(job)
        db.flush()

        for u in usage_entries:
            db.add(PrintUsage(
                print_job_id=job.id,
                spool_id=None,
                grams_used=u["grams"],
                ams_slot=u["ams_slot"],
            ))

        if task_id:
            existing_task_ids.add(task_id)
        imported += 1

    db.commit()
    return {"ok": True, "imported": imported, "skipped": skipped, "total": total}
