"""Job-related API routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.deps import get_current_user, get_db
from backend.api.schemas import (
    JobListResponse,
    JobResponse,
    JobSearchRequest,
    JobStatsResponse,
)
from backend.models.database import Job, Source

router = APIRouter()


def _job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location or "",
        country=job.country or "",
        remote=job.remote,
        salary=f"{job.salary_min or ''}-{job.salary_max or ''} {job.salary_currency or ''}".strip(),
        description=job.description or "",
        url=job.application_url or "",
        source=job.source.name if job.source else "",
        skills=job.skills_list,
        experience=job.experience_level or "",
        posted_at=job.posted_at,
        fetched_at=job.scraped_at,
    )


@router.get("/stats", response_model=JobStatsResponse)
async def get_job_stats(db: AsyncSession = Depends(get_db)) -> JobStatsResponse:
    total = (await db.execute(select(sa_func.count(Job.id)))).scalar() or 0

    by_source_rows = (
        await db.execute(
            select(Source.name, sa_func.count(Job.id))
            .join(Job, Job.source_id == Source.id)
            .group_by(Source.name)
        )
    ).all()
    by_source = {name: count for name, count in by_source_rows}

    by_country_rows = (
        await db.execute(
            select(Job.country, sa_func.count(Job.id))
            .group_by(Job.country)
        )
    ).all()
    by_country = {(c or "Unknown"): count for c, count in by_country_rows}

    avg_risk = (await db.execute(select(sa_func.avg(Job.risk_score)))).scalar() or 0.0
    avg_match = (await db.execute(select(sa_func.avg(Job.match_score)))).scalar() or 0.0

    return JobStatsResponse(
        total_jobs=total,
        by_source=by_source,
        by_country=by_country,
        by_remote={},
        avg_risk_score=round(float(avg_risk), 2),
        avg_match_score=round(float(avg_match), 2),
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    source: str | None = Query(None),
    country: str | None = Query(None),
    remote: bool | None = Query(None),
    salary_min: float | None = Query(None),
    match_score_min: float | None = Query(None),
    risk_level: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    filters = {
        "source": source, "country": country, "remote": remote,
        "salary_min": salary_min, "match_score_min": match_score_min,
        "risk_level": risk_level,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    query = select(Job).options(selectinload(Job.source))
    count_query = select(sa_func.count(Job.id))

    if source:
        query = query.join(Source).where(Source.name == source)
        count_query = count_query.join(Source).where(Source.name == source)
    if country:
        query = query.where(Job.country == country)
        count_query = count_query.where(Job.country == country)
    if remote is not None:
        query = query.where(Job.remote == remote)
        count_query = count_query.where(Job.remote == remote)
    if salary_min is not None:
        query = query.where(Job.salary_min >= int(salary_min))
        count_query = count_query.where(Job.salary_min >= int(salary_min))
    if match_score_min is not None:
        query = query.where(Job.match_score >= match_score_min)
        count_query = count_query.where(Job.match_score >= match_score_min)
    if risk_level:
        query = query.where(Job.risk_level == risk_level)
        count_query = count_query.where(Job.risk_level == risk_level)

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(Job.created_at.desc()).offset(offset).limit(page_size))
    db_jobs = result.scalars().all()

    return JobListResponse(
        jobs=[_job_to_response(j) for j in db_jobs],
        total=total,
        page=page,
        page_size=page_size,
        filters_applied=filters,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> JobResponse:
    result = await db.execute(select(Job).options(selectinload(Job.source)).where(Job.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _job_to_response(job)


@router.post("/search", response_model=JobListResponse)
async def search_jobs(
    request: JobSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    query = select(Job).options(selectinload(Job.source))
    count_query = select(sa_func.count(Job.id))
    pattern = f"%{request.query}%"

    query = query.where(Job.title.ilike(pattern) | Job.description.ilike(pattern) | Job.company.ilike(pattern))
    count_query = count_query.where(Job.title.ilike(pattern) | Job.description.ilike(pattern) | Job.company.ilike(pattern))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (request.page - 1) * request.page_size
    result = await db.execute(query.order_by(Job.created_at.desc()).offset(offset).limit(request.page_size))
    db_jobs = result.scalars().all()

    return JobListResponse(
        jobs=[_job_to_response(j) for j in db_jobs],
        total=total,
        page=request.page,
        page_size=request.page_size,
        filters_applied={"query": request.query},
    )


@router.post("/{job_id}/analyze", response_model=JobResponse)
async def analyze_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> JobResponse:
    result = await db.execute(select(Job).options(selectinload(Job.source)).where(Job.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    from backend.risk.engine import RiskEngine
    risk = RiskEngine().analyze({
        "title": job.title,
        "company": job.company,
        "location": job.location or "",
        "description": job.description or "",
        "url": job.application_url or "",
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
    })
    job.risk_score = risk["risk_score"]
    job.risk_level = risk["risk_level"]
    job.risk_flags_list = risk["risk_flags"]
    job.analyzed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)

    return _job_to_response(job)
