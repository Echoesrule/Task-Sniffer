"""Phase 5 API security regression tests.

Cover the confirmed defects fixed during the production-readiness review:
authenticated source mutations, CV upload path-traversal / type / size gating,
and the CORS credential policy.
"""

from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
import zipfile

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from backend.api import deps as api_deps
from backend.api.routes import candidates as candidates_routes
from backend.api.routes import jobs as jobs_routes
from backend.api.routes import sources as sources_routes
from backend.config import Settings
from backend.models.database import Candidate, Database, IngestionError, Job, Source, User
from backend.security import create_access_token, hash_password


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

    async def seed():
        async with db.async_session_factory() as session:
            user = User(
                email="testuser@example.com",
                hashed_password=hash_password("password123"),
                is_active=True,
            )
            session.add(user)
            await session.flush()
            session.add(Candidate(user_id=user.id, name="Test User", email=user.email))
            await session.commit()

    _run(seed())
    token = create_access_token({"sub": "testuser@example.com"})
    return app, db, token


def test_cv_upload_sanitizes_filename_and_stays_in_storage(tmp_path, monkeypatch):
    app, db, token = _with_app(candidates_routes.router, tmp_path)
    storage = tmp_path / "cvs"
    monkeypatch.setattr(candidates_routes, "get_settings", lambda: Settings(
        cv_storage_path=str(storage), encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode()
    ))
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            uploaded = await client.post(
                "/cv",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("../../evil.pdf", b"%PDF-1.4 payload", "application/pdf")},
            )
            downloaded = await client.get("/cv/file", headers={"Authorization": f"Bearer {token}"})
            return uploaded, downloaded

    try:
        response, downloaded = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert response.status_code == 200
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.4 payload"
    stored = list(storage.iterdir())
    assert len(stored) == 1
    name = stored[0].name
    assert name.endswith(".pdf")
    assert "evil" not in name and ".." not in name
    assert stored[0].parent == storage
    assert b"%PDF-1.4 payload" not in stored[0].read_bytes()
    # nothing escaped the storage directory
    assert not (tmp_path.parent / "evil.pdf").exists()
    assert not (tmp_path / "evil.pdf").exists()


def test_cv_upload_rejects_bad_extension(tmp_path, monkeypatch):
    app, db, token = _with_app(candidates_routes.router, tmp_path)
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
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("payload.sh", b"#!/bin/sh", "application/pdf")},
            )

    try:
        response = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert response.status_code == 400


def test_cv_upload_rejects_oversized_file(tmp_path, monkeypatch):
    app, db, token = _with_app(candidates_routes.router, tmp_path)
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
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("cv.pdf", b"x" * 64, "application/pdf")},
            )

    try:
        response = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert response.status_code == 413


def test_cv_upload_fails_closed_without_encryption_key(tmp_path, monkeypatch):
    app, db, token = _with_app(candidates_routes.router, tmp_path)
    storage = tmp_path / "cvs"
    monkeypatch.setattr(candidates_routes, "get_settings", lambda: Settings(cv_storage_path=str(storage), encryption_key=""))
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            return await client.post(
                "/cv", headers={"Authorization": f"Bearer {token}"},
                files={"file": ("cv.pdf", b"%PDF-1.4 plaintext", "application/pdf")},
            )

    try:
        response = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())
    assert response.status_code == 503
    assert not storage.exists()


def test_source_mutation_requires_token(tmp_path):
    app, db, token = _with_app(sources_routes.router, tmp_path, prefix="/sources")
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


def test_cors_uses_explicit_origins_when_credentials_are_allowed():
    from backend.api.app import create_app

    app = create_app()
    cors = [
        m
        for m in app.user_middleware
        if m.cls.__name__ == "CORSMiddleware"
    ]
    assert cors, "CORS middleware not configured"
    options = cors[0].kwargs
    if options.get("allow_credentials"):
        assert "*" not in options.get("allow_origins", [])


def test_cv_upload_rejects_file_with_wrong_magic_bytes(tmp_path, monkeypatch):
    app, db, token = _with_app(candidates_routes.router, tmp_path)
    storage = tmp_path / "cvs"
    monkeypatch.setattr(
        candidates_routes,
        "get_settings",
        lambda: Settings(
            cv_storage_path=str(storage),
            encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
        ),
    )
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            return await client.post(
                "/cv",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("cv.pdf", b"#!/bin/sh\nid", "application/pdf")},
            )

    try:
        response = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert response.status_code == 400
    assert not storage.exists() or not list(storage.iterdir())


def _docx_bytes(*, valid: bool = True) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if valid:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", "<w:document/>")
        else:
            archive.writestr("mimetype", "application/octet-stream")
    return buffer.getvalue()


def test_cv_upload_accepts_valid_docx_and_doc_signatures(tmp_path, monkeypatch):
    app, db, token = _with_app(candidates_routes.router, tmp_path)
    storage = tmp_path / "cvs"
    monkeypatch.setattr(
        candidates_routes,
        "get_settings",
        lambda: Settings(
            cv_storage_path=str(storage),
            encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
        ),
    )
    original = api_deps._db
    api_deps.set_db(db)
    docx_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    async def scenario():
        async with _client(app) as client:
            docx = await client.post(
                "/cv",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("cv.docx", _docx_bytes(), docx_type)},
            )
            docx_stored = sorted(path.suffix for path in storage.iterdir())
            doc = await client.post(
                "/cv",
                headers={"Authorization": f"Bearer {token}"},
                files={
                    "file": (
                        "cv.doc",
                        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"payload",
                        "application/msword",
                    )
                },
            )
        return docx, docx_stored, doc

    try:
        docx, docx_stored, doc = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert docx.status_code == 200
    assert docx_stored == [".docx"]
    assert doc.status_code == 200
    assert sorted(path.suffix for path in storage.iterdir()) == [".doc"]


def test_cv_upload_rejects_zip_that_is_not_a_docx(tmp_path, monkeypatch):
    app, db, token = _with_app(candidates_routes.router, tmp_path)
    storage = tmp_path / "cvs"
    monkeypatch.setattr(
        candidates_routes,
        "get_settings",
        lambda: Settings(
            cv_storage_path=str(storage),
            encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
        ),
    )
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            return await client.post(
                "/cv",
                headers={"Authorization": f"Bearer {token}"},
                files={
                    "file": (
                        "cv.docx",
                        _docx_bytes(valid=False),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )

    try:
        response = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert response.status_code == 400
    assert not storage.exists() or not list(storage.iterdir())


def test_source_errors_are_admin_only_and_redacted(tmp_path):
    app, db, token = _with_app(sources_routes.router, tmp_path, prefix="/sources")

    async def seed():
        async with db.async_session_factory() as session:
            admin = (await session.execute(select(User))).scalars().first()
            admin.role = "admin"
            regular = User(
                email="regular@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            source = Source(name="fixture", url="https://fixture.example")
            session.add_all([regular, source])
            await session.flush()
            session.add(
                IngestionError(
                    source_id=source.id,
                    job_url="https://user:pass@fixture.example/jobs/1?token=abc",
                    stage="fetch",
                    error_class="RuntimeError",
                    error_message=(
                        "failed reading /srv/app/backend/scraper.py "
                        "password=hunter2 https://internal.example/secret"
                    ),
                )
            )
            await session.commit()

    _run(seed())
    regular_token = create_access_token({"sub": "regular@example.com"})
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            as_regular = await client.get(
                "/sources/fixture/errors",
                headers={"Authorization": f"Bearer {regular_token}"},
            )
            as_admin = await client.get(
                "/sources/fixture/errors",
                headers={"Authorization": f"Bearer {token}"},
            )
        return as_regular, as_admin

    try:
        as_regular, as_admin = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert as_regular.status_code == 403
    assert as_admin.status_code == 200
    item = as_admin.json()[0]
    assert "user:pass" not in item["job_url"]
    assert "token=abc" not in item["job_url"]
    assert "http" not in item["error_message"]
    assert "/srv/app" not in item["error_message"]
    assert "hunter2" not in item["error_message"]


def test_job_analysis_is_admin_only(tmp_path):
    app, db, admin_token = _with_app(jobs_routes.router, tmp_path, prefix="/jobs")

    async def seed():
        async with db.async_session_factory() as session:
            admin = (await session.execute(select(User))).scalars().first()
            admin.role = "admin"
            regular = User(
                email="regular@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            source = Source(name="fixture", url="https://fixture.example")
            session.add_all([regular, source])
            await session.flush()
            job = Job(
                source_id=source.id,
                source_job_id="1",
                title="Backend Engineer",
                company="Fixture Ltd",
                description="Build reliable services.",
                application_url="https://fixture.example/jobs/1",
            )
            session.add(job)
            await session.commit()
            return job.id

    job_id = _run(seed())
    regular_token = create_access_token({"sub": "regular@example.com"})
    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        async with _client(app) as client:
            as_regular = await client.post(
                f"/jobs/{job_id}/analyze",
                headers={"Authorization": f"Bearer {regular_token}"},
            )
            as_admin = await client.post(
                f"/jobs/{job_id}/analyze",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        return as_regular, as_admin

    try:
        as_regular, as_admin = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert as_regular.status_code == 403
    assert as_admin.status_code == 200
    assert as_admin.json()["risk_level"]
