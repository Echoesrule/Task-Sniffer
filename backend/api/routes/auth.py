"""Authentication, registration, and session routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    get_current_user,
    get_db,
)
from backend.config import get_settings
from backend.models.database import TelegramLinkCode, User
from backend.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_csrf_token,
    generate_telegram_link_code,
    hash_password,
    hash_telegram_link_code,
    validate_password_strength,
    verify_password_or_dummy,
)
from backend.security.rate_limit import RateLimitBackendError, limiter

router = APIRouter()
logger = logging.getLogger(__name__)


class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    # Reject attempts to smuggle authorization fields into registration.
    model_config = {"extra": "forbid"}


class UserLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    model_config = {"extra": "forbid"}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str = "user"


class RegisterResponse(BaseModel):
    detail: str


class RefreshResponse(BaseModel):
    detail: str = "Session refreshed"
    user_id: str
    email: str
    role: str = "user"


class LinkCodeResponse(BaseModel):
    code: str
    expires_at: datetime


def _client_ip(request: Request) -> str:
    # ``request.client`` is the transport peer. Do not trust X-Forwarded-For
    # unless a trusted proxy layer is explicitly configured to overwrite it.
    return request.client.host if request.client else "unknown"


async def _enforce_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    try:
        allowed, retry_after = await limiter.hit(key, limit=limit, window_seconds=window_seconds)
    except RateLimitBackendError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable",
        ) from exc
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _set_session_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    settings = get_settings()
    max_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=generate_csrf_token(),
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def register(
    request: UserRegisterRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Create an account without revealing whether the email already exists.

    The response is intentionally identical for new and existing addresses.
    Clients should call ``/auth/login`` afterwards; a legitimate new user will
    succeed, while an attacker learns nothing from the registration response.
    """
    settings = get_settings()
    await _enforce_rate_limit(
        f"register:ip:{_client_ip(http_request)}",
        limit=settings.registration_rate_limit_attempts,
        window_seconds=settings.registration_rate_limit_window_seconds,
    )

    email = request.email.strip().lower()
    try:
        validate_password_strength(request.password, email=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing:
        # Equalise the expensive password-hashing path for existing addresses.
        hash_password(request.password)
        return RegisterResponse(
            detail="Registration request accepted. Sign in to continue."
        )

    new_user = User(
        email=email,
        hashed_password=hash_password(request.password),
        role="user",
        token_version=0,
        is_active=True,
        is_verified=False,
    )
    db.add(new_user)
    await db.commit()
    return RegisterResponse(detail="Registration request accepted. Sign in to continue.")


@router.post("/login", response_model=TokenResponse)
async def login(
    request: UserLoginRequest,
    http_request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    settings = get_settings()
    email = request.email.strip().lower()
    ip_key = f"login:ip:{_client_ip(http_request)}"
    account_key = f"login:account:{email}"

    await _enforce_rate_limit(
        ip_key,
        limit=settings.auth_rate_limit_attempts * 4,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    await _enforce_rate_limit(
        account_key,
        limit=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )

    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if not user or not verify_password_or_dummy(
        request.password, user.hashed_password if user else None
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive account",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await limiter.reset(account_key)
    token_version = int(user.token_version or 0)
    token = create_access_token(
        {"sub": user.email, "user_id": user.id},
        token_version=token_version,
    )
    refresh_token = create_refresh_token(
        {"sub": user.email, "user_id": user.id},
        token_version=token_version,
    )
    _set_session_cookies(response, token, refresh_token)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        role=user.role or "user",
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_session(
    http_request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    """Exchange a valid refresh cookie for a fresh short-lived access token.

    Refresh tokens are checked against the user's current ``token_version`` so
    that logout or a password change revokes them immediately.
    """
    refresh_token = http_request.cookies.get(REFRESH_COOKIE_NAME)
    payload = decode_refresh_token(refresh_token) if refresh_token else None
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_identifier = payload.get("sub") or payload.get("user_id")
    if not user_identifier:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing user subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (
        await db.execute(
            select(User).where(
                (User.id == str(user_identifier))
                | (User.email == str(user_identifier))
            )
        )
    ).scalars().first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_version = int(user.token_version or 0)
    if int(payload.get("ver", 0) or 0) != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        {"sub": user.email, "user_id": user.id},
        token_version=token_version,
    )
    rotated_refresh_token = create_refresh_token(
        {"sub": user.email, "user_id": user.id},
        token_version=token_version,
    )
    _set_session_cookies(response, access_token, rotated_refresh_token)
    return RefreshResponse(
        user_id=user.id,
        email=user.email,
        role=user.role or "user",
    )


@router.post("/logout")
async def logout(
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke every token issued to the current user and clear the session."""
    user = (
        await db.execute(select(User).where(User.id == current_user["user_id"]))
    ).scalar_one_or_none()
    if user is not None:
        user.token_version = int(user.token_version or 0) + 1
        await db.commit()
    _clear_session_cookies(response)
    return {"detail": "Signed out"}


@router.get("/me", response_model=dict[str, Any])
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "role": current_user["role"],
    }


@router.post("/telegram/link-code", response_model=LinkCodeResponse)
async def create_telegram_link_code(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkCodeResponse:
    """Issue a short-lived, single-use code for the Telegram ``/link`` command.

    The code is returned once and only its hash is stored. Passwords are never
    accepted through Telegram.
    """
    settings = get_settings()
    await _enforce_rate_limit(
        f"telegram-link-code:{current_user['user_id']}",
        limit=5,
        window_seconds=3600,
    )
    now = datetime.now(timezone.utc)
    # Retire any outstanding unused code so only the newest one is valid.
    await db.execute(
        delete(TelegramLinkCode).where(
            TelegramLinkCode.user_id == current_user["user_id"],
            TelegramLinkCode.used_at.is_(None),
        )
    )
    code = generate_telegram_link_code()
    expires_at = now + timedelta(seconds=settings.telegram_link_code_ttl_seconds)
    db.add(
        TelegramLinkCode(
            user_id=current_user["user_id"],
            code_hash=hash_telegram_link_code(code),
            expires_at=expires_at,
        )
    )
    await db.commit()
    return LinkCodeResponse(code=code, expires_at=expires_at)
