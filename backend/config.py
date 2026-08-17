"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./work_bot_hunter.db"
    database_url_sync: str = "sqlite:///./work_bot_hunter.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60

    # AI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Security
    cv_storage_path: str = "/data/cvs"
    encryption_key: str = "change-me"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Scraping
    scrape_interval_minutes: int = 60
    max_jobs_per_source: int = 100
    request_delay_seconds: float = 2.0

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
