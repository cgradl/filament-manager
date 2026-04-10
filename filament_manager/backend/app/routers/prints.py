from datetime import datetime, date as date_t
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, func, select as sa_select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import PrintJob, PrintUsage, Spool
from ..schemas import PrintJobCreate, PrintJobOut, PrintJobUpdate

router = APIRouter(prefix="/api/prints", tags=["prints"])


def _load_job(db: Session, job_id: int) -> PrintJob:
    job = (
        db.query(PrintJob)
        .options(
            joinedload(PrintJob.usages).joinedload(PrintUsage.spool)
        )
        .filter(PrintJob.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(404, "Print job not found")
    return job


def _apply_filters(
    q,
    search: str | None,
    date_from: str | None,
    date_to: str | None,
    timezone: str,
):
    """Apply optional search / date-range filters to a PrintJob query."""
    if search:
        s = f"%{search.lower()}%"
        # Subquery: print job IDs whose spools match the search term
        spool_subq = (
            sa_select(PrintUsage.print_job_id)
            .join(Spool, PrintUsage.spool_id == Spool.id)
            .where(
                or_(
                    func.lower(func.coalesce(Spool.brand, "") + " " + func.coalesce(Spool.material, "")).like(s),
                    func.lower(func.coalesce(Spool.color_name, "")).like(s),
                )
            )
            .scalar_subquery()
        )
        q = q.filter(
            or_(
                func.lower(func.coalesce(PrintJob.name, "")).like(s),
                func.lower(func.coalesce(PrintJob.printer_name, "")).like(s),
                PrintJob.id.in_(spool_subq),
            )
        )

    if date_from or date_to:
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("UTC")
        utc = ZoneInfo("UTC")

        if date_from:
            d = date_t.fromisoformat(date_from)
            utc_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz).astimezone(utc).replace(tzinfo=None)
            q = q.filter(PrintJob.started_at >= utc_start)

        if date_to:
            d = date_t.fromisoformat(date_to)
            utc_end = datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=tz).astimezone(utc).replace(tzinfo=None)
            q = q.filter(PrintJob.started_at <= utc_end)

    return q


@router.get("/count")
def count_prints(
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    timezone: str = "UTC",
    db: Session = Depends(get_db),
):
    q = _apply_filters(db.query(PrintJob), search, date_from, date_to, timezone)
    return {"total": q.count()}


@router.get("", response_model=list[PrintJobOut])
def list_prints(
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    timezone: str = "UTC",
    db: Session = Depends(get_db),
):
    q = _apply_filters(db.query(PrintJob), search, date_from, date_to, timezone)
    jobs = (
        q.options(joinedload(PrintJob.usages).joinedload(PrintUsage.spool))
        .order_by(PrintJob.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return jobs


@router.post("", response_model=PrintJobOut, status_code=201)
def create_print(body: PrintJobCreate, db: Session = Depends(get_db)):
    job = PrintJob(
        name=body.name,
        model_name=body.model_name,
        description=body.description,
        started_at=body.started_at,
        finished_at=body.finished_at,
        duration_seconds=body.duration_seconds,
        success=body.success,
        notes=body.notes,
        printer_name=body.printer_name,
        source="manual",
    )
    db.add(job)
    db.flush()

    for u in body.usages:
        spool = db.get(Spool, u.spool_id) if u.spool_id else None
        if u.spool_id and not spool:
            raise HTTPException(404, f"Spool {u.spool_id} not found")
        usage = PrintUsage(
            print_job_id=job.id,
            spool_id=u.spool_id,
            grams_used=u.grams_used,
            meters_used=u.meters_used,
            ams_slot=u.ams_slot,
        )
        db.add(usage)
        if spool:
            spool.current_weight_g = max(0, spool.current_weight_g - u.grams_used)

    db.commit()
    return _load_job(db, job.id)


@router.get("/{job_id}", response_model=PrintJobOut)
def get_print(job_id: int, db: Session = Depends(get_db)):
    return _load_job(db, job_id)


@router.patch("/{job_id}", response_model=PrintJobOut)
def update_print(job_id: int, body: PrintJobUpdate, db: Session = Depends(get_db)):
    job = db.get(PrintJob, job_id)
    if not job:
        raise HTTPException(404, "Print job not found")

    for field, value in body.model_dump(exclude_unset=True, exclude={"usages"}).items():
        setattr(job, field, value)

    if body.usages is not None:
        # Revert old spool weights
        for old in job.usages:
            if old.spool_id:
                spool = db.get(Spool, old.spool_id)
                if spool:
                    spool.current_weight_g = min(
                        spool.initial_weight_g,
                        spool.current_weight_g + old.grams_used,
                    )
            db.delete(old)
        db.flush()

        for u in body.usages:
            spool = db.get(Spool, u.spool_id) if u.spool_id else None
            if u.spool_id and not spool:
                raise HTTPException(404, f"Spool {u.spool_id} not found")
            usage = PrintUsage(
                print_job_id=job.id,
                spool_id=u.spool_id,
                grams_used=u.grams_used,
                meters_used=u.meters_used,
                ams_slot=u.ams_slot,
            )
            db.add(usage)
            if spool:
                spool.current_weight_g = max(0, spool.current_weight_g - u.grams_used)

    db.commit()
    return _load_job(db, job.id)


@router.delete("/{job_id}", status_code=204)
def delete_print(job_id: int, db: Session = Depends(get_db)):
    job = db.get(PrintJob, job_id)
    if not job:
        raise HTTPException(404, "Print job not found")
    # Revert spool weights
    for usage in job.usages:
        if usage.spool_id:
            spool = db.get(Spool, usage.spool_id)
            if spool:
                spool.current_weight_g = min(
                    spool.initial_weight_g,
                    spool.current_weight_g + usage.grams_used,
                )
    db.delete(job)
    db.commit()
