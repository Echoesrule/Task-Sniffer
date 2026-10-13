"""Tests for the ingestion engine (spec §§6, 14, 16).

Uses a temp SQLite DB and a fake adapter backed by httpx MockTransport so the
full pipeline (listing -> URL resolve -> validate -> persist -> dedup) runs
without network access.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from sqlalchemy import func as sa_func, select

from backend.models.database import Database, IngestionError, Job, Source
from backend.scrapers.adapter import JobSourceAdapter, ListingItem
from backend.services.ingestion import IngestionEngine
from backend.sources.models import (
    AccessMethod,
    PermissionStatus,
    ProvenanceClass,
    SourceConfig,
)
from backend.sources.registry import SourceRegistry


def _run(coro):
    return asyncio.run(coro)


def _approved(name: str, url: str = "") -> SourceConfig:
    return SourceConfig(
        name=name,
        url=url,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED,
        provenance=ProvenanceClass.OFFICIAL if "gov" in name else ProvenanceClass.JOB_BOARD,
        country_focus="KE",
        rate_limit=0.0,
    )


def _page(title: str, company: str, extra: str = "") -> str:
    filler = (
        "We are looking for a motivated professional to join our growing team. "
        "The successful candidate will work on interesting challenges, collaborate "
        "with experienced colleagues, and grow their skills over time."
    )
    return f"""<html><head><title>{title}</title></head>
    <body><h1>{title}</h1><p>We are {company} hiring.</p>
    <p>{filler}</p>
    <p>Responsibilities: backend work with Python and SQL.{extra}</p></body></html>"""


def make_fake_adapter(source_name: str, listings: list[tuple[str, str, str]]) -> JobSourceAdapter:
    """Return an adapter serving canned HTML detail pages."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for href, title, company in listings:
            if href in url:
                return httpx.Response(200, text=_page(title, company))
        return httpx.Response(404)

    adapter = type(
        "FakeAdapter",
        (JobSourceAdapter,),
        {
            "name": source_name,
            "job_url_patterns": [r"/jobs/[a-z0-9-]+"],
            "allowed_domains": ["fake.example.com"],
        },
    )(_approved(source_name))

    adapter._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    async def fetch_listings(*, limit=None, limiter=None):
        items = []
        for href, title, company in listings:
            items.append(
                ListingItem(
                    title=title,
                    company=company,
                    location="Nairobi",
                    url_candidates=[f"https://fake.example.com{href}?utm_source=x"],
                    raw_url=f"https://fake.example.com{href}",
                    source_url=f"https://fake.example.com{href}?utm_source=x",
                )
            )
        return items[:limit] if limit else items

    adapter.fetch_listings = fetch_listings  # type: ignore[method-assign]

    async def parse_detail(html, url):
        return {"description": f"parsed {len(html)} bytes"}

    adapter.parse_detail = parse_detail  # type: ignore[method-assign]
    return adapter


def _engine_with(db: Database) -> IngestionEngine:
    registry = SourceRegistry()

    def factory(config: SourceConfig) -> JobSourceAdapter:
        listings = _LISTING_HTML[config.name]
        return make_fake_adapter(config.name, listings)

    engine = IngestionEngine(
        db.async_session_factory,
        registry=registry,
        adapter_factory=factory,
        max_jobs_per_source=50,
    )
    return engine


_LISTING_HTML: dict[str, list[tuple[str, str, str]]] = {
    "fakesrc": [
        ("/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),
        ("/jobs/data-analyst-2", "Data Analyst", "Beta Corp"),
        ("/jobs/not-really-a-job", "Ops Manager", "Gamma Ltd"),
    ],
    "othersrc": [
        ("/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),
    ],
}


def test_run_source_persists_jobs_with_url_status(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'t1.db'}")
    _run(db.init_db())

    async def scenario():
        engine = _engine_with(db)
        registry = engine._registry
        registry.register(_approved("fakesrc"))
        result = await engine.run_source("fakesrc")
        async with db.async_session_factory() as session:
            rows = (await session.execute(select(Job))).scalars().all()
            jobs = {j.source_job_id: j for j in rows}
            src = (await session.execute(select(Source))).scalars().all()
        return result, jobs, src

    result, jobs, src = _run(scenario())
    _run(db.close())

    assert result.listings_seen == 3
    assert result.new_jobs == 3
    assert result.errors == 0
    assert len(jobs) == 3
    assert len(src) == 1
    job = jobs["backend-engineer-1"]
    assert job.title == "Backend Engineer"
    assert job.canonical_url == "https://fake.example.com/jobs/backend-engineer-1"
    assert "utm_source" not in job.canonical_url
    assert job.url_status == "VALID"
    assert job.provenances_list[0]["source"] == "fakesrc"


def test_run_source_dedups_and_merges_provenance(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'t2.db'}")
    _run(db.init_db())

    async def scenario():
        engine = _engine_with(db)
        engine._registry.register(_approved("fakesrc"))
        await engine.run_source("fakesrc")
        second = engine._registry.get("fakesrc")
        engine._registry.register(second)
        result2 = await engine.run_source("fakesrc")
        async with db.async_session_factory() as session:
            rows = (await session.execute(select(Job))).scalars().all()
            src = (await session.execute(select(Source))).scalars().one()
        return result2, rows, src

    result2, rows, src = _run(scenario())
    _run(db.close())
    # re-scrape: everything matches by (source, source_job_id) -> updated
    assert result2.new_jobs == 0
    assert result2.updated_jobs == 3
    assert len([r for r in rows]) == 3
    assert src.unique_jobs == 3


def test_run_source_cross_source_dedup_merges(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'t3.db'}")
    _run(db.init_db())

    async def scenario():
        engine = _engine_with(db)
        engine._registry.register(_approved("fakesrc"))
        engine._registry.register(_approved("othersrc"))
        await engine.run_source("fakesrc")
        result = await engine.run_source("othersrc")
        async with db.async_session_factory() as session:
            backend = (
                await session.execute(
                    select(Job).where(Job.title == "Backend Engineer")
                )
            ).scalars().first()
        return result, backend

    result, backend = _run(scenario())
    _run(db.close())
    assert result.new_jobs == 0
    assert result.duplicates == 1
    assert backend is not None
    provenances = backend.provenances_list
    assert {p["source"] for p in provenances} == {"fakesrc", "othersrc"}


def test_run_source_refused_source_does_nothing(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'t4.db'}")
    _run(db.init_db())

    async def scenario():
        engine = _engine_with(db)
        blocked = SourceConfig(
            name="blockedsrc",
            access_method=AccessMethod.HTML,
            permission_status=PermissionStatus.REVIEW,
        )
        engine._registry.register(blocked)
        result = await engine.run_source("blockedsrc", force=False)
        async with db.async_session_factory() as session:
            count = (await session.execute(select(sa_func.count(Job.id)))).scalar()
        return result, count

    result, count = _run(scenario())
    _run(db.close())
    assert count == 0
    assert result.error_messages and "permission_status" in result.error_messages[0]


def test_run_source_force_bypasses_access_policy(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'t5.db'}")
    _run(db.init_db())

    async def scenario():
        engine = _engine_with(db)
        blocked = SourceConfig(
            name="fakesrc",
            access_method=AccessMethod.HTML,
            permission_status=PermissionStatus.REVIEW,
        )
        engine._registry.register(blocked)
        result = await engine.run_source("fakesrc", force=True)
        return result

    result = _run(scenario())
    _run(db.close())
    assert result.errors == 0
    assert result.new_jobs == 3


def test_run_source_error_isolation(tmp_path):
    """A failing job never aborts the source run; errors are recorded."""

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'t6.db'}")
    _run(db.init_db())

    listings = _LISTING_HTML["fakesrc"]

    async def scenario():
        engine = _engine_with(db)
        engine._registry.register(_approved("fakesrc"))

        # force persistence to fail for exactly one job
        original = engine._persist_job

        async def flaky_persist(session, source_row, normalized, candidate, item):
            if "data-analyst-2" in candidate.get("url", ""):
                raise RuntimeError("persist boom")
            return await original(session, source_row, normalized, candidate, item)

        engine._persist_job = flaky_persist  # type: ignore[method-assign]
        result = await engine.run_source("fakesrc")

        async with db.async_session_factory() as session:
            rows = (await session.execute(select(Job))).scalars().all()
            errors = (await session.execute(select(IngestionError))).scalars().all()
        return result, rows, errors

    result, rows, errors = _run(scenario())
    _run(db.close())
    assert result.errors == 1
    assert result.new_jobs == 2
    assert len(rows) == 2
    assert "persist boom" in errors[0].error_message
    assert errors[0].stage == "process"


def test_run_source_reports_unconfigured_source(tmp_path):
    """A source with no adapter/policy is reported, not crashed on (Phase 4)."""

    from backend.scrapers.factory import build_adapter

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'t7.db'}")
    _run(db.init_db())

    async def scenario():
        engine = IngestionEngine(
            db.async_session_factory,
            registry=SourceRegistry(),
            adapter_factory=build_adapter,
            max_jobs_per_source=5,
        )
        engine._registry.register(_approved("careerpointkenya"))
        result = await engine.run_source("careerpointkenya")
        async with db.async_session_factory() as session:
            errors = (await session.execute(select(IngestionError))).scalars().all()
            jobs = (await session.execute(select(Job))).scalars().all()
        return result, errors, jobs

    result, errors, jobs = _run(scenario())
    _run(db.close())
    assert result.errors == 1
    assert result.paused is False
    assert result.new_jobs == 0
    assert any("no adapter" in m for m in result.error_messages)
    assert jobs == []
    assert errors and errors[0].stage == "adapter"
