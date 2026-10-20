"""Unit and integration tests for authentication and route security (Phase 1)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import pytest
from fastapi import FastAPI
import httpx

from backend.api import deps as api_deps
from backend.api.routes import auth as auth_routes
from backend.models.database import Database, User
from backend.security import create_access_token, hash_password


def _run(coro):
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def _setup_test_app(tmp_path):
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/auth")
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'auth_test.db'}")
    _run(db.init_db())
    return app, db


def test_auth_registration_and_login(tmp_path):
    app, db = _setup_test_app(tmp_path)
    original_db = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            # 1. Register a new user
            reg_res = await client.post(
                "/auth/register",
                json={"email": "newuser@example.com", "password": "securepassword123"},
            )
            # 2. Duplicate registration fails
            dup_res = await client.post(
                "/auth/register",
                json={"email": "newuser@example.com", "password": "securepassword123"},
            )
            # 3. Login with wrong password fails
            wrong_res = await client.post(
                "/auth/login",
                json={"email": "newuser@example.com", "password": "wrongpassword"},
            )
            # 4. Login with correct password succeeds
            login_res = await client.post(
                "/auth/login",
                json={"email": "newuser@example.com", "password": "securepassword123"},
            )
            token = login_res.json()["access_token"]
            # 5. Access protected /auth/me with token
            me_res = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        return reg_res, dup_res, wrong_res, login_res, me_res

    try:
        reg, dup, wrong, login, me = _run(scenario())
    finally:
        api_deps._db = original_db
        _run(db.close())

    assert reg.status_code == 201
    assert "access_token" in reg.json()
    assert dup.status_code == 400
    assert wrong.status_code == 401
    assert login.status_code == 200
    assert me.status_code == 200
    assert me.json()["email"] == "newuser@example.com"


def test_auth_token_rejection_cases(tmp_path):
    app, db = _setup_test_app(tmp_path)
    original_db = api_deps._db
    api_deps.set_db(db)

    async def seed():
        async with db.async_session_factory() as session:
            user = User(
                email="active@example.com",
                hashed_password=hash_password("password123"),
                is_active=True,
            )
            inactive = User(
                email="inactive@example.com",
                hashed_password=hash_password("password123"),
                is_active=False,
            )
            session.add_all([user, inactive])
            await session.commit()

    _run(seed())

    valid_token = create_access_token({"sub": "active@example.com"})
    expired_token = create_access_token(
        {"sub": "active@example.com"}, expires_delta=timedelta(seconds=-60)
    )
    tampered_token = valid_token[:-4] + "abcd"
    unknown_user_token = create_access_token({"sub": "ghost@example.com"})
    inactive_user_token = create_access_token({"sub": "inactive@example.com"})

    async def scenario():
        async with _client(app) as client:
            missing_auth = await client.get("/auth/me")
            bad_header_format = await client.get(
                "/auth/me", headers={"Authorization": "NotBearer some-token"}
            )
            empty_token = await client.get(
                "/auth/me", headers={"Authorization": "Bearer "}
            )
            expired_res = await client.get(
                "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
            )
            tampered_res = await client.get(
                "/auth/me", headers={"Authorization": f"Bearer {tampered_token}"}
            )
            unknown_res = await client.get(
                "/auth/me", headers={"Authorization": f"Bearer {unknown_user_token}"}
            )
            inactive_res = await client.get(
                "/auth/me", headers={"Authorization": f"Bearer {inactive_user_token}"}
            )
            valid_res = await client.get(
                "/auth/me", headers={"Authorization": f"Bearer {valid_token}"}
            )
        return (
            missing_auth,
            bad_header_format,
            empty_token,
            expired_res,
            tampered_res,
            unknown_res,
            inactive_res,
            valid_res,
        )

    try:
        (
            missing_auth,
            bad_header_format,
            empty_token,
            expired_res,
            tampered_res,
            unknown_res,
            inactive_res,
            valid_res,
        ) = _run(scenario())
    finally:
        api_deps._db = original_db
        _run(db.close())

    assert missing_auth.status_code == 401
    assert bad_header_format.status_code == 401
    assert empty_token.status_code == 401
    assert expired_res.status_code == 401
    assert tampered_res.status_code == 401
    assert unknown_res.status_code == 401
    assert inactive_res.status_code == 401
    assert valid_res.status_code == 200
    assert valid_res.json()["email"] == "active@example.com"
