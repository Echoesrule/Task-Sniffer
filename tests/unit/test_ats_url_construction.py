"""Phase 4: ATS detail-URL construction and source_job_id (spec §8)."""

from __future__ import annotations

import asyncio

import httpx

from backend.scrapers.adapter import JobSourceAdapter
from backend.scrapers.ashby import AshbyScraper, is_ashby_detail_url
from backend.scrapers.factory import _LegacyAdapter
from backend.scrapers.greenhouse import GreenhouseScraper, is_greenhouse_detail_url
from backend.sources.models import AccessMethod, PermissionStatus, ProvenanceClass, SourceConfig


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _close(scraper) -> None:
    asyncio.run(scraper._client.aclose())


# --- detail-url recognisers -------------------------------------------------


def test_greenhouse_detail_url_accepts_postings_only():
    assert is_greenhouse_detail_url("https://job-boards.greenhouse.io/acme/jobs/123")
    assert is_greenhouse_detail_url("https://boards.greenhouse.io/acme/jobs/123")
    assert not is_greenhouse_detail_url("https://stripe.com/jobs/search")
    assert not is_greenhouse_detail_url("https://careers.airbnb.com/positions/123")
    assert not is_greenhouse_detail_url("https://job-boards.greenhouse.io/acme")
    assert not is_greenhouse_detail_url("")


def test_ashby_detail_url_accepts_postings_only():
    assert is_ashby_detail_url("https://jobs.ashbyhq.com/acme/2f3b4c5d-1111")
    assert not is_ashby_detail_url("https://jobs.ashbyhq.com/acme")
    assert not is_ashby_detail_url("https://example.com/acme/2f3b4c5d-1111")
    assert not is_ashby_detail_url("")


# --- greenhouse -------------------------------------------------------------


def test_greenhouse_constructs_board_url_and_rejects_search_absolute_url():
    payload = {
        "jobs": [
            {
                "id": 7995153,
                "title": "Backend Engineer",
                "absolute_url": "https://careers.airbnb.com/positions/7995153",
                "location": {"name": "Remote"},
            },
            {
                "id": 999,
                "title": "SRE",
                "absolute_url": "https://stripe.com/jobs/search?gh_jid=999",
            },
        ]
    }
    scraper = GreenhouseScraper({"boards": ["acme"]})
    scraper._client = _mock_client(lambda request: httpx.Response(200, json=payload))
    try:
        jobs = asyncio.run(scraper._fetch_board("acme"))
    finally:
        _close(scraper)

    assert jobs[0]["url"] == "https://job-boards.greenhouse.io/acme/jobs/7995153"
    assert jobs[0]["source_job_id"] == "7995153"
    assert jobs[1]["url"] == "https://job-boards.greenhouse.io/acme/jobs/999"
    assert "stripe.com" not in jobs[1]["url"]


def test_greenhouse_without_id_and_bad_absolute_url_emits_no_url():
    payload = {"jobs": [{"title": "Ghost", "absolute_url": "https://stripe.com/jobs/search"}]}
    scraper = GreenhouseScraper({"boards": ["acme"]})
    scraper._client = _mock_client(lambda request: httpx.Response(200, json=payload))
    try:
        jobs = asyncio.run(scraper._fetch_board("acme"))
    finally:
        _close(scraper)

    assert jobs[0]["url"] == ""
    assert jobs[0]["source_job_id"] is None


# --- ashby ------------------------------------------------------------------


def test_ashby_constructs_detail_url_and_sets_id():
    payload = {
        "jobs": [
            {"id": "abc12345-aaaa", "title": "Engineer", "jobUrl": "https://example.com/nope"},
        ]
    }
    scraper = AshbyScraper({"boards": ["acme"]})
    scraper._client = _mock_client(lambda request: httpx.Response(200, json=payload))
    try:
        jobs = asyncio.run(scraper._fetch_board("acme"))
    finally:
        _close(scraper)

    assert jobs[0]["url"] == "https://jobs.ashbyhq.com/acme/abc12345-aaaa"
    assert jobs[0]["source_job_id"] == "abc12345-aaaa"


# --- legacy adapter propagation --------------------------------------------


class _StubLegacy:
    async def fetch_jobs(self):
        return [{
            "title": "T",
            "company": "C",
            "url": "https://job-boards.greenhouse.io/acme/jobs/1",
            "source_job_id": "1",
        }]

    async def fetch_job_details(self, url):
        return {}

    async def close(self):
        return None


def test_legacy_adapter_propagates_source_job_id():
    config = SourceConfig(
        name="greenhouse",
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED,
        provenance=ProvenanceClass.JOB_BOARD,
        extra_urls=["acme"],
    )
    adapter = _LegacyAdapter(config, "GreenhouseScraper")
    adapter._legacy = _StubLegacy()
    try:
        items = asyncio.run(adapter.fetch_listings())
    finally:
        asyncio.run(adapter.close())

    assert len(items) == 1
    assert items[0].source_job_id == "1"
    assert items[0].url_candidates == ["https://job-boards.greenhouse.io/acme/jobs/1"]
