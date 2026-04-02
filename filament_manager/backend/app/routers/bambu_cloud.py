"""
Bambu Lab Cloud REST endpoints.

POST /api/bambu-cloud/login    — start login (triggers 2FA email)
POST /api/bambu-cloud/verify   — submit 2FA code, complete login
GET  /api/bambu-cloud/status   — current connection state
DELETE /api/bambu-cloud/logout — disconnect + delete credentials
GET  /api/bambu-cloud/devices  — list cloud-bound printers
"""
from pydantic import BaseModel
from fastapi import APIRouter

from .. import bambu_cloud_client

router = APIRouter(prefix="/api/bambu-cloud", tags=["bambu-cloud"])


class LoginIn(BaseModel):
    email: str
    password: str


class VerifyIn(BaseModel):
    code: str


@router.post("/login")
async def login(body: LoginIn) -> dict:
    """Initiate login. Always returns {requires_2fa: true} — a code is sent by email."""
    return await bambu_cloud_client.begin_login(body.email, body.password)


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
        "print_stage":       raw.get("gcode_state"),
        "print_progress":    str(raw["mc_percent"]) if raw.get("mc_percent") is not None else None,
        "remaining_time":    str(raw["mc_remaining_time"]) if raw.get("mc_remaining_time") is not None else None,
        "nozzle_temp":       str(raw["nozzle_temper"]) if raw.get("nozzle_temper") is not None else None,
        "bed_temp":          str(raw["bed_temper"]) if raw.get("bed_temper") is not None else None,
        "current_file":      raw.get("subtask_name"),
        "active_tray":       active_tray,
        "filament_used":     str(raw["mc_print_filament_used"]) if raw.get("mc_print_filament_used") is not None else None,
        "lifetime_filament": str(raw["mc_lifetime_filament_usage"]) if raw.get("mc_lifetime_filament_usage") is not None else None,
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


@router.post("/reconnect")
async def force_reconnect() -> dict:
    """Force restart of all MQTT connections using saved credentials."""
    try:
        await bambu_cloud_client.reconnect()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
