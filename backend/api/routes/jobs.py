"""Job-related API routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sa_func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.deps import get_current_user, get_db, get_optional_current_user
from backend.api.schemas import (
    JobListResponse,
    JobResponse,
    JobSearchRequest,
    JobStatsResponse,
)
from backend.models.database import Candidate, CandidateJobScore, Job, Source

router = APIRouter()


def _job_to_response(job: Job, match: CandidateJobScore | None = None) -> JobResponse:
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
        source_url=job.source_url or "",
        canonical_url=job.canonical_url or "",
        url_status=job.url_status or "",
        skills=job.skills_list,
        skills_required=job.skills_required_list,
        skills_preferred=job.skills_preferred_list,
        skills_detail=job.skills_detail_list,
        experience=job.experience_level or "",
        posted_at=job.posted_at,
        fetched_at=job.scraped_at,
        match_score=match.score if match else None,
        match_breakdown=json.loads(match.breakdown) if match and match.breakdown else {},
        classification=match.classification if match else None,
        risk_score=job.risk_score or 0.0,
        risk_level=job.risk_level or None,
        status=job.status or "discovered",
    )


async def _candidate_id(db: AsyncSession, user_id: str) -> str | None:
    return (
        await db.execute(select(Candidate.id).where(Candidate.user_id == user_id).limit(1))
    ).scalar_one_or_none()


@router.get("/stats", response_model=JobStatsResponse)
async def get_job_stats(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> JobStatsResponse:
    candidate_id = await _candidate_id(db, user["user_id"]) if user else None
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
    avg_match = (await db.execute(select(sa_func.avg(CandidateJobScore.score)).where(CandidateJobScore.candidate_id == candidate_id))).scalar() if candidate_id else 0.0
    strong_matches = (await db.execute(
        select(sa_func.count(CandidateJobScore.id)).where(
            CandidateJobScore.candidate_id == candidate_id,
            CandidateJobScore.score >= 0.75,
        )
    )).scalar() if candidate_id else 0
    latest_created = (await db.execute(select(sa_func.max(Job.created_at)))).scalar()

    return JobStatsResponse(
        total_jobs=total,
        by_source=by_source,
        by_country=by_country,
        by_remote={},
        avg_risk_score=round(float(avg_risk), 2),
        avg_match_score=round(float(avg_match), 2) if avg_match is not None else None,
        strong_matches=strong_matches,
        latest_created_at=latest_created,
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
    user: dict | None = Depends(get_optional_current_user),
) -> JobListResponse:
    candidate_id = await _candidate_id(db, user["user_id"]) if user else None
    filters = {
        "source": source, "country": country, "remote": remote,
        "salary_min": salary_min, "match_score_min": match_score_min,
        "risk_level": risk_level,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    score_join = and_(CandidateJobScore.job_id == Job.id, CandidateJobScore.candidate_id == candidate_id)
    query = select(Job, CandidateJobScore).outerjoin(CandidateJobScore, score_join).options(selectinload(Job.source))
    count_query = select(sa_func.count(Job.id)).outerjoin(CandidateJobScore, score_join)

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
        query = query.where(CandidateJobScore.score >= match_score_min)
        count_query = count_query.where(CandidateJobScore.score >= match_score_min)
    if risk_level:
        query = query.where(Job.risk_level == risk_level)
        count_query = count_query.where(Job.risk_level == risk_level)

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(CandidateJobScore.score.desc().nullslast(), Job.created_at.desc()).offset(offset).limit(page_size))
    db_jobs = result.all()

    return JobListResponse(
        jobs=[_job_to_response(job, score) for job, score in db_jobs],
        total=total,
        page=page,
        page_size=page_size,
        filters_applied=filters,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> JobResponse:
    candidate_id = await _candidate_id(db, user["user_id"]) if user else None
    result = await db.execute(
        select(Job, CandidateJobScore)
        .outerjoin(CandidateJobScore, and_(CandidateJobScore.job_id == Job.id, CandidateJobScore.candidate_id == candidate_id))
        .options(selectinload(Job.source)).where(Job.id == job_id)
    )
    row = result.first()
    job, score = row if row else (None, None)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _job_to_response(job, score)


@router.post("/search", response_model=JobListResponse)
async def search_jobs(
    request: JobSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> JobListResponse:
    candidate_id = await _candidate_id(db, user["user_id"]) if user else None
    score_join = and_(CandidateJobScore.job_id == Job.id, CandidateJobScore.candidate_id == candidate_id)
    query = select(Job, CandidateJobScore).outerjoin(CandidateJobScore, score_join).options(selectinload(Job.source))
    count_query = select(sa_func.count(Job.id)).outerjoin(CandidateJobScore, score_join)
    pattern = f"%{request.query}%"

    query = query.where(Job.title.ilike(pattern) | Job.description.ilike(pattern) | Job.company.ilike(pattern))
    count_query = count_query.where(Job.title.ilike(pattern) | Job.description.ilike(pattern) | Job.company.ilike(pattern))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (request.page - 1) * request.page_size
    result = await db.execute(query.order_by(CandidateJobScore.score.desc().nullslast(), Job.created_at.desc()).offset(offset).limit(request.page_size))
    db_jobs = result.all()

    return JobListResponse(
        jobs=[_job_to_response(job, score) for job, score in db_jobs],
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

    candidate_id = await _candidate_id(db, _user["user_id"])
    score = None
    if candidate_id:
        score = (await db.execute(select(CandidateJobScore).where(
            CandidateJobScore.candidate_id == candidate_id,
            CandidateJobScore.job_id == job.id,
        ))).scalars().first()
    return _job_to_response(job, score)
