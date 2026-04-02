"""Home Assistant Supervisor API client."""
import os
import logging
import httpx

log = logging.getLogger(__name__)

HA_API = "http://supervisor/core/api"
_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

# Entity suffixes used by the greghesp Bambu Lab HA integration
_PRINTER_SUFFIXES = {
    "print_stage":    "current_stage",
    "print_progress": "print_progress",
    "remaining_time": "remaining_time",
    "nozzle_temp":    "nozzle_temperature",
    "bed_temp":       "bed_temperature",
    "current_file":   "task_name",
    "print_weight":   "print_weight",
}


def slugify(name: str) -> str:
    """'My Printer' → 'my_printer'. Mirrors HA's internal slug logic."""
    import re
    s = name.lower().strip()
    s = re.sub(r"[\s-]+", "_", s)   # spaces/hyphens → underscore
    s = re.sub(r"[^\w]", "", s)     # strip anything not a-z, 0-9, _
    s = re.sub(r"_+", "_", s)       # collapse consecutive underscores
    return s.strip("_")


def get_printer_entity_ids(device_slug: str, sensor_overrides: dict | None = None) -> dict[str, str]:
    """
    Return the effective entity_id for each printer sensor.
    Any key present in sensor_overrides replaces the auto-computed default,
    allowing users with non-English HA installations (or renamed entities) to
    specify their actual entity IDs.
    """
    result = {k: f"sensor.{device_slug}_{v}" for k, v in _PRINTER_SUFFIXES.items()}
    if sensor_overrides:
        for k, v in sensor_overrides.items():
            if v and v.strip():
                result[k] = v.strip()
    return result


def get_ams_config(device_slug: str, ams_unit_count: int, trays_per_ams: int = 4,
                   ams_device_slug: str | None = None,
                   ams_overrides: dict | None = None) -> list[dict]:
    """
    Build the AMS config structure (same format used by print_monitor).

    The greghesp Bambu Lab integration exposes each AMS unit as a separate
    HA device named "{printer_slug}_ams_{u}" (e.g. "my_printer_ams_1").
    Each tray is a single entity whose state = material name and whose
    attributes hold color and remain%. This is the default mode.

    When ams_device_slug is explicitly set, that slug is used instead of
    the auto-computed "{device_slug}_ams_{u}".

    ams_overrides keys: tray_pattern (default "tray_{t}"),
                        suffix_type, suffix_color, suffix_remain
    Use {u} and {t} as unit/tray placeholders inside tray_pattern.
    """
    ov = ams_overrides or {}
    tray_pattern  = ov.get("tray_pattern") or "tray_{t}"
    suffix_type   = ov.get("suffix_type")   or "_type"
    suffix_color  = ov.get("suffix_color")  or "_color"
    suffix_remain = ov.get("suffix_remain") or "_remain"

    units = []
    for u in range(1, ams_unit_count + 1):
        # Effective AMS device slug for this unit
        effective_ams_slug = ams_device_slug if ams_device_slug else f"{device_slug}_ams_{u}"
        trays = []
        for t in range(1, trays_per_ams + 1):
            slot = tray_pattern.format(u=u, t=t)
            if ams_device_slug:
                # Explicit override slug: attribute mode (single entity per tray)
                entity = f"sensor.{effective_ams_slug}_{slot}"
                trays.append({
                    "slot": t,
                    "entity_tray":      entity,
                    "entity_material":  entity,
                    "entity_color":     entity,
                    "entity_remaining": entity,
                    "remaining_source": "attribute",
                })
            else:
                # Default: greghesp integration auto-slug {device_slug}_ams_{u}, attribute mode
                entity = f"sensor.{effective_ams_slug}_{slot}"
                trays.append({
                    "slot": t,
                    "entity_tray":      entity,
                    "entity_material":  entity,
                    "entity_color":     entity,
                    "entity_remaining": entity,
                    "remaining_source": "attribute",
                })
        units.append({"ams_id": u, "trays": trays})
    return units


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_TOKEN}",
        "Content-Type": "application/json",
    }


async def get_entity_state(entity_id: str) -> dict | None:
    if not entity_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{HA_API}/states/{entity_id}", headers=_headers())
            if r.status_code == 200:
                return r.json()
            log.debug("HA entity %s returned %s", entity_id, r.status_code)
    except Exception as exc:
        log.warning("HA request failed for %s: %s", entity_id, exc)
    return None


async def get_all_entities() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{HA_API}/states", headers=_headers())
            if r.status_code == 200:
                return r.json()
    except Exception as exc:
        log.warning("HA get_all_entities failed: %s", exc)
    return []


async def get_entity_value(entity_id: str) -> str | None:
    data = await get_entity_state(entity_id)
    if data:
        return data.get("state")
    return None


async def get_ams_snapshot(ams_config: list[dict]) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for unit in ams_config:
        ams_id = unit.get("ams_id", 1)
        for tray in unit.get("trays", []):
            slot = tray.get("slot", 0)
            entity = tray.get("entity_remaining")
            source = tray.get("remaining_source", "state")
            if not entity:
                continue
            if source == "attribute":
                data = await get_entity_state(entity)
                if not data:
                    continue
                attrs = data.get("attributes", {})
                val = attrs.get("remain") or attrs.get("remaining") or attrs.get("remain_filament")
            else:
                val = await get_entity_value(entity)
            try:
                snapshot[f"ams{ams_id}_tray{slot}"] = float(val)
            except (TypeError, ValueError):
                pass
    return snapshot


async def is_ha_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{HA_API}/", headers=_headers())
            return r.status_code == 200
    except Exception:
        return False
