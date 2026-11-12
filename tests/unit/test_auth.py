"""Unit and integration tests for authentication and route security (Phase 1)."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi import FastAPI
import httpx
from jose import jwt

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
            # 1. Register a new user. The response is intentionally generic and
            #    does not authenticate or reveal whether the address existed.
            reg_res = await client.post(
                "/auth/register",
                json={"email": "newuser@example.com", "password": "securepassword123"},
            )
            # 2. Duplicate registration returns the same generic response.
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

    assert reg.status_code == 202
    assert "access_token" not in reg.json()
    assert dup.status_code == 202
    assert dup.json() == reg.json()
    assert wrong.status_code == 401
    assert login.status_code == 200
    assert me.status_code == 200
    assert me.json()["email"] == "newuser@example.com"
    assert me.json()["role"] == "user"


def test_registration_rejects_role_escalation_and_weak_passwords(tmp_path):
    app, db = _setup_test_app(tmp_path)
    original_db = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            escalation = await client.post(
                "/auth/register",
                json={
                    "email": "attacker@example.com",
                    "password": "securepassword123",
                    "role": "admin",
                },
            )
            short = await client.post(
                "/auth/register",
                json={"email": "short@example.com", "password": "short1"},
            )
            no_digit = await client.post(
                "/auth/register",
                json={"email": "letters@example.com", "password": "onlylettershere"},
            )
            common = await client.post(
                "/auth/register",
                json={"email": "common@example.com", "password": "password1234"},
            )
        return escalation, short, no_digit, common

    try:
        escalation, short, no_digit, common = _run(scenario())
    finally:
        api_deps._db = original_db
        _run(db.close())

    assert escalation.status_code == 422
    assert short.status_code == 400
    assert no_digit.status_code == 400
    assert common.status_code == 400


def test_logout_revokes_previously_issued_tokens(tmp_path):
    app, db = _setup_test_app(tmp_path)
    original_db = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            await client.post(
                "/auth/register",
                json={"email": "logout@example.com", "password": "securepassword123"},
            )
            login = await client.post(
                "/auth/login",
                json={"email": "logout@example.com", "password": "securepassword123"},
            )
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            before = await client.get("/auth/me", headers=headers)
            logout = await client.post("/auth/logout", headers=headers)
            after = await client.get("/auth/me", headers=headers)
            relogin = await client.post(
                "/auth/login",
                json={"email": "logout@example.com", "password": "securepassword123"},
            )
        return before, logout, after, relogin

    try:
        before, logout, after, relogin = _run(scenario())
    finally:
        api_deps._db = original_db
        _run(db.close())

    assert before.status_code == 200
    assert logout.status_code == 200
    assert after.status_code == 401
    assert relogin.status_code == 200


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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_token_algorithm_confusion_and_foreign_key_are_rejected(tmp_path):
    app, db = _setup_test_app(tmp_path)
    original_db = api_deps._db
    api_deps.set_db(db)

    async def seed():
        async with db.async_session_factory() as session:
            session.add(
                User(
                    email="active@example.com",
                    hashed_password=hash_password("password123"),
                    is_active=True,
                )
            )
            await session.commit()

    _run(seed())

    payload = {
        "sub": "active@example.com",
        "exp": int(
            (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()
        ),
        "ver": 0,
    }
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    unsigned = f"{header}.{body}."
    foreign = jwt.encode(payload, "attacker-controlled-key", algorithm="HS256")

    async def scenario():
        async with _client(app) as client:
            none_alg = await client.get(
                "/auth/me", headers={"Authorization": f"Bearer {unsigned}"}
            )
            wrong_key = await client.get(
                "/auth/me", headers={"Authorization": f"Bearer {foreign}"}
            )
        return none_alg, wrong_key

    try:
        none_alg, wrong_key = _run(scenario())
    finally:
        api_deps._db = original_db
        _run(db.close())

    assert none_alg.status_code == 401
    assert wrong_key.status_code == 401
