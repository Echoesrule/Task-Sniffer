"""Bridge between persisted jobs/candidates and the sync :class:`JobScorer`.

Job *extraction* (skills, risk) already happens at ingestion. This module adds
the missing *matching* step: it maps the ORM ``Job``/``Candidate`` rows to the
plain dicts the scorer expects, scores a job against a candidate, and writes the
result back onto the job row.

The persisted ``match_breakdown`` keys mirror the frontend ``MatchBreakdown``
type (``skills``/``experience``/``role``/``location``/``salary``/``projects``/
``freshness``/``source_quality``) so the job-detail view can render it directly.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Candidate, Job, User
from backend.services.scorer import JobScorer

#: local auth stub resolves every request to this identity (see api/deps.py).
DEFAULT_USER_EMAIL = "user@example.com"

_SCORER = JobScorer()

#: A starter profile so matching is meaningful out of the box. It is a normal
#: ``Candidate`` row and can be edited later via ``POST /candidate/profile``.
DEFAULT_CANDIDATE: dict[str, Any] = {
    "name": "Default Candidate",
    "email": DEFAULT_USER_EMAIL,
    "experience_level": "mid",
    "remote_ok": True,
    "preferred_locations": ["Nairobi", "Remote"],
    "preferred_roles": [
        "software engineer",
        "backend engineer",
        "full stack",
        "full-stack",
        "developer",
        "web developer",
        "data engineer",
    ],
    "skills": [
        "python",
        "javascript",
        "typescript",
        "react",
        "node",
        "sql",
        "postgresql",
        "docker",
        "kubernetes",
        "aws",
        "git",
        "rest api",
        "ci/cd",
        "agile",
        "communication",
        "problem solving",
    ],
    "projects": [
        {
            "name": "E-commerce platform",
            "skills": ["python", "django", "postgresql", "docker", "aws"],
        },
        {
            "name": "Analytics dashboard",
            "skills": ["javascript", "react", "sql", "rest api"],
        },
    ],
}


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


def apply_score(job: Job, result: dict[str, Any]) -> None:
    """Write a scorer result onto the job row (score, breakdown, class)."""
    job.match_score = float(result.get("score", 0.0))
    job.match_breakdown_dict = result.get("breakdown", {}) or {}
    job.classification = result.get("classification")


async def load_candidate(
    session: AsyncSession, email: str = DEFAULT_USER_EMAIL
) -> Candidate | None:
    """Load the candidate profile belonging to ``email`` (if any)."""
    result = await session.execute(
        select(Candidate)
        .join(User, Candidate.user_id == User.id)
        .where(User.email == email)
        .limit(1)
    )
    return result.scalars().first()


async def ensure_default_candidate(session: AsyncSession) -> Candidate:
    """Return the default candidate, creating the user + profile if missing."""
    existing = await load_candidate(session)
    if existing is not None:
        return existing

    user = (
        await session.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
    ).scalars().first()
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL, hashed_password="placeholder")
        session.add(user)
        await session.flush()

    candidate = Candidate(
        user_id=user.id,
        name=DEFAULT_CANDIDATE["name"],
        email=DEFAULT_CANDIDATE["email"],
        skills=json.dumps(DEFAULT_CANDIDATE["skills"]),
        preferred_roles=json.dumps(DEFAULT_CANDIDATE["preferred_roles"]),
        preferred_locations=json.dumps(DEFAULT_CANDIDATE["preferred_locations"]),
        projects=json.dumps(DEFAULT_CANDIDATE["projects"]),
        remote_preference="full" if DEFAULT_CANDIDATE["remote_ok"] else "onsite",
        experience_level=DEFAULT_CANDIDATE["experience_level"],
    )
    session.add(candidate)
    await session.flush()
    return candidate
