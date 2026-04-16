"""Home Assistant Supervisor API client.

Only the Supervisor-level helpers remain here — language/timezone detection
and connectivity check.  All greghesp ha-bambulab entity-polling code has
been removed; the app now uses Bambu Cloud MQTT exclusively for printer data.
"""
import os
import httpx

HA_API = "http://supervisor/core/api"
_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_TOKEN}",
        "Content-Type": "application/json",
    }


async def is_ha_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{HA_API}/", headers=_headers())
            return r.status_code == 200
    except Exception:
        return False
