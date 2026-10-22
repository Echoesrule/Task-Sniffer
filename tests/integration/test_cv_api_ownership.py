"""CV metadata and file access must remain scoped to the owning user."""

from __future__ import annotations

import asyncio
import base64

import httpx
from fastapi import FastAPI

from backend.api import deps as api_deps
from backend.api.routes import candidates
from backend.config import Settings
from backend.models.database import Candidate, Database, User
from backend.security import create_access_token, hash_password
from backend.security.cv_encryption import encrypt_cv


def _run(coro):
    return asyncio.run(coro)


def test_cv_metadata_and_download_are_user_scoped(tmp_path, monkeypatch):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'cv_scope.db'}")
    _run(db.init_db())
    cv_path = tmp_path / "private-cv.pdf"
    key = base64.urlsafe_b64encode(b"k" * 32).decode()
    cv_path.write_bytes(encrypt_cv(b"private document", key))
    monkeypatch.setattr(candidates, "get_settings", lambda: Settings(encryption_key=key))

    async def seed():
        async with db.async_session_factory() as session:
            owner = User(email="owner@example.com", hashed_password=hash_password("password123"))
            other = User(email="other@example.com", hashed_password=hash_password("password123"))
            session.add_all([owner, other])
            await session.flush()
            session.add_all([
                Candidate(user_id=owner.id, name="Owner", email="owner-contact@example.com", cv_file_path=str(cv_path)),
                Candidate(user_id=other.id, name="Other", email="other-contact@example.com"),
            ])
            await session.commit()
            return owner.id, other.id

    owner_id, other_id = _run(seed())
    owner_token = create_access_token({"sub": "owner@example.com", "user_id": owner_id})
    other_token = create_access_token({"sub": "other@example.com", "user_id": other_id})
    app = FastAPI()
    app.include_router(candidates.router, prefix="/candidate")
    old_db = api_deps._db
    api_deps.set_db(db)

    async def requests():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            owner_headers = {"Authorization": f"Bearer {owner_token}"}
            other_headers = {"Authorization": f"Bearer {other_token}"}
            return await asyncio.gather(
                client.get("/candidate/cv", headers=owner_headers),
                client.get("/candidate/cv/file", headers=owner_headers),
                client.get("/candidate/cv", headers=other_headers),
                client.get("/candidate/cv/file", headers=other_headers),
            )

    try:
        owner_meta, owner_file, other_meta, other_file = _run(requests())
        assert owner_meta.json()["filename"] == cv_path.name
        assert owner_file.content == b"private document"
        assert other_meta.json()["filename"] is None
        assert other_file.status_code == 404
    finally:
        api_deps._db = old_db
        _run(db.close())


def test_legacy_plaintext_cv_is_never_served_as_plaintext(tmp_path, monkeypatch):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'legacy_cv.db'}")
    _run(db.init_db())
    path = tmp_path / "legacy.pdf"
    path.write_bytes(b"legacy plaintext")
    key = base64.urlsafe_b64encode(b"k" * 32).decode()
    monkeypatch.setattr(candidates, "get_settings", lambda: Settings(encryption_key=key))

    async def seed():
        async with db.async_session_factory() as session:
            owner = User(email="legacy@example.com", hashed_password="x")
            session.add(owner)
            await session.flush()
            session.add(Candidate(user_id=owner.id, name="Legacy", email=owner.email, cv_file_path=str(path)))
            await session.commit()
            return owner.id

    user_id = _run(seed())
    token = create_access_token({"sub": "legacy@example.com", "user_id": user_id})
    app = FastAPI()
    app.include_router(candidates.router, prefix="/candidate")
    old_db = api_deps._db
    api_deps.set_db(db)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/candidate/cv/file", headers={"Authorization": f"Bearer {token}"})

    try:
        response = _run(request())
        assert response.status_code == 409
        assert path.read_bytes() == b"legacy plaintext"
    finally:
        api_deps._db = old_db
        _run(db.close())
