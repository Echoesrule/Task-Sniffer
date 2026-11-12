"""Regression coverage for the authentication/session hardening changes."""

from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from backend.api import deps as api_deps
from backend.api.middleware import CSRFMiddleware
from backend.api.routes import auth as auth_routes
from backend.config import Settings
from backend.models.database import Database, TelegramLinkCode, User
from backend.security import hash_password


def _run(coro):
    return asyncio.run(coro)


def _app(tmp_path):
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)
    app.include_router(auth_routes.router, prefix="/auth")
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'security.db'}")
    _run(db.init_db())
    return app, db


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def _seed_user(db: Database, *, email="session@example.com", password="securepassword123"):
    async def _do():
        async with db.async_session_factory() as session:
            session.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    role="user",
                    is_active=True,
                )
            )
            await session.commit()
    _run(_do())


def test_cookie_session_requires_csrf_and_logout_revokes_token(tmp_path):
    app, db = _app(tmp_path)
    _seed_user(db)
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            login = await client.post(
                "/auth/login",
                json={"email": "session@example.com", "password": "securepassword123"},
            )
            cookie_token = login.cookies.get("access_token")
            csrf = login.cookies.get("csrf_token")
            me = await client.get("/auth/me")
            without_csrf = await client.post("/auth/logout")
            with_csrf = await client.post(
                "/auth/logout", headers={"X-CSRF-Token": csrf}
            )
            revoked = await client.get(
                "/auth/me", headers={"Cookie": f"access_token={cookie_token}"}
            )
        return login, me, without_csrf, with_csrf, revoked, cookie_token

    try:
        login, me, without_csrf, with_csrf, revoked, cookie_token = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert login.status_code == 200
    assert cookie_token
    assert me.status_code == 200
    assert me.json()["email"] == "session@example.com"
    assert without_csrf.status_code == 403
    assert with_csrf.status_code == 200
    assert revoked.status_code == 401


def test_login_is_rate_limited(tmp_path):
    app, db = _app(tmp_path)
    _seed_user(db, email="ratelimit@example.com", password="securepassword123")
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            responses = []
            for _ in range(7):
                responses.append(
                    await client.post(
                        "/auth/login",
                        json={
                            "email": "ratelimit@example.com",
                            "password": "wrongpassword",
                        },
                    )
                )
            return responses

    try:
        responses = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert responses[0].status_code == 401
    limited = [r for r in responses if r.status_code == 429]
    assert limited, [r.status_code for r in responses]
    assert "Retry-After" in limited[0].headers


def test_telegram_link_code_is_hashed_single_active_challenge(tmp_path):
    app, db = _app(tmp_path)
    _seed_user(db)
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            login = await client.post(
                "/auth/login",
                json={"email": "session@example.com", "password": "securepassword123"},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            first = await client.post("/auth/telegram/link-code", headers=headers)
            second = await client.post("/auth/telegram/link-code", headers=headers)
            client.cookies.clear()
            anonymous = await client.post("/auth/telegram/link-code")
            return first, second, anonymous

    try:
        first, second, anonymous = _run(scenario())

        async def rows():
            async with db.async_session_factory() as session:
                return (
                    await session.execute(select(TelegramLinkCode))
                ).scalars().all()

        stored = _run(rows())
    finally:
        api_deps._db = original
        _run(db.close())

    assert first.status_code == 200
    assert second.status_code == 200
    assert anonymous.status_code == 401
    assert first.json()["code"] != second.json()["code"]
    assert len(stored) == 1  # the first unused challenge was retired
    assert stored[0].used_at is None
    assert stored[0].code_hash != first.json()["code"]
    assert stored[0].code_hash != second.json()["code"]


def test_login_issues_refresh_cookie_and_refresh_rotates_session(tmp_path):
    app, db = _app(tmp_path)
    _seed_user(db)
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            login = await client.post(
                "/auth/login",
                json={"email": "session@example.com", "password": "securepassword123"},
            )
            access_before = login.cookies.get("access_token")
            refresh_before = login.cookies.get("refresh_token")
            csrf = login.cookies.get("csrf_token")
            refreshed = await client.post(
                "/auth/refresh", headers={"X-CSRF-Token": csrf}
            )
            access_after = refreshed.cookies.get("access_token")
            refresh_after = refreshed.cookies.get("refresh_token")
            me = await client.get("/auth/me")
        return (
            login,
            refreshed,
            access_before,
            refresh_before,
            access_after,
            refresh_after,
            me,
        )

    try:
        (
            login,
            refreshed,
            access_before,
            refresh_before,
            access_after,
            refresh_after,
            me,
        ) = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert login.status_code == 200
    assert access_before
    assert refresh_before
    assert refreshed.status_code == 200
    # Rotation issues a brand new access token and refresh token.
    assert access_after and access_after != access_before
    assert refresh_after and refresh_after != refresh_before
    assert me.status_code == 200
    assert me.json()["email"] == "session@example.com"


def test_refresh_endpoint_rejects_access_token_as_refresh_token(tmp_path):
    app, db = _app(tmp_path)
    _seed_user(db)
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            login = await client.post(
                "/auth/login",
                json={"email": "session@example.com", "password": "securepassword123"},
            )
            access_token = login.cookies.get("access_token")
            # Present the access token where only a refresh token is valid.
            client.cookies.clear()
            return await client.post(
                "/auth/refresh",
                headers={"Cookie": f"refresh_token={access_token}"},
            )

    try:
        rejected = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert rejected.status_code == 401


def test_logout_revokes_refresh_token(tmp_path):
    app, db = _app(tmp_path)
    _seed_user(db)
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            login = await client.post(
                "/auth/login",
                json={"email": "session@example.com", "password": "securepassword123"},
            )
            refresh_token = login.cookies.get("refresh_token")
            csrf = login.cookies.get("csrf_token")
            logout = await client.post(
                "/auth/logout", headers={"X-CSRF-Token": csrf}
            )
            client.cookies.clear()
            rejected = await client.post(
                "/auth/refresh",
                headers={"Cookie": f"refresh_token={refresh_token}"},
            )
        return logout, rejected

    try:
        logout, rejected = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert logout.status_code == 200
    # Logout bumps token_version, so the refresh token cannot mint a new session.
    assert rejected.status_code == 401


def test_refresh_without_cookie_is_rejected(tmp_path):
    app, db = _app(tmp_path)
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            return await client.post("/auth/refresh")

    try:
        rejected = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert rejected.status_code == 401


def test_production_cookie_flags_are_configurable():
    settings = Settings(cookie_secure=True, cookie_samesite="strict")
    assert settings.cookie_secure is True
    assert settings.cookie_samesite == "strict"
    assert settings.cors_origin_list == ["http://localhost:3000"]
