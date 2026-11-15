"""Tests for deterministic schema.org ``JobPosting`` extraction."""

from __future__ import annotations

import json

from backend.scrapers.jsonld import extract_jobposting


def _page(*blocks: object) -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
        for block in blocks
    )
    return f"<html><head>{scripts}</head><body></body></html>"


def _jobposting(**overrides: object) -> dict:
    base = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Backend Engineer",
        "datePosted": "2026-11-15T13:38:37+00:00",
        "validThrough": "2026-12-15T23:59:59+00:00",
        "employmentType": ["FULL_TIME"],
        "hiringOrganization": {"@type": "Organization", "name": "Acme Ltd"},
        "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": {"@type": "Country", "name": "Germany"},
        "description": "<p>Build <strong>Python</strong> services.</p>",
        "baseSalary": {
            "@type": "MonetaryAmount",
            "currency": "EUR",
            "value": {
                "@type": "QuantitativeValue",
                "unitText": "YEAR",
                "minValue": 125000,
                "maxValue": 150000,
            },
        },
    }
    base.update(overrides)
    return base


def test_extracts_core_jobposting_facts():
    facts = extract_jobposting(_page(_jobposting()))

    assert facts["title"] == "Senior Backend Engineer"
    assert facts["company"] == "Acme Ltd"
    assert facts["description"] == "Build Python services."
    assert facts["location"] == "Germany"
    assert facts["salary_currency"] == "EUR"
    assert facts["salary_min"] == 125000
    assert facts["salary_max"] == 150000
    assert facts["salary_period"] == "YEAR"
    assert facts["employment_type"] == "FULL_TIME"
    assert facts["posted_at"] == "2026-11-15T13:38:37+00:00"
    assert facts["closing_at"] == "2026-12-15T23:59:59+00:00"
    assert facts["remote"] is True
    assert facts["remote_type"] == "remote"


def test_finds_jobposting_nested_in_graph_and_list():
    page = _page(
        {"@type": "Organization", "name": "Acme"},
        {"@graph": [{"@type": "BreadcrumbList"}, _jobposting(title="Graph Job")]},
    )
    assert extract_jobposting(page)["title"] == "Graph Job"


def test_location_from_postal_address():
    posting = _jobposting(
        applicantLocationRequirements=None,
        jobLocationType=None,
        jobLocation={
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Nairobi",
                "addressCountry": "KE",
            },
        },
    )
    facts = extract_jobposting(_page(posting))
    assert facts["location"] == "Nairobi, KE"
    assert "remote_type" not in facts


def test_single_salary_value_sets_min_and_max():
    posting = _jobposting(
        baseSalary={
            "currency": "USD",
            "value": {"unitText": "HOUR", "value": 75},
        }
    )
    facts = extract_jobposting(_page(posting))
    assert facts["salary_min"] == 75
    assert facts["salary_max"] == 75
    assert facts["salary_period"] == "HOUR"


def test_missing_or_malformed_jsonld_returns_empty():
    assert extract_jobposting("") == {}
    assert extract_jobposting("<html><body>no json-ld</body></html>") == {}
    assert extract_jobposting(
        '<script type="application/ld+json">{not json}</script>'
    ) == {}
    assert extract_jobposting(_page({"@type": "Organization", "name": "Acme"})) == {}


def test_html_entities_are_unescaped_once():
    posting = _jobposting(description="<p>R&amp;D with Python</p>")
    assert extract_jobposting(_page(posting))["description"] == "R&D with Python"
