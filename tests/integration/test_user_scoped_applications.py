"""Regression coverage for candidate ownership in application APIs."""

from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from backend.api import deps as api_deps
from backend.api.routes import analytics, applications
from backend.models.database import Application, Candidate, Database, Job, Source, User
from backend.security import create_access_token, hash_password


def _run(coro):
    return asyncio.run(coro)


def test_application_reads_updates_and_analytics_are_user_scoped(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'user_scope.db'}")
    _run(db.init_db())

    async def seed():
        async with db.async_session_factory() as session:
            alice = User(email="alice@example.com", hashed_password=hash_password("password123"))
            bob = User(email="bob@example.com", hashed_password=hash_password("password123"))
            session.add_all([alice, bob])
            await session.flush()
            alice_candidate = Candidate(user_id=alice.id, name="Alice", email="alice-contact@example.com")
            bob_candidate = Candidate(user_id=bob.id, name="Bob", email="bob-contact@example.com")
            source = Source(name="fixture", url="https://fixture.example")
            session.add_all([alice_candidate, bob_candidate, source])
            await session.flush()
            job_a = Job(source_id=source.id, source_job_id="a", title="Engineer A", company="A")
            job_b = Job(source_id=source.id, source_job_id="b", title="Engineer B", company="B")
            session.add_all([job_a, job_b])
            await session.flush()
            app_a = Application(candidate_id=alice_candidate.id, job_id=job_a.id, status="shortlisted")
            app_b = Application(candidate_id=bob_candidate.id, job_id=job_b.id, status="applied")
            session.add_all([app_a, app_b])
            await session.commit()
            return {
                "alice_id": alice.id, "alice_app": app_a.id,
                "bob_app": app_b.id, "bob_status": app_b.status,
            }

    ids = _run(seed())
    alice_token = create_access_token({"sub": "alice@example.com", "user_id": ids["alice_id"]})
    app = FastAPI()
    app.include_router(applications.router, prefix="/applications")
    app.include_router(analytics.router, prefix="/analytics")
    old_db = api_deps._db
    api_deps.set_db(db)

    async def requests():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {alice_token}"}
            return (
                await client.get("/applications", headers=headers),
                await client.get("/applications/stats", headers=headers),
                await client.get(f"/applications/{ids['bob_app']}", headers=headers),
                await client.patch(f"/applications/{ids['bob_app']}", headers=headers, json={"status": "rejected"}),
                await client.get("/analytics/overview", headers=headers),
                await client.get("/analytics/applications", headers=headers),
                await client.get("/analytics/sources", headers=headers),
            )

    try:
        listing, stats, bob_get, bob_patch, overview, funnel, sources = _run(requests())
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()] == [ids["alice_app"]]
        assert stats.json()["total"] == 1
        assert bob_get.status_code == 404
        assert bob_patch.status_code == 404
        assert overview.json()["total_applications"] == 1
        assert overview.json()["total_shortlisted"] == 1
        assert funnel.json()["shortlisted"] == 1
        assert funnel.json()["applied"] == 0
        assert sources.json()[0]["application_count"] == 1

        async def verify_unchanged():
            async with db.async_session_factory() as session:
                record = await session.get(Application, ids["bob_app"])
                assert record.status == ids["bob_status"]
        _run(verify_unchanged())
    finally:
        api_deps._db = old_db
        _run(db.close())


def test_application_creation_uses_user_id_not_contact_email(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'candidate_email.db'}")
    _run(db.init_db())

    async def seed():
        async with db.async_session_factory() as session:
            user = User(email="account@example.com", hashed_password=hash_password("password123"))
            source = Source(name="fixture", url="https://fixture.example")
            session.add_all([user, source])
            await session.flush()
            candidate = Candidate(user_id=user.id, name="Account holder", email="contact@example.com")
            job = Job(source_id=source.id, source_job_id="job", title="Engineer", company="Acme")
            session.add_all([candidate, job])
            await session.commit()
            return user.id, job.id

    user_id, job_id = _run(seed())
    token = create_access_token({"sub": "account@example.com", "user_id": user_id})
    app = FastAPI()
    app.include_router(applications.router, prefix="/applications")
    old_db = api_deps._db
    api_deps.set_db(db)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/applications", headers={"Authorization": f"Bearer {token}"},
                json={"job_id": job_id, "risk_score": 35},
            )

    try:
        response = _run(request())
        assert response.status_code == 201
        assert response.json()["company"] == "Acme"
    finally:
        api_deps._db = old_db
        _run(db.close())


def test_production_settings_require_signing_and_cv_encryption_keys():
    import base64
    import pytest
    from pydantic import ValidationError
    from backend.config import Settings

    with pytest.raises(ValidationError):
        Settings(app_env="production", secret_key="")
    with pytest.raises(ValidationError):
        Settings(app_env="production", secret_key="change-me")
    with pytest.raises(ValidationError):
        Settings(app_env="production", secret_key="too-short")
    with pytest.raises(ValidationError):
        Settings(app_env="production", secret_key="s" * 48)
    encryption_key = base64.urlsafe_b64encode(b"e" * 32).decode()
    configured = Settings(app_env="production", secret_key="s" * 48, encryption_key=encryption_key)
    assert configured.encryption_key == encryption_key
    assert Settings(app_env="development", secret_key="").secret_key != "change-me"
