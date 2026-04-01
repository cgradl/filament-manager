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
