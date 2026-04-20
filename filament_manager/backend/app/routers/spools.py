from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Spool, BrandSpoolWeight, FilamentSubtype, FilamentMaterial, SpoolAudit
from ..schemas import SpoolCreate, SpoolOut, SpoolUpdate, SpoolAuditEntry


def _resolve_spool_weight(brand: str | None, db: Session) -> float:
    """Look up tare weight from brand config. Returns 0 if not found."""
    if not brand:
        return 0.0
    entry = db.query(BrandSpoolWeight).filter(
        BrandSpoolWeight.brand.ilike(brand)
    ).first()
    return entry.spool_weight_g if entry else 0.0

router = APIRouter(prefix="/api/spools", tags=["spools"])


@router.get("", response_model=list[SpoolOut])
def list_spools(
    material: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Spool)
    if material:
        q = q.filter(Spool.material == material)
    return q.order_by(Spool.brand, Spool.material).all()


@router.post("", response_model=SpoolOut, status_code=201)
def create_spool(body: SpoolCreate, db: Session = Depends(get_db)):
    data = body.model_dump()
    data["spool_weight_g"] = _resolve_spool_weight(data.get("brand"), db)
    spool = Spool(**data)
    db.add(spool)
    db.commit()
    db.refresh(spool)
    return spool


@router.get("/{spool_id}", response_model=SpoolOut)
def get_spool(spool_id: int, db: Session = Depends(get_db)):
    spool = db.get(Spool, spool_id)
    if not spool:
        raise HTTPException(404, "Spool not found")
    return spool


@router.patch("/{spool_id}", response_model=SpoolOut)
def update_spool(spool_id: int, body: SpoolUpdate, db: Session = Depends(get_db)):
    spool = db.get(Spool, spool_id)
    if not spool:
        raise HTTPException(404, "Spool not found")
    updates = body.model_dump(exclude_unset=True)
    # Always re-resolve tare from brand config; ignore any client-supplied value
    brand = updates.get("brand", spool.brand)
    updates["spool_weight_g"] = _resolve_spool_weight(brand, db)
    weight_before = spool.current_weight_g
    for field, value in updates.items():
        setattr(spool, field, value)
    spool.updated_at = datetime.utcnow()
    if "current_weight_g" in updates:
        weight_after = spool.current_weight_g
        db.add(SpoolAudit(
            spool_id=spool.id,
            action="spool_edit",
            delta_g=weight_after - weight_before,
            weight_before=weight_before,
            weight_after=weight_after,
        ))
    db.commit()
    db.refresh(spool)
    from .. import ha_publisher
    ha_publisher.trigger()
    return spool


@router.get("/{spool_id}/audit", response_model=list[SpoolAuditEntry])
def get_spool_audit(spool_id: int, db: Session = Depends(get_db)):
    spool = db.get(Spool, spool_id)
    if not spool:
        raise HTTPException(404, "Spool not found")
    return (
        db.query(SpoolAudit)
        .filter(SpoolAudit.spool_id == spool_id)
        .order_by(SpoolAudit.changed_at.desc())
        .all()
    )


@router.post("/{spool_id}/audit/{entry_id}/correct", response_model=SpoolAuditEntry, status_code=201)
def correct_spool_audit(spool_id: int, entry_id: int, db: Session = Depends(get_db)):
    """Create a reversal correction entry for an audit row and update spool weight accordingly."""
    spool = db.get(Spool, spool_id)
    if not spool:
        raise HTTPException(404, "Spool not found")
    entry = (
        db.query(SpoolAudit)
        .filter(SpoolAudit.id == entry_id, SpoolAudit.spool_id == spool_id)
        .first()
    )
    if not entry:
        raise HTTPException(404, "Audit entry not found")

    weight_before = spool.current_weight_g
    correction_delta = -entry.delta_g
    spool.current_weight_g = max(0.0, min(spool.initial_weight_g, weight_before + correction_delta))
    spool.updated_at = datetime.utcnow()
    weight_after = spool.current_weight_g
    actual_delta = weight_after - weight_before

    correction = SpoolAudit(
        spool_id=spool_id,
        action="correction",
        delta_g=actual_delta,
        weight_before=weight_before,
        weight_after=weight_after,
        print_name=f"Correction: {entry.print_name or entry.action}",
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    return correction


@router.delete("/{spool_id}", status_code=204)
def delete_spool(spool_id: int, db: Session = Depends(get_db)):
    spool = db.get(Spool, spool_id)
    if not spool:
        raise HTTPException(404, "Spool not found")
    db.delete(spool)
    db.commit()
    from .. import ha_publisher
    ha_publisher.trigger()


@router.get("/materials/list")
def list_materials(db: Session = Depends(get_db)):
    rows = db.query(FilamentMaterial).order_by(FilamentMaterial.name).all()
    return [r.name for r in rows]


@router.get("/subtypes/list")
def list_subtypes(db: Session = Depends(get_db)):
    rows = db.query(FilamentSubtype).order_by(FilamentSubtype.name).all()
    return [r.name for r in rows]
