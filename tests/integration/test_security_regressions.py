"""Additional security regression tests.

These cover authorization boundaries, CSRF behaviour, source-inventory
redaction, and rate limiting at the HTTP layer. They complement
``test_api_security.py`` and ``test_security_hardening.py``.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI

from backend.api import deps as api_deps
from backend.api.middleware import CSRFMiddleware
from backend.api.routes import auth as auth_routes
from backend.api.routes import sources as sources_routes
from backend.models.database import Database, Source, User
from backend.security import create_access_token, hash_password


def _run(coro):
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def _db(tmp_path, name="security-regressions.db") -> Database:
    db = Database(f"sqlite+aiosqlite:///{tmp_path / name}")
    _run(db.init_db())
    return db


def _seed_users(db: Database) -> dict[str, str]:
    """Create one admin and one regular account, returning their tokens."""

    async def seed():
        async with db.async_session_factory() as session:
            admin = User(
                email="admin@example.com",
                hashed_password=hash_password("securepassword123"),
                role="admin",
                is_active=True,
            )
            regular = User(
                email="regular@example.com",
                hashed_password=hash_password("securepassword123"),
                role="user",
                is_active=True,
            )
            session.add_all([admin, regular])
            await session.commit()

    _run(seed())
    return {
        "admin": create_access_token({"sub": "admin@example.com"}, token_version=0),
        "regular": create_access_token({"sub": "regular@example.com"}, token_version=0),
    }


def _with_router(router, tmp_path, prefix=""):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    db = _db(tmp_path)
    tokens = _seed_users(db)
    return app, db, tokens


def test_all_source_mutations_require_admin(tmp_path):
    app, db, tokens = _with_router(
        sources_routes.router, tmp_path, prefix="/sources"
    )

    async def seed_source():
        async with db.async_session_factory() as session:
            session.add(
                Source(name="fixture", url="https://fixture.example", source_status="ACTIVE")
            )
            await session.commit()

    _run(seed_source())
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            regular_pause = await client.post(
                "/sources/fixture/pause",
                headers={"Authorization": f"Bearer {tokens['regular']}"},
            )
            regular_resume = await client.post(
                "/sources/fixture/resume",
                headers={"Authorization": f"Bearer {tokens['regular']}"},
            )
            regular_ingest = await client.post(
                "/sources/fixture/ingest",
                headers={"Authorization": f"Bearer {tokens['regular']}"},
                json={"force": True, "limit": 500},
            )
            admin_pause = await client.post(
                "/sources/fixture/pause",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
                params={"reason": "MANUAL"},
            )
            admin_resume = await client.post(
                "/sources/fixture/resume",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
            )
        return regular_pause, regular_resume, regular_ingest, admin_pause, admin_resume

    try:
        regular_pause, regular_resume, regular_ingest, admin_pause, admin_resume = (
            _run(scenario())
        )
    finally:
        api_deps._db = original
        _run(db.close())

    assert regular_pause.status_code == 403
    assert regular_resume.status_code == 403
    assert regular_ingest.status_code == 403
    assert admin_pause.status_code == 200
    assert admin_pause.json()["source_status"] == "PAUSED"
    assert admin_resume.status_code == 200
    assert admin_resume.json()["source_status"] == "ACTIVE"


def test_source_inventory_and_url_stats_require_auth_and_hide_details(tmp_path):
    app, db, tokens = _with_router(
        sources_routes.router, tmp_path, prefix="/sources"
    )

    async def seed_source():
        async with db.async_session_factory() as session:
            session.add(
                Source(
                    name="fixture",
                    url="https://fixture.example",
                    source_status="PAUSED",
                    pause_reason="MANUAL",
                    last_error=(
                        "failed https://user:pass@internal.example/jobs/1 "
                        "reading /srv/app/backend/scraper.py password=hunter2"
                    ),
                )
            )
            await session.commit()

    _run(seed_source())
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            anonymous_list = await client.get("/sources")
            anonymous_urls = await client.get("/sources/fixture/urls")
            regular_list = await client.get(
                "/sources", headers={"Authorization": f"Bearer {tokens['regular']}"}
            )
            regular_urls = await client.get(
                "/sources/fixture/urls",
                headers={"Authorization": f"Bearer {tokens['regular']}"},
            )
            admin_list = await client.get(
                "/sources", headers={"Authorization": f"Bearer {tokens['admin']}"}
            )
        return anonymous_list, anonymous_urls, regular_list, regular_urls, admin_list

    try:
        (
            anonymous_list,
            anonymous_urls,
            regular_list,
            regular_urls,
            admin_list,
        ) = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert anonymous_list.status_code == 401
    assert anonymous_urls.status_code == 401
    assert regular_list.status_code == 200
    assert regular_urls.status_code == 200

    regular_item = next(
        item for item in regular_list.json()["sources"] if item["name"] == "fixture"
    )
    assert regular_item["pause_reason"] is None
    assert regular_item["last_error"] is None

    admin_item = next(
        item for item in admin_list.json()["sources"] if item["name"] == "fixture"
    )
    assert admin_item["pause_reason"] == "MANUAL"
    assert admin_item["last_error"] is not None
    assert "user:pass" not in admin_item["last_error"]
    assert "/srv/app" not in admin_item["last_error"]
    assert "hunter2" not in admin_item["last_error"]


def test_csrf_rejects_mismatch_but_allows_bearer_and_safe_methods(tmp_path):
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)
    app.include_router(auth_routes.router, prefix="/auth")
    db = _db(tmp_path, "csrf.db")

    async def seed():
        async with db.async_session_factory() as session:
            session.add(
                User(
                    email="csrf@example.com",
                    hashed_password=hash_password("securepassword123"),
                    role="user",
                    is_active=True,
                )
            )
            await session.commit()

    _run(seed())
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            login = await client.post(
                "/auth/login",
                json={
                    "email": "csrf@example.com",
                    "password": "securepassword123",
                },
            )
            csrf = login.cookies.get("csrf_token")
            token = login.json()["access_token"]

            safe_get = await client.get("/auth/me")
            wrong = await client.post(
                "/auth/telegram/link-code",
                headers={"X-CSRF-Token": "not-the-cookie-value"},
            )
            missing = await client.post("/auth/telegram/link-code")
            correct = await client.post(
                "/auth/telegram/link-code", headers={"X-CSRF-Token": csrf}
            )

            # Bearer clients are not CSRF-vulnerable and need no double-submit
            # value, even when a stale cookie is also present.
            bearer = await client.post(
                "/auth/telegram/link-code",
                headers={"Authorization": f"Bearer {token}"},
            )
        return login, safe_get, wrong, missing, correct, bearer

    try:
        login, safe_get, wrong, missing, correct, bearer = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert login.status_code == 200
    assert safe_get.status_code == 200
    assert wrong.status_code == 403
    assert missing.status_code == 403
    assert correct.status_code == 200
    assert bearer.status_code == 200


def test_registration_is_rate_limited(tmp_path):
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/auth")
    db = _db(tmp_path, "registration-limit.db")
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            responses = []
            for index in range(7):
                responses.append(
                    await client.post(
                        "/auth/register",
                        json={
                            "email": f"person{index}@example.com",
                            "password": "securepassword123",
                        },
                    )
                )
            return responses

    try:
        responses = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert responses[0].status_code == 202
    limited = [response for response in responses if response.status_code == 429]
    assert limited, [response.status_code for response in responses]
    assert "Retry-After" in limited[0].headers


def test_successful_login_resets_the_account_failure_bucket(tmp_path):
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/auth")
    db = _db(tmp_path, "login-reset.db")

    async def seed():
        async with db.async_session_factory() as session:
            session.add(
                User(
                    email="reset@example.com",
                    hashed_password=hash_password("securepassword123"),
                    role="user",
                    is_active=True,
                )
            )
            await session.commit()

    _run(seed())
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            failures = [
                await client.post(
                    "/auth/login",
                    json={"email": "reset@example.com", "password": "wrongpassword"},
                )
                for _ in range(4)
            ]
            success = await client.post(
                "/auth/login",
                json={
                    "email": "reset@example.com",
                    "password": "securepassword123",
                },
            )
            # The bucket was reset, so five further failures are throttled only
            # on the sixth attempt.
            after_reset = [
                await client.post(
                    "/auth/login",
                    json={"email": "reset@example.com", "password": "wrongpassword"},
                )
                for _ in range(6)
            ]
        return failures, success, after_reset

    try:
        failures, success, after_reset = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert all(response.status_code == 401 for response in failures)
    assert success.status_code == 200
    assert [response.status_code for response in after_reset[:5]] == [401] * 5
    assert after_reset[5].status_code == 429


def test_source_error_rows_are_not_visible_to_non_admins(tmp_path):
    app, db, tokens = _with_router(
        sources_routes.router, tmp_path, prefix="/sources"
    )

    async def seed_source():
        async with db.async_session_factory() as session:
            session.add(
                Source(name="fixture", url="https://fixture.example", source_status="ACTIVE")
            )
            await session.commit()

    _run(seed_source())
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            regular = await client.get(
                "/sources/fixture/errors",
                headers={"Authorization": f"Bearer {tokens['regular']}"},
            )
            admin = await client.get(
                "/sources/fixture/errors",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
            )
        return regular, admin

    try:
        regular, admin = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert regular.status_code == 403
    assert admin.status_code == 200
    assert admin.json() == []
