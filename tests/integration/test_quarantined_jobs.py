"""Data-quality quarantined jobs are hidden from normal listing views."""

from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI

from backend.api import deps as api_deps
from backend.api.routes import jobs
from backend.models.database import Database, Job, Source


def _run(coro):
    return asyncio.run(coro)


def test_quarantined_jobs_are_excluded_unless_requested(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'quarantine.db'}")
    _run(db.init_db())

    async def seed():
        async with db.async_session_factory() as session:
            source = Source(name="fixture", url="https://fixture.example")
            session.add(source)
            await session.flush()
            visible = Job(
                source_id=source.id, source_job_id="visible",
                title="Visible Job", company="Acme", status="discovered",
            )
            hidden = Job(
                source_id=source.id, source_job_id="hidden",
                title="Hidden Job", company="Acme", status="quarantined",
            )
            session.add_all([visible, hidden])
            await session.commit()
            return visible.id, hidden.id

    visible_id, hidden_id = _run(seed())
    app = FastAPI()
    app.include_router(jobs.router, prefix="/jobs")
    old_db = api_deps._db
    api_deps.set_db(db)

    async def requests():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return (
                await client.get("/jobs"),
                await client.get("/jobs?include_quarantined=true"),
                await client.get("/jobs/stats"),
                await client.get("/jobs/stats?include_quarantined=true"),
                await client.post("/jobs/search", json={"query": "Job"}),
                await client.post(
                    "/jobs/search?include_quarantined=true", json={"query": "Job"}
                ),
                await client.get(f"/jobs/{hidden_id}"),
            )

    try:
        (
            default_list, full_list, default_stats, full_stats,
            default_search, full_search, hidden_detail,
        ) = _run(requests())

        assert [job["id"] for job in default_list.json()["jobs"]] == [visible_id]
        assert default_list.json()["total"] == 1
        assert {job["id"] for job in full_list.json()["jobs"]} == {visible_id, hidden_id}

        assert default_stats.json()["total_jobs"] == 1
        assert full_stats.json()["total_jobs"] == 2
        assert default_stats.json()["by_source"] == {"fixture": 1}
        assert full_stats.json()["by_source"] == {"fixture": 2}

        assert [job["id"] for job in default_search.json()["jobs"]] == [visible_id]
        assert {job["id"] for job in full_search.json()["jobs"]} == {visible_id, hidden_id}

        # Direct access by id remains possible for auditing.
        assert hidden_detail.status_code == 200
        assert hidden_detail.json()["status"] == "quarantined"
    finally:
        api_deps._db = old_db
        _run(db.close())
