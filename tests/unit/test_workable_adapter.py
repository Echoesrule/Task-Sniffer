from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from backend.scrapers.adapters.workable import WorkableAdapter
from backend.scrapers.factory import build_adapter
from backend.sources.urls import extract_url_signals
from backend.sources.models import AccessMethod, PermissionStatus, SourceConfig


FIXTURE = Path(__file__).parents[1] / "fixtures" / "workable_public_jobs.json"


def _config(accounts: list[str] | None = None) -> SourceConfig:
    return SourceConfig(
        name="workable",
        url="https://apply.workable.com/",
        extra_urls=accounts or [],
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.REVIEW,
    )


def test_workable_adapter_parses_documented_public_jobs_fixture():
    payload = json.loads(FIXTURE.read_text())
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    adapter = WorkableAdapter(_config(["acme"]), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        items = asyncio.run(adapter.fetch_listings())
    finally:
        asyncio.run(adapter.close())

    assert len(items) == 2
    first, second = items
    assert first.title == "Senior Software Engineer"
    assert first.company == "Acme"
    assert first.location == "Nairobi, Kenya"
    assert first.source_job_id == "ENG-42"
    assert first.source_url == "https://acme.workable.com/jobs/ENG-42"
    assert first.apply_hint == "https://acme.workable.com/jobs/ENG-42/candidates/new"
    assert first.description == "<p>Build reliable services.</p>"
    assert second.remote is True
    assert second.apply_hint == ""
    assert second.source_url == "https://apply.workable.com/acme/j/AN-7/"
    assert len(requests) == 1
    assert str(requests[0].url) == (
        "https://www.workable.com/api/accounts/acme?details=true"
    )

    signals = extract_url_signals(
        "", first.source_url,
        allowed_domains=adapter.expected_domains(),
        apply_hint=first.apply_hint,
        detail_url=first.source_url,
    )
    assert signals.application_url == first.apply_hint


def test_workable_missing_account_fails_before_network():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"jobs": []})

    adapter = WorkableAdapter(_config(), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises(ValueError, match="WORKABLE_ACCOUNT_SUBDOMAINS"):
            asyncio.run(adapter.fetch_listings())
    finally:
        asyncio.run(adapter.close())
    assert called is False


def test_workable_rate_limit_error_is_not_hidden_or_retried_as_html():
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(429, text="rate limited")

    adapter = WorkableAdapter(_config(["acme"]), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(adapter.fetch_listings())
    finally:
        asyncio.run(adapter.close())
    assert requests == ["https://www.workable.com/api/accounts/acme?details=true"]


def test_workable_account_identifiers_are_validated():
    config = _config(["good-account", "bad/account"])
    adapter = WorkableAdapter(config)
    assert adapter.accounts == ["good-account"]
    asyncio.run(adapter.close())


def test_workable_adapter_is_registered_in_the_shared_factory():
    adapter = build_adapter(_config(["acme"]))
    try:
        assert isinstance(adapter, WorkableAdapter)
    finally:
        asyncio.run(adapter.close())
