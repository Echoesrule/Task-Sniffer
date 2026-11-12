"""Application configuration."""

from collections import Counter
from functools import lru_cache
import math
import os
import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings


# Substrings that are never acceptable in a production signing secret. This is a
# defence-in-depth check on top of the entropy requirement, not a replacement.
_PLACEHOLDER_MARKERS = (
    "change",
    "changeme",
    "example",
    "sample",
    "placeholder",
    "secret",
    "password",
    "default",
    "insecure",
    "development",
    "test",
    "todo",
)


def _shannon_entropy(value: str) -> float:
    """Return bits of entropy per character for ``value``."""
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./work_bot_hunter.db"
    database_url_sync: str = "sqlite:///./work_bot_hunter.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = ""
    app_env: str = "development"
    access_token_expire_minutes: int = 15
    password_min_length: int = 12

    # Browser session
    # The frontend is a separate origin during local development, so cookie
    # auth is opt-in via CORS origins and SameSite configuration.
    cors_origins: str = "http://localhost:3000"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"

    # Authentication throttling. Redis is used when reachable so limits are
    # shared across API workers; a process-local fallback exists for development.
    auth_rate_limit_attempts: int = 5
    auth_rate_limit_window_seconds: int = 900
    registration_rate_limit_attempts: int = 5
    registration_rate_limit_window_seconds: int = 3600
    telegram_link_code_ttl_seconds: int = 600
    telegram_link_attempts: int = 5
    telegram_link_window_seconds: int = 900

    # AI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Security
    cv_storage_path: str = "/data/cvs"
    encryption_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # Comma-separated chat IDs allowed to use global operational commands.
    telegram_admin_chat_ids: str = ""

    # Scraping
    scrape_interval_minutes: int = 60
    max_jobs_per_source: int = 100
    request_delay_seconds: float = 2.0

    # Optional public ATS board configuration. Identifiers are not credentials;
    # each source remains disabled until it has IDs and an explicit opt-in.
    greenhouse_enabled: bool = False
    greenhouse_board_tokens: str = ""
    ashby_enabled: bool = False
    ashby_board_names: str = ""
    workable_account_subdomains: str = ""

    # Matching weights
    weight_skills: float = 0.30
    weight_experience: float = 0.20
    weight_role: float = 0.15
    weight_location: float = 0.10
    weight_salary: float = 0.10
    weight_projects: float = 0.05
    weight_freshness: float = 0.05
    weight_source_quality: float = 0.05

    # Classification thresholds
    score_excellent: int = 90
    score_strong: int = 75
    score_possible: int = 60
    score_weak: int = 40

    # Risk thresholds
    risk_block: int = 70
    risk_review: int = 40

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_auth_secret(self) -> "Settings":
        production = self.app_env.lower() in {"production", "prod"}
        if not self.secret_key:
            if production:
                raise ValueError("SECRET_KEY must be configured in production")
            # A per-process development key avoids shipping a known JWT signing secret.
            self.secret_key = secrets.token_urlsafe(48)
        elif production:
            if not os.environ.get("SECRET_KEY"):
                raise ValueError(
                    "SECRET_KEY must be supplied through the process environment "
                    "or a secret manager in production; .env values are not accepted"
                )
            lowered = self.secret_key.lower()
            if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
                raise ValueError("SECRET_KEY must not contain a placeholder or development marker")
            if len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must contain at least 32 characters in production")
            # A random 32-byte urlsafe token scores ~5 bits/char; a 32-byte hex
            # token scores ~3.9. Requiring 3.8 rejects repeated/word-like values
            # while still allowing both common secure encodings.
            if _shannon_entropy(self.secret_key) < 3.8:
                raise ValueError(
                    "SECRET_KEY does not contain enough entropy; generate it with "
                    "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`"
                )
        if production:
            from backend.security.cv_encryption import CVEncryptionError, load_cv_key

            try:
                load_cv_key(self.encryption_key)
            except CVEncryptionError as exc:
                raise ValueError("ENCRYPTION_KEY must be URL-safe base64 for exactly 32 random bytes in production") from exc
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def telegram_admin_chat_id_set(self) -> set[str]:
        return {
            chat_id.strip()
            for chat_id in self.telegram_admin_chat_ids.split(",")
            if chat_id.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
