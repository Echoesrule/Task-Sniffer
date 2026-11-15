"""Tests for the Jobicy API adapter's mapping and pagination."""

from __future__ import annotations

import asyncio
import json

from backend.scrapers.jobicy import JobicyScraper


def _run(coro):
    return asyncio.run(coro)


def _job(job_id: int, **overrides: object) -> dict:
    base = {
        "id": job_id,
        "url": f"https://jobicy.com/jobs/{job_id}-backend-engineer",
        "jobTitle": "Backend Engineer",
        "companyName": "Acme Ltd",
        "jobIndustry": ["Engineering"],
        "jobType": ["Full-Time"],
        "jobGeo": "Germany",
        "jobDescription": "<p>Python and PostgreSQL.</p>",
        "salaryCurrency": "EUR",
        "annualSalaryMin": 90000,
        "annualSalaryMax": 120000,
        "pubDate": "2026-11-15T13:38:37+00:00",
    }
    base.update(overrides)
    return base


def test_fetch_jobs_follows_cursor_pagination():
    calls: list[dict] = []
    pages = {
        None: {"jobs": [_job(1)], "hasMore": True, "nextCursor": "cursor-2"},
        "cursor-2": {"jobs": [_job(2)], "hasMore": False, "nextCursor": "cursor-3"},
    }

    async def fake_fetch(url, params=None):
        calls.append(dict(params or {}))
        return pages.get((params or {}).get("cursor"))

    scraper = JobicyScraper({"max_pages": 5})
    scraper.fetch = fake_fetch  # type: ignore[method-assign]

    jobs = _run(scraper.fetch_jobs())

    assert [job["source_job_id"] for job in jobs] == ["1", "2"]
    assert "cursor" not in calls[0]
    assert calls[1]["cursor"] == "cursor-2"
    # The API rejects a ``page`` parameter; never send one.
    assert all("page" not in call for call in calls)


def test_fetch_jobs_stops_when_has_more_is_false():
    calls = 0

    async def fake_fetch(url, params=None):
        nonlocal calls
        calls += 1
        return {"jobs": [_job(1)], "hasMore": False, "nextCursor": "ignored"}

    scraper = JobicyScraper({"max_pages": 10})
    scraper.fetch = fake_fetch  # type: ignore[method-assign]

    assert len(_run(scraper.fetch_jobs())) == 1
    assert calls == 1


def test_job_industry_is_not_treated_as_skills():
    async def fake_fetch(url, params=None):
        return {"jobs": [_job(1)], "hasMore": False}

    scraper = JobicyScraper()
    scraper.fetch = fake_fetch  # type: ignore[method-assign]

    job = _run(scraper.fetch_jobs())[0]
    assert job["skills"] == []
    assert "Engineering" not in json.dumps(job)


def test_job_type_list_is_flattened_and_salary_period_is_set():
    async def fake_fetch(url, params=None):
        return {"jobs": [_job(1)], "hasMore": False}

    scraper = JobicyScraper()
    scraper.fetch = fake_fetch  # type: ignore[method-assign]

    job = _run(scraper.fetch_jobs())[0]
    assert job["employment_type"] == "Full-Time"
    assert job["salary_period"] == "year"
    assert job["salary_currency"] == "EUR"
    assert job["remote"] is True
    assert job["remote_type"] == "remote"


def test_missing_salary_does_not_invent_currency_or_amount():
    async def fake_fetch(url, params=None):
        return {
            "jobs": [
                _job(
                    1,
                    salaryCurrency="USD",
                    annualSalaryMin=None,
                    annualSalaryMax=None,
                )
            ],
            "hasMore": False,
        }

    scraper = JobicyScraper()
    scraper.fetch = fake_fetch  # type: ignore[method-assign]

    job = _run(scraper.fetch_jobs())[0]
    assert job["salary_currency"] is None
    assert job["salary_min"] is None
    assert job["salary_max"] is None
    assert job["salary_period"] == ""


def test_missing_geo_is_not_replaced_with_a_fake_location():
    async def fake_fetch(url, params=None):
        return {"jobs": [_job(1, jobGeo="")], "hasMore": False}

    scraper = JobicyScraper()
    scraper.fetch = fake_fetch  # type: ignore[method-assign]

    assert _run(scraper.fetch_jobs())[0]["location"] == ""


def test_fetch_job_details_parses_html_jsonld():
    html = (
        '<html><head><script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "JobPosting",
                "title": "Backend Engineer",
                "hiringOrganization": {"name": "Acme Ltd"},
                "description": "<p>Python role.</p>",
                "jobLocationType": "TELECOMMUTE",
                "baseSalary": {
                    "currency": "EUR",
                    "value": {"unitText": "YEAR", "minValue": 1, "maxValue": 2},
                },
            }
        )
        + "</script></head><body></body></html>"
    )

    async def fake_fetch_text(url):
        return html

    scraper = JobicyScraper()
    scraper.fetch_text = fake_fetch_text  # type: ignore[method-assign]

    details = _run(scraper.fetch_job_details("https://jobicy.com/jobs/1"))
    assert details["title"] == "Backend Engineer"
    assert details["company"] == "Acme Ltd"
    assert details["description"] == "Python role."
    assert details["salary_currency"] == "EUR"
    assert details["url"] == "https://jobicy.com/jobs/1"


def test_fetch_job_details_returns_none_without_html():
    async def fake_fetch_text(url):
        return None

    scraper = JobicyScraper()
    scraper.fetch_text = fake_fetch_text  # type: ignore[method-assign]

    assert _run(scraper.fetch_job_details("https://jobicy.com/jobs/1")) is None
