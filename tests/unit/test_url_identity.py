"""Phase 1 regression tests.

Covers URL identity extraction, ATS URL classification, normalization
stability, and the Greenhouse ``gh_jid`` regression. These tests exercise the
current interfaces of ``JobNormalizer`` and ``backend.sources.urls``.
"""

from __future__ import annotations

import pytest

from backend.services.normalizer import JobNormalizer
from backend.sources.models import UrlType
from backend.sources.urls import (
    CandidateLink,
    canonicalize_url,
    classify_url,
    identify_job_url,
)


# ---------------------------------------------------------------------------
# A. Query-based job identity
# ---------------------------------------------------------------------------


def test_greenhouse_query_identity_is_preserved():
    n = JobNormalizer()
    out = n.normalize(
        {
            "title": "Account Executive",
            "company": "Stripe",
            "url": "https://stripe.com/jobs/search?gh_jid=7993151",
        },
        "greenhouse",
    )
    assert "gh_jid=7993151" in out["url"]
    assert out["source_job_id"] == "7993151"


def test_generic_job_id_query_identity_is_extracted():
    n = JobNormalizer()
    out = n.normalize(
        {
            "title": "Backend Engineer",
            "company": "Fuzu",
            "url": "https://www.fuzu.com/kenya/jobs/x?job_id=42",
        },
        "fuzu",
    )
    assert out["source_job_id"] == "42"
    assert "job_id=42" in out["url"]


def test_source_specific_identifier_beats_generic_path_segment():
    n = JobNormalizer()
    out = n.normalize(
        {
            "title": "Account Executive",
            "company": "Stripe",
            "url": "https://stripe.com/jobs/search?gh_jid=7993151",
        },
        "greenhouse",
    )
    assert out["source_job_id"] not in {"search", "jobs"}


def test_no_identity_from_generic_path_segment():
    n = JobNormalizer()
    out = n.normalize(
        {"title": "T", "company": "C", "url": "https://stripe.com/jobs/search"},
        "stripe",
    )
    assert out["source_job_id"] not in {"search", "jobs"}
    assert out["source_job_id"]


def test_slug_job_url_identity_unchanged():
    n = JobNormalizer()
    out = n.normalize(
        {
            "title": "Dev",
            "company": "Acme",
            "url": "https://www.fuzu.com/kenya/jobs/backend-engineer-42",
        },
        "fuzu",
    )
    assert out["source_job_id"] == "backend-engineer-42"


def test_tracking_params_stripped_identity_survives():
    n = JobNormalizer()
    out = n.normalize(
        {
            "title": "T",
            "company": "C",
            "url": "https://example.com/jobs/1?utm_source=news&job_id=5",
        },
        "example",
    )
    assert "utm_source" not in out["url"]
    assert "job_id=5" in out["url"]
    assert out["source_job_id"] == "5"


def test_unrelated_query_param_is_not_identity():
    n = JobNormalizer()
    out = n.normalize(
        {
            "title": "T",
            "company": "C",
            "url": "https://example.com/jobs/known-role?color=blue",
        },
        "example",
    )
    assert out["source_job_id"] == "known-role"


# ---------------------------------------------------------------------------
# B. ATS URL classification
# ---------------------------------------------------------------------------

VALID_ATS_DETAIL_URLS = [
    "https://jobs.ashbyhq.com/openai/abc-123",
    "https://apply.workable.com/acme/j/ABC123/",
    "https://remotive.com/remote-jobs/software-dev/some-role-123",
]

NON_DETAIL_URLS = [
    "https://myjobmag.co.ke/search/jobs?q=x",
    "https://example.com/company/acme",
    "https://kra.go.ke/careers",
    "https://example.com/category/engineering",
    "https://example.com/jobs?page=2",
    "https://jobs.ashbyhq.com/openai",
]


@pytest.mark.parametrize("url", VALID_ATS_DETAIL_URLS)
def test_valid_ats_detail_urls_classified_as_job_detail(url):
    assert classify_url(url) == UrlType.JOB_DETAIL


@pytest.mark.parametrize("url", VALID_ATS_DETAIL_URLS)
def test_valid_ats_detail_urls_are_identified(url):
    assert identify_job_url([CandidateLink(url=url)]) is not None


@pytest.mark.parametrize("url", NON_DETAIL_URLS)
def test_non_detail_urls_are_not_job_detail(url):
    assert classify_url(url) != UrlType.JOB_DETAIL


@pytest.mark.parametrize("url", NON_DETAIL_URLS)
def test_non_detail_urls_are_not_identified(url):
    assert identify_job_url([CandidateLink(url=url)]) is None


# ---------------------------------------------------------------------------
# C. Normalization stability
# ---------------------------------------------------------------------------

STABILITY_URLS = [
    "https://example.com/jobs/1?utm_source=a&job_id=5",
    "https://example.com/jobs/1#apply",
    "HTTPS://WWW.Example.COM/jobs/1/",
    "https://jobs.ashbyhq.com/openai/abc-123?utm_campaign=x",
    "https://stripe.com/jobs/search?gh_jid=7993151",
]


@pytest.mark.parametrize("url", STABILITY_URLS)
def test_canonicalize_is_idempotent(url):
    once = canonicalize_url(url)
    assert canonicalize_url(once) == once


def test_normalizer_url_is_idempotent():
    n = JobNormalizer()
    url = "https://example.com/jobs/1?utm_source=a&job_id=5"
    once = n.normalize({"title": "T", "company": "C", "url": url}, "example")["url"]
    twice = n.normalize({"title": "T", "company": "C", "url": once}, "example")["url"]
    assert once == twice


def test_fragment_is_removed():
    assert "#" not in canonicalize_url("https://example.com/jobs/1#apply")


def test_scheme_and_host_are_normalized():
    assert canonicalize_url("HTTPS://WWW.Example.COM/jobs/1/") == (
        "https://www.example.com/jobs/1"
    )


def test_distinct_jobs_do_not_collapse():
    a = canonicalize_url("https://example.com/jobs/1?job_id=1")
    b = canonicalize_url("https://example.com/jobs/2?job_id=2")
    assert a != b


# ---------------------------------------------------------------------------
# D. Greenhouse regression
# ---------------------------------------------------------------------------


def test_greenhouse_search_url_keeps_jid_but_is_not_a_job_detail():
    url = "https://stripe.com/jobs/search?gh_jid=7993151"

    n = JobNormalizer()
    out = n.normalize(
        {"title": "Account Executive", "company": "Stripe", "url": url},
        "greenhouse",
    )
    assert out["source_job_id"] == "7993151"
    assert "gh_jid=7993151" in out["url"]

    # containing gh_jid does NOT make the search page a valid job detail
    assert classify_url(url) != UrlType.JOB_DETAIL
    assert identify_job_url([CandidateLink(url=url)]) is None
