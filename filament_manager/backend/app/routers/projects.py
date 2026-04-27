from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import PrintJob, PrintUsage, Project, ProjectPrint, Spool
from ..schemas import ProjectCreate, ProjectDetailOut, ProjectOut, ProjectUpdate, PrintJobOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_out(project: Project) -> ProjectOut:
    # Build lookup: print_job_id → is_test_print
    pp_by_job: dict[int, bool] = {pp.print_job_id: pp.is_test_print for pp in project.project_prints}

    jobs = project.print_jobs
    print_count = len(jobs)
    total_duration_seconds = sum(j.duration_seconds or 0 for j in jobs)
    total_cost = sum(j.total_cost for j in jobs)
    total_grams = sum(j.total_grams for j in jobs)
    nozzle_diameters = sorted({j.nozzle_diameter for j in jobs if j.nozzle_diameter})
    materials: list[str] = []
    for j in jobs:
        for u in j.usages:
            if u.spool and u.spool.material and u.spool.material not in materials:
                materials.append(u.spool.material)
    materials.sort()
    started_dates = [j.started_at for j in jobs if j.started_at]
    date_first = min(started_dates) if started_dates else None
    date_last = max(started_dates) if started_dates else None

    energy_values = [j.energy_kwh for j in jobs if j.energy_kwh is not None]
    total_energy_kwh = round(sum(energy_values), 4) if energy_values else None
    energy_cost_values = [j.energy_cost for j in jobs if j.energy_cost is not None]
    total_energy_cost = round(sum(energy_cost_values), 4) if energy_cost_values else None

    # Test / normal split
    test_jobs = [j for j in jobs if pp_by_job.get(j.id, False)]
    test_print_count = len(test_jobs)
    test_total_grams = round(sum(j.total_grams for j in test_jobs), 2)
    test_total_cost = round(sum(j.total_cost for j in test_jobs), 4)
    test_energy_vals = [j.energy_kwh for j in test_jobs if j.energy_kwh is not None]
    test_total_energy_kwh = round(sum(test_energy_vals), 4) if test_energy_vals else None
    test_energy_cost_vals = [j.energy_cost for j in test_jobs if j.energy_cost is not None]
    test_total_energy_cost = round(sum(test_energy_cost_vals), 4) if test_energy_cost_vals else None

    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        url=project.url,
        print_count=print_count,
        total_duration_seconds=total_duration_seconds,
        total_cost=round(total_cost, 4),
        total_grams=round(total_grams, 2),
        total_energy_kwh=total_energy_kwh,
        total_energy_cost=total_energy_cost,
        nozzle_diameters=nozzle_diameters,
        materials=materials,
        date_first=date_first,
        date_last=date_last,
        created_at=project.created_at,
        test_print_count=test_print_count,
        test_total_grams=test_total_grams,
        test_total_cost=test_total_cost,
        test_total_energy_kwh=test_total_energy_kwh,
        test_total_energy_cost=test_total_energy_cost,
    )


def _load_project(db: Session, project_id: int) -> Project:
    p = (
        db.query(Project)
        .options(
            joinedload(Project.print_jobs)
            .joinedload(PrintJob.usages)
            .joinedload(PrintUsage.spool),
            joinedload(Project.project_prints),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    projects = (
        db.query(Project)
        .options(
            joinedload(Project.print_jobs)
            .joinedload(PrintJob.usages)
            .joinedload(PrintUsage.spool),
            joinedload(Project.project_prints),
        )
        .order_by(Project.name)
        .all()
    )
    return [_project_out(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=body.name, description=body.description, url=body.url)
    db.add(project)
    db.commit()
    return _project_out(_load_project(db, project.id))


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = _load_project(db, project_id)
    base = _project_out(p)
    pp_by_job: dict[int, bool] = {pp.print_job_id: pp.is_test_print for pp in p.project_prints}
    print_jobs = []
    for j in p.print_jobs:
        job_out = PrintJobOut.model_validate(j)
        job_out.is_test_print = pp_by_job.get(j.id, False)
        print_jobs.append(job_out)
    print_jobs.sort(key=lambda j: j.started_at, reverse=True)
    return ProjectDetailOut(**base.model_dump(), print_jobs=print_jobs)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    return _project_out(_load_project(db, project_id))


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    for job in p.print_jobs:
        job.fm_project_id = None
    db.delete(p)
    db.commit()


@router.post("/{project_id}/assign", response_model=ProjectOut)
def assign_prints(project_id: int, body: dict, db: Session = Depends(get_db)):
    """Assign a list of print job IDs to this project."""
    p = _load_project(db, project_id)
    job_ids: list[int] = body.get("job_ids", [])
    for job_id in job_ids:
        job = db.get(PrintJob, job_id)
        if not job:
            raise HTTPException(404, f"Print job {job_id} not found")
        job.fm_project_id = project_id
        # Upsert into project_print join table
        pp = db.query(ProjectPrint).filter_by(project_id=project_id, print_job_id=job_id).first()
        if not pp:
            db.add(ProjectPrint(project_id=project_id, print_job_id=job_id, is_test_print=False))
    db.commit()
    return _project_out(_load_project(db, project_id))


@router.post("/{project_id}/unassign", response_model=ProjectOut)
def unassign_prints(project_id: int, body: dict, db: Session = Depends(get_db)):
    """Remove a list of print job IDs from this project."""
    p = _load_project(db, project_id)
    job_ids: list[int] = body.get("job_ids", [])
    for job_id in job_ids:
        job = db.get(PrintJob, job_id)
        if job and job.fm_project_id == project_id:
            job.fm_project_id = None
        pp = db.query(ProjectPrint).filter_by(project_id=project_id, print_job_id=job_id).first()
        if pp:
            db.delete(pp)
    db.commit()
    return _project_out(_load_project(db, project_id))


class PrintFlagUpdate(BaseModel):
    is_test_print: bool


@router.patch("/{project_id}/prints/{print_id}", response_model=ProjectOut)
def update_project_print(
    project_id: int, print_id: int, body: PrintFlagUpdate, db: Session = Depends(get_db)
):
    """Toggle the is_test_print flag for a print job within a project."""
    pp = db.query(ProjectPrint).filter_by(project_id=project_id, print_job_id=print_id).first()
    if not pp:
        raise HTTPException(404, "Print not assigned to this project")
    pp.is_test_print = body.is_test_print
    db.commit()
    return _project_out(_load_project(db, project_id))
