from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from .database import Base


MATERIAL_DENSITY: dict[str, float] = {
    "PLA":    1.24,
    "PLA+":   1.24,
    "PETG":   1.27,
    "ABS":    1.05,
    "ASA":    1.07,
    "TPU":    1.21,
    "PA":     1.13,
    "PA-CF":  1.22,
    "PC":     1.20,
    "PVA":    1.23,
    "HIPS":   1.06,
    "PET":    1.37,
}


class Spool(Base):
    __tablename__ = "spools"

    id = Column(Integer, primary_key=True, index=True)
    custom_id = Column(Integer, nullable=True)   # user-assigned reference number (1–9999)
    brand = Column(String, nullable=False)
    material = Column(String, nullable=False)
    subtype = Column(String)
    subtype2 = Column(String)
    color_name = Column(String, nullable=False)
    color_hex = Column(String, default="#888888")
    diameter_mm = Column(Float, default=1.75)

    initial_weight_g = Column(Float, nullable=False)
    current_weight_g = Column(Float, nullable=False)
    spool_weight_g = Column(Float, default=0)

    purchase_price = Column(Float)
    purchased_at = Column(DateTime)
    # purchase_url kept in DB but no longer exposed (orphaned column)

    purchase_location = Column(String)
    storage_location = Column(String)
    article_number = Column(String, nullable=True)
    ams_slot = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usages = relationship("PrintUsage", back_populates="spool")

    @property
    def remaining_pct(self) -> float:
        if self.initial_weight_g:
            return max(0.0, round(self.current_weight_g / self.initial_weight_g * 100, 1))
        return 0.0

    @property
    def price_per_kg(self) -> float | None:
        if self.purchase_price and self.initial_weight_g:
            return round(self.purchase_price / (self.initial_weight_g / 1000), 2)
        return None

    @property
    def cost_per_gram(self) -> float | None:
        if self.purchase_price and self.initial_weight_g:
            return self.purchase_price / self.initial_weight_g
        return None


class Project(Base):
    """User-defined project that groups multiple print jobs."""
    __tablename__ = "projects"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    print_jobs = relationship("PrintJob", back_populates="project")


class PrintJob(Base):
    __tablename__ = "print_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    model_name = Column(String)           # raw gcode filename from printer
    description = Column(Text)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    duration_seconds = Column(Integer)
    success = Column(Boolean, default=True)
    notes = Column(Text)
    printer_name = Column(String)
    source = Column(String, default="manual")
    ams_snapshot_start = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Bambu Cloud / MQTT enrichment fields
    task_id = Column(String, nullable=True)        # Bambu task ID (cloud job reference)
    project_id = Column(String, nullable=True)     # Bambu project/profile ID
    total_layer_num = Column(Integer, nullable=True)
    layer_num = Column(Integer, nullable=True)     # final layer reached (at print end)
    nozzle_diameter = Column(String, nullable=True)  # "0.4", "0.6", etc.
    nozzle_type = Column(String, nullable=True)    # "stainless_steel", "hardened_steel", etc.
    print_type = Column(String, nullable=True)     # "cloud", "local", "sdcard"
    error_code = Column(String, nullable=True)     # mc_print_error_code on failure
    print_weight_g = Column(Float, nullable=True)  # total filament weight (g) reported by printer/cloud
    suggested_usages = Column(JSON, nullable=True)  # cloud-sourced per-tray usage hints [{ams_slot, grams, filament_type, color}]
    design_title = Column(String, nullable=True)   # MakerWorld/cloud model name (designTitle field from Bambu)
    url = Column(String, nullable=True)            # user-set URL for the model/print source
    fm_project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)

    project = relationship("Project", back_populates="print_jobs")
    usages = relationship(
        "PrintUsage", back_populates="print_job", cascade="all, delete-orphan"
    )

    @property
    def total_grams(self) -> float:
        return sum(u.grams_used for u in self.usages)

    @property
    def total_cost(self) -> float:
        return sum((u.cost or 0) for u in self.usages)

    @property
    def duration_hours(self) -> float | None:
        if self.duration_seconds:
            return round(self.duration_seconds / 3600, 2)
        return None

    @property
    def project_name(self) -> str | None:
        return self.project.name if self.project else None


class PrintUsage(Base):
    __tablename__ = "print_usages"

    id = Column(Integer, primary_key=True, index=True)
    print_job_id = Column(Integer, ForeignKey("print_jobs.id"), nullable=False)
    spool_id = Column(Integer, ForeignKey("spools.id"), nullable=True)
    grams_used = Column(Float, nullable=False)
    meters_used = Column(Float)
    ams_slot = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    print_job = relationship("PrintJob", back_populates="usages")
    spool = relationship("Spool", back_populates="usages")

    @property
    def cost(self) -> float | None:
        if self.spool and self.spool.cost_per_gram:
            return round(self.grams_used * self.spool.cost_per_gram, 4)
        return None


class BrandSpoolWeight(Base):
    """Empty spool tare weight per brand — used to calculate remaining from scale reading."""
    __tablename__ = "brand_spool_weights"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, unique=True, nullable=False)
    spool_weight_g = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FilamentSubtype(Base):
    """User-managed list of filament subtypes shown in the spool form."""
    __tablename__ = "filament_subtypes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FilamentMaterial(Base):
    """User-managed list of filament material types."""
    __tablename__ = "filament_materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FilamentBrand(Base):
    """User-managed list of filament brands for autocomplete."""
    __tablename__ = "filament_brands"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PurchaseLocation(Base):
    """User-managed list of purchase locations (shops/stores)."""
    __tablename__ = "purchase_locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class StorageLocation(Base):
    """User-managed list of physical storage locations (shelves, boxes, etc.)."""
    __tablename__ = "storage_locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FilamentCatalog(Base):
    """User-managed filament product catalog (brand + material + color + article number)."""
    __tablename__ = "filament_catalog"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, nullable=False)
    material = Column(String, nullable=False)
    subtype = Column(String, nullable=True)
    subtype2 = Column(String, nullable=True)
    color_name = Column(String, nullable=False)
    color_hex = Column(String, default="#888888")
    article_number = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SpoolAudit(Base):
    """Immutable audit log of every change to a spool's current_weight_g."""
    __tablename__ = "spool_audit"

    id           = Column(Integer, primary_key=True, index=True)
    spool_id     = Column(Integer, ForeignKey("spools.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
    # 'print_auto' | 'print_manual' | 'print_delete' | 'spool_edit'
    action       = Column(String, nullable=False)
    delta_g      = Column(Float, nullable=False)   # negative = used, positive = restored/corrected
    weight_before = Column(Float)
    weight_after  = Column(Float)
    print_job_id = Column(Integer, ForeignKey("print_jobs.id", ondelete="SET NULL"), nullable=True)
    print_name   = Column(String, nullable=True)   # denormalised snapshot — survives job deletion


class UserPreferences(Base):
    """Single-row table (id=1) for user-configurable overrides of HA-derived values."""
    __tablename__ = "user_preferences"

    id                      = Column(Integer, primary_key=True, default=1)
    timezone_override       = Column(String,  nullable=True)   # IANA tz, e.g. "Europe/Berlin"
    currency_override       = Column(String,  nullable=True)   # ISO 4217, e.g. "EUR"
    country_override        = Column(String,  nullable=True)   # ISO 3166-1 alpha-2, e.g. "DE"
    low_stock_threshold_pct = Column(Integer, nullable=False, default=20)  # 1–100


class PrinterConfig(Base):
    __tablename__ = "printer_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)              # friendly name, e.g. "My Printer"
    ams_unit_count = Column(Integer, default=1)        # number of AMS units (1-4)
    is_active = Column(Boolean, default=True)
    bambu_serial = Column(String, nullable=True)       # Bambu Lab device serial number
    bambu_source = Column(String, nullable=False, default="cloud")  # always "cloud"

    # When True: apply suggested_usages automatically on print completion (no user confirmation needed)
    auto_deduct = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
