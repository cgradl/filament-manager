from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PrinterConfig, Spool
from ..schemas import SpoolOut
from .. import ha_client

router = APIRouter(prefix="/api/printers", tags=["printers"])


# ── Schemas (inline — simpler than a separate file for this small resource) ───

class PrinterIn(BaseModel):
    name: str
    device_slug: str
    ams_device_slug: str | None = None
    ams_unit_count: int = 1
    is_active: bool = True
    bambu_serial: str | None = None
    bambu_source: str = "ha"
    # Per-printer sensor entity ID overrides (empty string = use default)
    sensor_print_stage:    str | None = None
    sensor_print_progress: str | None = None
    sensor_remaining_time: str | None = None
    sensor_nozzle_temp:    str | None = None
    sensor_bed_temp:       str | None = None
    sensor_current_file:   str | None = None
    sensor_print_weight:   str | None = None
    # AMS entity pattern/suffix overrides
    ams_tray_pattern:  str | None = None
    ams_suffix_type:   str | None = None
    ams_suffix_color:  str | None = None
    ams_suffix_remain: str | None = None

    def model_post_init(self, __context) -> None:
        # Normalise empty strings to None so they're not stored as overrides
        for field in ("sensor_print_stage", "sensor_print_progress", "sensor_remaining_time",
                      "sensor_nozzle_temp", "sensor_bed_temp", "sensor_current_file",
                      "sensor_print_weight",
                      "ams_tray_pattern", "ams_suffix_type", "ams_suffix_color", "ams_suffix_remain"):
            if isinstance(getattr(self, field), str) and not getattr(self, field).strip():
                setattr(self, field, None)


class PrinterOut(BaseModel):
    id: int
    name: str
    device_slug: str
    ams_device_slug: str | None
    ams_unit_count: int
    is_active: bool
    bambu_serial: str | None
    bambu_source: str
    sensor_print_stage:    str | None
    sensor_print_progress: str | None
    sensor_remaining_time: str | None
    sensor_nozzle_temp:    str | None
    sensor_bed_temp:       str | None
    sensor_current_file:   str | None
    sensor_print_weight:   str | None
    ams_tray_pattern:  str | None
    ams_suffix_type:   str | None
    ams_suffix_color:  str | None
    ams_suffix_remain: str | None

    class Config:
        from_attributes = True


# ── Static routes BEFORE /{printer_id} ───────────────────────────────────────

@router.get("/discover")
async def discover_printer(device: str, ams_device: str | None = None):
    """
    Given a device name (e.g. "My Printer"), derive entity IDs and check which ones
    actually exist in HA. Returns discovered entities + current state values.
    Optional ams_device to test a separate AMS device name.
    """
    slug = ha_client.slugify(device)
    ams_slug = ha_client.slugify(ams_device) if ams_device else slug
    all_entities = await ha_client.get_all_entities()
    entity_map = {e["entity_id"]: e.get("state") for e in all_entities}

    printer_ids = ha_client.get_printer_entity_ids(slug)
    printer_result = {}
    for key, eid in printer_ids.items():
        printer_result[key] = {
            "entity_id": eid,
            "found": eid in entity_map,
            "state": entity_map.get(eid),
        }

    # AMS preview — discover actual tray count for unit 1 from HA entities
    ams_tray_counts = await ha_client.discover_ams_tray_counts(
        slug, ams_unit_count=1, ams_device_slug=ams_slug if ams_device else None,
    )
    ams_config = ha_client.get_ams_config(
        slug, ams_unit_count=1, trays_per_unit=ams_tray_counts,
        ams_device_slug=ams_slug if ams_device else None,
    )
    ams_result = []
    for unit in ams_config:
        trays = []
        for tray in unit["trays"]:
            trays.append({
                "slot": tray["slot"],
                "entity_remaining": tray["entity_remaining"],
                "found": tray["entity_remaining"] in entity_map,
                "state": entity_map.get(tray["entity_remaining"]),
            })
        ams_result.append({"ams_id": unit["ams_id"], "trays": trays})

    # All HA entities that contain either the printer or AMS slug (for debugging)
    # Include the auto-computed ams_1 slug so discover shows AMS entities even without explicit ams_device
    search_slugs = {slug, ams_slug, f"{slug}_ams_1"}
    fuzzy = [
        {"entity_id": e["entity_id"],
         "state": e.get("state"),
         "friendly_name": e.get("attributes", {}).get("friendly_name", "")}
        for e in all_entities
        if any(s in e["entity_id"] for s in search_slugs)
    ]

    return {
        "slug": slug,
        "ams_slug": ams_slug,
        "printer_entities": printer_result,
        "ams_preview": ams_result,
        "all_matching": sorted(fuzzy, key=lambda x: x["entity_id"]),
    }


# ── AMS tray assignment (BEFORE /{printer_id} to avoid routing conflict) ─────

@router.get("/{printer_id}/ams")
async def get_ams_trays(printer_id: int, db: Session = Depends(get_db)):
    """
    Returns AMS tray data: HA sensor values + the linked spool from inventory.
    Slot keys use the format "ams{unit}_tray{slot}" (e.g. "ams1_tray2").
    """
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")

    # Cloud-source printers: enumerate directly from MQTT cache keys.
    # The cache contains exactly the slot keys Bambu reported, so AMS variants
    # (e.g. AMS HT with 1 slot, standard AMS with 4) are handled automatically.
    if p.bambu_source == "cloud" and p.bambu_serial:
        import re as _re
        from .. import bambu_cloud_client
        detail = bambu_cloud_client.get_ams_detail_for_serial(p.bambu_serial)

        def _slot_sort_key(k: str) -> tuple[int, int]:
            m = _re.match(r'^ams(\d+)_tray(\d+)$', k)
            return (int(m.group(1)), int(m.group(2))) if m else (99, 99)

        result = []
        for slot_key in sorted(detail.keys(), key=_slot_sort_key):
            m = _re.match(r'^ams(\d+)_tray(\d+)$', slot_key)
            if not m:
                continue
            u, t = int(m.group(1)), int(m.group(2))
            td = detail[slot_key]
            full_key = f"{p.name}:{slot_key}"
            spool = (
                db.query(Spool).filter(Spool.ams_slot == full_key).first()
                or db.query(Spool).filter(Spool.ams_slot == slot_key).first()
            )
            remain_val = td.get("remain")
            # Negative remain (typically -1) means "not tracked by AMS" — show nothing
            ha_remaining = str(round(remain_val, 1)) if remain_val is not None and remain_val >= 0 else None
            result.append({
                "slot_key":     slot_key,
                "ams_id":       u,
                "tray":         t,
                "ha_material":  td.get("material") or None,
                "ha_color_hex": td.get("color"),
                "ha_remaining": ha_remaining,
                "spool":        SpoolOut.model_validate(spool).model_dump() if spool else None,
            })
        return result

    tray_counts = await ha_client.discover_ams_tray_counts(
        p.device_slug, p.ams_unit_count, p.ams_device_slug, p.ams_overrides,
    )
    ams_config = ha_client.get_ams_config(
        p.device_slug, p.ams_unit_count, trays_per_unit=tray_counts,
        ams_device_slug=p.ams_device_slug, ams_overrides=p.ams_overrides,
    )
    all_entities = await ha_client.get_all_entities()
    entity_map = {e["entity_id"]: e for e in all_entities}

    result = []
    _invalid = {"unknown", "unavailable", "none", "", None}

    for unit in ams_config:
        for tray in unit["trays"]:
            slot_key = f"ams{unit['ams_id']}_tray{tray['slot']}"
            source = tray.get("remaining_source", "state")

            tray_entity = entity_map.get(tray["entity_tray"], {})
            attrs = tray_entity.get("attributes", {})

            if source == "attribute":
                # Single tray entity: state = material name, attrs hold color & remaining
                ha_material  = tray_entity.get("state")
                ha_remaining = attrs.get("remain") or attrs.get("remaining") or attrs.get("remain_filament")
                ha_color_raw = attrs.get("color") or attrs.get("color_hex") or attrs.get("hex_color")
            else:
                # Separate entities per attribute
                col_entity   = entity_map.get(tray["entity_color"],     {})
                rem_entity   = entity_map.get(tray["entity_remaining"], {})
                ha_material  = tray_entity.get("state")
                ha_remaining = rem_entity.get("state")
                ha_color_raw = col_entity.get("attributes", {}).get("color_hex") or col_entity.get("state")

            # Normalise color to #rrggbb
            ha_color_hex = None
            if ha_color_raw and str(ha_color_raw).lower() not in _invalid:
                s = str(ha_color_raw).strip().lstrip("#")
                if len(s) == 6:
                    ha_color_hex = f"#{s}"

            full_key = f"{p.name}:{slot_key}"
            spool = (
                db.query(Spool).filter(Spool.ams_slot == full_key).first()
                or db.query(Spool).filter(Spool.ams_slot == slot_key).first()
            )

            result.append({
                "slot_key":     slot_key,
                "ams_id":       unit["ams_id"],
                "tray":         tray["slot"],
                "ha_material":  ha_material if ha_material not in _invalid else None,
                "ha_color_hex": ha_color_hex,
                "ha_remaining": str(ha_remaining) if ha_remaining not in _invalid else None,
                "spool":        SpoolOut.model_validate(spool).model_dump() if spool else None,
            })

    return result


@router.post("/{printer_id}/ams/sync")
async def sync_ams_weights(printer_id: int, db: Session = Depends(get_db)):
    """
    Read current remaining % from HA tray entities and update each assigned spool's
    current_weight_g to match (initial_weight * remaining_pct / 100).
    Returns a list of updated spools.
    """
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")

    updated = []

    # Cloud-source printers: use MQTT cache instead of HA entities
    if p.bambu_source == "cloud" and p.bambu_serial:
        from .. import bambu_cloud_client
        snapshot = bambu_cloud_client.get_ams_snapshot_for_serial(p.bambu_serial)
        for slot_key, remaining_pct in snapshot.items():
            # Skip trays where the AMS has no reliable data (non-Bambu spools report -1)
            if remaining_pct is None or remaining_pct < 0:
                continue
            full_key = f"{p.name}:{slot_key}"
            spool = (
                db.query(Spool).filter(Spool.ams_slot == full_key).first()
                or db.query(Spool).filter(Spool.ams_slot == slot_key).first()
            )
            if not spool:
                continue
            new_weight = round(spool.initial_weight_g * remaining_pct / 100, 1)
            spool.current_weight_g = min(spool.initial_weight_g, max(0.0, new_weight))
            updated.append({
                "slot_key": slot_key,
                "spool_id": spool.id,
                "spool_name": f"{spool.brand} {spool.material} {spool.color_name}",
                "remaining_pct": remaining_pct,
                "new_weight_g": spool.current_weight_g,
            })
        db.commit()
        return {"updated": updated}

    tray_counts_sync = await ha_client.discover_ams_tray_counts(
        p.device_slug, p.ams_unit_count, p.ams_device_slug, p.ams_overrides,
    )
    ams_config = ha_client.get_ams_config(
        p.device_slug, p.ams_unit_count, trays_per_unit=tray_counts_sync,
        ams_device_slug=p.ams_device_slug, ams_overrides=p.ams_overrides,
    )
    all_entities = await ha_client.get_all_entities()
    entity_map = {e["entity_id"]: e for e in all_entities}

    for unit in ams_config:
        for tray in unit["trays"]:
            slot_key = f"ams{unit['ams_id']}_tray{tray['slot']}"
            source = tray.get("remaining_source", "state")

            tray_entity = entity_map.get(tray["entity_remaining"], {})
            attrs = tray_entity.get("attributes", {})

            if source == "attribute":
                val = (attrs.get("remain") or attrs.get("remaining")
                       or attrs.get("remain_filament") or attrs.get("filament_remaining"))
            else:
                val = tray_entity.get("state")

            try:
                remaining_pct = float(val)
            except (TypeError, ValueError):
                continue

            # Skip trays where HA has no reliable data (non-Bambu spools may report -1 or 0)
            if remaining_pct < 0:
                continue

            full_key = f"{p.name}:{slot_key}"
            spool = (
                db.query(Spool).filter(Spool.ams_slot == full_key).first()
                or db.query(Spool).filter(Spool.ams_slot == slot_key).first()
            )
            if not spool:
                continue

            new_weight = round(spool.initial_weight_g * remaining_pct / 100, 1)
            spool.current_weight_g = min(spool.initial_weight_g, max(0.0, new_weight))
            updated.append({
                "slot_key": slot_key,
                "spool_id": spool.id,
                "spool_name": f"{spool.brand} {spool.material} {spool.color_name}",
                "remaining_pct": remaining_pct,
                "new_weight_g": spool.current_weight_g,
            })

    db.commit()
    return {"updated": updated}


@router.post("/{printer_id}/ams/{slot_key}/sync")
async def sync_ams_tray_weight(printer_id: int, slot_key: str, db: Session = Depends(get_db)):
    """
    Read remaining % from HA for a single AMS tray and update its linked spool.
    Only updates when HA returns a valid percentage > 0 (avoids zeroing non-Bambu spools).
    """
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")

    full_key = f"{p.name}:{slot_key}"
    spool = (
        db.query(Spool).filter(Spool.ams_slot == full_key).first()
        or db.query(Spool).filter(Spool.ams_slot == slot_key).first()
    )
    if not spool:
        raise HTTPException(404, "No spool assigned to this tray")

    # Cloud-source printers: use MQTT cache instead of HA entities
    if p.bambu_source == "cloud" and p.bambu_serial:
        from .. import bambu_cloud_client
        snapshot = bambu_cloud_client.get_ams_snapshot_for_serial(p.bambu_serial)
        remaining_pct_raw = snapshot.get(slot_key)
        if remaining_pct_raw is None:
            raise HTTPException(422, "No MQTT data for this tray — printer may not be connected")
        remaining_pct = float(remaining_pct_raw)
        if remaining_pct <= 0:
            raise HTTPException(422, "MQTT reports 0 % remaining — skipped to avoid zeroing a non-Bambu spool")
        new_weight = round(spool.initial_weight_g * remaining_pct / 100, 1)
        spool.current_weight_g = min(spool.initial_weight_g, max(0.0, new_weight))
        db.commit()
        return {
            "slot_key": slot_key,
            "spool_id": spool.id,
            "spool_name": f"{spool.brand} {spool.material} {spool.color_name}",
            "remaining_pct": remaining_pct,
            "new_weight_g": spool.current_weight_g,
        }

    tray_counts_single = await ha_client.discover_ams_tray_counts(
        p.device_slug, p.ams_unit_count, p.ams_device_slug, p.ams_overrides,
    )
    ams_config = ha_client.get_ams_config(
        p.device_slug, p.ams_unit_count, trays_per_unit=tray_counts_single,
        ams_device_slug=p.ams_device_slug, ams_overrides=p.ams_overrides,
    )
    all_entities = await ha_client.get_all_entities()
    entity_map = {e["entity_id"]: e for e in all_entities}

    # Find the tray config entry for this slot_key
    tray_cfg = None
    for unit in ams_config:
        for tray in unit["trays"]:
            if f"ams{unit['ams_id']}_tray{tray['slot']}" == slot_key:
                tray_cfg = tray
                break
        if tray_cfg:
            break

    if not tray_cfg:
        raise HTTPException(404, "Tray config not found — check AMS unit count in printer settings")

    source = tray_cfg.get("remaining_source", "state")
    tray_entity = entity_map.get(tray_cfg["entity_remaining"], {})
    attrs = tray_entity.get("attributes", {})

    if source == "attribute":
        val = (attrs.get("remain") or attrs.get("remaining")
               or attrs.get("remain_filament") or attrs.get("filament_remaining"))
    else:
        val = tray_entity.get("state")

    try:
        remaining_pct = float(val)
    except (TypeError, ValueError):
        raise HTTPException(422, "No valid remaining % data from HA for this tray — entity may be unavailable or this is a non-Bambu spool")

    if remaining_pct <= 0:
        raise HTTPException(422, "HA reports 0 % remaining — skipped to avoid zeroing a non-Bambu spool")

    new_weight = round(spool.initial_weight_g * remaining_pct / 100, 1)
    spool.current_weight_g = min(spool.initial_weight_g, max(0.0, new_weight))
    db.commit()

    return {
        "slot_key": slot_key,
        "spool_id": spool.id,
        "spool_name": f"{spool.brand} {spool.material} {spool.color_name}",
        "remaining_pct": remaining_pct,
        "new_weight_g": spool.current_weight_g,
    }


@router.post("/{printer_id}/ams/{slot_key}/assign")
def assign_ams_tray(
    printer_id: int,
    slot_key: str,
    spool_id: int | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
):
    """Assign a spool to an AMS tray slot (or pass spool_id=null to unassign)."""
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")

    # Clear any spool currently in this slot (handle both prefixed and legacy bare format)
    full_key = f"{p.name}:{slot_key}"
    db.query(Spool).filter(
        (Spool.ams_slot == full_key) | (Spool.ams_slot == slot_key)
    ).update({"ams_slot": None})

    previous_slot: str | None = None
    if spool_id is not None:
        spool = db.get(Spool, spool_id)
        if not spool:
            raise HTTPException(404, "Spool not found")
        # If this spool is already assigned to a different slot, clear it and record the old slot
        if spool.ams_slot and spool.ams_slot != full_key:
            previous_slot = spool.ams_slot
        spool.ams_slot = full_key  # store as "PrinterName:ams1_tray2"

    db.commit()
    return {"ok": True, "previous_slot": previous_slot}


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[PrinterOut])
def list_printers(db: Session = Depends(get_db)):
    return db.query(PrinterConfig).all()


@router.post("", response_model=PrinterOut, status_code=201)
def create_printer(body: PrinterIn, db: Session = Depends(get_db)):
    from .. import bambu_cloud_client
    p = PrinterConfig(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    if p.bambu_serial:
        bambu_cloud_client.register_printer(p.id, p.bambu_serial)
        ha_client.clear_registry_cache(p.bambu_serial)
    return p


@router.get("/{printer_id}", response_model=PrinterOut)
def get_printer(printer_id: int, db: Session = Depends(get_db)):
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")
    return p


@router.patch("/{printer_id}", response_model=PrinterOut)
def update_printer(printer_id: int, body: PrinterIn, db: Session = Depends(get_db)):
    from .. import bambu_cloud_client
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    if p.bambu_serial:
        bambu_cloud_client.register_printer(p.id, p.bambu_serial)
        ha_client.clear_registry_cache(p.bambu_serial)
    return p


@router.delete("/{printer_id}", status_code=204)
def delete_printer(printer_id: int, db: Session = Depends(get_db)):
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")
    db.delete(p)
    db.commit()


@router.get("/{printer_id}/status")
async def get_printer_status(printer_id: int, db: Session = Depends(get_db)):
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")

    if getattr(p, "bambu_source", "ha") == "cloud":
        from .. import bambu_cloud_client
        raw = bambu_cloud_client.get_printer_cloud_status(p.bambu_serial)
        return {
            "print_stage":    raw.get("gcode_state"),
            "print_progress": str(raw["mc_percent"]) if raw.get("mc_percent") is not None else None,
            "remaining_time": str(raw["mc_remaining_time"]) if raw.get("mc_remaining_time") is not None else None,
            "nozzle_temp":    str(raw["nozzle_temper"]) if raw.get("nozzle_temper") is not None else None,
            "bed_temp":       str(raw["bed_temper"]) if raw.get("bed_temper") is not None else None,
            "current_file":   raw.get("subtask_name"),
        }

    entities = await ha_client.resolve_printer_entity_ids(
        p.device_slug, p.sensor_overrides, getattr(p, "bambu_serial", None)
    )
    result = {}
    for key, eid in entities.items():
        result[key] = await ha_client.get_entity_value(eid)
    return result
