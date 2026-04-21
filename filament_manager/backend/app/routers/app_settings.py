from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BrandSpoolWeight, FilamentSubtype, FilamentMaterial, FilamentBrand, PurchaseLocation, StorageLocation, FilamentCatalog, UserPreferences
from ..schemas import BrandSpoolWeightOut, FilamentCatalogCreate, FilamentCatalogUpdate, FilamentCatalogOut

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


_CHANGELOG = Path("/CHANGELOG.md")

@router.get("/ha-sensor-value")
async def get_ha_sensor_value(entity_id: str):
    """Read the current numeric state of an HA sensor entity. Used to preview sensor values in the UI."""
    from ..ha_client import get_ha_state
    value = await get_ha_state(entity_id)
    return {"entity_id": entity_id, "value": value}


@router.get("/changelog")
def get_changelog():
    try:
        content = _CHANGELOG.read_text(encoding="utf-8")
    except Exception:
        content = ""
    return {"changelog": content}


_SUPPORTED_LANGS = {"en", "de", "es"}

@router.get("/ha-locale")
async def get_ha_locale(db: Session = Depends(get_db)):
    """Return language/timezone/currency/country — user overrides take precedence over HA values."""
    from ..ha_client import _headers
    import httpx, re

    prefs = db.get(UserPreferences, 1)
    tz_ov  = (prefs.timezone_override or "").strip() if prefs else ""
    cur_ov = (prefs.currency_override or "").strip() if prefs else ""
    cty_ov = (prefs.country_override  or "").strip() if prefs else ""

    lang = "en"
    time_zone = "UTC"
    country   = ""
    currency  = "EUR"

    # Only call HA if at least one value is not overridden
    if not (tz_ov and cur_ov):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://supervisor/core/api/config", headers=_headers())
                r.raise_for_status()
                data = r.json()
                lang_raw: str = data.get("language", "en")
                time_zone = data.get("time_zone", "UTC")
                country   = (data.get("country", "") or "").upper()
                currency  = (data.get("currency", "EUR") or "EUR").upper()
                code = re.match(r"[a-z]{2}", lang_raw.lower())
                lang = code.group() if code and code.group() in _SUPPORTED_LANGS else "en"
        except Exception:
            pass

    return {
        "language":  lang,
        "time_zone": tz_ov  or time_zone,
        "country":   cty_ov or country,
        "currency":  cur_ov or currency,
    }


# ── User Preferences (HA value overrides) ─────────────────────────────────────

class UserPrefsIn(BaseModel):
    timezone_override:       str | None = None
    currency_override:       str | None = None
    country_override:        str | None = None
    low_stock_threshold_pct: int | None = None


class UserPrefsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    timezone_override:       str | None
    currency_override:       str | None
    country_override:        str | None
    low_stock_threshold_pct: int


@router.get("/user-prefs", response_model=UserPrefsOut)
def get_user_prefs(db: Session = Depends(get_db)):
    prefs = db.get(UserPreferences, 1)
    if not prefs:
        return UserPrefsOut(
            timezone_override=None, currency_override=None,
            country_override=None, low_stock_threshold_pct=20,
        )
    return prefs


@router.post("/user-prefs", response_model=UserPrefsOut)
def save_user_prefs(body: UserPrefsIn, db: Session = Depends(get_db)):
    def _clean(v: str | None) -> str | None:
        return v.strip() or None if v is not None else None

    prefs = db.get(UserPreferences, 1)
    if not prefs:
        prefs = UserPreferences(id=1)
        db.add(prefs)
    prefs.timezone_override = _clean(body.timezone_override)
    prefs.currency_override = (_clean(body.currency_override) or "").upper() or None
    prefs.country_override  = (_clean(body.country_override)  or "").upper() or None
    if body.low_stock_threshold_pct is not None:
        pct = max(1, min(100, body.low_stock_threshold_pct))
        prefs.low_stock_threshold_pct = pct
    db.commit()
    db.refresh(prefs)
    from .. import ha_publisher
    ha_publisher.trigger()
    return prefs


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


# ── Storage Locations ─────────────────────────────────────────────────────────

@router.get("/storage-locations", response_model=list[SubtypeOut])
def list_storage_locations(db: Session = Depends(get_db)):
    return db.query(StorageLocation).order_by(StorageLocation.name).all()


@router.post("/storage-locations", response_model=SubtypeOut, status_code=201)
def create_storage_location(body: SubtypeIn, db: Session = Depends(get_db)):
    if db.query(StorageLocation).filter(StorageLocation.name == body.name.strip()).first():
        raise HTTPException(409, f"Storage location '{body.name}' already exists")
    entry = StorageLocation(name=body.name.strip())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/storage-locations/{entry_id}", response_model=SubtypeOut)
def update_storage_location(entry_id: int, body: SubtypeIn, db: Session = Depends(get_db)):
    entry = db.get(StorageLocation, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.name = body.name.strip()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/storage-locations/{entry_id}", status_code=204)
def delete_storage_location(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(StorageLocation, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()


# ── Filament Catalog ──────────────────────────────────────────────────────────

@router.get("/filament-catalog", response_model=list[FilamentCatalogOut])
def list_filament_catalog(db: Session = Depends(get_db)):
    return db.query(FilamentCatalog).order_by(FilamentCatalog.brand, FilamentCatalog.material, FilamentCatalog.color_name).all()


@router.post("/filament-catalog", response_model=FilamentCatalogOut, status_code=201)
def create_filament_catalog(body: FilamentCatalogCreate, db: Session = Depends(get_db)):
    entry = FilamentCatalog(**body.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/filament-catalog/{entry_id}", response_model=FilamentCatalogOut)
def update_filament_catalog(entry_id: int, body: FilamentCatalogUpdate, db: Session = Depends(get_db)):
    from ..models import Spool
    entry = db.get(FilamentCatalog, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    updates = body.model_dump(exclude_unset=True)
    propagate = updates.pop("propagate_to_spools", False)
    for field, value in updates.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    if propagate and entry.article_number:
        spool_fields = {k: updates[k] for k in ("brand", "material", "subtype", "subtype2", "color_name", "color_hex") if k in updates}
        if spool_fields:
            db.query(Spool).filter(Spool.article_number == entry.article_number).update(spool_fields)
            db.commit()
    return entry


@router.delete("/filament-catalog/{entry_id}", status_code=204)
def delete_filament_catalog(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(FilamentCatalog, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    db.delete(entry)
    db.commit()


class CatalogImportRow(BaseModel):
    brand: str
    material: str
    subtype: str | None = None
    subtype2: str | None = None
    color_name: str
    color_hex: str = "#888888"
    article_number: str | None = None


class CatalogImportBody(BaseModel):
    rows: list[CatalogImportRow]


@router.post("/filament-catalog/import")
def import_filament_catalog(body: CatalogImportBody, db: Session = Depends(get_db)):
    """Upsert filament catalog rows. Unique key: (brand, article_number).
    Rows without an article_number are always inserted as new entries."""
    added = 0
    updated = 0

    # Build lookup by (brand, article_number) for rows that have an article_number
    existing: dict[tuple[str, str], FilamentCatalog] = {
        (e.brand, e.article_number): e
        for e in db.query(FilamentCatalog).all()
        if e.article_number
    }

    for row in body.rows:
        key = (row.brand, row.article_number) if row.article_number else None
        if key and key in existing:
            entry = existing[key]
            entry.material = row.material
            entry.subtype = row.subtype or None
            entry.subtype2 = row.subtype2 or None
            entry.color_name = row.color_name
            entry.color_hex = row.color_hex
            entry.updated_at = datetime.utcnow()
            updated += 1
        else:
            new_entry = FilamentCatalog(
                brand=row.brand,
                material=row.material,
                subtype=row.subtype or None,
                subtype2=row.subtype2 or None,
                color_name=row.color_name,
                color_hex=row.color_hex,
                article_number=row.article_number or None,
            )
            db.add(new_entry)
            added += 1

    db.commit()
    return {"added": added, "updated": updated}
