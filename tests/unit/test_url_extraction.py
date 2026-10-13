"""Phase 3 regression tests: detail/canonical/application URL extraction.

Covers explicit apply-button extraction, canonical tag and JSON-LD
``JobPosting.url`` handling, precedence/conflict rules, gh_jid identity
preservation, and the requirement that extracted URLs cannot bypass the
Phase 2 safety/domain/validation gate. All HTTP is mocked offline.
"""

from __future__ import annotations

import asyncio
import json

import httpx
from sqlalchemy import select

from backend.models.database import Database, Job
from backend.scrapers.adapter import JobSourceAdapter, ListingItem
from backend.services.ingestion import IngestionEngine
from backend.services.normalizer import JobNormalizer
from backend.sources.models import (
    AccessMethod,
    PermissionStatus,
    ProvenanceClass,
    SourceConfig,
    UrlStatus,
)
from backend.sources.registry import SourceRegistry
from backend.sources.urls import (
    canonicalize_url,
    extract_canonical_url,
    extract_url_signals,
    validate_job_page,
)


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


FILLER = (
    "We are looking for a motivated professional to join our growing team. "
    "The successful candidate will work on interesting challenges, collaborate "
    "with experienced colleagues, and grow their skills over time."
)


def _page(
    *,
    canonical_href: str = "",
    jsonld: object | None = None,
    apply_href: str = "",
    apply_text: str = "Apply for this job",
    extra_markup: str = "",
) -> str:
    links = ""
    if canonical_href:
        links += f'<link rel="canonical" href="{canonical_href}">'
    ld = ""
    if jsonld is not None:
        ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>'
    apply = f'<a href="{apply_href}">{apply_text}</a>' if apply_href else ""
    return (
        "<html><head><title>Backend Engineer - Acme Ltd</title>"
        f"{links}{ld}</head><body>"
        "<h1>Backend Engineer</h1><p>We are Acme Ltd hiring.</p>"
        f"<p>{FILLER}</p>{apply}{extra_markup}</body></html>"
    )


VALID = _page()
DEFAULT_LISTINGS = (("/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),)
DEFAULT_DOMAINS = ("fake.example.com",)


def _listings_with(page: str) -> list[tuple[str, str, str]]:
    return DEFAULT_LISTINGS


def _make_engine(db, *, page_provider, listings=DEFAULT_LISTINGS, allowed_domains=DEFAULT_DOMAINS):
    registry = SourceRegistry()
    registry.register(_approved("fakesrc"))

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if any(href in url for href, _, _ in listings):
            return httpx.Response(200, headers={"content-type": "text/html"}, text=page_provider())
        return httpx.Response(404)

    def factory(config):
        adapter = type(
            "FakeAdapter",
            (JobSourceAdapter,),
            {
                "name": config.name,
                "job_url_patterns": [r"/jobs/[a-z0-9-]+"],
                "allowed_domains": list(allowed_domains),
            },
        )(config)
        adapter._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        )

        async def fetch_listings(*, limit=None, limiter=None):
            items = []
            for href, title, company in listings:
                items.append(
                    ListingItem(
                        title=title,
                        company=company,
                        location="Nairobi",
                        url_candidates=[f"https://fake.example.com{href}"],
                        raw_url=f"https://fake.example.com{href}",
                        source_url=f"https://fake.example.com{href}",
                    )
                )
            return items

        adapter.fetch_listings = fetch_listings  # type: ignore[method-assign]

        async def parse_detail(html, url):
            return {}

        adapter.parse_detail = parse_detail  # type: ignore[method-assign]
        return adapter

    return IngestionEngine(db.async_session_factory, registry=registry, adapter_factory=factory)


def _run_engine(db, *, page, listings=DEFAULT_LISTINGS, allowed_domains=DEFAULT_DOMAINS, runs=1):
    state = {"page": page}

    def page_provider():
        return state["page"]

    db = Database(f"sqlite+aiosqlite:///{db}")
    _run(db.init_db())
    engine = _make_engine(
        db,
        page_provider=page_provider,
        listings=listings,
        allowed_domains=allowed_domains,
    )
    results = [_run(engine.run_source("fakesrc")) for _ in range(runs)]

    async def go():
        async with db.async_session_factory() as session:
            rows = (await session.execute(select(Job))).scalars().all()
        return {j.source_job_id: j for j in rows}

    jobs = _run(go())
    _run(db.close())
    return results, jobs


# ---------------------------------------------------------------------------
# Explicit application URL extraction
# ---------------------------------------------------------------------------


def test_explicit_apply_button_absolute_url():
    page = _page(apply_href="https://fake.example.com/careers/apply/backend-engineer-1")
    signals = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    )
    assert signals.application_url == "https://fake.example.com/careers/apply/backend-engineer-1"


def test_relative_application_url_resolution():
    page = _page(apply_href="/jobs/backend-engineer-1/apply")
    signals = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1?utm_source=x",
        allowed_domains=set(DEFAULT_DOMAINS),
    )
    assert signals.application_url == "https://fake.example.com/jobs/backend-engineer-1/apply"


def test_external_ats_application_url_requires_policy():
    page = _page(apply_href="https://ats.example.com/apply/ABC123")

    denied = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains={"fake.example.com"},
    )
    assert denied.application_url == ""

    allowed = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains={"fake.example.com", "ats.example.com"},
    )
    assert allowed.application_url == "https://ats.example.com/apply/ABC123"


def test_missing_application_link_does_not_fabricate():
    signals = extract_url_signals(
        VALID, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    )
    assert signals.application_url == ""
    assert signals.canonical_url == ""


def test_no_application_url_is_stored_as_null(tmp_path):
    _results, jobs = _run_engine(tmp_path / "noapp.db", page=VALID)
    job = jobs["backend-engineer-1"]
    assert job.application_url is None


def test_failed_extraction_preserves_existing_application_url(tmp_path):
    first = _page(apply_href="/jobs/backend-engineer-1/apply")
    second = _page()

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'preserve.db'}")
    _run(db.init_db())
    state = {"page": first}

    def provider():
        return state["page"]

    engine = _make_engine(db, page_provider=provider)
    _run(engine.run_source("fakesrc"))
    before = _jobs(db)["backend-engineer-1"]
    assert before.application_url == "https://fake.example.com/jobs/backend-engineer-1/apply"

    state["page"] = second
    result = _run(engine.run_source("fakesrc"))
    after = _jobs(db)["backend-engineer-1"]
    _run(db.close())

    assert result.updated_jobs == 1
    assert after.application_url == before.application_url


def _jobs(db):
    async def go():
        async with db.async_session_factory() as session:
            rows = (await session.execute(select(Job))).scalars().all()
        return {j.source_job_id: j for j in rows}

    return _run(go())


# ---------------------------------------------------------------------------
# Canonical URL extraction (link[rel=canonical] and JSON-LD)
# ---------------------------------------------------------------------------


def test_canonical_url_extraction_and_normalization():
    page = _page(canonical_href="https://www.fake.example.com/jobs/backend-engineer-1?utm_source=x")
    canonical = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    ).canonical_url
    assert canonical == "https://www.fake.example.com/jobs/backend-engineer-1"
    assert "utm_source" not in canonical


def test_canonical_search_page_rejected():
    page = _page(canonical_href="https://fake.example.com/search/jobs")
    canonical = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    ).canonical_url
    assert canonical == ""


def test_canonical_tag_to_unsafe_private_host_rejected():
    page = _page(canonical_href="http://10.0.0.5/jobs/backend-engineer-1")
    canonical = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    ).canonical_url
    assert canonical == ""


def test_multiple_canonical_tags_first_valid_wins():
    page = (
        '<html><head><link rel="canonical" href="javascript:void(0)">'
        '<link rel="canonical" href="https://www.fake.example.com/jobs/backend-engineer-1">'
        "</head><body>%s</body></html>" % FILLER
    )
    canonical = extract_canonical_url(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
        detail_url="https://fake.example.com/jobs/backend-engineer-1",
    )
    assert canonical == "https://www.fake.example.com/jobs/backend-engineer-1"


def test_jsonld_jobposting_url_extraction():
    page = _page(
        jsonld={
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Backend Engineer",
            "url": "https://www.fake.example.com/jobs/backend-engineer-1",
        }
    )
    canonical = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    ).canonical_url
    assert canonical == "https://www.fake.example.com/jobs/backend-engineer-1"


def test_malformed_and_multiple_jsonld_objects():
    good = {
        "@type": "JobPosting",
        "title": "Backend Engineer",
        "url": "https://www.fake.example.com/jobs/backend-engineer-1",
    }
    page = _page(
        jsonld=[{"@type": "Organization", "name": "Acme"}, good],
        extra_markup='<script type="application/ld+json">{not valid json</script>',
    )
    canonical = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    ).canonical_url
    assert canonical == "https://www.fake.example.com/jobs/backend-engineer-1"


def test_conflicting_canonical_and_jsonld_do_not_override_detail_identity():
    page = _page(
        canonical_href="https://fake.example.com/jobs/data-analyst-2",
        jsonld={"@type": "JobPosting", "url": "https://fake.example.com/jobs/backend-engineer-1"},
    )
    canonical = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    ).canonical_url
    assert canonical == ""


def test_canonical_equals_detail_kept_blank():
    page = _page(canonical_href="https://fake.example.com/jobs/backend-engineer-1")
    signals = extract_url_signals(
        page, "https://fake.example.com/jobs/backend-engineer-1",
        allowed_domains=set(DEFAULT_DOMAINS),
    )
    assert signals.canonical_url == ""


def test_gh_jid_query_identity_survives_normalization():
    url = canonicalize_url("https://stripe.com/jobs/search?gh_jid=7993151&utm_source=x")
    assert "gh_jid=7993151" in url
    assert "utm_source" not in url
    job_id = JobNormalizer._extract_source_job_id(
        "https://stripe.com/jobs/search?gh_jid=7993151",
        "Stripe",
        "Backend Engineer",
        "greenhouse",
    )
    assert job_id == "7993151"


def test_search_and_company_careers_urls_not_detail():
    for url in (
        "https://fake.example.com/search/jobs?q=engineer",
        "https://fake.example.com/company/acme",
        "https://fake.example.com/",
    ):
        v = validate_job_page(
            url=url,
            status_code=200,
            page_title="Backend Engineer - Acme Ltd",
            body_text="Acme Ltd is hiring a Backend Engineer. " * 5,
            expected_title="Backend Engineer",
            expected_company="Acme Ltd",
            allowed_domains=set(DEFAULT_DOMAINS),
        )
        assert not v.ok
        assert v.status == UrlStatus.INVALID, url


def test_application_url_integration_into_job(tmp_path):
    page = _page(apply_href="/jobs/backend-engineer-1/apply")
    _results, jobs = _run_engine(tmp_path / "app.db", page=page)
    job = jobs["backend-engineer-1"]
    assert job.application_url == "https://fake.example.com/jobs/backend-engineer-1/apply"
    assert job.canonical_url == "https://fake.example.com/jobs/backend-engineer-1"


def test_canonical_url_integration_into_job(tmp_path):
    page = _page(canonical_href="https://www.fake.example.com/jobs/backend-engineer-1")
    _results, jobs = _run_engine(tmp_path / "canon.db", page=page)
    job = jobs["backend-engineer-1"]
    assert job.canonical_url == "https://www.fake.example.com/jobs/backend-engineer-1"
    assert job.source_url == "https://fake.example.com/jobs/backend-engineer-1"


def test_extracted_canonical_cannot_bypass_phase2_in_engine(tmp_path):
    page = _page(canonical_href="http://127.0.0.1/jobs/backend-engineer-1")

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'ns.db'}")
    _run(db.init_db())
    hits: list[str] = []

    def handler(request):
        hits.append(str(request.url))
        if "/jobs/backend-engineer-1" in str(request.url):
            return httpx.Response(200, headers={"content-type": "text/html"}, text=page)
        return httpx.Response(404)

    registry = SourceRegistry()
    registry.register(_approved("fakesrc"))

    def factory(config):
        adapter = type(
            "FakeAdapter",
            (JobSourceAdapter,),
            {"name": config.name, "job_url_patterns": [r"/jobs/[a-z0-9-]+"], "allowed_domains": list(DEFAULT_DOMAINS)},
        )(config)
        adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter.fetch_listings = _fetch_listings  # type: ignore[method-assign]
        adapter.parse_detail = _parse_detail  # type: ignore[method-assign]
        return adapter

    engine = IngestionEngine(db.async_session_factory, registry=registry, adapter_factory=factory)
    result = _run(engine.run_source("fakesrc"))
    jobs = _jobs(db)
    _run(db.close())

    assert result.new_jobs == 1
    assert len(hits) == 1  # the loopback canonical URL was never fetched
    assert not any("127.0.0.1" in h for h in hits)
    assert jobs["backend-engineer-1"].canonical_url == "https://fake.example.com/jobs/backend-engineer-1"


async def _fetch_listings(*, limit=None, limiter=None):
    items = []
    for href, title, company in DEFAULT_LISTINGS:
        items.append(
            ListingItem(
                title=title,
                company=company,
                location="Nairobi",
                url_candidates=[f"https://fake.example.com{href}"],
                raw_url=f"https://fake.example.com{href}",
                source_url=f"https://fake.example.com{href}",
            )
        )
    return items


async def _parse_detail(html, url):
    return {}


def test_api_and_celery_share_engine_entry_point():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for rel in ("backend/api/routes/sources.py", "backend/workers/tasks.py"):
        text = (root / rel).read_text()
        assert "run_source(" in text, rel