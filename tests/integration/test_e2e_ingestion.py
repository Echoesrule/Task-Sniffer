"""Phase 5 end-to-end verification of the ingestion pipeline.

These tests drive the real ``IngestionEngine`` with ``httpx.MockTransport`` and
an isolated temp SQLite database, so every stage runs for real (URL resolution,
redirect enforcement, validation gating, normalization, dedup, persistence)
without touching the network or any production database.

They assert the Phase 5 "end-to-end correctness" checklist: valid postings are
persisted; search/category/company/expired pages are rejected; unknown /
temporarily-unavailable pages are withheld; a withheld page never overwrites a
valid record; redirects cannot bypass the SSRF/domain policy; a destination that
cannot be resolved is fail-closed; duplicate ingestion does not duplicate jobs;
distinct postings are not merged; and the API and Celery share one engine entry
point.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from backend.api import deps as api_deps
from backend.api.routes import sources as sources_routes
from backend.models.database import Database, Job, User
from backend.security import create_access_token, hash_password
from backend.scrapers.adapter import JobSourceAdapter, ListingItem
from backend.services.ingestion import IngestionEngine
from backend.sources.models import (
    AccessMethod,
    PermissionStatus,
    ProvenanceClass,
    SourceConfig,
    UrlStatus,
)
from backend.sources.registry import SourceRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(coro):
    return asyncio.run(coro)


def _approved(name: str, url: str = "") -> SourceConfig:
    return SourceConfig(
        name=name,
        url=url,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED,
        provenance=ProvenanceClass.JOB_BOARD,
        country_focus="KE",
        rate_limit=0.0,
    )


def _page(title: str, company: str, body: str = "") -> str:
    filler = (
        "We are looking for a motivated professional to join our growing team. "
        "The successful candidate will work on interesting challenges, collaborate "
        "with experienced colleagues, and grow their skills over time. "
        "Responsibilities include backend work with Python and SQL."
    )
    return (
        f"<html><head><title>{title}</title></head><body>"
        f"<h1>{title}</h1><p>We are {company} hiring.</p><p>{filler}</p>"
        f"{body}</body></html>"
    )


def _build_engine(db, *, source, listings, handler, allowed_domains, patterns=None):
    registry = SourceRegistry()
    registry.register(_approved(source))
    patterns = patterns or [r"/jobs/[a-z0-9-]+"]

    def factory(config: SourceConfig) -> JobSourceAdapter:
        adapter = type(
            "E2EAdapter",
            (JobSourceAdapter,),
            {
                "name": config.name,
                "job_url_patterns": list(patterns),
                "allowed_domains": list(allowed_domains),
            },
        )(config)
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
            max_redirects=5,
        )

        async def fetch_listings(*, limit=None, limiter=None):
            items = [
                ListingItem(
                    title=title,
                    company=company,
                    location="Nairobi",
                    url_candidates=[href],
                    raw_url=href,
                    source_url=href,
                )
                for href, title, company in listings
            ]
            return items[:limit] if limit else items

        adapter.fetch_listings = fetch_listings  # type: ignore[method-assign]

        async def parse_detail(html, url):
            return {"description": "parsed detail"}

        adapter.parse_detail = parse_detail  # type: ignore[method-assign]
        return adapter

    return IngestionEngine(db.async_session_factory, registry=registry, adapter_factory=factory)


def _jobs(db):
    async def go():
        async with db.async_session_factory() as session:
            return (await session.execute(select(Job))).scalars().all()

    return _run(go())


BASE = "https://fake.example.com"
DEFAULT_LISTINGS = [(f"{BASE}/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd")]


# ---------------------------------------------------------------------------
# 1. Valid posting persisted; detail / canonical / application URLs validated
# ---------------------------------------------------------------------------


def test_valid_posting_persisted_with_distinct_validated_urls(tmp_path):
    html = _page(
        "Backend Engineer",
        "Acme Kenya Ltd",
        body=(
            f'<link rel="canonical" href="{BASE}/jobs/backend-engineer-1">'
            f'<a href="{BASE}/apply/backend-engineer-1">Apply now</a>'
        ),
    )

    def handler(request):
        if "/jobs/backend-engineer-1" in str(request.url):
            return httpx.Response(
                200, headers={"content-type": "text/html"}, text=html
            )
        return httpx.Response(404)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'valid.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db,
        source="fakesrc",
        listings=DEFAULT_LISTINGS,
        handler=handler,
        allowed_domains=("fake.example.com",),
    )
    result = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert result.new_jobs == 1 and result.errors == 0
    assert len(jobs) == 1
    job = jobs[0]
    assert job.url_status == UrlStatus.VALID.value
    assert job.canonical_url == f"{BASE}/jobs/backend-engineer-1"
    assert job.source_url.startswith(BASE)
    if job.application_url:
        assert job.application_url.startswith(BASE)


# ---------------------------------------------------------------------------
# 2. Search / category / company / careers landing pages are rejected
# ---------------------------------------------------------------------------


def test_non_job_landing_pages_are_rejected(tmp_path):
    redirections = {
        f"{BASE}/jobs/backend-engineer-1": f"{BASE}/search/jobs?q=engineer",
        f"{BASE}/jobs/data-analyst-2": f"{BASE}/category/engineering",
        f"{BASE}/jobs/ops-manager-3": f"{BASE}/company/acme",
        f"{BASE}/jobs/designer-4": f"{BASE}/careers",
    }
    listings = [
        (f"{BASE}/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),
        (f"{BASE}/jobs/data-analyst-2", "Data Analyst", "Beta Corp"),
        (f"{BASE}/jobs/ops-manager-3", "Ops Manager", "Gamma Ltd"),
        (f"{BASE}/jobs/designer-4", "Designer", "Delta Ltd"),
    ]

    def handler(request):
        url = str(request.url)
        if url in redirections:
            return httpx.Response(302, headers={"location": redirections[url]})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=_page("x", "y"))

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'reject.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db,
        source="fakesrc",
        listings=listings,
        handler=handler,
        allowed_domains=("fake.example.com",),
    )
    result = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert result.new_jobs == 0
    assert jobs == []
    # search / category / company are affirmatively invalid; a bare /careers
    # landing has no posting identity and is withheld as NEEDS_REVIEW.
    assert result.invalid_urls == 3
    assert result.review_urls == 1


# ---------------------------------------------------------------------------
# 3. Expired/removed postings are invalid, not persisted
# ---------------------------------------------------------------------------


def test_expired_posting_marked_invalid_not_persisted(tmp_path):
    def handler(request):
        url = str(request.url)
        if "/jobs/backend-engineer-1" in url:
            return httpx.Response(410, headers={"content-type": "text/html"})
        if "/jobs/data-analyst-2" in url:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=_page("Job no longer available", "Beta Corp"),
            )
        return httpx.Response(404)

    listings = [
        (f"{BASE}/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),
        (f"{BASE}/jobs/data-analyst-2", "Data Analyst", "Beta Corp"),
    ]

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'expired.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db, source="fakesrc", listings=listings, handler=handler,
        allowed_domains=("fake.example.com",),
    )
    result = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert result.new_jobs == 0
    assert jobs == []
    assert result.invalid_urls >= 1


# ---------------------------------------------------------------------------
# 4. Unknown / temporarily-unavailable page is withheld (NEEDS_REVIEW)
# ---------------------------------------------------------------------------


def test_unknown_page_is_withheld(tmp_path):
    def handler(request):
        if "/jobs/backend-engineer-1" in str(request.url):
            return httpx.Response(429, headers={"content-type": "text/html"})
        return httpx.Response(404)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'unknown.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db, source="fakesrc", listings=DEFAULT_LISTINGS, handler=handler,
        allowed_domains=("fake.example.com",),
    )
    result = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert result.new_jobs == 0
    assert jobs == []
    assert result.review_urls == 1
    assert result.invalid_urls == 0


# ---------------------------------------------------------------------------
# 5. A withheld update cannot overwrite a previously-valid record
# ---------------------------------------------------------------------------


def test_unknown_update_does_not_overwrite_valid_record(tmp_path):
    state = {"mode": "valid"}

    def handler(request):
        if "/jobs/backend-engineer-1" in str(request.url):
            if state["mode"] == "valid":
                return httpx.Response(
                    200, headers={"content-type": "text/html"},
                    text=_page("Backend Engineer", "Acme Kenya Ltd"),
                )
            return httpx.Response(503, headers={"content-type": "text/html"})
        return httpx.Response(404)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'nowoverwrite.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db, source="fakesrc", listings=DEFAULT_LISTINGS, handler=handler,
        allowed_domains=("fake.example.com",),
    )
    first = _run(engine.run_source("fakesrc"))
    assert first.new_jobs == 1
    job_before = _jobs(db)[0]
    title_before, status_before = job_before.title, job_before.url_status

    state["mode"] = "unavailable"
    second = _run(engine.run_source("fakesrc"))
    job_after = _jobs(db)[0]
    _run(db.close())

    assert second.new_jobs == 0
    assert job_after.title == title_before
    assert job_after.url_status == status_before == UrlStatus.VALID.value


# ---------------------------------------------------------------------------
# 6. ATS identifier survives normalization
# ---------------------------------------------------------------------------


def test_ats_identifier_survives_normalization(tmp_path):
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            text=_page("Backend Engineer", "Acme Kenya Ltd"),
        )

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'atsid.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db, source="fakesrc",
        listings=[(f"{BASE}/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd")],
        handler=handler, allowed_domains=("fake.example.com",),
    )
    _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "backend-engineer-1"


# ---------------------------------------------------------------------------
# 7. A redirect to a private address is blocked (never requested)
# ---------------------------------------------------------------------------


def test_redirect_to_private_address_is_blocked(tmp_path):
    hits: list[str] = []

    def handler(request):
        url = str(request.url)
        hits.append(url)
        if "/jobs/backend-engineer-1" in url:
            return httpx.Response(302, headers={"location": "http://10.0.0.5/jobs/x"})
        if "10.0.0.5" in url:
            return httpx.Response(
                200, headers={"content-type": "text/html"},
                text=_page("Backend Engineer", "Acme Kenya Ltd"),
            )
        return httpx.Response(404)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'ssrf.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db, source="fakesrc", listings=DEFAULT_LISTINGS, handler=handler,
        allowed_domains=("fake.example.com",),
    )
    result = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert result.new_jobs == 0
    assert jobs == []
    assert not any("10.0.0.5" in h for h in hits), "private hop was requested"
    assert result.invalid_urls == 1


# ---------------------------------------------------------------------------
# 8. A host that cannot be resolved is fail-closed (withheld, not fetched)
# ---------------------------------------------------------------------------


def test_dns_unverifiable_host_is_withheld(tmp_path, monkeypatch):
    import backend.sources.urls as urlsmod

    monkeypatch.setattr(urlsmod, "_resolve_host_ips", lambda host: set())
    urlsmod._DNS_CACHE.clear()
    hits: list[str] = []

    def handler(request):
        hits.append(str(request.url))
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            text=_page("Backend Engineer", "Acme Kenya Ltd"),
        )

    listings = [("https://real-ats.net/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd")]
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'dns.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db, source="fakesrc", listings=listings, handler=handler,
        allowed_domains=("real-ats.net",),
    )
    result = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert result.new_jobs == 0
    assert jobs == []
    assert hits == [], "unverifiable host must not be requested"
    assert result.review_urls == 1
    assert result.invalid_urls == 0


# ---------------------------------------------------------------------------
# 9. Duplicate ingestion does not create duplicate jobs
# ---------------------------------------------------------------------------


def test_duplicate_ingestion_does_not_create_duplicate_jobs(tmp_path):
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            text=_page("Backend Engineer", "Acme Kenya Ltd"),
        )

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'dupe.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db, source="fakesrc", listings=DEFAULT_LISTINGS, handler=handler,
        allowed_domains=("fake.example.com",),
    )
    first = _run(engine.run_source("fakesrc"))
    second = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert first.new_jobs == 1
    assert second.new_jobs == 0
    assert len(jobs) == 1


# ---------------------------------------------------------------------------
# 10. Distinct postings are not incorrectly merged
# ---------------------------------------------------------------------------


def test_distinct_postings_are_not_merged(tmp_path):
    listings = [
        (f"{BASE}/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),
        (f"{BASE}/jobs/data-analyst-2", "Data Analyst", "Beta Corp"),
    ]

    def handler(request):
        url = str(request.url)
        if "backend-engineer-1" in url:
            return httpx.Response(
                200, headers={"content-type": "text/html"},
                text=_page("Backend Engineer", "Acme Kenya Ltd"),
            )
        if "data-analyst-2" in url:
            return httpx.Response(
                200, headers={"content-type": "text/html"},
                text=_page("Data Analyst", "Beta Corp"),
            )
        return httpx.Response(404)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'distinct.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db, source="fakesrc", listings=listings, handler=handler,
        allowed_domains=("fake.example.com",),
    )
    result = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert result.new_jobs == 2
    assert len(jobs) == 2
    assert {j.title for j in jobs} == {"Backend Engineer", "Data Analyst"}


# ---------------------------------------------------------------------------
# 11. API ingestion and Celery share one engine entry point
# ---------------------------------------------------------------------------


def test_api_and_celery_share_engine_entrypoint():
    api_src = (REPO_ROOT / "backend" / "api" / "routes" / "sources.py").read_text()
    worker_src = (REPO_ROOT / "backend" / "workers" / "tasks.py").read_text()
    for text in (api_src, worker_src):
        assert "IngestionEngine" in text
        assert "run_source" in text


# ---------------------------------------------------------------------------
# 12. Source-mutating API endpoints require authentication
# ---------------------------------------------------------------------------


def test_source_mutating_endpoints_require_auth(tmp_path):
    app = FastAPI()
    app.include_router(sources_routes.router, prefix="/sources")

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'api.db'}")
    _run(db.init_db())

    async def seed():
        async with db.async_session_factory() as session:
            user = User(
                email="admin@example.com",
                hashed_password=hash_password("adminpass123"),
                is_active=True,
            )
            session.add(user)
            await session.commit()

    _run(seed())
    valid_token = create_access_token({"sub": "admin@example.com"})

    original = api_deps._db
    api_deps.set_db(db)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            no_auth = await client.post("/sources/fakesrc/pause")
            with_auth = await client.post(
                "/sources/fakesrc/pause",
                headers={"Authorization": f"Bearer {valid_token}"},
            )
            read = await client.get("/sources")
        return no_auth, with_auth, read

    try:
        no_auth, with_auth, read = _run(scenario())
    finally:
        api_deps._db = original
        _run(db.close())

    assert no_auth.status_code == 401
    assert with_auth.status_code == 404  # auth passed; source row absent
    assert read.status_code == 200
