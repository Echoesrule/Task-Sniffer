"""Application management routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.api.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatsResponse,
    ApplicationUpdate,
)
from backend.models.database import Application, ApplicationStatusChange, Candidate, Job

router = APIRouter()


def _app_to_response(a: Application) -> ApplicationResponse:
    return ApplicationResponse(
        id=a.id,
        job_id=a.job_id,
        status=a.status,
        notes=a.notes or "",
        match_score=a.match_score,
        risk_score=a.risk_score,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


@router.get("/stats", response_model=ApplicationStatsResponse)
async def get_application_stats(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> ApplicationStatsResponse:
    result = await db.execute(select(Application))
    apps = result.scalars().all()

    total = len(apps)
    by_status = {}
    for a in apps:
        by_status[a.status] = by_status.get(a.status, 0) + 1

    match_scores = [a.match_score for a in apps if a.match_score is not None]
    risk_scores = [a.risk_score for a in apps if a.risk_score is not None]
    accepted = by_status.get("accepted", 0)
    offered = by_status.get("offered", 0)

    return ApplicationStatsResponse(
        total=total,
        by_status=by_status,
        avg_match_score=round(sum(match_scores) / len(match_scores), 3) if match_scores else 0.0,
        avg_risk_score=round(sum(risk_scores) / len(risk_scores), 3) if risk_scores else 0.0,
        acceptance_rate=round(accepted / offered, 3) if offered > 0 else 0.0,
    )


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> list[ApplicationResponse]:
    query = select(Application)
    if status:
        query = query.where(Application.status == status)
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(Application.created_at.desc()).offset(offset).limit(page_size))
    return [_app_to_response(a) for a in result.scalars().all()]


@router.post("", response_model=ApplicationResponse, status_code=201)
async def create_application(
    application: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> ApplicationResponse:
    job_result = await db.execute(select(Job).where(Job.id == application.job_id))
    job = job_result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {application.job_id} not found")

    user_result = await db.execute(
        select(Candidate).where(Candidate.email == _user["email"])
    )
    candidate = user_result.scalars().first()
    if not candidate:
        raise HTTPException(status_code=400, detail="Create a candidate profile first")

    existing = await db.execute(
        select(Application).where(
            Application.candidate_id == candidate.id,
            Application.job_id == application.job_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Already applied to this job")

    app = Application(
        candidate_id=candidate.id,
        job_id=application.job_id,
        status="shortlisted",
        notes=application.notes,
        match_score=application.match_score,
        risk_score=application.risk_score,
    )
    db.add(app)
    await db.flush()

    change = ApplicationStatusChange(
        application_id=app.id,
        old_status=None,
        new_status="shortlisted",
    )
    db.add(change)
    await db.commit()
    await db.refresh(app)

    return _app_to_response(app)


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: str,
    update: ApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> ApplicationResponse:
    result = await db.execute(select(Application).where(Application.id == application_id))
    app = result.scalars().first()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")

    old_status = app.status

    if update.status:
        app.status = update.status.value if hasattr(update.status, "value") else update.status
        change = ApplicationStatusChange(
            application_id=app.id,
            old_status=old_status,
            new_status=app.status,
            notes=update.notes,
        )
        db.add(change)
    if update.notes is not None:
        app.notes = update.notes

    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)
