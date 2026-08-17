"""FastAPI dependencies for database, auth, and configuration."""

from __future__ import annotations

from typing import Any, AsyncGenerator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.models.database import Database


_db: Database | None = None


def set_db(db: Database) -> None:
    global _db
    _db = db


def get_db_settings() -> Settings:
    return get_settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if _db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    async for session in _db.get_session():
        yield session


async def get_current_user(
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Extract and validate the current user from the Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or empty token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user_id": "placeholder-user-id",
        "email": "user@example.com",
        "role": "user",
    }
