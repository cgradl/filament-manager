from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BrandSpoolWeight, FilamentSubtype, FilamentMaterial, FilamentBrand, PurchaseLocation
from ..schemas import BrandSpoolWeightOut

router = APIRouter(prefix="/api/settings", tags=["settings"])

_CONFIG = Path("/config.yaml")

def _read_version() -> str:
    try:
        for line in _CONFIG.read_text().splitlines():
            if line.startswith("version:"):
                return line.split(":", 1)[1].strip().strip('"')
    except Exception:
        pass
    return "unknown"


@router.get("/version")
def get_version():
    return {"version": _read_version()}


_SUPPORTED_LANGS = {"en", "de", "es"}

@router.get("/ha-locale")
async def get_ha_locale():
    """Return the HA instance language and timezone."""
    from ..ha_client import _headers
    import httpx, re
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("http://supervisor/core/api/config", headers=_headers())
            r.raise_for_status()
            data = r.json()
            lang: str = data.get("language", "en")
            time_zone: str = data.get("time_zone", "UTC")
            code = re.match(r"[a-z]{2}", lang.lower())
            language = code.group() if code and code.group() in _SUPPORTED_LANGS else "en"
            return {"language": language, "time_zone": time_zone}
    except Exception:
        pass
    return {"language": "en", "time_zone": "UTC"}


class BrandWeightIn(BaseModel):
    brand: str
    spool_weight_g: float


@router.get("/brand-weights", response_model=list[BrandSpoolWeightOut])
def list_brand_weights(db: Session = Depends(get_db)):
    return db.query(BrandSpoolWeight).order_by(BrandSpoolWeight.brand).all()


@router.post("/brand-weights", response_model=BrandSpoolWeightOut, status_code=201)
def create_brand_weight(body: BrandWeightIn, db: Session = Depends(get_db)):
    existing = db.query(BrandSpoolWeight).filter(BrandSpoolWeight.brand == body.brand).first()
    if existing:
        raise HTTPException(409, f"Brand '{body.brand}' already configured")
    entry = BrandSpoolWeight(brand=body.brand, spool_weight_g=body.spool_weight_g)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/brand-weights/{entry_id}", response_model=BrandSpoolWeightOut)
def update_brand_weight(entry_id: int, body: BrandWeightIn, db: Session = Depends(get_db)):
    entry = db.get(BrandSpoolWeight, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.brand = body.brand
    entry.spool_weight_g = body.spool_weight_g
    entry.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/brand-weights/{entry_id}", status_code=204)
def delete_brand_weight(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(BrandSpoolWeight, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()


# ── Filament Subtypes ─────────────────────────────────────────────────────────

class SubtypeIn(BaseModel):
    name: str


class SubtypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


@router.get("/subtypes", response_model=list[SubtypeOut])
def list_subtypes(db: Session = Depends(get_db)):
    return db.query(FilamentSubtype).order_by(FilamentSubtype.name).all()


@router.post("/subtypes", response_model=SubtypeOut, status_code=201)
def create_subtype(body: SubtypeIn, db: Session = Depends(get_db)):
    existing = db.query(FilamentSubtype).filter(FilamentSubtype.name == body.name.strip()).first()
    if existing:
        raise HTTPException(409, f"Subtype '{body.name}' already exists")
    entry = FilamentSubtype(name=body.name.strip())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/subtypes/{entry_id}", response_model=SubtypeOut)
def update_subtype(entry_id: int, body: SubtypeIn, db: Session = Depends(get_db)):
    entry = db.get(FilamentSubtype, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.name = body.name.strip()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/subtypes/{entry_id}", status_code=204)
def delete_subtype(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(FilamentSubtype, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()


# ── Filament Materials ────────────────────────────────────────────────────────

@router.get("/materials", response_model=list[SubtypeOut])
def list_materials(db: Session = Depends(get_db)):
    return db.query(FilamentMaterial).order_by(FilamentMaterial.name).all()


@router.post("/materials", response_model=SubtypeOut, status_code=201)
def create_material(body: SubtypeIn, db: Session = Depends(get_db)):
    if db.query(FilamentMaterial).filter(FilamentMaterial.name == body.name.strip()).first():
        raise HTTPException(409, f"Material '{body.name}' already exists")
    entry = FilamentMaterial(name=body.name.strip())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/materials/{entry_id}", response_model=SubtypeOut)
def update_material(entry_id: int, body: SubtypeIn, db: Session = Depends(get_db)):
    entry = db.get(FilamentMaterial, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.name = body.name.strip()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/materials/{entry_id}", status_code=204)
def delete_material(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(FilamentMaterial, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()


# ── Filament Brands ───────────────────────────────────────────────────────────

@router.get("/brands", response_model=list[SubtypeOut])
def list_brands(db: Session = Depends(get_db)):
    return db.query(FilamentBrand).order_by(FilamentBrand.name).all()


@router.post("/brands", response_model=SubtypeOut, status_code=201)
def create_brand(body: SubtypeIn, db: Session = Depends(get_db)):
    if db.query(FilamentBrand).filter(FilamentBrand.name == body.name.strip()).first():
        raise HTTPException(409, f"Brand '{body.name}' already exists")
    entry = FilamentBrand(name=body.name.strip())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/brands/{entry_id}", response_model=SubtypeOut)
def update_brand(entry_id: int, body: SubtypeIn, db: Session = Depends(get_db)):
    entry = db.get(FilamentBrand, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.name = body.name.strip()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/brands/{entry_id}", status_code=204)
def delete_brand(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(FilamentBrand, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()


# ── Purchase Locations ────────────────────────────────────────────────────────

@router.get("/purchase-locations", response_model=list[SubtypeOut])
def list_purchase_locations(db: Session = Depends(get_db)):
    return db.query(PurchaseLocation).order_by(PurchaseLocation.name).all()


@router.post("/purchase-locations", response_model=SubtypeOut, status_code=201)
def create_purchase_location(body: SubtypeIn, db: Session = Depends(get_db)):
    if db.query(PurchaseLocation).filter(PurchaseLocation.name == body.name.strip()).first():
        raise HTTPException(409, f"Location '{body.name}' already exists")
    entry = PurchaseLocation(name=body.name.strip())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/purchase-locations/{entry_id}", response_model=SubtypeOut)
def update_purchase_location(entry_id: int, body: SubtypeIn, db: Session = Depends(get_db)):
    entry = db.get(PurchaseLocation, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.name = body.name.strip()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/purchase-locations/{entry_id}", status_code=204)
def delete_purchase_location(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(PurchaseLocation, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()
