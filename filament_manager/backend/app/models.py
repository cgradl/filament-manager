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


class PrintUsage(Base):
    __tablename__ = "print_usages"

    id = Column(Integer, primary_key=True, index=True)
    print_job_id = Column(Integer, ForeignKey("print_jobs.id"), nullable=False)
    spool_id = Column(Integer, ForeignKey("spools.id"), nullable=False)
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


class PrinterConfig(Base):
    __tablename__ = "printer_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)              # friendly name, e.g. "My Printer"
    device_slug = Column(String, nullable=False)       # HA entity slug, e.g. "my_printer"
    ams_device_slug = Column(String)                   # AMS device slug if different from printer
    ams_unit_count = Column(Integer, default=1)        # number of AMS units (1-4)
    is_active = Column(Boolean, default=True)
    bambu_serial = Column(String, nullable=True)          # Bambu Lab device serial number
    bambu_source = Column(String, nullable=False, default="ha")  # "ha" | "cloud"

    # Optional per-printer sensor entity ID overrides (for non-English HA installations)
    sensor_print_stage    = Column(String, nullable=True)
    sensor_print_progress = Column(String, nullable=True)
    sensor_remaining_time = Column(String, nullable=True)
    sensor_nozzle_temp    = Column(String, nullable=True)
    sensor_bed_temp       = Column(String, nullable=True)
    sensor_current_file   = Column(String, nullable=True)
    sensor_print_weight   = Column(String, nullable=True)

    # Optional AMS entity pattern/suffix overrides
    # ams_tray_pattern: replaces "ams_{u}_tray_{t}" (no ams_device_slug) or "tray_{t}" (with ams_device_slug)
    # ams_suffix_*: replaces "_type" / "_color" / "_remain" suffixes (no ams_device_slug mode only)
    ams_tray_pattern  = Column(String, nullable=True)
    ams_suffix_type   = Column(String, nullable=True)
    ams_suffix_color  = Column(String, nullable=True)
    ams_suffix_remain = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def sensor_overrides(self) -> dict:
        """Return only the printer sensor keys that have a non-empty override set."""
        keys = ("print_stage", "print_progress", "remaining_time",
                "nozzle_temp", "bed_temp", "current_file", "print_weight")
        return {
            k: getattr(self, f"sensor_{k}")
            for k in keys
            if getattr(self, f"sensor_{k}", None)
        }

    @property
    def ams_overrides(self) -> dict:
        """Return AMS entity overrides dict, omitting keys that are unset."""
        result = {}
        if self.ams_tray_pattern:
            result["tray_pattern"] = self.ams_tray_pattern
        if self.ams_suffix_type:
            result["suffix_type"] = self.ams_suffix_type
        if self.ams_suffix_color:
            result["suffix_color"] = self.ams_suffix_color
        if self.ams_suffix_remain:
            result["suffix_remain"] = self.ams_suffix_remain
        return result
