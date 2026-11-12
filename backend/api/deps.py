"""FastAPI dependencies for database, auth, and configuration."""

from __future__ import annotations

from typing import Any, AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.models.database import Database, User
from backend.security import decode_access_token


_db: Database | None = None

ACCESS_COOKIE_NAME = "access_token"


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


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None
    return parts[1]


async def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Extract, decode, and validate the current user.

    Bearer tokens are preferred for API clients. The browser session uses an
    HttpOnly ``access_token`` cookie; the returned ``auth_method`` lets callers
    apply CSRF protection only to cookie-authenticated requests.
    """
    token = _extract_bearer(authorization)
    auth_method = "bearer" if token else None
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME)
        auth_method = "cookie" if token else None

    if not token:
        if authorization:
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

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

    # ``ver`` allows a logout or password change to invalidate every token that
    # was issued before the change without maintaining a per-token denylist.
    token_version = int(payload.get("ver", 0) or 0)
    if token_version != int(user.token_version or 0):
        raise HTTPException(
            status_code=401,
            detail="Access token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user_id": user.id,
        "email": user.email,
        "role": user.role or "user",
        "token_version": int(user.token_version or 0),
        "auth_method": auth_method,
    }


async def require_admin(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Require an administrator principal; regular users receive 403."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return current_user


async def get_optional_current_user(
    request: Request,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any] | None:
    """Resolve an authenticated user when supplied, while preserving public job browsing."""
    if not authorization and not request.cookies.get(ACCESS_COOKIE_NAME):
        return None
    return await get_current_user(request=request, authorization=authorization, db=db)
