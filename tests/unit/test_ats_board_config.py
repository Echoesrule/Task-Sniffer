"""Phase 2: Greenhouse/Ashby board configuration and zero-job diagnostics.

Boards are configured as ``SourceConfig.extra_urls`` (sourced from
``registry.ATS_BOARD_CONFIG``). A source with no verified boards must report a
diagnosable warning and record per-board outcomes rather than silently
returning nothing.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from backend.scrapers.ashby import AshbyScraper
from backend.scrapers.factory import _LegacyAdapter, build_adapter
from backend.scrapers.greenhouse import GreenhouseScraper
from backend.sources.models import (
    AccessMethod,
    PermissionStatus,
    ProvenanceClass,
    SourceConfig,
)
from backend.sources.registry import ATS_BOARD_CONFIG, default_registry


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _close(scraper) -> None:
    asyncio.run(scraper._client.aclose())


# --- empty board list -------------------------------------------------------


def test_greenhouse_empty_boards_warns_and_records_nothing(caplog):
    scraper = GreenhouseScraper({})
    try:
        with caplog.at_level(logging.WARNING):
            jobs = asyncio.run(scraper.fetch_jobs())
    finally:
        _close(scraper)
    assert jobs == []
    assert scraper.board_stats == []
    assert "no boards configured" in caplog.text


def test_ashby_empty_boards_warns(caplog):
    scraper = AshbyScraper({})
    try:
        with caplog.at_level(logging.WARNING):
            jobs = asyncio.run(scraper.fetch_jobs())
    finally:
        _close(scraper)
    assert jobs == []
    assert scraper.board_stats == []
    assert "no boards configured" in caplog.text


# --- valid board list + per-board stats -------------------------------------


def test_greenhouse_valid_boards_record_stats():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/acme/jobs"):
            return httpx.Response(
                200,
                json={"jobs": [{"id": 1, "title": "Eng", "location": {"name": "Remote"}}]},
            )
        if request.url.path.endswith("/globex/jobs"):
            return httpx.Response(200, json={"jobs": []})
        return httpx.Response(404)

    scraper = GreenhouseScraper({"boards": ["acme", "globex"]})
    scraper._client = _mock_client(handler)
    try:
        jobs = asyncio.run(scraper.fetch_jobs())
    finally:
        _close(scraper)

    assert [j["source_job_id"] for j in jobs] == ["1"]
    assert scraper.board_stats == [
        {"board": "acme", "ok": True, "jobs": 1},
        {"board": "globex", "ok": True, "jobs": 0},
    ]


def test_ashby_valid_board_record_stats():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"jobs": [{"id": "abc12345-aaaa", "title": "Eng"}]}
        )

    scraper = AshbyScraper({"boards": ["acme"]})
    scraper._client = _mock_client(handler)
    try:
        jobs = asyncio.run(scraper.fetch_jobs())
    finally:
        _close(scraper)

    assert len(jobs) == 1
    assert scraper.board_stats == [{"board": "acme", "ok": True, "jobs": 1}]


# --- invalid board identifier / API error -----------------------------------


def test_greenhouse_invalid_board_id_recorded_as_failure():
    scraper = GreenhouseScraper({"boards": ["does-not-exist"]})
    scraper._client = _mock_client(lambda request: httpx.Response(404))
    try:
        jobs = asyncio.run(scraper.fetch_jobs())
    finally:
        _close(scraper)

    assert jobs == []
    assert scraper.board_stats[0]["board"] == "does-not-exist"
    assert scraper.board_stats[0]["ok"] is False
    assert scraper.board_stats[0]["jobs"] == 0


def test_greenhouse_api_error_recorded_as_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    scraper = GreenhouseScraper({"boards": ["acme"]})
    scraper._client = _mock_client(handler)
    try:
        jobs = asyncio.run(scraper.fetch_jobs())
    finally:
        _close(scraper)

    assert jobs == []
    assert scraper.board_stats[0]["ok"] is False


def test_ashby_api_error_recorded_as_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    scraper = AshbyScraper({"boards": ["acme"]})
    scraper._client = _mock_client(handler)
    try:
        jobs = asyncio.run(scraper.fetch_jobs())
    finally:
        _close(scraper)

    assert jobs == []
    assert scraper.board_stats[0]["ok"] is False


# --- zero-result response ---------------------------------------------------


def test_greenhouse_zero_result_ok_but_no_jobs():
    scraper = GreenhouseScraper({"boards": ["acme"]})
    scraper._client = _mock_client(
        lambda request: httpx.Response(200, json={"jobs": []})
    )
    try:
        jobs = asyncio.run(scraper.fetch_jobs())
    finally:
        _close(scraper)

    assert jobs == []
    assert scraper.board_stats == [{"board": "acme", "ok": True, "jobs": 0}]


# --- registry / factory wiring ----------------------------------------------


def test_ats_board_config_wired_into_registry():
    for name in ("greenhouse", "ashby"):
        cfg = default_registry.get(name)
        assert cfg is not None
        assert cfg.extra_urls == list(ATS_BOARD_CONFIG.get(name, []))


def test_factory_passes_extra_urls_as_boards():
    config = SourceConfig(
        name="greenhouse",
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED,
        provenance=ProvenanceClass.JOB_BOARD,
        extra_urls=["acme", "globex"],
    )
    adapter = build_adapter(config)
    try:
        assert isinstance(adapter, _LegacyAdapter)
        assert adapter._legacy._boards == ["acme", "globex"]
    finally:
        asyncio.run(_close_legacy(adapter))


async def _close_legacy(adapter: _LegacyAdapter) -> None:
    await adapter.close()
    await adapter._legacy._client.aclose()


def test_registry_ats_sources_have_policy():
    from backend.scrapers.policy import unconfigured_sources

    unconfigured = set(unconfigured_sources())
    assert "greenhouse" not in unconfigured
    assert "ashby" not in unconfigured
