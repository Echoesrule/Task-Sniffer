"""Tests for legacy-adapter detail enrichment via JSON-LD."""

from __future__ import annotations

import asyncio
import json

from backend.scrapers.factory import _LegacyAdapter


def _run(coro):
    return asyncio.run(coro)


def _adapter(legacy):
    adapter = object.__new__(_LegacyAdapter)
    adapter._legacy = legacy
    return adapter


class _FakeLegacy:
    def __init__(self, details=None):
        self.details = details or {}
        self.calls = 0

    async def fetch_job_details(self, url):
        self.calls += 1
        return self.details


def _html(jobposting: dict | None) -> str:
    if jobposting is None:
        return "<html><body>No structured data</body></html>"
    return (
        '<html><head><script type="application/ld+json">'
        f"{json.dumps(jobposting)}"
        "</script></head><body></body></html>"
    )


def test_jsonld_description_wins_and_skips_legacy_fetch():
    legacy = _FakeLegacy({"description": "legacy description", "skills": ["python"]})
    adapter = _adapter(legacy)

    details = _run(
        adapter.parse_detail(
            _html(
                {
                    "@type": "JobPosting",
                    "title": "Backend Engineer",
                    "description": "<p>Structured description</p>",
                    "baseSalary": {
                        "currency": "EUR",
                        "value": {"unitText": "YEAR", "minValue": 1, "maxValue": 2},
                    },
                }
            ),
            "https://jobicy.com/jobs/1",
        )
    )

    assert details["description"] == "Structured description"
    assert details["salary_currency"] == "EUR"
    assert legacy.calls == 0


def test_legacy_details_fill_gaps_without_overriding_jsonld():
    legacy = _FakeLegacy(
        {
            "title": "Legacy title",
            "company": "Legacy Co",
            "description": "legacy description",
            "skills": ["python"],
            "url": "https://jobicy.com/jobs/1",
        }
    )
    adapter = _adapter(legacy)

    details = _run(
        adapter.parse_detail(
            _html({"@type": "JobPosting", "title": "Structured title"}),
            "https://jobicy.com/jobs/1",
        )
    )

    assert details["title"] == "Structured title"
    assert details["company"] == "Legacy Co"
    assert details["description"] == "legacy description"
    assert details["skills"] == ["python"]
    assert "url" not in details
    assert legacy.calls == 1


def test_legacy_failure_keeps_jsonld_facts():
    class _Boom:
        async def fetch_job_details(self, url):
            raise RuntimeError("network down")

    adapter = _adapter(_Boom())
    details = _run(
        adapter.parse_detail(
            _html({"@type": "JobPosting", "title": "Backend Engineer"}),
            "https://jobicy.com/jobs/1",
        )
    )
    assert details == {"title": "Backend Engineer"}
