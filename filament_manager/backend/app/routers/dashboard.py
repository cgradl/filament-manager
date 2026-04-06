from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Spool, PrintJob, PrintUsage, PrinterConfig
from ..schemas import DashboardStats, MaterialBreakdown, PriceByLocation, PrinterHours, PrintJobOut, SpoolOut
from .. import ha_client

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
async def get_dashboard(db: Session = Depends(get_db)):
    spools = db.query(Spool).all()
    active_spools = [s for s in spools if s.current_weight_g > 0]
    empty_spools  = [s for s in spools if s.current_weight_g <= 0]
    low_stock     = [s for s in active_spools if 0 < s.remaining_pct < 20]

    # Weight totals
    total_filament_kg  = sum(s.initial_weight_g for s in spools) / 1000
    total_available_kg = sum(s.current_weight_g for s in active_spools) / 1000

    # Cost totals
    total_filament_spent = sum((s.purchase_price or 0) for s in spools)
    total_available_eur  = sum(
        (s.purchase_price or 0) * (s.remaining_pct / 100)
        for s in active_spools
    )

    # Print jobs
    jobs = (
        db.query(PrintJob)
        .options(joinedload(PrintJob.usages).joinedload(PrintUsage.spool))
        .order_by(PrintJob.started_at.desc())
        .all()
    )
    total_print_grams = sum(j.total_grams for j in jobs)
    total_print_cost  = sum(j.total_cost  for j in jobs)

    # Material breakdown (by current remaining weight)
    mat: dict[str, dict] = defaultdict(lambda: {"count": 0, "current_kg": 0.0})
    for s in spools:
        mat[s.material]["count"]      += 1
        mat[s.material]["current_kg"] += s.current_weight_g / 1000
    material_breakdown = [
        MaterialBreakdown(material=m, count=d["count"], current_kg=round(d["current_kg"], 3))
        for m, d in sorted(mat.items())
    ]

    # Avg price per purchase location (only spools that have both fields set)
    loc: dict[str, list[float]] = defaultdict(list)
    for s in spools:
        if s.purchase_location and s.purchase_price is not None:
            loc[s.purchase_location].append(s.purchase_price)
    price_by_location = sorted(
        [
            PriceByLocation(
                location=l,
                avg_price=round(sum(prices) / len(prices), 2),
                count=len(prices),
            )
            for l, prices in loc.items()
        ],
        key=lambda x: x.location,
    )

    # Hours printed per printer
    # HA-source: read sensor.{device_slug}_total_usage directly from HA (lifetime counter)
    # Cloud-source or HA entity unavailable: aggregate duration_seconds from print jobs
    ph: dict[str, float] = {}
    job_hours: dict[str, float] = defaultdict(float)
    for j in jobs:
        if j.printer_name and j.duration_seconds:
            job_hours[j.printer_name] += j.duration_seconds / 3600

    printers = db.query(PrinterConfig).filter(PrinterConfig.is_active == True).all()  # noqa: E712
    for p in printers:
        hours: float | None = None

        if getattr(p, "bambu_source", "ha") == "cloud" and getattr(p, "bambu_serial", None):
            from .. import bambu_cloud_client
            status = bambu_cloud_client.get_printer_cloud_status(p.bambu_serial)
            tick_cnt = status.get("mc_print_tick_cnt")
            if tick_cnt is not None:
                try:
                    hours = round(float(tick_cnt) / 3600, 2)
                except (ValueError, TypeError):
                    pass
        else:
            entity_id = f"sensor.{p.device_slug}_total_usage"
            val = await ha_client.get_entity_value(entity_id)
            if val is not None:
                try:
                    hours = round(float(val), 2)
                except (ValueError, TypeError):
                    pass

        # Fall back to job aggregation (or 0) so every printer always gets a bar
        if hours is None:
            hours = round(job_hours.get(p.name, 0.0), 2)

        ph[p.name] = hours

    printer_hours = sorted(
        [PrinterHours(printer=name, hours=h) for name, h in ph.items()],
        key=lambda x: x.printer,
    )

    # Running job: most recent open print (no finished_at)
    running_job = next((j for j in jobs if j.finished_at is None), None)

    return DashboardStats(
        total_spools=len(spools),
        active_spools=len(active_spools),
        empty_spools=len(empty_spools),
        low_stock_spools=len(low_stock),
        total_filament_kg=round(total_filament_kg, 3),
        total_printed_kg=round(total_print_grams / 1000, 3),
        total_available_kg=round(total_available_kg, 3),
        total_filament_spent_eur=round(total_filament_spent, 2),
        total_print_cost_eur=round(total_print_cost, 2),
        total_available_eur=round(total_available_eur, 2),
        total_prints=len(jobs),
        material_breakdown=material_breakdown,
        price_by_location=price_by_location,
        printer_hours=printer_hours,
        recent_prints=jobs[:5],
        low_stock=sorted(low_stock, key=lambda s: s.remaining_pct),
        running_job=running_job,
    )


@router.get("/ha-status")
async def ha_status():
    available = await ha_client.is_ha_available()
    return {"ha_available": available}
