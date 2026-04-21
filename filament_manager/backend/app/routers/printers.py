from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PrinterConfig, Spool
from ..schemas import SpoolOut

router = APIRouter(prefix="/api/printers", tags=["printers"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PrinterIn(BaseModel):
    name: str
    ams_unit_count: int = 1
    is_active: bool = True
    auto_deduct: bool = False
    bambu_serial: str | None = None
    bambu_source: str = "cloud"
    energy_sensor_entity_id: str | None = None
    price_sensor_entity_id: str | None = None


class PrinterOut(BaseModel):
    id: int
    name: str
    ams_unit_count: int
    is_active: bool
    auto_deduct: bool
    bambu_serial: str | None
    bambu_source: str
    energy_sensor_entity_id: str | None
    price_sensor_entity_id: str | None

    class Config:
        from_attributes = True


# ── AMS tray assignment ───────────────────────────────────────────────────────

@router.get("/{printer_id}/ams")
async def get_ams_trays(printer_id: int, db: Session = Depends(get_db)):
    """
    Returns AMS tray data from the Bambu Cloud MQTT cache plus the linked spool
    from inventory.  Slot keys use the format "ams{unit}_tray{slot}" (e.g. "ams1_tray2").
    """
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")
    if not p.bambu_serial:
        raise HTTPException(422, "Printer has no Bambu serial — cannot read AMS data")

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


@router.post("/{printer_id}/ams/sync")
async def sync_ams_weights(printer_id: int, db: Session = Depends(get_db)):
    """
    Read current remaining % from the Bambu Cloud MQTT cache and update each
    assigned spool's current_weight_g to match (initial_weight × remaining_pct / 100).
    """
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")
    if not p.bambu_serial:
        raise HTTPException(422, "Printer has no Bambu serial — cannot sync AMS data")

    from .. import bambu_cloud_client
    snapshot = bambu_cloud_client.get_ams_snapshot_for_serial(p.bambu_serial)
    updated = []
    for slot_key, remaining_pct in snapshot.items():
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


@router.post("/{printer_id}/ams/{slot_key}/sync")
async def sync_ams_tray_weight(printer_id: int, slot_key: str, db: Session = Depends(get_db)):
    """
    Read remaining % from the Bambu Cloud MQTT cache for a single AMS tray
    and update its linked spool.
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
    if not p.bambu_serial:
        raise HTTPException(422, "Printer has no Bambu serial — cannot sync AMS data")

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

    full_key = f"{p.name}:{slot_key}"
    db.query(Spool).filter(
        (Spool.ams_slot == full_key) | (Spool.ams_slot == slot_key)
    ).update({"ams_slot": None})

    previous_slot: str | None = None
    if spool_id is not None:
        spool = db.get(Spool, spool_id)
        if not spool:
            raise HTTPException(404, "Spool not found")
        if spool.ams_slot and spool.ams_slot != full_key:
            previous_slot = spool.ams_slot
        spool.ams_slot = full_key

    db.commit()
    from .. import ha_publisher
    ha_publisher.trigger()
    return {"ok": True, "previous_slot": previous_slot}


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[PrinterOut])
def list_printers(db: Session = Depends(get_db)):
    return db.query(PrinterConfig).all()


@router.post("", response_model=PrinterOut, status_code=201)
def create_printer(body: PrinterIn, db: Session = Depends(get_db)):
    from .. import bambu_cloud_client
    data = body.model_dump()
    data["bambu_source"] = "cloud"
    p = PrinterConfig(**data)
    db.add(p)
    db.commit()
    db.refresh(p)
    if p.bambu_serial:
        bambu_cloud_client.register_printer(p.id, p.bambu_serial)
    from .. import ha_publisher
    ha_publisher.trigger()
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
    data = body.model_dump(exclude_unset=True)
    data["bambu_source"] = "cloud"
    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    if p.bambu_serial:
        bambu_cloud_client.register_printer(p.id, p.bambu_serial)
    from .. import ha_publisher
    ha_publisher.trigger()
    return p


@router.delete("/{printer_id}", status_code=204)
def delete_printer(printer_id: int, db: Session = Depends(get_db)):
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")
    db.delete(p)
    db.commit()
    from .. import ha_publisher
    ha_publisher.trigger()


@router.get("/{printer_id}/status")
async def get_printer_status(printer_id: int, db: Session = Depends(get_db)):
    p = db.get(PrinterConfig, printer_id)
    if not p:
        raise HTTPException(404, "Printer not found")
    if not p.bambu_serial:
        return {k: None for k in ("print_stage", "print_progress", "remaining_time",
                                   "nozzle_temp", "bed_temp", "current_file",
                                   "print_weight", "ams_active", "active_tray")}

    from .. import bambu_cloud_client
    raw = bambu_cloud_client.get_printer_cloud_status(p.bambu_serial)
    active_tray = None
    tray_now = raw.get("tray_now")
    if tray_now is not None:
        try:
            idx = int(tray_now)
            active_tray = bambu_cloud_client._ams_index_to_slot_key(
                idx, bambu_cloud_client.get_ams_unit_tray_counts(p.bambu_serial)
            )
        except (ValueError, TypeError):
            pass
    return {
        "print_stage":    raw.get("gcode_state"),
        "print_progress": str(raw["mc_percent"]) if raw.get("mc_percent") is not None else None,
        "remaining_time": str(raw["mc_remaining_time"]) if raw.get("mc_remaining_time") is not None else None,
        "nozzle_temp":    str(raw["nozzle_temper"]) if raw.get("nozzle_temper") is not None else None,
        "bed_temp":       str(raw["bed_temper"]) if raw.get("bed_temper") is not None else None,
        "current_file":   raw.get("subtask_name"),
        "print_weight":   str(raw["gcode_file_weight"]) if raw.get("gcode_file_weight") is not None else None,
        "ams_active":     None,
        "active_tray":    active_tray,
    }
