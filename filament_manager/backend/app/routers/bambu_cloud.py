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
