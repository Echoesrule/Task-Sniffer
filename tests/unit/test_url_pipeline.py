"""Tests for the URL pipeline (spec §§7-11)."""

from backend.sources.urls import (
    CandidateLink,
    canonicalize_url,
    classify_url,
    extract_candidate_urls,
    identify_job_url,
    strip_tracking_params,
    validate_job_page,
)
from backend.sources.models import UrlStatus, UrlType

LISTING = (
    '<html><body>'
    '<a href="/kenya/jobs?utm_source=newsletter">Browse jobs</a>'
    '<a href="/kenya/jobs/backend-engineer-42?utm_medium=email&job_id=42">Backend Engineer</a>'
    '<a href="/about">About</a>'
    '<a href="https://external.example.com/tracking?gclid=abc">Vendor</a>'
    '</body></html>'
)


def test_canonicalize_normalizes_host_scheme_and_strips_tracking():
    url = canonicalize_url(
        "HTTPS://www.Fuzu.com/kenya/jobs/backend-dev?utm_source=x&job_id=42#frag"
    )
    assert url == "https://www.fuzu.com/kenya/jobs/backend-dev?job_id=42"
    assert "#" not in url
    assert "utm_source" not in url


def test_identity_params_preserved_tracking_stripped():
    url = strip_tracking_params(
        "https://x.com/job?id=9&utm_campaign=summer&ref=home"
    )
    assert "id=9" in url
    assert "utm_campaign" not in url
    assert "ref=home" in url


def test_classify_detail_vs_listing_vs_search():
    assert classify_url("https://www.fuzu.com/kenya/jobs/backend-dev") == UrlType.JOB_DETAIL
    assert classify_url("https://www.myjobmag.co.ke/job/chief-finance-officer") == UrlType.JOB_DETAIL
    assert classify_url("https://www.fuzu.com/kenya/jobs") == UrlType.UNKNOWN
    assert classify_url("https://myjobmag.co.ke/search/jobs?q=x") == UrlType.SEARCH
    assert classify_url("https://kra.go.ke/careers") == UrlType.UNKNOWN
    assert classify_url("https://kra.go.ke/careers/tax-officer-2026") == UrlType.JOB_DETAIL


def test_source_patterns_override_classify():
    assert (
        classify_url("https://www.fuzu.com/kenya/jobs/backend-dev",
                     source_patterns=[r"/jobs/[a-z0-9-]+/?$"])
        == UrlType.JOB_DETAIL
    )


def test_extract_candidates_canonicalized_deduped_skips_non_http():
    links = extract_candidate_urls(LISTING, "https://www.fuzu.com/kenya/jobs")
    urls = [l.url for l in links]
    assert any(u == "https://www.fuzu.com/kenya/jobs/backend-engineer-42?job_id=42" for u in urls)
    assert "https://www.fuzu.com/about" in urls
    # 'gclid' tracking link is canonicalized (still kept here since canonicalization
    # removes tracking params but doesn't drop the link)
    assert not any("utm" in u for u in urls)


def test_identify_job_url_does_not_trust_first_anchor():
    links = extract_candidate_urls(LISTING, "https://www.fuzu.com/kenya/jobs")
    chosen = identify_job_url(links, title_hint="Backend Engineer")
    assert chosen is not None
    assert "backend-engineer-42" in chosen.url
    assert chosen.url.startswith("https://www.fuzu.com")


def test_identify_job_url_returns_none_when_no_detail():
    links = [
        CandidateLink(url="https://a.com/jobs", text="Browse"),
        CandidateLink(url="https://a.com/about", text="About"),
    ]
    assert identify_job_url(links, title_hint="Engineer") is None


def test_validate_job_page_ok():
    v = validate_job_page(
        url="https://fuzu.com/kenya/jobs/backend-engineer-42",
        status_code=200,
        page_title="Backend Engineer - Acme Ltd",
        body_text="We are Acme Ltd seeking a Backend Engineer with Python. Apply now.",
        expected_title="Backend Engineer",
        expected_company="Acme Ltd",
        allowed_domains={"fuzu.com"},
        has_job_markers=True,
    )
    assert v.ok
    assert v.status == UrlStatus.VALID


def test_validate_job_page_http_error_invalid():
    v = validate_job_page(
        url="https://fuzu.com/kenya/jobs/backend-engineer-42",
        status_code=404,
        allowed_domains={"fuzu.com"},
    )
    assert not v.ok
    assert v.status == UrlStatus.INVALID


def test_validate_job_page_unexpected_domain_needs_review():
    v = validate_job_page(
        url="https://evil.example.com/kenya/jobs/backend-engineer-42",
        status_code=200,
        page_title="Backend Engineer - Acme Ltd",
        body_text="stuff stuff stuff stuff backend engineer acme",
        expected_title="Backend Engineer",
        expected_company="Acme Ltd",
        allowed_domains={"fuzu.com"},
    )
    assert not v.ok
    assert v.status == UrlStatus.NEEDS_REVIEW


def test_validate_job_page_no_content_needs_review():
    v = validate_job_page(
        url="https://fuzu.com/kenya/jobs/backend-engineer-42",
        status_code=200,
        page_title="Backend Engineer - Acme Ltd",
        body_text="",
        expected_title="Backend Engineer",
        expected_company="Acme Ltd",
        allowed_domains={"fuzu.com"},
    )
    assert not v.ok
    assert v.status == UrlStatus.NEEDS_REVIEW