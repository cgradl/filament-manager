"""
Export / Import all application data as a single JSON bundle.

Export:  GET  /api/data/export
Import:  POST /api/data/import

The bundle format is versioned so future schema changes can be handled gracefully.
On import, existing records are never deleted — data is merged additively.
Spool IDs in print_usages are remapped from the source database to the target database.
"""

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Spool, PrintJob, PrintUsage,
    BrandSpoolWeight, FilamentMaterial, FilamentSubtype, FilamentBrand,
    PurchaseLocation, StorageLocation, PrinterConfig, FilamentCatalog, UserPreferences, MATERIAL_DENSITY,
)

router = APIRouter(prefix="/api/data", tags=["data-transfer"])

EXPORT_VERSION = 1


# ── helpers ───────────────────────────────────────────────────────────────────

def _dt(v) -> str | None:
    return v.isoformat() if v else None

def _spool_dict(s: Spool) -> dict:
    return {
        "id": s.id,
        "custom_id": s.custom_id,
        "brand": s.brand,
        "material": s.material,
        "subtype": s.subtype,
        "subtype2": s.subtype2,
        "color_name": s.color_name,
        "color_hex": s.color_hex,
        "diameter_mm": s.diameter_mm,
        "initial_weight_g": s.initial_weight_g,
        "current_weight_g": s.current_weight_g,
        "spool_weight_g": s.spool_weight_g,
        "purchase_price": s.purchase_price,
        "purchased_at": _dt(s.purchased_at),
        "purchase_location": s.purchase_location,
        "article_number": s.article_number,
        "storage_location": s.storage_location,
        "ams_slot": s.ams_slot,
        "notes": s.notes,
        "created_at": _dt(s.created_at),
    }

def _usage_dict(u: PrintUsage) -> dict:
    return {
        "spool_id": u.spool_id,
        "grams_used": u.grams_used,
        "meters_used": u.meters_used,
        "ams_slot": u.ams_slot,
    }

def _job_dict(j: PrintJob) -> dict:
    return {
        "id": j.id,
        "name": j.name,
        "model_name": j.model_name,
        "description": j.description,
        "started_at": _dt(j.started_at),
        "finished_at": _dt(j.finished_at),
        "duration_seconds": j.duration_seconds,
        "success": j.success,
        "notes": j.notes,
        "printer_name": j.printer_name,
        "source": j.source,
        "ams_snapshot_start": j.ams_snapshot_start,
        "task_id": j.task_id,
        "project_id": j.project_id,
        "total_layer_num": j.total_layer_num,
        "layer_num": j.layer_num,
        "nozzle_diameter": j.nozzle_diameter,
        "nozzle_type": j.nozzle_type,
        "print_type": j.print_type,
        "error_code": j.error_code,
        "print_weight_g": j.print_weight_g,
        "suggested_usages": j.suggested_usages,
        "created_at": _dt(j.created_at),
        "usages": [_usage_dict(u) for u in j.usages],
    }


# ── export ────────────────────────────────────────────────────────────────────

@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    spools          = db.query(Spool).order_by(Spool.id).all()
    jobs            = db.query(PrintJob).order_by(PrintJob.id).all()
    printers        = db.query(PrinterConfig).order_by(PrinterConfig.id).all()
    bw              = db.query(BrandSpoolWeight).order_by(BrandSpoolWeight.brand).all()
    materials       = db.query(FilamentMaterial).order_by(FilamentMaterial.name).all()
    subtypes        = db.query(FilamentSubtype).order_by(FilamentSubtype.name).all()
    brands          = db.query(FilamentBrand).order_by(FilamentBrand.name).all()
    locations       = db.query(PurchaseLocation).order_by(PurchaseLocation.name).all()
    storage_locs    = db.query(StorageLocation).order_by(StorageLocation.name).all()
    catalog         = db.query(FilamentCatalog).order_by(FilamentCatalog.brand, FilamentCatalog.material, FilamentCatalog.color_name).all()
    user_prefs      = db.get(UserPreferences, 1)

    bundle = {
        "version": EXPORT_VERSION,
        "exported_at": datetime.utcnow().isoformat(),
        "spools": [_spool_dict(s) for s in spools],
        "print_jobs": [_job_dict(j) for j in jobs],
        "printer_configs": [
            {
                "name": p.name,
                "bambu_serial": p.bambu_serial,
                "bambu_source": p.bambu_source,
                "ams_unit_count": p.ams_unit_count,
                "is_active": p.is_active,
                "auto_deduct": p.auto_deduct,
            }
            for p in printers
        ],
        "user_preferences": {
            "timezone_override": user_prefs.timezone_override if user_prefs else None,
            "currency_override": user_prefs.currency_override if user_prefs else None,
            "country_override":  user_prefs.country_override  if user_prefs else None,
        },
        "settings": {
            "brand_weights":      [{"brand": b.brand, "spool_weight_g": b.spool_weight_g} for b in bw],
            "materials":          [m.name for m in materials],
            "subtypes":           [s.name for s in subtypes],
            "brands":             [b.name for b in brands],
            "purchase_locations": [l.name for l in locations],
            "storage_locations":  [l.name for l in storage_locs],
            "filament_catalog":   [
                {
                    "brand": e.brand,
                    "material": e.material,
                    "subtype": e.subtype,
                    "subtype2": e.subtype2,
                    "color_name": e.color_name,
                    "color_hex": e.color_hex,
                    "article_number": e.article_number,
                }
                for e in catalog
            ],
        },
    }

    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": 'attachment; filename="filament_manager_export.json"'},
    )


# ── Spool CSV export ──────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "id", "custom_id", "brand", "material", "subtype", "subtype2",
    "color_name", "color_hex", "diameter_mm",
    "initial_weight_g", "current_weight_g", "spool_weight_g", "remaining_pct",
    "purchase_price", "price_per_kg",
    "purchased_at", "purchase_location", "storage_location",
    "article_number", "ams_slot", "notes",
]

@router.get("/export-spools-csv")
def export_spools_csv(db: Session = Depends(get_db)):
    spools = db.query(Spool).order_by(Spool.brand, Spool.material, Spool.color_name).all()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for s in spools:
        writer.writerow({
            "id":               s.id,
            "custom_id":        s.custom_id or "",
            "brand":            s.brand,
            "material":         s.material,
            "subtype":          s.subtype or "",
            "subtype2":         s.subtype2 or "",
            "color_name":       s.color_name,
            "color_hex":        s.color_hex,
            "diameter_mm":      s.diameter_mm or "",
            "initial_weight_g": s.initial_weight_g,
            "current_weight_g": s.current_weight_g,
            "spool_weight_g":   s.spool_weight_g or "",
            "remaining_pct":    s.remaining_pct,
            "purchase_price":   s.purchase_price or "",
            "price_per_kg":     s.price_per_kg or "",
            "purchased_at":     _dt(s.purchased_at) or "",
            "purchase_location": s.purchase_location or "",
            "storage_location": s.storage_location or "",
            "article_number":   s.article_number or "",
            "ams_slot":         s.ams_slot or "",
            "notes":            s.notes or "",
        })
    filename = f"spools_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Spoolman export ───────────────────────────────────────────────────────────

@router.get("/export-spoolman")
def export_spoolman(db: Session = Depends(get_db)):
    """
    Export spool inventory in Spoolman's native GET-response shape.

    Each spool contains a fully-embedded filament object (which itself contains
    a fully-embedded vendor object), mirroring what GET /api/v1/spool returns
    so that standard Spoolman import tools can parse brand, material and color.
    """
    now_iso = datetime.utcnow().isoformat()
    spools = db.query(Spool).order_by(Spool.id).all()

    # ── pass 1: build deduplicated vendor + filament objects ──────────────────
    vendor_name_to_id: dict[str, int] = {}
    vendor_objs: dict[int, dict] = {}

    filament_key_to_id: dict[tuple, int] = {}
    filament_objs: dict[int, dict] = {}

    for spool in spools:
        # Vendor (brand)
        brand = spool.brand or "Unknown"
        if brand not in vendor_name_to_id:
            vid = len(vendor_name_to_id) + 1
            vendor_name_to_id[brand] = vid
            vendor_objs[vid] = {
                "id": vid,
                "registered": now_iso,
                "name": brand,
                "comment": None,
                "empty_spool_weight": spool.spool_weight_g or None,
                "external_id": None,
                "extra": {},
            }
        vid = vendor_name_to_id[brand]

        # Filament type — deduplicate by (brand, material, color_hex, diameter)
        color_hex = (spool.color_hex or "#888888").lstrip("#").upper()
        mat = spool.material or "PLA"
        dia = spool.diameter_mm or 1.75
        key = (brand, mat, color_hex, dia)
        if key not in filament_key_to_id:
            fid = len(filament_key_to_id) + 1
            filament_key_to_id[key] = fid
            density = MATERIAL_DENSITY.get(mat, 1.24)
            price_per_kg: float | None = None
            if spool.purchase_price and spool.initial_weight_g:
                price_per_kg = round(spool.purchase_price / (spool.initial_weight_g / 1000), 2)
            subtype_comment = " / ".join(filter(None, [spool.subtype, spool.subtype2])) or None
            filament_objs[fid] = {
                "id": fid,
                "registered": now_iso,
                "name": spool.color_name or mat,
                "vendor": vendor_objs[vid],
                "material": mat,
                "color_hex": color_hex,
                "weight": spool.initial_weight_g,
                "spool_weight": spool.spool_weight_g or None,
                "price": price_per_kg,
                "density": density,
                "diameter": dia,
                "comment": subtype_comment,
                "settings_extruder_temp": None,
                "settings_bed_temp": None,
                "article_number": None,
                "external_id": None,
                "extra": {},
            }

    # ── pass 2: build spool objects with embedded filament ────────────────────
    spoolman_spools: list[dict] = []
    for spool in spools:
        color_hex = (spool.color_hex or "#888888").lstrip("#").upper()
        mat = spool.material or "PLA"
        key = (spool.brand or "Unknown", mat, color_hex, spool.diameter_mm or 1.75)
        fid = filament_key_to_id[key]

        remaining = round(spool.current_weight_g or 0, 2)
        used = round(max(0.0, (spool.initial_weight_g or 0) - (spool.current_weight_g or 0)), 2)

        comment_parts = list(filter(None, [
            spool.notes,
            f"Bought at: {spool.purchase_location}" if spool.purchase_location else None,
        ]))

        spoolman_spools.append({
            "id": spool.id,
            "registered": _dt(spool.created_at) or now_iso,
            "first_used": None,
            "last_used": None,
            "filament": filament_objs[fid],
            "initial_weight": spool.initial_weight_g,
            "spool_weight": spool.spool_weight_g or None,
            "remaining_weight": remaining,
            "used_weight": used,
            "archived": remaining <= 0,
            "location": None,
            "lot_nr": None,
            "comment": " | ".join(comment_parts) or None,
            "extra": {},
        })

    bundle = {
        "spoolman_export": True,
        "created": now_iso,
        "filaments": list(filament_objs.values()),
        "spools": spoolman_spools,
    }

    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": 'attachment; filename="spoolman_export.json"'},
    )


# ── Spool CSV import ──────────────────────────────────────────────────────────

def _parse_float(v: str) -> float | None:
    try:
        return float(v) if v.strip() else None
    except ValueError:
        return None

def _parse_date(v: str):
    from datetime import date
    try:
        return date.fromisoformat(v.strip()[:10]) if v.strip() else None
    except ValueError:
        return None

@router.post("/import-spools-csv")
async def import_spools_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    text = content.decode("utf-8-sig")  # strips BOM if present
    reader = csv.DictReader(io.StringIO(text))

    # Columns we write back (skip computed remaining_pct, price_per_kg)
    WRITABLE = {
        "custom_id", "brand", "material", "subtype", "subtype2",
        "color_name", "color_hex", "diameter_mm",
        "initial_weight_g", "current_weight_g", "spool_weight_g",
        "purchase_price", "purchased_at", "purchase_location",
        "storage_location", "article_number", "ams_slot", "notes",
    }
    FLOAT_COLS = {"diameter_mm", "initial_weight_g", "current_weight_g", "spool_weight_g", "purchase_price"}
    INT_COLS: set[str] = set()

    created = updated = skipped = 0

    for row in reader:
        brand = (row.get("brand") or "").strip()
        material = (row.get("material") or "").strip()
        color_name = (row.get("color_name") or "").strip()
        color_hex = (row.get("color_hex") or "").strip()
        if not brand or not material or not color_name or not color_hex:
            skipped += 1
            continue

        # Build field dict
        fields: dict = {}
        for col in WRITABLE:
            raw = (row.get(col) or "").strip()
            if col in FLOAT_COLS:
                fields[col] = _parse_float(raw)
            elif col == "purchased_at":
                fields[col] = _parse_date(raw)
            else:
                fields[col] = raw or None

        # Upsert: update if id matches an existing spool, else create
        raw_id = (row.get("id") or "").strip()
        existing = None
        if raw_id:
            try:
                existing = db.get(Spool, int(raw_id))
            except (ValueError, TypeError):
                pass

        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Spool(**fields))
            created += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


# ── import ────────────────────────────────────────────────────────────────────

class ImportBundle(BaseModel):
    version: int
    spools: list[dict[str, Any]] = []
    print_jobs: list[dict[str, Any]] = []
    printer_configs: list[dict[str, Any]] = []
    settings: dict[str, Any] = {}
    user_preferences: dict[str, Any] = {}


@router.post("/import")
def import_data(bundle: ImportBundle, db: Session = Depends(get_db)):
    if bundle.version != EXPORT_VERSION:
        raise HTTPException(400, f"Unsupported export version {bundle.version} (expected {EXPORT_VERSION})")

    stats: dict[str, int] = {
        "spools": 0,
        "print_jobs": 0,
        "print_usages": 0,
        "printer_configs": 0,
        "materials": 0,
        "subtypes": 0,
        "brands": 0,
        "purchase_locations": 0,
        "storage_locations": 0,
        "brand_weights": 0,
        "filament_catalog": 0,
    }

    # ── settings lists (skip duplicates by name) ──────────────────────────────
    s = bundle.settings

    existing_mats = {r.name for r in db.query(FilamentMaterial).all()}
    for name in s.get("materials", []):
        if name and name not in existing_mats:
            db.add(FilamentMaterial(name=name))
            stats["materials"] += 1

    existing_sub = {r.name for r in db.query(FilamentSubtype).all()}
    for name in s.get("subtypes", []):
        if name and name not in existing_sub:
            db.add(FilamentSubtype(name=name))
            stats["subtypes"] += 1

    existing_br = {r.name for r in db.query(FilamentBrand).all()}
    for name in s.get("brands", []):
        if name and name not in existing_br:
            db.add(FilamentBrand(name=name))
            stats["brands"] += 1

    existing_loc = {r.name for r in db.query(PurchaseLocation).all()}
    for name in s.get("purchase_locations", []):
        if name and name not in existing_loc:
            db.add(PurchaseLocation(name=name))
            stats["purchase_locations"] += 1

    existing_sloc = {r.name for r in db.query(StorageLocation).all()}
    for name in s.get("storage_locations", []):
        if name and name not in existing_sloc:
            db.add(StorageLocation(name=name))
            stats["storage_locations"] += 1

    existing_bw = {r.brand for r in db.query(BrandSpoolWeight).all()}
    for bw in s.get("brand_weights", []):
        if bw.get("brand") and bw["brand"] not in existing_bw:
            db.add(BrandSpoolWeight(brand=bw["brand"], spool_weight_g=bw["spool_weight_g"]))
            stats["brand_weights"] += 1

    # deduplicate filament catalog by article_number when present, else by (brand, material, color_name)
    existing_catalog_by_article = {
        r.article_number for r in db.query(FilamentCatalog).all() if r.article_number
    }
    existing_catalog_by_key = {
        (r.brand, r.material, r.color_name) for r in db.query(FilamentCatalog).all()
    }
    for entry in s.get("filament_catalog", []):
        article = entry.get("article_number")
        key = (entry.get("brand", ""), entry.get("material", ""), entry.get("color_name", ""))
        if article and article in existing_catalog_by_article:
            continue
        if not article and key in existing_catalog_by_key:
            continue
        db.add(FilamentCatalog(
            brand=entry.get("brand", ""),
            material=entry.get("material", ""),
            subtype=entry.get("subtype"),
            subtype2=entry.get("subtype2"),
            color_name=entry.get("color_name", ""),
            color_hex=entry.get("color_hex", "#888888"),
            article_number=article,
        ))
        if article:
            existing_catalog_by_article.add(article)
        else:
            existing_catalog_by_key.add(key)
        stats["filament_catalog"] += 1

    # ── user preferences (only restore non-null overrides from bundle) ──────────
    up = bundle.user_preferences
    if up:
        prefs = db.get(UserPreferences, 1)
        if not prefs:
            prefs = UserPreferences(id=1)
            db.add(prefs)
        if up.get("timezone_override"):
            prefs.timezone_override = up["timezone_override"]
        if up.get("currency_override"):
            prefs.currency_override = up["currency_override"]
        if up.get("country_override"):
            prefs.country_override = up["country_override"]

    db.flush()

    # ── printer configs (skip if same bambu_serial already exists) ───────────
    existing_serials = {r.bambu_serial for r in db.query(PrinterConfig).all() if r.bambu_serial}
    for p in bundle.printer_configs:
        serial = p.get("bambu_serial")
        if serial and serial in existing_serials:
            continue
        db.add(PrinterConfig(
            name=p.get("name", serial or "Imported printer"),
            bambu_serial=serial,
            bambu_source=p.get("bambu_source", "cloud"),
            ams_unit_count=p.get("ams_unit_count", 1),
            is_active=p.get("is_active", True),
            auto_deduct=p.get("auto_deduct", False),
        ))
        if serial:
            existing_serials.add(serial)
        stats["printer_configs"] += 1

    db.flush()

    # ── spools: import all, build old_id → new_id map ─────────────────────────
    spool_id_map: dict[int, int] = {}
    for sp in bundle.spools:
        old_id = sp.get("id")
        new_spool = Spool(
            custom_id=sp.get("custom_id"),
            brand=sp.get("brand", "Unknown"),
            material=sp.get("material", "PLA"),
            subtype=sp.get("subtype"),
            subtype2=sp.get("subtype2"),
            color_name=sp.get("color_name", ""),
            color_hex=sp.get("color_hex", "#888888"),
            diameter_mm=sp.get("diameter_mm", 1.75),
            initial_weight_g=sp.get("initial_weight_g", 1000),
            current_weight_g=sp.get("current_weight_g", 0),
            spool_weight_g=sp.get("spool_weight_g", 0),
            purchase_price=sp.get("purchase_price"),
            purchased_at=_parse_dt(sp.get("purchased_at")),
            article_number=sp.get("article_number"),
            purchase_location=sp.get("purchase_location"),
            storage_location=sp.get("storage_location"),
            ams_slot=sp.get("ams_slot"),
            notes=sp.get("notes"),
            created_at=_parse_dt(sp.get("created_at")) or datetime.utcnow(),
        )
        db.add(new_spool)
        db.flush()
        if old_id is not None:
            spool_id_map[old_id] = new_spool.id
        stats["spools"] += 1

    # ── print jobs + usages: remap spool IDs ──────────────────────────────────
    for job_data in bundle.print_jobs:
        job = PrintJob(
            name=job_data.get("name", "Imported print"),
            model_name=job_data.get("model_name"),
            description=job_data.get("description"),
            started_at=_parse_dt(job_data.get("started_at")) or datetime.utcnow(),
            finished_at=_parse_dt(job_data.get("finished_at")),
            duration_seconds=job_data.get("duration_seconds"),
            success=job_data.get("success", True),
            notes=job_data.get("notes"),
            printer_name=job_data.get("printer_name"),
            source=job_data.get("source", "imported"),
            ams_snapshot_start=job_data.get("ams_snapshot_start") or {},
            task_id=job_data.get("task_id"),
            project_id=job_data.get("project_id"),
            total_layer_num=job_data.get("total_layer_num"),
            layer_num=job_data.get("layer_num"),
            nozzle_diameter=job_data.get("nozzle_diameter"),
            nozzle_type=job_data.get("nozzle_type"),
            print_type=job_data.get("print_type"),
            error_code=job_data.get("error_code"),
            print_weight_g=job_data.get("print_weight_g"),
            suggested_usages=job_data.get("suggested_usages"),
            created_at=_parse_dt(job_data.get("created_at")) or datetime.utcnow(),
        )
        db.add(job)
        db.flush()
        stats["print_jobs"] += 1

        for u in job_data.get("usages", []):
            old_spool_id = u.get("spool_id")
            if old_spool_id is not None:
                new_spool_id = spool_id_map.get(old_spool_id)
                if new_spool_id is None:
                    # spool referenced but not in this import — skip usage rather than fail
                    continue
            else:
                # null spool_id = cloud-imported print with unassigned usage; preserve as-is
                new_spool_id = None
            db.add(PrintUsage(
                print_job_id=job.id,
                spool_id=new_spool_id,
                grams_used=u.get("grams_used", 0),
                meters_used=u.get("meters_used"),
                ams_slot=u.get("ams_slot"),
            ))
            stats["print_usages"] += 1

    db.commit()
    return {"ok": True, "imported": stats}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
