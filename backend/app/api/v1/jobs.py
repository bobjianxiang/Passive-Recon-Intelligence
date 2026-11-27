from uuid import UUID
from fastapi import APIRouter, Depends, status, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.job import ReconJob, JobStatus
from app.models.recon import Entity
from app.schemas.job import JobCreateRequest, JobResponse
from app.services.jobs import execute_recon_pipeline
from app.services.entity_validation import is_valid_entity_value
from app.models.recon import ModuleRun

router = APIRouter()

@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreateRequest, 
    background_tasks: BackgroundTasks, 
    db: AsyncSession = Depends(get_db)
):
    new_job = ReconJob(
        target_domain=payload.target_domain,
        selected_modules={"modules": payload.modules},
        status=JobStatus.PENDING
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)

    # Queue background OSINT pipeline execution
    background_tasks.add_task(execute_recon_pipeline, new_job.id)

    return new_job

@router.get("/{job_id}/entities")
async def get_job_entities(job_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Entity).where(Entity.job_id == job_id)
    result = await db.execute(stmt)
    entities = [
        entity for entity in result.scalars().all()
        if is_valid_entity_value(entity.entity_type, entity.canonical_value)
    ]
    return entities

@router.get("/{job_id}/status")
async def get_job_status(job_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(ReconJob).where(ReconJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "target_domain": job.target_domain,
        "status": job.status,
        "created_at": job.created_at
    }

@router.get("/{job_id}/modules")
async def get_job_module_runs(job_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(ModuleRun).where(ModuleRun.job_id == job_id)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return runs
