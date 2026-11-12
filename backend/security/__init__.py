"""Security utilities - auth, encryption, access control."""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

# Used to equalise the cost of a login for an unknown account. The value is
# never a valid credential for any user.
_DUMMY_HASH = pwd_context.hash(secrets.token_urlsafe(32))

_COMMON_PASSWORDS = {
    "123456789012",
    "password1234",
    "passwordpassword",
    "qwertyuiop12",
    "letmein12345",
    "welcome12345",
    "adminadmin12",
    "iloveyou1234",
    "monkey123456",
    "dragon123456",
    "football1234",
    "baseball1234",
    "sunshine1234",
    "princess1234",
    "trustno1trustno1",
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def verify_password_or_dummy(plain: str, hashed: str | None) -> bool:
    """Verify a password while keeping unknown-account timing comparable."""
    if hashed:
        return pwd_context.verify(plain, hashed)
    pwd_context.verify(plain, _DUMMY_HASH)
    return False


def validate_password_strength(password: str, *, email: str | None = None) -> None:
    """Raise ``ValueError`` when a password does not meet the policy.

    The policy is intentionally simple and dependency-free: a length floor,
    at least one letter and one digit, no common passwords, and no password
    that is simply the email local-part.
    """
    min_length = get_settings().password_min_length
    if len(password) < min_length:
        raise ValueError(f"Password must be at least {min_length} characters long")
    if len(password) > 128:
        raise ValueError("Password must be at most 128 characters long")
    if password.lower() in _COMMON_PASSWORDS:
        raise ValueError("Password is too common")
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise ValueError("Password must contain at least one letter and one digit")
    if email:
        local_part = email.split("@", 1)[0].strip().lower()
        if local_part and len(local_part) >= 3 and local_part in password.lower():
            raise ValueError("Password must not contain the email address")


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    *,
    token_version: int = 0,
) -> str:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be configured to generate tokens")
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update(
        {
            "exp": expire,
            "ver": int(token_version),
            "jti": secrets.token_urlsafe(16),
        }
    )
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    *,
    token_version: int = 0,
) -> str:
    """Issue a long-lived refresh token that can only mint access tokens.

    Refresh tokens carry ``typ="refresh"`` so they are rejected anywhere an
    access token is expected, including the Authorization header.
    """
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be configured to generate tokens")
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.refresh_token_expire_days)
    )
    to_encode.update(
        {
            "exp": expire,
            "ver": int(token_version),
            "jti": secrets.token_urlsafe(16),
            "typ": "refresh",
        }
    )
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    if not settings.secret_key or not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    # A refresh token must never be usable as a bearer access token.
    if payload.get("typ") == "refresh":
        return None
    return payload


def decode_refresh_token(token: str) -> Optional[dict]:
    if not settings.secret_key or not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("typ") != "refresh":
        return None
    return payload


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def generate_telegram_link_code() -> str:
    """Generate a short, high-entropy, human-typeable linking code."""
    return secrets.token_hex(5).upper()


def hash_telegram_link_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()
