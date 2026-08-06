from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Spool, PrintJob, PrintUsage, PrinterConfig, UserPreferences
from ..schemas import DashboardStats, MaterialBreakdown, PriceByLocation, PrinterHours, PrinterEnergy, PrintJobOut, SpoolOut, PrintsPerDay

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
async def get_dashboard(db: Session = Depends(get_db)):
    prefs = db.get(UserPreferences, 1)
    low_stock_threshold = (prefs.low_stock_threshold_pct if prefs else None) or 20

    spools = db.query(Spool).all()
    active_spools = [s for s in spools if s.current_weight_g > 0]
    empty_spools  = [s for s in spools if s.current_weight_g <= 0]
    low_stock     = [s for s in active_spools if 0 < s.remaining_pct < low_stock_threshold]

    # Weight totals
    total_filament_kg  = sum(s.initial_weight_g for s in spools) / 1000
    total_available_kg = sum(s.current_weight_g for s in active_spools) / 1000

    # Cost totals
    total_filament_spent = sum((s.purchase_price or 0) for s in spools)
    total_available_eur  = sum(
        (s.purchase_price or 0) * (s.remaining_pct / 100)
        for s in active_spools
    )

    # Refill-pack breakdown (bulk filament bought without a new physical spool)
    refill_spools = [s for s in spools if s.is_refill_pack]
    refill_pack_spools    = len(refill_spools)
    refill_pack_spent_eur = sum((s.purchase_price or 0) for s in refill_spools)
    refill_pack_kg        = sum(s.initial_weight_g for s in refill_spools) / 1000

    # Print job statistics — SQL aggregates instead of hydrating the entire
    # history (jobs × usages × spools) on every dashboard call.
    total_prints = db.query(func.count(PrintJob.id)).scalar() or 0

    # grams + material cost in one pass over usages; cost_per_gram is
    # purchase_price / initial_weight_g (NULL price or zero weight → NULL in
    # SQLite → excluded from SUM, matching the Python property semantics)
    total_print_grams, material_cost_sum = db.query(
        func.coalesce(func.sum(PrintUsage.grams_used), 0.0),
        func.coalesce(func.sum(
            PrintUsage.grams_used * Spool.purchase_price / Spool.initial_weight_g
        ), 0.0),
    ).outerjoin(Spool, PrintUsage.spool_id == Spool.id).one()

    energy_cost_sum = db.query(func.coalesce(func.sum(PrintJob.energy_cost), 0.0)).scalar() or 0.0
    total_print_cost = material_cost_sum + energy_cost_sum

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
    # Cloud source: prefer lifetime counter from MQTT (mc_print_tick_cnt).
    # Fall back to aggregated duration_seconds from stored print jobs.
    ph: dict[str, float] = {}
    job_hours: dict[str, float] = defaultdict(float)
    for printer_name, seconds in (
        db.query(PrintJob.printer_name, func.sum(PrintJob.duration_seconds))
        .filter(PrintJob.printer_name.isnot(None), PrintJob.duration_seconds.isnot(None))
        .group_by(PrintJob.printer_name)
        .all()
    ):
        job_hours[printer_name] = (seconds or 0) / 3600

    printers = db.query(PrinterConfig).filter(PrinterConfig.is_active == True).all()  # noqa: E712
    for p in printers:
        hours: float | None = None

        if p.bambu_serial:
            from .. import bambu_cloud_client
            status = bambu_cloud_client.get_printer_cloud_status(p.bambu_serial)
            tick_cnt = status.get("mc_print_tick_cnt")
            if tick_cnt is not None:
                try:
                    hours = round(float(tick_cnt) / 3600, 2)
                except (ValueError, TypeError):
                    pass

        if hours is None:
            hours = round(job_hours.get(p.name, 0.0), 2)

        ph[p.name] = hours

    printer_hours = sorted(
        [PrinterHours(printer=name, hours=h) for name, h in ph.items()],
        key=lambda x: x.printer,
    )

    # Energy per printer (from completed jobs with energy_kwh set)
    # count(energy_cost) skips NULLs → 0 means no job had a cost recorded
    printer_energy = sorted(
        [
            PrinterEnergy(
                printer=name,
                energy_kwh=round(kwh or 0.0, 3),
                energy_cost=round(cost or 0.0, 4) if cost_count else None,
            )
            for name, kwh, cost, cost_count in (
                db.query(
                    PrintJob.printer_name,
                    func.sum(PrintJob.energy_kwh),
                    func.sum(PrintJob.energy_cost),
                    func.count(PrintJob.energy_cost),
                )
                .filter(PrintJob.printer_name.isnot(None), PrintJob.energy_kwh.isnot(None))
                .group_by(PrintJob.printer_name)
                .all()
            )
        ],
        key=lambda x: x.printer,
    )

    # Running job: most recent open print (no finished_at)
    running_job = (
        db.query(PrintJob)
        .filter(PrintJob.finished_at.is_(None))
        .options(joinedload(PrintJob.usages).joinedload(PrintUsage.spool))
        .order_by(PrintJob.started_at.desc())
        .first()
    )

    # Recent prints: 5 most recent jobs only
    recent_prints = (
        db.query(PrintJob)
        .options(joinedload(PrintJob.usages).joinedload(PrintUsage.spool))
        .order_by(PrintJob.started_at.desc())
        .limit(5)
        .all()
    )

    # Prints per day: from first job date to today, filling gaps with 0
    prints_per_day: list[PrintsPerDay] = []
    day_rows = (
        db.query(func.date(PrintJob.started_at), func.count(PrintJob.id))
        .group_by(func.date(PrintJob.started_at))
        .all()
    )
    if day_rows:
        day_counts = {date.fromisoformat(d): c for d, c in day_rows if d}
        first_date = min(day_counts.keys())
        today = date.today()
        current = first_date
        while current <= today:
            prints_per_day.append(PrintsPerDay(date=current.isoformat(), count=day_counts.get(current, 0)))
            current += timedelta(days=1)

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
        refill_pack_spools=refill_pack_spools,
        refill_pack_spent_eur=round(refill_pack_spent_eur, 2),
        refill_pack_kg=round(refill_pack_kg, 3),
        total_prints=total_prints,
        material_breakdown=material_breakdown,
        price_by_location=price_by_location,
        printer_hours=printer_hours,
        printer_energy=printer_energy,
        recent_prints=recent_prints,
        low_stock=sorted(low_stock, key=lambda s: s.remaining_pct),
        running_job=running_job,
        prints_per_day=prints_per_day,
    )


@router.get("/ha-status")
async def ha_status():
    from .. import ha_client
    available = await ha_client.is_ha_available()
    return {"ha_available": available}
