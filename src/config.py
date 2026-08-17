"""Configuration management for Work Hunter Bot."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class Config:
    """Load and manage configuration from settings.yaml and environment variables."""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = str(Path(__file__).parent.parent / "config" / "settings.yaml")

        load_dotenv()
        self._config = self._load_config(config_path)
        self._resolve_env_vars(self._config)

    def _load_config(self, path: str) -> dict[str, Any]:
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def _resolve_env_vars(self, obj: Any) -> Any:
        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return os.getenv(env_var, "")
        elif isinstance(obj, dict):
            for key, value in obj.items():
                obj[key] = self._resolve_env_vars(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                obj[i] = self._resolve_env_vars(item)
        return obj

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    @property
    def telegram_token(self) -> str:
        return self.get("telegram.bot_token", "")

    @property
    def telegram_chat_id(self) -> str:
        return self.get("telegram.chat_id", "")

    @property
    def scraping_interval(self) -> int:
        return self.get("scraping.interval_minutes", 60)

    @property
    def request_delay(self) -> float:
        return self.get("scraping.request_delay_seconds", 2)

    @property
    def max_jobs_per_source(self) -> int:
        return self.get("scraping.max_jobs_per_source", 50)

    @property
    def filters(self) -> dict:
        return self.get("filters", {})

    @property
    def sources(self) -> dict:
        return self.get("sources", {})

    @property
    def analysis(self) -> dict:
        return self.get("analysis", {})

    @property
    def min_match_score(self) -> float:
        return self.get("analysis.min_match_score", 60)

    @property
    def max_risk_score(self) -> float:
        return self.get("analysis.max_risk_score", 60)


config = Config()
