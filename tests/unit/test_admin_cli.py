"""Security tests for the administrator provisioning CLI."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.config import Settings
from backend.models.database import Database, User
from backend.security import hash_password, verify_password

ROOT = Path(__file__).resolve().parents[2]


def _run(coro):
    return asyncio.run(coro)


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "create_admin_cli", ROOT / "scripts" / "create_admin.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _settings(tmp_path) -> Settings:
    return Settings(
        app_env="development",
        secret_key="test-signing-secret",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'admin-cli.db'}",
    )


def test_admin_cli_refuses_password_from_noninteractive_terminal(monkeypatch):
    cli = _load_cli()
    monkeypatch.setattr(sys, "stdin", io.StringIO("password-from-pipe\n"))
    with pytest.raises(ValueError, match="non-interactive"):
        cli._read_password(False)


def test_admin_cli_creates_admin_and_promotes_without_password_overwrite(
    tmp_path, monkeypatch
):
    cli = _load_cli()
    settings = _settings(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    assert _run(cli._provision("admin@example.com", "securepassword123", False)) == 0

    db = Database(settings.database_url)

    async def read_user(email: str):
        async with db.async_session_factory() as session:
            return (
                await session.execute(select(User).where(User.email == email))
            ).scalars().first()

    try:
        admin = _run(read_user("admin@example.com"))
        assert admin is not None
        assert admin.role == "admin"
        assert verify_password("securepassword123", admin.hashed_password)

        async def seed_regular():
            async with db.async_session_factory() as session:
                session.add(
                    User(
                        email="existing@example.com",
                        hashed_password=hash_password("oldpassword123"),
                        role="user",
                        is_active=True,
                    )
                )
                await session.commit()

        _run(seed_regular())
        existing = _run(read_user("existing@example.com"))
        old_hash = existing.hashed_password

        assert _run(cli._provision("existing@example.com", None, True)) == 0
        promoted = _run(read_user("existing@example.com"))
        assert promoted.role == "admin"
        assert promoted.hashed_password == old_hash
    finally:
        _run(db.close())


def test_admin_cli_rejects_weak_password(tmp_path, monkeypatch):
    cli = _load_cli()
    settings = _settings(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="at least"):
        _run(cli._provision("weak@example.com", "short1", False))
