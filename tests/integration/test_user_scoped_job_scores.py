"""Personalized job list, ranking, and analytics must use the request owner."""

from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI

from backend.api import deps as api_deps
from backend.api.routes import analytics, jobs
from backend.models.database import Candidate, CandidateJobScore, Database, Job, Source, User
from backend.security import create_access_token


def _run(coro):
    return asyncio.run(coro)


def test_job_scores_are_scoped_for_api_filter_order_and_analytics(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'personalized_scores.db'}")
    _run(db.init_db())

    async def seed():
        async with db.async_session_factory() as session:
            alice = User(email="alice-score@example.com", hashed_password="x")
            bob = User(email="bob-score@example.com", hashed_password="x")
            source = Source(name="fixture", url="https://fixture.example")
            session.add_all([alice, bob, source])
            await session.flush()
            alice_candidate = Candidate(user_id=alice.id, name="Alice", email=alice.email)
            bob_candidate = Candidate(user_id=bob.id, name="Bob", email=bob.email)
            session.add_all([alice_candidate, bob_candidate])
            await session.flush()
            jobs_rows = [
                Job(source_id=source.id, source_job_id="a", title="Job A", company="Acme"),
                Job(source_id=source.id, source_job_id="b", title="Job B", company="Acme"),
            ]
            session.add_all(jobs_rows)
            await session.flush()
            session.add_all([
                CandidateJobScore(candidate_id=alice_candidate.id, job_id=jobs_rows[0].id, score=0.9, breakdown='{"skills": 0.9}'),
                CandidateJobScore(candidate_id=alice_candidate.id, job_id=jobs_rows[1].id, score=0.2, breakdown='{"skills": 0.2}'),
                CandidateJobScore(candidate_id=bob_candidate.id, job_id=jobs_rows[0].id, score=0.1, breakdown='{"skills": 0.1}'),
                CandidateJobScore(candidate_id=bob_candidate.id, job_id=jobs_rows[1].id, score=0.95, breakdown='{"skills": 0.95}'),
            ])
            await session.commit()
            return alice.id, bob.id, jobs_rows[0].id, jobs_rows[1].id

    alice_id, bob_id, job_a, job_b = _run(seed())
    app = FastAPI()
    app.include_router(jobs.router, prefix="/jobs")
    app.include_router(analytics.router, prefix="/analytics")
    old_db = api_deps._db
    api_deps.set_db(db)

    async def requests():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            alice_headers = {"Authorization": f"Bearer {create_access_token({'sub': 'alice-score@example.com', 'user_id': alice_id})}"}
            bob_headers = {"Authorization": f"Bearer {create_access_token({'sub': 'bob-score@example.com', 'user_id': bob_id})}"}
            return (
                await client.get("/jobs", headers=alice_headers),
                await client.get("/jobs", headers=bob_headers),
                await client.get("/jobs?match_score_min=0.5", headers=alice_headers),
                await client.get("/jobs/stats", headers=alice_headers),
                await client.get("/analytics/matches", headers=alice_headers),
                await client.get("/jobs"),
                await client.get(f"/jobs/{job_a}"),
            )

    try:
        alice_list, bob_list, filtered, stats, distribution, anonymous, anonymous_detail = _run(requests())
        assert [job["id"] for job in alice_list.json()["jobs"]] == [job_a, job_b]
        assert [job["id"] for job in bob_list.json()["jobs"]] == [job_b, job_a]
        assert alice_list.json()["jobs"][0]["match_score"] == 0.9
        assert bob_list.json()["jobs"][0]["match_score"] == 0.95
        assert alice_list.json()["jobs"][0]["match_breakdown"] == {"skills": 0.9}
        assert [job["id"] for job in filtered.json()["jobs"]] == [job_a]
        assert stats.json()["avg_match_score"] == 0.55
        assert distribution.json()["excellent"] == 1
        assert distribution.json()["poor"] == 1
        assert anonymous.status_code == 200
        assert all(job["match_score"] is None and job["match_breakdown"] == {} for job in anonymous.json()["jobs"])
        assert anonymous_detail.json()["match_score"] is None
    finally:
        api_deps._db = old_db
        _run(db.close())
