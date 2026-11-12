"""Focused tests for security helper functions and fail-closed behaviour."""

from __future__ import annotations

import asyncio
import sys
import types

import httpx
import pytest

import backend.security.rate_limit as rate_limit_module
import backend.sources.urls as urls_module
from backend.api.routes.sources import _redact_error, _safe_url
from backend.services.ingestion import IngestionEngine


def _run(coro):
    return asyncio.run(coro)


def test_safe_url_strips_userinfo_query_and_fragment():
    assert (
        _safe_url("https://user:pass@example.com:8443/jobs/1?token=abc#frag")
        == "https://example.com:8443/jobs/1"
    )
    assert _safe_url(None) is None
    assert _safe_url("not a url") == "not a url"


def test_redact_error_removes_urls_paths_and_credentials():
    cleaned = _redact_error(
        "failed https://user:pass@internal.example/jobs/1 "
        "reading /srv/app/backend/scraper.py password=hunter2"
    )
    assert cleaned is not None
    assert "https://" not in cleaned
    assert "user:pass" not in cleaned
    assert "/srv/app" not in cleaned
    assert "hunter2" not in cleaned
    assert "<url>" in cleaned
    assert "<path>" in cleaned
    assert "password=<redacted>" in cleaned


def test_redact_error_is_bounded():
    cleaned = _redact_error("x" * 2000)
    assert cleaned is not None
    assert len(cleaned) == 500


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "http://127.0.0.1/",
        "http://localhost/",
        "http://metadata.google.internal/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "javascript:alert(1)",
        "http://example.com:22/",
    ],
)
def test_ssrf_policy_rejects_unsafe_destinations(url):
    assert urls_module.is_safe_fetch_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/jobs/1",
        "https://93.184.216.34/jobs/1",
        "http://example.com:8080/jobs/1",
    ],
)
def test_ssrf_policy_allows_public_http_destinations(url):
    assert urls_module.is_safe_fetch_url(url) is True


def test_fetch_with_policy_rejects_redirect_to_non_http_scheme():
    hits: list[str] = []

    def handler(request):
        hits.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "file:///etc/passwd"})
        return httpx.Response(200, text="should never be fetched")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )

    async def go():
        try:
            return await urls_module.fetch_with_policy(
                client, "https://93.184.216.34/start"
            )
        finally:
            await client.aclose()

    response, final_url, chain, error = _run(go())
    assert response is None
    assert final_url == "file:///etc/passwd"
    assert "unsafe" in error
    assert hits == ["https://93.184.216.34/start"]


def test_production_rate_limiter_fails_closed_without_backend(monkeypatch):
    class FailingRedis:
        @classmethod
        def from_url(cls, *args, **kwargs):
            raise RuntimeError("Redis is unavailable")

    fake_asyncio = types.ModuleType("redis.asyncio")
    fake_asyncio.Redis = FailingRedis
    fake_redis = types.ModuleType("redis")
    fake_redis.asyncio = fake_asyncio
    monkeypatch.setitem(sys.modules, "redis", fake_redis)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio)
    monkeypatch.setattr(
        rate_limit_module,
        "get_settings",
        lambda: types.SimpleNamespace(
            app_env="production", redis_url="redis://127.0.0.1:1/0"
        ),
    )

    limiter = rate_limit_module.RateLimiter()
    with pytest.raises(rate_limit_module.RateLimitBackendError):
        _run(limiter.hit("login:ip:test", limit=5, window_seconds=60))


def test_ingestion_run_lock_serializes_concurrent_runs():
    engine = IngestionEngine(None)
    state = {"active": 0, "peak": 0, "calls": 0}

    async def fake_unlocked(name, *, force=False, limit=None, on_job=None):
        state["calls"] += 1
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return name

    engine._run_source_unlocked = fake_unlocked  # type: ignore[method-assign]

    async def scenario():
        return await asyncio.gather(
            engine.run_source("lock-test"),
            engine.run_source("lock-test"),
        )

    assert _run(scenario()) == ["lock-test", "lock-test"]
    assert state["calls"] == 2
    assert state["peak"] == 1
