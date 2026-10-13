"""Phase 2 regression tests: validation gating and redirect enforcement.

The engine is exercised end-to-end with httpx.MockTransport so the pipeline
(listing -> candidate -> fetch -> validate -> persist) is deterministic and
offline. Individual ``validate_job_page`` status semantics are unit-tested too.
"""

from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import select

from backend.models.database import Database, Job
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
from backend.sources.urls import fetch_with_policy, is_safe_fetch_url, validate_job_page


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


def _page(title: str, company: str, extra: str = "") -> str:
    filler = (
        "We are looking for a motivated professional to join our growing team. "
        "The successful candidate will work on interesting challenges, collaborate "
        "with experienced colleagues, and grow their skills over time."
    )
    return (
        f"<html><head><title>{title}</title></head><body>"
        f"<h1>{title}</h1><p>We are {company} hiring.</p><p>{filler}</p>"
        f"<p>Responsibilities: backend work with Python and SQL.{extra}</p>"
        f"</body></html>"
    )


VALID_HTML = _page("Backend Engineer", "Acme Kenya Ltd")


def _build_engine(
    db,
    *,
    source: str,
    handler,
    allowed_domains,
    patterns,
    listings,
    max_redirects: int = 5,
):
    registry = SourceRegistry()
    registry.register(_approved(source))

    def factory(config):
        adapter = type(
            "FakeAdapter",
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
            max_redirects=max_redirects,
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
            return items[:limit] if limit else items

        adapter.fetch_listings = fetch_listings  # type: ignore[method-assign]

        async def parse_detail(html, url):
            return {"description": "parsed"}

        adapter.parse_detail = parse_detail  # type: ignore[method-assign]
        return adapter

    return IngestionEngine(db.async_session_factory, registry=registry, adapter_factory=factory)


def _jobs(db):
    async def go():
        async with db.async_session_factory() as session:
            return {j.source_job_id: j for j in (await session.execute(select(Job))).scalars().all()}

    return _run(go())


DEFAULT_LISTINGS = (("/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),)
DEFAULT_PATTERNS = (r"/jobs/[a-z0-9-]+",)
DEFAULT_DOMAINS = ("fake.example.com",)


def _run_case(
    tmp_path,
    dbname,
    handler,
    *,
    allowed_domains=DEFAULT_DOMAINS,
    patterns=DEFAULT_PATTERNS,
    listings=DEFAULT_LISTINGS,
    source="fakesrc",
    runs=1,
    max_redirects=5,
):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/dbname}")
    _run(db.init_db())
    engine = _build_engine(
        db,
        source=source,
        handler=handler,
        allowed_domains=allowed_domains,
        patterns=patterns,
        listings=listings,
        max_redirects=max_redirects,
    )
    results = [_run(engine.run_source(source)) for _ in range(runs)]
    rows = _jobs(db)
    _run(db.close())
    return results, rows


# ---------------------------------------------------------------------------
# 1. Valid job-detail page is eligible for normal persistence
# ---------------------------------------------------------------------------


def test_valid_job_is_persisted(tmp_path):
    def handler(request):
        if "backend-engineer-1" in str(request.url):
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    results, jobs = _run_case(tmp_path, "valid.db", handler)
    assert results[0].new_jobs == 1
    assert len(jobs) == 1
    job = jobs["backend-engineer-1"]
    assert job.url_status == UrlStatus.VALID.value


# ---------------------------------------------------------------------------
# 2. Confirmed search page is not persisted
# ---------------------------------------------------------------------------


def test_search_page_redirect_is_not_persisted(tmp_path):
    def handler(request):
        url = str(request.url)
        if url.endswith("/jobs/backend-engineer-1"):
            return httpx.Response(302, headers={"location": "https://fake.example.com/search/jobs"})
        if "/search/jobs" in url:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    results, jobs = _run_case(tmp_path, "search.db", handler)
    assert results[0].new_jobs == 0
    assert len(jobs) == 0
    assert results[0].invalid_urls == 1


# ---------------------------------------------------------------------------
# 3. Company homepage / careers landing is not persisted
# ---------------------------------------------------------------------------


def test_homepage_redirect_is_not_persisted(tmp_path):
    def handler(request):
        url = str(request.url)
        if url.endswith("/jobs/backend-engineer-1"):
            return httpx.Response(302, headers={"location": "https://fake.example.com/"})
        if url.rstrip("/") == "https://fake.example.com":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<html><body>Welcome to our company.</body></html>")
        return httpx.Response(404)

    results, jobs = _run_case(tmp_path, "home.db", handler)
    assert results[0].new_jobs == 0
    assert len(jobs) == 0


# ---------------------------------------------------------------------------
# 4. 404 is rejected for new active-job ingestion
# ---------------------------------------------------------------------------


def test_404_is_rejected(tmp_path):
    def handler(request):
        return httpx.Response(404, headers={"content-type": "text/html"}, text="not found")

    results, jobs = _run_case(tmp_path, "notfound.db", handler)
    assert results[0].new_jobs == 0
    assert len(jobs) == 0
    assert results[0].invalid_urls == 1


# ---------------------------------------------------------------------------
# 5. 403 / 429 are inconclusive (NEEDS_REVIEW), not affirmative invalid
# ---------------------------------------------------------------------------


def test_403_is_inconclusive():
    v = validate_job_page(url="https://fake.example.com/jobs/x", status_code=403, allowed_domains={"fake.example.com"})
    assert not v.ok
    assert v.status == UrlStatus.NEEDS_REVIEW


def test_429_is_inconclusive():
    v = validate_job_page(url="https://fake.example.com/jobs/x", status_code=429, allowed_domains={"fake.example.com"})
    assert not v.ok
    assert v.status == UrlStatus.NEEDS_REVIEW


def test_403_does_not_persist(tmp_path):
    def handler(request):
        return httpx.Response(403, headers={"content-type": "text/html"}, text="denied")

    results, jobs = _run_case(tmp_path, "forbidden.db", handler)
    assert results[0].new_jobs == 0
    assert len(jobs) == 0
    assert results[0].review_urls == 1


# ---------------------------------------------------------------------------
# 6. text/plain error response is not accepted as an HTML job page
# ---------------------------------------------------------------------------


def test_text_plain_response_rejected(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="upstream error: service unavailable")

    results, jobs = _run_case(tmp_path, "plain.db", handler)
    assert results[0].new_jobs == 0
    assert len(jobs) == 0


def test_validate_rejects_non_html_content_type():
    v = validate_job_page(
        url="https://fake.example.com/jobs/x",
        status_code=200,
        body_text="upstream error",
        allowed_domains={"fake.example.com"},
        content_type="text/plain",
        is_html=False,
    )
    assert not v.ok
    assert v.status == UrlStatus.INVALID


# ---------------------------------------------------------------------------
# 7. Cloudflare/CAPTCHA interstitial returning 200 is not accepted
# ---------------------------------------------------------------------------


def test_cloudflare_interstitial_not_persisted(tmp_path):
    interstitial = (
        "<html><head><title>Just a moment...</title></head>"
        "<body>Checking your browser before accessing. Enable JavaScript and cookies to continue.</body></html>"
    )

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=interstitial)

    results, jobs = _run_case(tmp_path, "cf.db", handler)
    assert results[0].new_jobs == 0
    assert len(jobs) == 0
    assert results[0].review_urls == 1


# ---------------------------------------------------------------------------
# 8. Off-policy redirect is rejected / unknown
# ---------------------------------------------------------------------------


def test_off_policy_redirect_not_persisted(tmp_path):
    def handler(request):
        url = str(request.url)
        if url.endswith("/jobs/backend-engineer-1"):
            return httpx.Response(302, headers={"location": "https://evil.example.com/jobs/backend-engineer-1"})
        if "evil.example.com" in url:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    results, jobs = _run_case(tmp_path, "offdomain.db", handler)
    assert results[0].new_jobs == 0
    assert len(jobs) == 0


# ---------------------------------------------------------------------------
# 9. Legitimate external ATS destination handled per explicit config
# ---------------------------------------------------------------------------


def test_allowed_external_ats_redirect_is_accepted(tmp_path):
    def handler(request):
        url = str(request.url)
        if url.endswith("/jobs/backend-engineer-1"):
            return httpx.Response(302, headers={"location": "https://ats.example.com/apply/abc"})
        if "ats.example.com" in url:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    results, jobs = _run_case(
        tmp_path,
        "ats.db",
        handler,
        allowed_domains=("fake.example.com", "ats.example.com"),
    )
    assert results[0].new_jobs == 1
    assert len(jobs) == 1


# ---------------------------------------------------------------------------
# 10. Redirect loop / excessive redirect chain is bounded safely
# ---------------------------------------------------------------------------


def test_redirect_loop_is_bounded(tmp_path):
    def handler(request):
        url = str(request.url)
        if "loop-a" in url:
            return httpx.Response(302, headers={"location": "https://fake.example.com/loop-b"})
        if "loop-b" in url:
            return httpx.Response(302, headers={"location": "https://fake.example.com/loop-a"})
        if url.endswith("/jobs/backend-engineer-1"):
            return httpx.Response(302, headers={"location": "https://fake.example.com/loop-a"})
        return httpx.Response(404)

    results, jobs = _run_case(tmp_path, "loop.db", handler, max_redirects=2)
    assert results[0].new_jobs == 0
    assert len(jobs) == 0
    assert results[0].errors == 0


# ---------------------------------------------------------------------------
# 11. Timeout does not mark existing valid job expired / overwrite its URL
# ---------------------------------------------------------------------------


def test_timeout_preserves_existing_valid_record(tmp_path):
    state = {"fail": False}

    def handler(request):
        if state["fail"]:
            raise httpx.ConnectTimeout("timed out")
        if "backend-engineer-1" in str(request.url):
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'timeout.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db,
        source="fakesrc",
        handler=handler,
        allowed_domains=DEFAULT_DOMAINS,
        patterns=DEFAULT_PATTERNS,
        listings=list(DEFAULT_LISTINGS),
    )
    first = _run(engine.run_source("fakesrc"))
    before = _jobs(db)["backend-engineer-1"]
    original_url = before.canonical_url

    state["fail"] = True
    second = _run(engine.run_source("fakesrc"))
    after = _jobs(db)["backend-engineer-1"]
    _run(db.close())

    assert first.new_jobs == 1
    assert second.new_jobs == 0
    assert second.updated_jobs == 0
    assert after.canonical_url == original_url
    assert after.url_status == UrlStatus.VALID.value


# ---------------------------------------------------------------------------
# 12. Invalid candidate cannot overwrite an existing valid record
# ---------------------------------------------------------------------------


def test_invalid_does_not_overwrite_valid_record(tmp_path):
    state = {"notfound": False}

    def handler(request):
        if state["notfound"]:
            return httpx.Response(404, headers={"content-type": "text/html"}, text="gone")
        if "backend-engineer-1" in str(request.url):
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'overwrite.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db,
        source="fakesrc",
        handler=handler,
        allowed_domains=DEFAULT_DOMAINS,
        patterns=DEFAULT_PATTERNS,
        listings=list(DEFAULT_LISTINGS),
    )
    _run(engine.run_source("fakesrc"))
    before = _jobs(db)["backend-engineer-1"]
    original_url = before.canonical_url

    state["notfound"] = True
    result = _run(engine.run_source("fakesrc"))
    after = _jobs(db)["backend-engineer-1"]
    _run(db.close())

    assert result.updated_jobs == 0
    assert after.canonical_url == original_url
    assert after.url_status == UrlStatus.VALID.value


# ---------------------------------------------------------------------------
# 13. Missing source config cannot silently disable domain validation
# ---------------------------------------------------------------------------


def test_empty_domain_policy_fails_closed(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)

    results, jobs = _run_case(tmp_path, "nodomain.db", handler, allowed_domains=())
    assert results[0].new_jobs == 0
    assert len(jobs) == 0
    assert results[0].review_urls == 1


def test_validate_missing_domain_policy_needs_review():
    v = validate_job_page(
        url="https://fake.example.com/jobs/x",
        status_code=200,
        page_title="Backend Engineer - Acme Kenya Ltd",
        body_text="Acme Kenya Ltd is hiring a Backend Engineer. " * 5,
        expected_title="Backend Engineer",
        expected_company="Acme Kenya Ltd",
        allowed_domains=set(),
    )
    assert not v.ok
    assert v.status == UrlStatus.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# 14. SSRF safeguards remain effective for destination resolution
# ---------------------------------------------------------------------------


def test_loopback_destination_rejected(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)

    results, jobs = _run_case(
        tmp_path,
        "ssrf.db",
        handler,
        allowed_domains=("127.0.0.1", "fake.example.com"),
        listings=(("http://127.0.0.1/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),),
        patterns=(r"/jobs/[a-z0-9-]+",),
    )
    assert results[0].new_jobs == 0
    assert len(jobs) == 0


def test_private_redirect_destination_rejected(tmp_path):
    def handler(request):
        url = str(request.url)
        if url.endswith("/jobs/backend-engineer-1"):
            return httpx.Response(302, headers={"location": "http://10.0.0.5/jobs/backend-engineer-1"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)

    results, jobs = _run_case(
        tmp_path,
        "ssrf2.db",
        handler,
        allowed_domains=("fake.example.com", "10.0.0.5"),
    )
    assert results[0].new_jobs == 0
    assert len(jobs) == 0


# ---------------------------------------------------------------------------
# 15. Security fixes: per-hop SSRF, DNS, encoded IPs, ports, savepoints
# ---------------------------------------------------------------------------


def test_intermediate_redirect_hop_is_never_fetched(tmp_path):
    hits: list[str] = []

    def handler(request):
        url = str(request.url)
        hits.append(url)
        if url.endswith("/jobs/backend-engineer-1"):
            return httpx.Response(302, headers={"location": "http://10.0.0.5/step"})
        if "10.0.0.5" in url:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    results, jobs = _run_case(tmp_path, "hop.db", handler, allowed_domains=("fake.example.com",))
    assert results[0].new_jobs == 0
    assert len(jobs) == 0
    assert results[0].invalid_urls == 1
    assert not any("10.0.0.5" in h for h in hits), "private intermediate hop was requested"


def test_dns_resolving_to_private_is_blocked(monkeypatch):
    import backend.sources.urls as urlsmod

    monkeypatch.setattr(urlsmod, "_resolve_host_ips", lambda host: {"10.0.0.5"})
    urlsmod._DNS_CACHE.clear()
    hits: list[str] = []

    def handler(request):
        hits.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)

    async def go():
        try:
            return await urlsmod.fetch_with_policy(client, "https://rebind.public-ats.net/jobs/x")
        finally:
            await client.aclose()

    response, _final, _chain, error = _run(go())
    assert response is None
    assert "unsafe" in error
    assert hits == []


def test_dns_failure_is_fail_closed_and_not_cached(monkeypatch):
    import backend.sources.urls as urlsmod

    monkeypatch.setattr(urlsmod, "_resolve_host_ips", lambda host: set())
    urlsmod._DNS_CACHE.clear()
    hits: list[str] = []

    def handler(request):
        hits.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)

    async def go():
        try:
            return await urlsmod.fetch_with_policy(client, "https://unresolvable.public-ats.net/jobs/x")
        finally:
            await client.aclose()

    response, _final, _chain, error = _run(go())
    assert response is None, "unverifiable host must not be fetched"
    assert "could not be verified" in error
    assert "unsafe" not in error
    assert hits == []
    # failures must not poison the cache (no permanent lock-out)
    assert "unresolvable.public-ats.net" not in urlsmod._DNS_CACHE


def test_classify_url_safety_verdicts(monkeypatch):
    import backend.sources.urls as urlsmod

    monkeypatch.setattr(urlsmod, "_resolve_host_ips", lambda host: set())
    urlsmod._DNS_CACHE.clear()
    assert _run(urlsmod._classify_url_safety("https://unresolvable.public-ats.net/x")) == urlsmod.SAFETY_UNVERIFIED

    monkeypatch.setattr(urlsmod, "_resolve_host_ips", lambda host: {"10.1.2.3"})
    urlsmod._DNS_CACHE.clear()
    assert _run(urlsmod._classify_url_safety("https://rebind.public-ats.net/x")) == urlsmod.SAFETY_UNSAFE

    monkeypatch.setattr(urlsmod, "_resolve_host_ips", lambda host: {"93.184.216.34"})
    urlsmod._DNS_CACHE.clear()
    assert _run(urlsmod._classify_url_safety("https://real-ats.net/x")) == urlsmod.SAFETY_SAFE
    assert urlsmod._DNS_CACHE["real-ats.net"] == frozenset({"93.184.216.34"})


def test_encoded_ip_literals_are_rejected():
    for url in (
        "http://2130706433/",
        "http://0x7f000001/",
        "http://017700000001/",
        "http://127.1/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::1]/",
    ):
        assert not is_safe_fetch_url(url), url


def test_non_web_ports_rejected():
    assert not is_safe_fetch_url("http://fake.example.com:22/jobs/x")
    assert not is_safe_fetch_url("https://fake.example.com:3306/jobs/x")
    assert is_safe_fetch_url("https://fake.example.com:8443/jobs/x")
    assert is_safe_fetch_url("https://fake.example.com:443/jobs/x")
    assert is_safe_fetch_url("http://fake.example.com:80/jobs/x")


def test_company_page_is_invalid():
    v = validate_job_page(
        url="https://fake.example.com/company/acme",
        status_code=200,
        page_title="Backend Engineer - Acme Kenya Ltd",
        body_text="Acme Kenya Ltd is hiring a Backend Engineer. " * 5,
        expected_title="Backend Engineer",
        expected_company="Acme Kenya Ltd",
        allowed_domains={"fake.example.com"},
    )
    assert not v.ok
    assert v.status == UrlStatus.INVALID


def test_homepage_is_invalid():
    v = validate_job_page(
        url="https://fake.example.com/",
        status_code=200,
        page_title="Backend Engineer - Acme Kenya Ltd",
        body_text="Acme Kenya Ltd is hiring a Backend Engineer. " * 5,
        expected_title="Backend Engineer",
        expected_company="Acme Kenya Ltd",
        allowed_domains={"fake.example.com"},
    )
    assert not v.ok
    assert v.status == UrlStatus.INVALID


def test_script_noise_does_not_trigger_antibot(tmp_path):
    noisy = VALID_HTML.replace(
        "</body>",
        "<script>var msg='just a moment, checking your browser and captcha';</script></body>",
    )

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=noisy)

    results, jobs = _run_case(tmp_path, "noise.db", handler)
    assert results[0].new_jobs == 1
    assert len(jobs) == 1


def test_redirect_chain_and_original_url_recorded(tmp_path):
    def handler(request):
        url = str(request.url)
        if url.endswith("/jobs/backend-engineer-1"):
            return httpx.Response(302, headers={"location": "https://ats.example.com/apply/abc"})
        if "ats.example.com" in url:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    results, jobs = _run_case(
        tmp_path,
        "chain.db",
        handler,
        allowed_domains=("fake.example.com", "ats.example.com"),
    )
    assert results[0].new_jobs == 1
    job = jobs["backend-engineer-1"]
    assert job.original_url == "https://fake.example.com/jobs/backend-engineer-1"
    assert job.final_url == "https://ats.example.com/apply/abc"
    assert "https://fake.example.com/jobs/backend-engineer-1" in job.redirect_chain_list
    assert "https://ats.example.com/apply/abc" in job.redirect_chain_list


def test_5xx_preserves_existing_valid_record(tmp_path):
    state = {"code": 200}

    def handler(request):
        if state["code"] >= 300:
            return httpx.Response(state["code"], headers={"content-type": "text/html"}, text="error")
        if "backend-engineer-1" in str(request.url):
            return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)
        return httpx.Response(404)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'fivexx.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db,
        source="fakesrc",
        handler=handler,
        allowed_domains=DEFAULT_DOMAINS,
        patterns=DEFAULT_PATTERNS,
        listings=list(DEFAULT_LISTINGS),
    )
    _run(engine.run_source("fakesrc"))
    before = _jobs(db)["backend-engineer-1"]

    state["code"] = 503
    result = _run(engine.run_source("fakesrc"))
    after = _jobs(db)["backend-engineer-1"]
    _run(db.close())

    assert result.updated_jobs == 0
    assert after.canonical_url == before.canonical_url
    assert after.url_status == UrlStatus.VALID.value


def test_partial_failure_rolls_back_only_that_job(tmp_path):
    listings = (
        ("/jobs/backend-engineer-1", "Backend Engineer", "Acme Kenya Ltd"),
        ("/jobs/failing-engineer-2", "Failing Engineer", "Acme Kenya Ltd"),
    )

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=VALID_HTML)

    db = Database(f"sqlite+aiosqlite:///{tmp_path/'savepoint.db'}")
    _run(db.init_db())
    engine = _build_engine(
        db,
        source="fakesrc",
        handler=handler,
        allowed_domains=DEFAULT_DOMAINS,
        patterns=DEFAULT_PATTERNS,
        listings=listings,
    )

    original = engine._persist_job

    async def flaky(session, source_row, normalized, candidate, item):
        if "failing" in item.source_url:
            session.add(
                Job(
                    source_id=source_row.id,
                    source_job_id="partial-write",
                    title=item.title,
                    company="Acme Kenya Ltd",
                    source_url=item.source_url,
                    url_status=UrlStatus.VALID.value,
                )
            )
            await session.flush()
            raise ValueError("boom")
        return await original(session, source_row, normalized, candidate, item)

    engine._persist_job = flaky  # type: ignore[method-assign]
    result = _run(engine.run_source("fakesrc"))
    rows = _jobs(db)
    _run(db.close())

    assert result.errors == 1
    assert "backend-engineer-1" in rows
    assert "partial-write" not in rows
    assert len(rows) == 1

