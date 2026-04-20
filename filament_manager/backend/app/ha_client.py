"""Home Assistant Supervisor API client.

Only the Supervisor-level helpers remain here — language/timezone detection,
connectivity check, and sensor-state push.
"""
import logging
import os
import httpx

log = logging.getLogger(__name__)

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


async def push_ha_state(entity_id: str, state: int | str, attributes: dict) -> bool:
    """POST a sensor state to the HA states API. Returns True on success."""
    if not _TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(
                f"{HA_API}/states/{entity_id}",
                headers=_headers(),
                json={"state": str(state), "attributes": attributes},
            )
            if r.status_code not in (200, 201):
                log.warning("push_ha_state %s → HTTP %d", entity_id, r.status_code)
                return False
        return True
    except Exception as exc:
        log.debug("push_ha_state %s failed: %s", entity_id, exc)
        return False
