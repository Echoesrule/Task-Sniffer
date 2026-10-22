"""Analytics routes for dashboard and reporting."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.api.schemas import (
    AnalyticsOverview,
    ApplicationFunnel,
    MatchDistribution,
    SourceStats,
)
from backend.models.database import Application, Candidate, CandidateJobScore, Job, Source

router = APIRouter()


@router.get("/overview", response_model=AnalyticsOverview)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> AnalyticsOverview:
    candidate_ids = select(Candidate.id).where(Candidate.user_id == _user["user_id"])
    total_jobs = (await db.execute(select(sa_func.count(Job.id)))).scalar() or 0
    user_applications = Application.candidate_id.in_(candidate_ids)
    total_apps = (await db.execute(
        select(sa_func.count(Application.id)).where(user_applications)
    )).scalar() or 0

    shortlisted = (await db.execute(
        select(sa_func.count(Application.id)).where(user_applications, Application.status == "shortlisted")
    )).scalar() or 0
    rejected = (await db.execute(
        select(sa_func.count(Application.id)).where(user_applications, Application.status == "rejected")
    )).scalar() or 0

    candidate_id = (await db.execute(
        select(Candidate.id).where(Candidate.user_id == _user["user_id"]).limit(1)
    )).scalar_one_or_none()
    avg_match = (await db.execute(
        select(sa_func.avg(CandidateJobScore.score)).where(CandidateJobScore.candidate_id == candidate_id)
    )).scalar() if candidate_id else None
    avg_risk = (await db.execute(select(sa_func.avg(Job.risk_score)))).scalar() or 0.0

    source_rows = (
        await db.execute(
            select(Source.name, sa_func.count(Job.id))
            .join(Job, Job.source_id == Source.id, isouter=True)
            .group_by(Source.name)
            .order_by(sa_func.count(Job.id).desc())
            .limit(5)
        )
    ).all()

    top_sources = [
        SourceStats(source=name, total_jobs=count)
        for name, count in source_rows
    ]

    return AnalyticsOverview(
        total_jobs=total_jobs,
        total_applications=total_apps,
        total_shortlisted=shortlisted,
        total_rejected=rejected,
        avg_match_score=round(float(avg_match), 3) if avg_match is not None else None,
        avg_risk_score=round(float(avg_risk), 2),
        top_sources=top_sources,
        recent_activity=[],
    )


@router.get("/sources", response_model=list[SourceStats])
async def get_source_stats(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> list[SourceStats]:
    candidate_id = (await db.execute(
        select(Candidate.id).where(Candidate.user_id == _user["user_id"]).limit(1)
    )).scalar_one_or_none()
    job_rows = (
        await db.execute(
            select(Source.name, sa_func.count(Job.id), sa_func.avg(CandidateJobScore.score), sa_func.avg(Job.risk_score))
            .outerjoin(Job, Job.source_id == Source.id)
            .outerjoin(CandidateJobScore, (CandidateJobScore.job_id == Job.id) & (CandidateJobScore.candidate_id == candidate_id))
            .group_by(Source.name)
        )
    ).all()
    candidate_ids = select(Candidate.id).where(Candidate.user_id == _user["user_id"])
    app_rows = (
        await db.execute(
            select(Source.name, sa_func.count(Application.id))
            .join(Job, Job.source_id == Source.id)
            .join(Application, Application.job_id == Job.id)
            .where(Application.candidate_id.in_(candidate_ids))
            .group_by(Source.name)
        )
    ).all()
    app_counts = dict(app_rows)

    return [
        SourceStats(
            source=r.name,
            total_jobs=r[1],
            avg_match_score=float(r[2]) if r[2] is not None else None,
            avg_risk_score=float(r[3] or 0),
            application_count=app_counts.get(r[0], 0),
        )
        for r in job_rows
    ]


@router.get("/matches", response_model=MatchDistribution)
async def get_match_distribution(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> MatchDistribution:
    candidate_id = (await db.execute(
        select(Candidate.id).where(Candidate.user_id == _user["user_id"]).limit(1)
    )).scalar_one_or_none()
    if not candidate_id:
        return MatchDistribution()
    result = await db.execute(
        select(CandidateJobScore.score).where(CandidateJobScore.candidate_id == candidate_id)
    )
    scores = [row[0] for row in result.all() if row[0] is not None]

    if not scores:
        return MatchDistribution()

    excellent = sum(1 for s in scores if s >= 0.8)
    good = sum(1 for s in scores if 0.6 <= s < 0.8)
    fair = sum(1 for s in scores if 0.4 <= s < 0.6)
    poor = sum(1 for s in scores if s < 0.4)
    avg = sum(scores) / len(scores)
    sorted_scores = sorted(scores)
    mid = len(sorted_scores) // 2
    median = sorted_scores[mid] if len(sorted_scores) % 2 else (sorted_scores[mid - 1] + sorted_scores[mid]) / 2

    return MatchDistribution(
        excellent=excellent,
        good=good,
        fair=fair,
        poor=poor,
        avg_score=round(avg, 3),
        median_score=round(median, 3),
    )


@router.get("/applications", response_model=ApplicationFunnel)
async def get_application_funnel(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> ApplicationFunnel:
    candidate_ids = select(Candidate.id).where(Candidate.user_id == _user["user_id"])
    rows = (
        await db.execute(
            select(Application.status, sa_func.count(Application.id))
            .where(Application.candidate_id.in_(candidate_ids))
            .group_by(Application.status)
        )
    ).all()
    status_counts = {status: count for status, count in rows}

    return ApplicationFunnel(
        viewed=status_counts.get("viewed", 0) or status_counts.get("discovered", 0),
        shortlisted=status_counts.get("shortlisted", 0),
        applied=status_counts.get("applied", 0),
        interview=status_counts.get("interview", 0),
        offered=status_counts.get("offered", 0),
        accepted=status_counts.get("accepted", 0),
    )
