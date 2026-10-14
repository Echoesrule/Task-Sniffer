"""Tests for candidate/job match scoring (backend.matching.scoring)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy import select, func as sa_func

from backend.matching.scoring import (
    DEFAULT_USER_EMAIL,
    candidate_to_scoring_dict,
    ensure_default_candidate,
    job_to_scoring_dict,
    load_candidate,
    score_job,
)
from backend.models.database import Candidate, Database, User


def _run(coro):
    return asyncio.run(coro)


def test_default_candidate_created_and_idempotent(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'c1.db'}")
    _run(db.init_db())

    async def scenario():
        async with db.async_session_factory() as session:
            first = await ensure_default_candidate(session)
            await session.commit()
            second = await ensure_default_candidate(session)
            await session.commit()
            users = (await session.execute(select(sa_func.count(User.id)))).scalar()
            candidates = (await session.execute(select(sa_func.count(Candidate.id)))).scalar()
            loaded = await load_candidate(session)
            return first.id, second.id, users, candidates, loaded.id if loaded else None

    first_id, second_id, users, candidates, loaded_id = _run(scenario())
    _run(db.close())

    assert first_id == second_id == loaded_id
    assert users == 1
    assert candidates == 1


def test_candidate_to_scoring_dict_shape(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'c2.db'}")
    _run(db.init_db())

    async def scenario():
        async with db.async_session_factory() as session:
            candidate = await ensure_default_candidate(session)
            await session.commit()
            return candidate_to_scoring_dict(candidate)

    mapping = _run(scenario())
    _run(db.close())

    assert mapping["skills"]
    assert mapping["preferred_roles"]
    assert mapping["location_preferences"]["remote"] is True
    assert isinstance(mapping["projects"], list)


def test_score_job_produces_breakdown():
    job = SimpleNamespace(
        id="j1",
        skills_list=["python", "docker"],
        experience_level="mid",
        title="Backend Engineer",
        location="Remote",
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        posted_at=None,
    )
    candidate = {
        "skills": ["python", "docker"],
        "experience_level": "mid",
        "preferred_roles": ["backend engineer"],
        "location_preferences": {"cities": ["Remote"], "countries": [], "relocate": True, "remote": True},
        "salary_preferences": {"min": None, "max": None},
        "projects": [],
    }

    result = score_job(job, candidate)

    assert 0.0 <= result["score"] <= 1.0
    assert result["score"] > 0.0
    assert {"skills", "experience", "role", "location", "salary",
            "freshness", "source_quality"} <= set(result["breakdown"])
    # exact skill overlap should score well above the 0.5 neutral baseline
    assert result["breakdown"]["skills"] > 0.5


def test_job_to_scoring_dict_serializes_posted_at():
    from datetime import datetime, timezone

    job = SimpleNamespace(
        id="j2",
        skills_list=[],
        experience_level=None,
        title="Analyst",
        location="Nairobi",
        salary_min=1000,
        salary_max=2000,
        salary_currency="USD",
        posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    mapping = job_to_scoring_dict(job)
    assert mapping["posted_at"].startswith("2026-01-01")
    assert mapping["salary_currency"] == "USD"
