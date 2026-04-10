from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ── Spool ────────────────────────────────────────────────────────────────────

class SpoolBase(BaseModel):
    custom_id: int | None = None
    brand: str
    material: str
    subtype: str | None = None
    subtype2: str | None = None
    color_name: str
    color_hex: str = "#888888"
    diameter_mm: float = 1.75
    initial_weight_g: float
    current_weight_g: float
    spool_weight_g: float = 0
    purchase_price: float | None = None
    purchased_at: datetime | None = None
    purchase_location: str | None = None
    storage_location: str | None = None
    ams_slot: str | None = None
    notes: str | None = None


class SpoolCreate(SpoolBase):
    pass


class SpoolUpdate(BaseModel):
    custom_id: int | None = None
    brand: str | None = None
    material: str | None = None
    subtype: str | None = None
    subtype2: str | None = None
    color_name: str | None = None
    color_hex: str | None = None
    diameter_mm: float | None = None
    initial_weight_g: float | None = None
    current_weight_g: float | None = None
    spool_weight_g: float | None = None
    purchase_price: float | None = None
    purchased_at: datetime | None = None
    purchase_location: str | None = None
    storage_location: str | None = None
    ams_slot: str | None = None
    notes: str | None = None


class SpoolOut(SpoolBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    remaining_pct: float
    price_per_kg: float | None
    cost_per_gram: float | None
    created_at: datetime
    updated_at: datetime


# ── PrintUsage ───────────────────────────────────────────────────────────────

class PrintUsageBase(BaseModel):
    spool_id: int | None = None
    grams_used: float
    meters_used: float | None = None
    ams_slot: str | None = None


class PrintUsageCreate(PrintUsageBase):
    pass


class PrintUsageOut(PrintUsageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    print_job_id: int
    cost: float | None
    spool: SpoolOut | None = None


# ── PrintJob ─────────────────────────────────────────────────────────────────

class PrintJobBase(BaseModel):
    name: str
    model_name: str | None = None
    description: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    success: bool = True
    notes: str | None = None
    printer_name: str | None = None


class PrintJobCreate(PrintJobBase):
    usages: list[PrintUsageCreate] = []


class PrintJobUpdate(BaseModel):
    name: str | None = None
    model_name: str | None = None
    description: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    success: bool | None = None
    notes: str | None = None
    printer_name: str | None = None
    usages: list[PrintUsageCreate] | None = None


class PrintJobOut(PrintJobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    total_grams: float
    total_cost: float
    duration_hours: float | None
    usages: list[PrintUsageOut] = []
    created_at: datetime

    # Bambu Cloud / MQTT enrichment fields (None for manual/HA-tracked jobs)
    task_id: str | None = None
    project_id: str | None = None
    total_layer_num: int | None = None
    layer_num: int | None = None
    nozzle_diameter: str | None = None
    nozzle_type: str | None = None
    print_type: str | None = None
    error_code: str | None = None
    print_weight_g: float | None = None
    suggested_usages: list | None = None


# ── Dashboard ────────────────────────────────────────────────────────────────

class MaterialBreakdown(BaseModel):
    material: str
    count: int
    current_kg: float


class PriceByLocation(BaseModel):
    location: str
    avg_price: float
    count: int


class PrinterHours(BaseModel):
    printer: str
    hours: float


class PrintsPerDay(BaseModel):
    date: str   # "YYYY-MM-DD"
    count: int


class DashboardStats(BaseModel):
    total_spools: int
    active_spools: int
    empty_spools: int
    low_stock_spools: int

    # Weight
    total_filament_kg: float       # total purchased (initial weight)
    total_printed_kg: float        # total consumed in prints
    total_available_kg: float      # current remaining across all active spools

    # Cost
    total_filament_spent_eur: float   # total purchase cost
    total_print_cost_eur: float       # cost of filament used in prints
    total_available_eur: float        # estimated value of remaining filament

    total_prints: int
    material_breakdown: list[MaterialBreakdown] = []
    price_by_location: list[PriceByLocation] = []
    printer_hours: list[PrinterHours] = []
    recent_prints: list[PrintJobOut] = []
    low_stock: list[SpoolOut] = []
    running_job: PrintJobOut | None = None
    prints_per_day: list[PrintsPerDay] = []


class BrandSpoolWeightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    brand: str
    spool_weight_g: float


class HAEntityState(BaseModel):
    entity_id: str
    state: str
    attributes: dict = {}
    friendly_name: str | None = None
