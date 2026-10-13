"""Phase 5 API security regression tests.

Cover the confirmed defects fixed during the production-readiness review:
authenticated source mutations, CV upload path-traversal / type / size gating,
and the CORS credential policy.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi import FastAPI

from backend.api import deps as api_deps
from backend.api.routes import candidates as candidates_routes
from backend.api.routes import sources as sources_routes
from backend.config import Settings
from backend.models.database import Database


def _run(coro):
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def _with_app(router, tmp_path, prefix=""):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'api.db'}")
    _run(db.init_db())
    return app, db


def test_cv_upload_sanitizes_filename_and_stays_in_storage(tmp_path, monkeypatch):
    app, db = _with_app(candidates_routes.router, tmp_path)
    storage = tmp_path / "cvs"
    monkeypatch.setattr(
        candidates_routes,
        "get_settings",
        lambda: Settings(cv_storage_path=str(storage)),
    )
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            return await client.post(
                "/cv",
                headers={"Authorization": "Bearer test-token"},
                files={"file": ("../../evil.pdf", b"%PDF-1.4 payload", "application/pdf")},
            )

    try:
        response = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert response.status_code == 200
    stored = list(storage.iterdir())
    assert len(stored) == 1
    name = stored[0].name
    assert name.endswith(".pdf")
    assert "evil" not in name and ".." not in name
    assert stored[0].parent == storage
    # nothing escaped the storage directory
    assert not (tmp_path.parent / "evil.pdf").exists()
    assert not (tmp_path / "evil.pdf").exists()


def test_cv_upload_rejects_bad_extension(tmp_path, monkeypatch):
    app, db = _with_app(candidates_routes.router, tmp_path)
    monkeypatch.setattr(
        candidates_routes,
        "get_settings",
        lambda: Settings(cv_storage_path=str(tmp_path / "cvs")),
    )
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            return await client.post(
                "/cv",
                headers={"Authorization": "Bearer test-token"},
                files={"file": ("payload.sh", b"#!/bin/sh", "application/pdf")},
            )

    try:
        response = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert response.status_code == 400


def test_cv_upload_rejects_oversized_file(tmp_path, monkeypatch):
    app, db = _with_app(candidates_routes.router, tmp_path)
    monkeypatch.setattr(
        candidates_routes,
        "get_settings",
        lambda: Settings(cv_storage_path=str(tmp_path / "cvs")),
    )
    monkeypatch.setattr(candidates_routes, "MAX_CV_BYTES", 16)
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            return await client.post(
                "/cv",
                headers={"Authorization": "Bearer test-token"},
                files={"file": ("cv.pdf", b"x" * 64, "application/pdf")},
            )

    try:
        response = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert response.status_code == 413


def test_source_mutation_requires_token(tmp_path):
    app, db = _with_app(sources_routes.router, tmp_path, prefix="/sources")
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            missing = await client.post("/sources/fakesrc/resume")
            empty = await client.post(
                "/sources/fakesrc/resume", headers={"Authorization": "Bearer "}
            )
        return missing, empty

    try:
        missing, empty = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert missing.status_code == 401
    assert empty.status_code == 401


def test_cors_does_not_allow_credentials_with_wildcard():
    from backend.api.app import create_app

    app = create_app()
    cors = [
        m
        for m in app.user_middleware
        if m.cls.__name__ == "CORSMiddleware"
    ]
    assert cors, "CORS middleware not configured"
    options = cors[0].kwargs
    if options.get("allow_origins") == ["*"]:
        assert options.get("allow_credentials") is False
