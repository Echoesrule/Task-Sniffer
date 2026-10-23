from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from sqlalchemy import select

from backend.api.routes.jobs import list_jobs
from backend.models.database import Database, Job
from backend.scrapers.factory import build_adapter
from backend.services import ingestion
from backend.services.ingestion import IngestionEngine
from backend.sources.registry import SourceRegistry, default_registry


def test_myjobskenya_registered_legacy_adapter_fetches_and_parses_fixture():
    fixture = Path("tests/fixtures/myjobskenya_listing.html").read_text()
    adapter = build_adapter(default_registry.get("myjobskenya"))
    fetched_urls = []

    async def fetch_text(url):
        fetched_urls.append(url)
        return fixture

    adapter._legacy.fetch_text = fetch_text

    async def scenario():
        try:
            return await adapter.fetch_listings()
        finally:
            await adapter._legacy._client.aclose()
            await adapter.close()

    items = asyncio.run(scenario())
    assert fetched_urls == ["https://www.myjobskenya.com"]
    assert len(items) == 1
    assert items[0].title == "Sample Fixture Role"
    assert items[0].company == "Example Employer"
    assert items[0].source_url == "https://www.myjobskenya.com/job/sample-fixture-role"
    assert items[0].source_job_id == "sample-fixture-role"


def test_myjobskenya_adapter_runs_fixture_through_validation_and_persistence(tmp_path, monkeypatch):
    fixture = Path("tests/fixtures/myjobskenya_listing.html").read_text()
    detail_url = "https://www.myjobskenya.com/job/sample-fixture-role"
    detail_html = (
        "<html><head><title>Sample Fixture Role</title></head><body>"
        "<h1>Sample Fixture Role</h1><p>Example Employer is hiring.</p>"
        "<article class='job-content'>" + "Software engineering duties. " * 15 + "</article>"
        "</body></html>"
    )
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'myjobskenya.db'}")

    async def scenario():
        await db.init_db()
        config = default_registry.get("myjobskenya")
        adapter = build_adapter(config)

        async def fetch_text(url):
            return fixture if url == "https://www.myjobskenya.com" else detail_html

        adapter._legacy.fetch_text = fetch_text
        registry = SourceRegistry()
        engine = IngestionEngine(
            db.async_session_factory,
            registry=registry,
            adapter_factory=lambda _config: adapter,
        )

        async def fake_fetch_with_policy(_client, url, **_kwargs):
            return (
                httpx.Response(200, request=httpx.Request("GET", url),
                               headers={"content-type": "text/html"}, text=detail_html),
                url,
                [],
                "",
            )

        monkeypatch.setattr(ingestion, "fetch_with_policy", fake_fetch_with_policy)
        result = await engine.run_source("myjobskenya")
        async with db.async_session_factory() as session:
            jobs = (await session.execute(select(Job))).scalars().all()
            api_result = await list_jobs(
                source=None, country=None, remote=None, salary_min=None,
                match_score_min=None, risk_level=None, page=1, page_size=5,
                db=session, user=None,
            )
        await adapter._legacy._client.aclose()
        await adapter.close()
        await db.close()
        return result, jobs, api_result

    result, jobs, api_result = asyncio.run(scenario())
    assert result.listings_seen == result.parsed_jobs == 1
    assert result.identified_urls == result.normalized_jobs == result.validated_jobs == 1
    assert result.new_jobs == result.persistence_attempts == 1
    assert result.rejected_urls == 0
    assert len(jobs) == 1
    assert jobs[0].source_url == detail_url
    assert jobs[0].url_status == "VALID"
    assert api_result.total == 1
    assert len(api_result.jobs) == 1
    assert api_result.jobs[0].source == "myjobskenya"
