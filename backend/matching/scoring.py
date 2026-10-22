"""Bridge between persisted jobs/candidates and the sync :class:`JobScorer`.

Job *extraction* (skills, risk) already happens at ingestion. This module adds
the missing *matching* step: it maps the ORM ``Job``/``Candidate`` rows to the
plain dicts the scorer expects, scores a job against a candidate, and writes the
result into the candidate/job score store without mutating the shared job row.

The persisted score breakdown keys mirror the frontend ``MatchBreakdown``
type (``skills``/``experience``/``role``/``location``/``salary``/``projects``/
``freshness``/``source_quality``) so the job-detail view can render it directly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Candidate, CandidateJobScore, Job
from backend.services.scorer import JobScorer

_SCORER = JobScorer()


def _json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


def candidate_to_scoring_dict(candidate: Candidate) -> dict[str, Any]:
    """Project a ``Candidate`` row onto the scorer's candidate schema."""
    remote = (candidate.remote_preference or "").lower() == "full"
    return {
        "id": candidate.id,
        "skills": candidate.skills_list,
        "experience_level": candidate.experience_level or "",
        "preferred_roles": candidate.preferred_roles_list,
        "location_preferences": {
            "cities": candidate.preferred_locations_list,
            "countries": [],
            "relocate": remote,
            "remote": remote,
        },
        "salary_preferences": {
            "min": candidate.salary_min,
            "max": candidate.salary_max,
        },
        "projects": _json_list(candidate.projects),
    }


def job_to_scoring_dict(job: Job) -> dict[str, Any]:
    """Project a ``Job`` row onto the scorer's job schema."""
    posted = job.posted_at.isoformat() if job.posted_at else ""
    return {
        "id": job.id,
        "skills": job.skills_list,
        "experience_level": job.experience_level or "",
        "title": job.title or "",
        "location": job.location or "",
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency or "",
        "posted_at": posted,
        "source_stats": {},
    }


def score_job(job: Job, candidate: dict[str, Any]) -> dict[str, Any]:
    """Score a job against a candidate scoring-dict; returns the scorer result."""
    return _SCORER.score(job_to_scoring_dict(job), candidate)


async def rescore_candidate(session: AsyncSession, candidate: Candidate) -> int:
    """Recompute a candidate's scores after their profile changes."""
    jobs = (await session.execute(select(Job))).scalars().all()
    candidate_dict = candidate_to_scoring_dict(candidate)
    existing = {
        record.job_id: record
        for record in (await session.execute(
            select(CandidateJobScore).where(CandidateJobScore.candidate_id == candidate.id)
        )).scalars().all()
    }
    for job in jobs:
        store_score(session, candidate, job, score_job(job, candidate_dict), existing.get(job.id))
    return len(jobs)


async def apply_score(
    session: AsyncSession,
    candidate: Candidate,
    job: Job,
    result: dict[str, Any],
) -> CandidateJobScore:
    """Upsert a candidate-specific score without changing shared job data."""
    record = (
        await session.execute(
            select(CandidateJobScore).where(
                CandidateJobScore.candidate_id == candidate.id,
                CandidateJobScore.job_id == job.id,
            )
        )
    ).scalars().first()
    return store_score(session, candidate, job, result, record)


def store_score(
    session: AsyncSession,
    candidate: Candidate,
    job: Job,
    result: dict[str, Any],
    record: CandidateJobScore | None = None,
) -> CandidateJobScore:
    """Set score fields on an existing or new record; callers may batch-load records."""
    if record is None:
        record = CandidateJobScore(candidate_id=candidate.id, job_id=job.id)
        session.add(record)
    record.score = float(result.get("score", 0.0))
    record.breakdown = json.dumps(result.get("breakdown", {}) or {})
    record.classification = result.get("classification")
    record.algorithm_version = "job-scorer-v1"
    record.scored_at = datetime.now(timezone.utc)
    return record


async def load_candidate(session: AsyncSession, user_id: str) -> Candidate | None:
    """Load a candidate by its immutable authenticated user relationship."""
    result = await session.execute(
        select(Candidate).where(Candidate.user_id == user_id)
        .limit(1)
    )
    return result.scalars().first()
