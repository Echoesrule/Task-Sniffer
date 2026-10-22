"""FastAPI dependencies for database, auth, and configuration."""

from __future__ import annotations

from typing import Any, AsyncGenerator

from fastapi import Depends, Header, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.models.database import Database, User
from backend.security import decode_access_token


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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Extract, decode, and validate the current user from the Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_identifier = payload.get("sub") or payload.get("email") or payload.get("user_id")
    if not user_identifier:
        raise HTTPException(
            status_code=401,
            detail="Token missing user subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(
        or_(User.id == str(user_identifier), User.email == str(user_identifier))
    )
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user_id": user.id,
        "email": user.email,
        "role": getattr(user, "role", "user") or "user",
    }


async def get_optional_current_user(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any] | None:
    """Resolve an authenticated user when supplied, while preserving public job browsing."""
    if not authorization:
        return None
    return await get_current_user(authorization=authorization, db=db)
