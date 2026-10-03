"""Politeness and rate limiting for source ingestion (spec §16).

Each source adapter supports: request delay, concurrency limit, retry limit,
exponential backoff, timeout. On repeated 429s a source is paused.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from backend.sources.models import SourceConfig, SourceStatus, utcnow

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a source keeps returning 429 / 5xx backoff responses."""


@dataclass
class RateLimiter:
    """Enforce per-source politeness and detect rate-limiting."""

    config: SourceConfig
    _last_request_at: float = 0.0
    _consecutive_throttled: int = 0
    _semaphore: asyncio.Semaphore = field(default_factory=asyncio.Semaphore)

    def __post_init__(self) -> None:
        # fresh semaphore (safe default; replaced if called under a running loop)
        try:
            asyncio.get_running_loop()
            if self._semaphore.locked() is False and self._semaphore._value == 1:
                pass
        except RuntimeError:
            self._semaphore = asyncio.Semaphore(1)
        limit = max(1, int(getattr(self.config, "concurrency_limit", 1) or 1))
        if self._semaphore._value != limit:
            self._semaphore = asyncio.Semaphore(limit)

    @property
    def is_throttled_out(self) -> bool:
        return self._consecutive_throttled >= self.config.retry_limit

    async def wait_slot(self) -> None:
        """Wait for a concurrency slot and enforce the request delay."""
        delay = float(self.config.rate_limit or 1.0)
        if self._last_request_at:
            elapsed = asyncio.get_event_loop().time() - self._last_request_at
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
        self._last_request_at = asyncio.get_event_loop().time()

    async def __aenter__(self) -> "RateLimiter":
        await self.wait_slot()
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, *_: object) -> None:
        self._semaphore.release()

    def record_response(self, response: httpx.Response | None) -> None:
        """Record an HTTP status to detect throttling."""
        status = response.status_code if response else None
        if status in (429, 502, 503, 504):
            self._consecutive_throttled += 1
            logger.warning(
                "[%s] throttled (HTTP %s) %d/%d",
                self.config.name, status, self._consecutive_throttled, self.config.retry_limit,
            )
        else:
            self._consecutive_throttled = 0

    def backoff_sleep(self) -> float:
        """Exponential backoff seconds for the current retry."""
        base = float(getattr(self.config, "backoff_base", 2.0) or 2.0)
        return base ** max(self._consecutive_throttled, 1)


def should_pause(limiter: RateLimiter) -> bool:
    return limiter.is_throttled_out


def pause_config(config: SourceConfig, reason: str = "RATE_LIMITED") -> SourceConfig:
    """Return a copy of the config marked paused for backoff (spec §16)."""
    paused = config.model_copy(deep=True)
    paused.source_status = SourceStatus.PAUSED
    paused.pause_reason = reason
    paused.retry_at = utcnow()
    return paused