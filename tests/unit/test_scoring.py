"""Candidate-scoped match scoring regression tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy import select

from backend.matching.scoring import (
    apply_score,
    candidate_to_scoring_dict,
    job_to_scoring_dict,
    load_candidate,
    score_job,
)
from backend.models.database import Candidate, CandidateJobScore, Database, Job, Source, User


def _run(coro):
    return asyncio.run(coro)


def _profile_score(job, skills, roles):
    return score_job(job, {
        "skills": skills,
        "experience_level": "mid",
        "preferred_roles": roles,
        "location_preferences": {"cities": ["Remote"], "countries": [], "relocate": True, "remote": True},
        "salary_preferences": {"min": None, "max": None},
        "projects": [],
    })


def test_candidate_lookup_requires_explicit_user_id(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'identity.db'}")
    _run(db.init_db())

    async def scenario():
        async with db.async_session_factory() as session:
            owner = User(email="one@example.com", hashed_password="x")
            other = User(email="two@example.com", hashed_password="x")
            session.add_all([owner, other])
            await session.flush()
            profile = Candidate(user_id=owner.id, name="One", email="mutable-contact@example.com")
            session.add(profile)
            await session.commit()
            loaded = await load_candidate(session, owner.id)
            absent = await load_candidate(session, other.id)
            return profile.id, loaded.id if loaded else None, absent

    profile_id, loaded_id, absent = _run(scenario())
    _run(db.close())
    assert loaded_id == profile_id
    assert absent is None


def test_two_candidates_keep_independent_scores_for_same_job(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'candidate_scores.db'}")
    _run(db.init_db())

    async def scenario():
        async with db.async_session_factory() as session:
            one = User(email="one@example.com", hashed_password="x")
            two = User(email="two@example.com", hashed_password="x")
            source = Source(name="fixture", url="https://fixture.example")
            session.add_all([one, two, source])
            await session.flush()
            candidate_one = Candidate(user_id=one.id, name="Python profile", email=one.email, skills='["python", "docker"]', preferred_roles='["backend engineer"]')
            candidate_two = Candidate(user_id=two.id, name="Design profile", email=two.email, skills='["figma", "design"]', preferred_roles='["designer"]')
            session.add_all([candidate_one, candidate_two])
            job = Job(source_id=source.id, source_job_id="j1", title="Backend Engineer", company="Acme", skills='["python", "docker"]', experience_level="mid", location="Remote")
            session.add(job)
            await session.flush()

            first = _profile_score(job, ["python", "docker"], ["backend engineer"])
            second = _profile_score(job, ["figma", "design"], ["designer"])
            await apply_score(session, candidate_one, job, first)
            await apply_score(session, candidate_two, job, second)
            await session.commit()

            first_record = (await session.execute(select(CandidateJobScore).where(CandidateJobScore.candidate_id == candidate_one.id))).scalar_one()
            second_record = (await session.execute(select(CandidateJobScore).where(CandidateJobScore.candidate_id == candidate_two.id))).scalar_one()
            second_before = second_record.score

            first["score"] = 0.11
            first["breakdown"] = {"skills": 0.11}
            await apply_score(session, candidate_one, job, first)
            await session.commit()
            await session.refresh(second_record)
            return (first_record.score, first_record.breakdown, second_before, second_record.score,
                    job.match_score, job.match_breakdown_dict)

    first_score, first_breakdown, second_before, second_after, legacy_score, legacy_breakdown = _run(scenario())
    _run(db.close())
    assert first_score == 0.11
    assert first_breakdown == '{"skills": 0.11}'
    assert second_before != first_score
    assert second_after == second_before
    assert legacy_score == 0.0
    assert legacy_breakdown == {}


def test_candidate_to_scoring_dict_shape():
    candidate = Candidate(
        id="c1", user_id="u1", name="Candidate", email="candidate@example.com",
        skills='["python"]', preferred_roles='["backend engineer"]',
        preferred_locations='["Remote"]', remote_preference="full",
    )
    mapping = candidate_to_scoring_dict(candidate)
    assert mapping["skills"] == ["python"]
    assert mapping["preferred_roles"] == ["backend engineer"]
    assert mapping["location_preferences"]["remote"] is True
    assert isinstance(mapping["projects"], list)


def test_score_job_produces_breakdown():
    job = SimpleNamespace(
        id="j1", skills_list=["python", "docker"], experience_level="mid",
        title="Backend Engineer", location="Remote", salary_min=None,
        salary_max=None, salary_currency=None, posted_at=None,
    )
    result = _profile_score(job, ["python", "docker"], ["backend engineer"])
    assert 0.0 <= result["score"] <= 1.0
    assert result["score"] > 0.0
    assert {"skills", "experience", "role", "location", "salary", "freshness", "source_quality"} <= set(result["breakdown"])
    assert result["breakdown"]["skills"] > 0.5


def test_job_to_scoring_dict_serializes_posted_at():
    from datetime import datetime, timezone

    job = SimpleNamespace(
        id="j2", skills_list=[], experience_level=None, title="Analyst", location="Nairobi",
        salary_min=1000, salary_max=2000, salary_currency="USD",
        posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    mapping = job_to_scoring_dict(job)
    assert mapping["posted_at"].startswith("2026-01-01")
    assert mapping["salary_currency"] == "USD"
