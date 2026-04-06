"""Home Assistant Supervisor API client."""
import os
import logging
import httpx

log = logging.getLogger(__name__)

HA_API = "http://supervisor/core/api"
_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

# Entity suffixes used by the greghesp Bambu Lab HA integration (English defaults).
# Used as the last-resort fallback when neither the entity registry nor manual overrides
# resolve an entity ID.  All produce sensor.{slug}_{suffix} entity IDs.
_PRINTER_SUFFIXES = {
    "print_stage":    "current_stage",
    "print_progress": "print_progress",
    "remaining_time": "remaining_time",
    "nozzle_temp":    "nozzle_temperature",
    "bed_temp":       "bed_temperature",
    "current_file":   "task_name",
    "print_weight":   "print_weight",
    "active_tray":    "active_tray",    # sensor.{slug}_active_tray — currently loaded tray slot
}

# Binary sensor suffixes — produce binary_sensor.{slug}_{suffix} entity IDs.
_PRINTER_BINARY_SUFFIXES = {
    "ams_active": "ams_1_active",   # binary_sensor.{slug}_ams_1_active — Running/Not running (AMS unit 1 in use)
}

# Maps ha-bambulab sensor `key` (in definitions.py / unique_id suffix) → our internal key.
# unique_id format used by ha-bambulab: "{serial}_{key}"
_BAMBU_KEY_MAP: dict[str, str] = {
    "stage":          "print_stage",
    "print_progress": "print_progress",
    "remaining_time": "remaining_time",
    "nozzle_temp":    "nozzle_temp",
    "bed_temp":       "bed_temp",
    "subtask_name":   "current_file",
    "print_weight":   "print_weight",
}

# Per-serial cache of registry-discovered entity IDs: serial → {our_key: entity_id}
_registry_cache: dict[str, dict[str, str]] = {}

# Per-device-slug cache of discovered AMS tray counts: device_slug → {unit_id: tray_count}
# Populated by discover_ams_tray_counts(); reused by print_monitor to avoid extra HA calls.
_ams_tray_counts_cache: dict[str, dict[int, int]] = {}


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
    Return the effective entity_id for each printer sensor / binary sensor.
    Any key present in sensor_overrides replaces the auto-computed default,
    allowing users with non-English HA installations (or renamed entities) to
    specify their actual entity IDs.
    """
    result = {k: f"sensor.{device_slug}_{v}" for k, v in _PRINTER_SUFFIXES.items()}
    result.update({k: f"binary_sensor.{device_slug}_{v}" for k, v in _PRINTER_BINARY_SUFFIXES.items()})
    if sensor_overrides:
        for k, v in sensor_overrides.items():
            if v and v.strip():
                result[k] = v.strip()
    return result


def get_cached_ams_tray_counts(device_slug: str) -> dict[int, int] | None:
    """Return the last discovered per-unit tray counts for a device slug, or None if unknown."""
    return _ams_tray_counts_cache.get(device_slug)


async def discover_ams_tray_counts(
    device_slug: str,
    ams_unit_count: int,
    ams_device_slug: str | None = None,
    ams_overrides: dict | None = None,
) -> dict[int, int]:
    """Discover the actual number of trays per AMS unit by checking which HA entities exist.

    For each unit 1..ams_unit_count, probes HA entity IDs and counts how many
    consecutive tray entities are present.  This detects AMS variants (e.g. AMS HT
    with 1 slot vs standard AMS with 4) without any hardcoding.

    Result is cached in _ams_tray_counts_cache[device_slug] and also returned.
    Falls back to 4 trays per unit when HA is unreachable or no entities are found.
    """
    ov = ams_overrides or {}
    tray_pattern = ov.get("tray_pattern") or "tray_{t}"

    try:
        all_entities = await get_all_entities()
        entity_ids = {e["entity_id"] for e in all_entities}
    except Exception:
        result = {u: 4 for u in range(1, ams_unit_count + 1)}
        _ams_tray_counts_cache[device_slug] = result
        return result

    result: dict[int, int] = {}
    for u in range(1, ams_unit_count + 1):
        slug = ams_device_slug if ams_device_slug else f"{device_slug}_ams_{u}"
        highest = 0
        for t in range(1, 17):  # generous upper bound
            slot = tray_pattern.format(u=u, t=t)
            entity = f"sensor.{slug}_{slot}"
            if entity in entity_ids:
                highest = t
            elif highest > 0:
                break  # first gap after finding at least one — stop
        # Fall back to 4 if no entities found (HA offline or not yet discovered)
        result[u] = highest if highest > 0 else 4

    _ams_tray_counts_cache[device_slug] = result
    return result


def get_ams_config(
    device_slug: str,
    ams_unit_count: int,
    trays_per_unit: dict[int, int] | None = None,
    trays_per_ams: int = 4,
    ams_device_slug: str | None = None,
    ams_overrides: dict | None = None,
) -> list[dict]:
    """
    Build the AMS config structure (same format used by print_monitor).

    The greghesp Bambu Lab integration exposes each AMS unit as a separate
    HA device named "{printer_slug}_ams_{u}" (e.g. "my_printer_ams_1").
    Each tray is a single entity whose state = material name and whose
    attributes hold color and remain%. This is the default mode.

    When ams_device_slug is explicitly set, that slug is used instead of
    the auto-computed "{device_slug}_ams_{u}".

    trays_per_unit: per-unit tray count dict {unit_id: count} from discover_ams_tray_counts().
                    When provided, overrides trays_per_ams for each unit individually.
    trays_per_ams:  fallback tray count per unit when trays_per_unit is not given.

    ams_overrides keys: tray_pattern (default "tray_{t}"),
                        suffix_type, suffix_color, suffix_remain
    Use {u} and {t} as unit/tray placeholders inside tray_pattern.
    """
    ov = ams_overrides or {}
    tray_pattern = ov.get("tray_pattern") or "tray_{t}"

    units = []
    for u in range(1, ams_unit_count + 1):
        # Effective AMS device slug for this unit
        effective_ams_slug = ams_device_slug if ams_device_slug else f"{device_slug}_ams_{u}"
        tray_count = (trays_per_unit or {}).get(u, trays_per_ams)
        trays = []
        for t in range(1, tray_count + 1):
            slot = tray_pattern.format(u=u, t=t)
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


async def discover_bambu_sensor_ids(serial: str) -> dict[str, str]:
    """Query the HA entity registry to find actual entity_ids for a Bambu printer.

    ha-bambulab assigns unique_id = "{serial}_{key}" for every sensor (e.g.
    "01S00A123456789_print_weight").  HA stores the entity_id that was generated
    at install time (language-dependent) in the entity registry, so matching by
    unique_id suffix is the only reliable way to find the correct entity_id
    regardless of the HA language or device name.

    Results are cached for the process lifetime.  Call clear_registry_cache()
    after saving a printer config to force a fresh lookup.
    """
    if serial in _registry_cache:
        return _registry_cache[serial]

    result: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{HA_API}/config/entity_registry_entries/sensor",
                headers=_headers(),
            )
            if r.status_code == 200:
                prefix = f"{serial}_"
                for entry in r.json():
                    if entry.get("platform") != "bambu_lab":
                        continue
                    uid = entry.get("unique_id", "")
                    if not uid.startswith(prefix):
                        continue
                    bambu_key = uid[len(prefix):]
                    our_key = _BAMBU_KEY_MAP.get(bambu_key)
                    if our_key:
                        entity_id = entry.get("entity_id")
                        if entity_id:
                            result[our_key] = entity_id
                            log.debug("Registry: %s → %s (uid=%s)", our_key, entity_id, uid)
            else:
                log.debug("HA entity registry returned %s", r.status_code)
    except Exception as exc:
        log.warning("HA entity registry lookup failed for %s: %s", serial, exc)

    _registry_cache[serial] = result
    if result:
        log.info("Discovered %d sensor entity IDs for serial %s via HA registry", len(result), serial)
    return result


def clear_registry_cache(serial: str | None = None) -> None:
    """Invalidate the cached registry lookup for a serial (or all serials)."""
    if serial:
        _registry_cache.pop(serial, None)
    else:
        _registry_cache.clear()


async def resolve_printer_entity_ids(
    device_slug: str,
    sensor_overrides: dict | None = None,
    serial: str | None = None,
) -> dict[str, str]:
    """Return effective entity_id for each printer sensor.

    Resolution priority (highest → lowest):
    1. Manual sensor_overrides stored on the printer config
    2. Entity registry auto-discovered entity_id (requires bambu_serial)
    3. Default: sensor.{device_slug}_{english_suffix}
    """
    result = {k: f"sensor.{device_slug}_{v}" for k, v in _PRINTER_SUFFIXES.items()}

    if serial:
        discovered = await discover_bambu_sensor_ids(serial)
        result.update(discovered)

    if sensor_overrides:
        for k, v in sensor_overrides.items():
            if v and v.strip():
                result[k] = v.strip()

    return result


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
