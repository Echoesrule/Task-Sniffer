"""Distributed authentication rate limiting.

Redis is the primary backend so limits are shared by every API worker. A
process-local fallback is used only in development; in production a Redis
failure fails closed instead of silently weakening brute-force protection.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass

from backend.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__("Too many attempts")


class RateLimitBackendError(Exception):
    """Raised when a production rate-limit backend cannot be reached."""


@dataclass
class _LocalBucket:
    count: int
    reset_at: float


class RateLimiter:
    def __init__(self, redis_url: str | None = None, prefix: str = "task-sniffer:rl") -> None:
        settings = get_settings()
        self._redis_url = redis_url or settings.redis_url
        self._prefix = prefix
        self._production = settings.app_env.lower() in {"production", "prod"}
        self._redis = None  # None = not connected, False = unavailable
        self._local: dict[str, _LocalBucket] = {}
        self._lock = asyncio.Lock()
        self._next_retry = 0.0

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]

    async def _client(self):
        if self._redis is not None:
            if self._redis is False:
                # Retry a previously unavailable backend after a cooldown instead
                # of failing closed for the lifetime of the process.
                if time.monotonic() < self._next_retry:
                    if self._production:
                        raise RateLimitBackendError("Rate-limit backend unavailable")
                    return None
                self._redis = None
            else:
                return self._redis
        if time.monotonic() < self._next_retry:
            if self._production:
                raise RateLimitBackendError("Rate-limit backend unavailable")
            return None
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            await client.ping()
            self._redis = client
            return client
        except Exception as exc:  # noqa: BLE001 - backend availability is best-effort
            logger.warning("Rate-limit Redis unavailable; using local fallback: %s", exc)
            self._redis = False
            self._next_retry = time.monotonic() + 30
            if self._production:
                raise RateLimitBackendError("Rate-limit backend unavailable") from exc
            return None

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Record one attempt. Returns ``(allowed, retry_after_seconds)``."""
        digest = self._digest(key)
        bucket = int(time.time() // max(1, window_seconds))
        retry_after = window_seconds - int(time.time() % max(1, window_seconds))
        full_key = f"{self._prefix}:{digest}:{bucket}"
        client = await self._client()
        if client is not None:
            count = await client.incr(full_key)
            if count == 1:
                await client.expire(full_key, window_seconds + 1)
            return count <= limit, retry_after
        async with self._lock:
            now = time.monotonic()
            current = self._local.get(full_key)
            if current is None or current.reset_at <= now:
                current = _LocalBucket(count=0, reset_at=now + window_seconds)
                self._local[full_key] = current
            current.count += 1
            # Opportunistic cleanup keeps the fallback dictionary bounded.
            if len(self._local) > 4096:
                self._local = {
                    k: v for k, v in self._local.items() if v.reset_at > now
                }
            return current.count <= limit, retry_after

    async def reset(self, key: str) -> None:
        """Clear the current window for ``key`` (used after a successful login)."""
        digest = self._digest(key)
        try:
            client = await self._client()
        except RateLimitBackendError:
            return
        if client is not None:
            pattern = f"{self._prefix}:{digest}:*"
            try:
                async for found in client.scan_iter(match=pattern, count=100):
                    await client.delete(found)
            except Exception:  # noqa: BLE001 - reset is best-effort
                return
        async with self._lock:
            for stored in [k for k in self._local if f":{digest}:" in k]:
                self._local.pop(stored, None)


limiter = RateLimiter()
