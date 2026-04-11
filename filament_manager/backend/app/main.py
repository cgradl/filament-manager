import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import engine, Base
from .routers import spools, prints, printers, dashboard, app_settings, data_transfer, bambu_cloud
from . import print_monitor, bambu_cloud_client

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Incremental migrations
    with engine.connect() as conn:
        from sqlalchemy import text, inspect
        insp = inspect(engine)

        # print_jobs: add model_name if missing
        job_cols = [c["name"] for c in insp.get_columns("print_jobs")]
        if "model_name" not in job_cols:
            conn.execute(text("ALTER TABLE print_jobs ADD COLUMN model_name TEXT"))
            conn.commit()
            log.info("Migration: added print_jobs.model_name")

        # print_jobs: Bambu Cloud enrichment fields
        for _col in ("task_id", "project_id", "nozzle_diameter", "nozzle_type",
                     "print_type", "error_code"):
            if _col not in job_cols:
                conn.execute(text(f"ALTER TABLE print_jobs ADD COLUMN {_col} TEXT"))
                conn.commit()
                log.info("Migration: added print_jobs.%s", _col)
        for _col in ("total_layer_num", "layer_num"):
            if _col not in job_cols:
                conn.execute(text(f"ALTER TABLE print_jobs ADD COLUMN {_col} INTEGER"))
                conn.commit()
                log.info("Migration: added print_jobs.%s", _col)

        # spools: add custom_id if missing
        spool_cols = [c["name"] for c in insp.get_columns("spools")]
        if "custom_id" not in spool_cols:
            conn.execute(text("ALTER TABLE spools ADD COLUMN custom_id INTEGER"))
            conn.commit()
            log.info("Migration: added spools.custom_id")

        # spools: add purchase_location if missing
        if "purchase_location" not in spool_cols:
            conn.execute(text("ALTER TABLE spools ADD COLUMN purchase_location TEXT"))
            conn.commit()
            log.info("Migration: added spools.purchase_location")

        # spools: add subtype2 if missing
        if "subtype2" not in spool_cols:
            conn.execute(text("ALTER TABLE spools ADD COLUMN subtype2 TEXT"))
            conn.commit()
            log.info("Migration: added spools.subtype2")

        # spools: add storage_location if missing
        if "storage_location" not in spool_cols:
            conn.execute(text("ALTER TABLE spools ADD COLUMN storage_location TEXT"))
            conn.commit()
            log.info("Migration: added spools.storage_location")

        # spools: add article_number if missing
        if "article_number" not in spool_cols:
            conn.execute(text("ALTER TABLE spools ADD COLUMN article_number TEXT"))
            conn.commit()
            log.info("Migration: added spools.article_number")

        # printer_configs: rebuild if it still has the old entity-per-column schema
        printer_cols = [c["name"] for c in insp.get_columns("printer_configs")]
        if "device_slug" not in printer_cols:
            conn.execute(text("DROP TABLE IF EXISTS printer_configs"))
            conn.commit()
            Base.metadata.tables["printer_configs"].create(bind=engine)
            log.info("Migration: rebuilt printer_configs with simplified schema")
        elif "ams_device_slug" not in printer_cols:
            conn.execute(text("ALTER TABLE printer_configs ADD COLUMN ams_device_slug TEXT"))
            conn.commit()
            log.info("Migration: added printer_configs.ams_device_slug")

        # printer_configs: add bambu_serial if missing
        if "bambu_serial" not in printer_cols:
            conn.execute(text("ALTER TABLE printer_configs ADD COLUMN bambu_serial TEXT"))
            conn.commit()
            log.info("Migration: added printer_configs.bambu_serial")

        # printer_configs: add bambu_source if missing
        if "bambu_source" not in printer_cols:
            conn.execute(text(
                "ALTER TABLE printer_configs ADD COLUMN bambu_source TEXT NOT NULL DEFAULT 'ha'"
            ))
            conn.commit()
            log.info("Migration: added printer_configs.bambu_source")

        # printer_configs: add per-printer sensor entity ID overrides
        for _col in ("sensor_print_stage", "sensor_print_progress", "sensor_remaining_time",
                     "sensor_nozzle_temp", "sensor_bed_temp", "sensor_current_file",
                     "sensor_print_weight", "sensor_active_tray", "sensor_ams_active",
                     "ams_tray_pattern"):
            if _col not in printer_cols:
                conn.execute(text(f"ALTER TABLE printer_configs ADD COLUMN {_col} TEXT"))
                conn.commit()
                log.info("Migration: added printer_configs.%s", _col)

        # printer_configs: add auto_deduct flag
        if "auto_deduct" not in printer_cols:
            conn.execute(text(
                "ALTER TABLE printer_configs ADD COLUMN auto_deduct INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
            log.info("Migration: added printer_configs.auto_deduct")

        # print_jobs: add print_weight_g if missing
        if "print_weight_g" not in job_cols:
            conn.execute(text("ALTER TABLE print_jobs ADD COLUMN print_weight_g REAL"))
            conn.commit()
            log.info("Migration: added print_jobs.print_weight_g")

        # print_jobs: add suggested_usages if missing
        if "suggested_usages" not in job_cols:
            conn.execute(text("ALTER TABLE print_jobs ADD COLUMN suggested_usages TEXT"))
            conn.commit()
            log.info("Migration: added print_jobs.suggested_usages")

        # print_usages: make spool_id nullable (SQLite can't ALTER COLUMN — rebuild table)
        usage_cols_info = insp.get_columns("print_usages")
        spool_id_info = next((c for c in usage_cols_info if c["name"] == "spool_id"), None)
        if spool_id_info and spool_id_info.get("nullable") is False:
            conn.execute(text("""
                CREATE TABLE print_usages_new (
                    id INTEGER PRIMARY KEY,
                    print_job_id INTEGER NOT NULL REFERENCES print_jobs(id),
                    spool_id INTEGER REFERENCES spools(id),
                    grams_used REAL NOT NULL,
                    meters_used REAL,
                    ams_slot TEXT,
                    created_at DATETIME
                )
            """))
            conn.execute(text(
                "INSERT INTO print_usages_new "
                "SELECT id, print_job_id, spool_id, grams_used, meters_used, ams_slot, created_at "
                "FROM print_usages"
            ))
            conn.execute(text("DROP TABLE print_usages"))
            conn.execute(text("ALTER TABLE print_usages_new RENAME TO print_usages"))
            conn.commit()
            log.info("Migration: rebuilt print_usages with nullable spool_id")

        # spools: if current_weight_g is 0 for ALL spools and initial_weight_g exists,
        # recover from is_active flag (legacy) — set current = initial for active spools
        if "is_active" in spool_cols:
            total = conn.execute(text("SELECT COUNT(*) FROM spools")).scalar() or 0
            zero_weight = conn.execute(
                text("SELECT COUNT(*) FROM spools WHERE current_weight_g = 0 OR current_weight_g IS NULL")
            ).scalar() or 0
            if total > 0 and zero_weight == total:
                result = conn.execute(text(
                    "UPDATE spools SET current_weight_g = initial_weight_g "
                    "WHERE is_active = 1 AND initial_weight_g > 0"
                ))
                conn.commit()
                log.info("Migration: recovered current_weight_g from initial_weight_g for %d active spools", result.rowcount)

        # spools: rename German color names to English
        _COLOR_RENAMES = {
            "Schwarz": "Black", "Weiß": "White", "Grau": "Gray",
            "Space Grau": "Space Gray", "Aschgrau": "Ash Gray",
            "Rot": "Red", "Olivengruen": "Olive Green", "Kaffee Braun": "Coffee Brown",
            "Durchsichtiges Hellblau": "Transparent Light Blue", "Klar": "Clear",
            "Leuchtend-Orange": "Luminous Orange", "Weißer Marmor": "White Marble",
            "Metallisches Kobaltblau": "Metallic Cobalt Blue", "Schwarze Walnuss": "Black Walnut",
            "Jade-Weiß": "Jade White", "Silber": "Silver", "Kupfer": "Copper",
        }
        for de, en in _COLOR_RENAMES.items():
            result = conn.execute(
                text("UPDATE spools SET color_name = :en WHERE color_name = :de"),
                {"en": en, "de": de}
            )
            if result.rowcount:
                log.info("Migration: renamed color '%s' → '%s' (%d rows)", de, en, result.rowcount)
        conn.commit()

    log.info("Database ready")

    # Seed default filament materials if table is empty
    _DEFAULT_MATERIALS = [
        "ABS", "ASA", "ASA-CF", "HIPS", "PA", "PA-CF", "PC",
        "PET", "PETG", "PETG-CF", "PLA", "PLA+", "PLA-CF", "PLA Silk",
        "PVA", "TPU", "Other",
    ]
    with engine.connect() as conn:
        from .models import FilamentMaterial as _FMT
        from sqlalchemy.orm import Session as _Session0
        with _Session0(engine) as s:
            existing_mats = {r.name for r in s.query(_FMT).all()}
            added_mt = [n for n in _DEFAULT_MATERIALS if n not in existing_mats]
            for name in added_mt:
                s.add(_FMT(name=name))
            if added_mt:
                s.commit()
                log.info("Seeded filament materials: %s", added_mt)

    # Seed default purchase locations if table is empty
    _DEFAULT_LOCATIONS = ["Amazon", "Aliexpress", "Bambu Lab", "Temu"]
    with engine.connect() as conn:
        from .models import PurchaseLocation as _PL
        from sqlalchemy.orm import Session as _Session000
        with _Session000(engine) as s:
            existing_loc = {r.name for r in s.query(_PL).all()}
            added_loc = [n for n in _DEFAULT_LOCATIONS if n not in existing_loc]
            for name in added_loc:
                s.add(_PL(name=name))
            if added_loc:
                s.commit()
                log.info("Seeded purchase locations: %s", added_loc)

    # Seed default filament brands if table is empty
    _DEFAULT_BRANDS = [
        "Bambu Lab", "SUNLU", "Jayo", "Geeetech",
    ]
    with engine.connect() as conn:
        from .models import FilamentBrand as _FBR
        from sqlalchemy.orm import Session as _Session00
        with _Session00(engine) as s:
            existing_br = {r.name for r in s.query(_FBR).all()}
            added_br = [n for n in _DEFAULT_BRANDS if n not in existing_br]
            for name in added_br:
                s.add(_FBR(name=name))
            if added_br:
                s.commit()
                log.info("Seeded filament brands: %s", added_br)

    # Seed default filament subtypes if table is empty
    _DEFAULT_SUBTYPES = [
        "Basic", "Matte", "Silk", "Silk+", "Shiny Silk", "Plus",
        "Marble", "Galaxy", "Glow", "Wood", "Metal", "Carbon Fiber",
        "Translucent", "High Speed", "HF", "HSM", "Elite", "4AMS", "Other",
    ]
    with engine.connect() as conn:
        from .models import FilamentSubtype as _FST
        from sqlalchemy.orm import Session as _Session2
        with _Session2(engine) as s:
            existing_subtypes = {r.name for r in s.query(_FST).all()}
            added_st = []
            for name in _DEFAULT_SUBTYPES:
                if name not in existing_subtypes:
                    s.add(_FST(name=name))
                    added_st.append(name)
            if added_st:
                s.commit()
                log.info("Seeded filament subtypes: %s", added_st)

    # Seed default brand spool weights if table is empty
    _DEFAULT_BRAND_WEIGHTS = [
        ("Jayo",      127.0),
        ("Bambu Lab", 250.0),
        ("SUNLU",     225.0),
    ]
    with engine.connect() as conn:
        from sqlalchemy import text as _text
        from .models import BrandSpoolWeight as _BSW
        from sqlalchemy.orm import Session as _Session
        with _Session(engine) as s:
            existing_brands = {r.brand for r in s.query(_BSW).all()}
            added = []
            for brand, weight in _DEFAULT_BRAND_WEIGHTS:
                if brand not in existing_brands:
                    s.add(_BSW(brand=brand, spool_weight_g=weight))
                    added.append(brand)
            if added:
                s.commit()
                log.info("Seeded brand weights: %s", added)

    # Start print monitor
    scheduler.add_job(
        print_monitor.poll_printers,
        "interval",
        seconds=30,
        id="poll_printers",
        replace_existing=True,
    )
    scheduler.start()
    log.info("Print monitor started (30s interval)")

    await bambu_cloud_client.startup()

    yield

    await bambu_cloud_client.shutdown()
    scheduler.shutdown()
    log.info("Scheduler stopped")


app = FastAPI(title="Filament Manager", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(spools.router)
app.include_router(prints.router)
app.include_router(printers.router)
app.include_router(dashboard.router)
app.include_router(app_settings.router)
app.include_router(data_transfer.router)
app.include_router(bambu_cloud.router)

# Serve React frontend
# In container: __file__ = /app/app/main.py → parent.parent = /app → /app/static
STATIC_DIR = Path(__file__).parent.parent / "static"
log.info("Static dir: %s (exists=%s)", STATIC_DIR, STATIC_DIR.exists())

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def root():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        # Let API routes 404 naturally; everything else → SPA
        index = STATIC_DIR / "index.html"
        return FileResponse(index)
else:
    log.warning("Static dir not found — frontend will not be served")
