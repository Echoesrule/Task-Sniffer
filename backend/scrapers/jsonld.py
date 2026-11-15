"""Extract structured job facts from a page's JSON-LD ``JobPosting``.

Sources such as Jobicy, Greenhouse, and Fuzu publish a schema.org ``JobPosting``
block on their HTML detail pages. The listing/API payload often omits fields
that are present here (salary, closing date, employment type), so parsing this
block is the deterministic enrichment path for legacy adapters.

Only explicit facts are returned. Missing fields are omitted rather than
defaulted, so the normalizer can keep "unknown" distinct from a real value.
"""

from __future__ import annotations

import html as html_module
import json
from typing import Any, Iterator

from bs4 import BeautifulSoup

from backend.scrapers.adapters._common import clean_text


def _nodes(blob: Any) -> Iterator[dict[str, Any]]:
    """Yield every dict node, including ``@graph``/``mainEntity`` children."""
    if isinstance(blob, list):
        for item in blob:
            yield from _nodes(item)
        return
    if not isinstance(blob, dict):
        return
    yield blob
    graph = blob.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _nodes(item)
    main = blob.get("mainEntity")
    if isinstance(main, (dict, list)):
        yield from _nodes(main)


def _is_jobposting(node: dict[str, Any]) -> bool:
    value = node.get("@type")
    if isinstance(value, str):
        return value.lower() == "jobposting"
    if isinstance(value, list):
        return any(str(item).lower() == "jobposting" for item in value)
    return False


def _first_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            text = _first_str(item)
            if text:
                return text
    return ""


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _salary(node: dict[str, Any]) -> dict[str, Any]:
    salary = node.get("baseSalary")
    if not isinstance(salary, dict):
        return {}

    currency = _first_str(salary.get("currency"))
    value = salary.get("value")
    period = ""
    minimum: int | None = None
    maximum: int | None = None

    if isinstance(value, list) and value:
        value = value[0]

    if isinstance(value, dict):
        period = _first_str(value.get("unitText"))
        minimum = _to_int(value.get("minValue"))
        maximum = _to_int(value.get("maxValue"))
        if minimum is None:
            minimum = _to_int(value.get("value"))
        if maximum is None:
            maximum = _to_int(value.get("value"))
    else:
        minimum = _to_int(value)
        maximum = minimum

    result: dict[str, Any] = {}
    if currency:
        result["salary_currency"] = currency
    if minimum is not None:
        result["salary_min"] = minimum
    if maximum is not None:
        result["salary_max"] = maximum
    if period:
        result["salary_period"] = period
    return result


def _address_text(address: Any) -> str:
    if isinstance(address, str):
        return clean_text(address)
    if not isinstance(address, dict):
        return ""
    parts: list[str] = []
    for key in ("addressLocality", "addressRegion", "addressCountry"):
        value = address.get(key)
        if isinstance(value, dict):
            value = value.get("name") or value.get("addressCountry")
        text = _first_str(value)
        if text and text not in parts:
            parts.append(text)
    return ", ".join(parts)


def _location(node: dict[str, Any]) -> str:
    location = node.get("jobLocation")
    if isinstance(location, list):
        location = location[0] if location else None
    if isinstance(location, dict):
        text = _address_text(location.get("address"))
        if text:
            return text
        text = _first_str(location.get("name"))
        if text:
            return text

    # Remote postings often omit jobLocation and instead list the countries a
    # candidate may live in.
    requirements = node.get("applicantLocationRequirements")
    if isinstance(requirements, list):
        requirements = requirements[0] if requirements else None
    if isinstance(requirements, dict):
        return _first_str(requirements.get("name"))
    return _first_str(requirements)


def _employment_type(node: dict[str, Any]) -> str:
    value = node.get("employmentType")
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return _first_str(value)


def extract_jobposting(html: str) -> dict[str, Any]:
    """Return explicit ``JobPosting`` facts found in ``html``.

    The returned keys match the normalizer/adapter payload:
    ``title``, ``company``, ``description``, ``location``,
    ``salary_currency``, ``salary_min``, ``salary_max``, ``salary_period``,
    ``employment_type``, ``posted_at``, ``closing_at``, ``remote``,
    ``remote_type``.
    """
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            blob = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _nodes(blob):
            if not _is_jobposting(node):
                continue

            result: dict[str, Any] = {}
            title = _first_str(node.get("title") or node.get("jobTitle"))
            if title:
                result["title"] = clean_text(title)

            hirer = node.get("hiringOrganization")
            if isinstance(hirer, list):
                hirer = hirer[0] if hirer else None
            if isinstance(hirer, dict):
                company = _first_str(hirer.get("name"))
                if company:
                    result["company"] = clean_text(company)

            description = node.get("description")
            if description:
                result["description"] = clean_text(
                    html_module.unescape(str(description))
                )

            location = _location(node)
            if location:
                result["location"] = location

            result.update(_salary(node))

            employment_type = _employment_type(node)
            if employment_type:
                result["employment_type"] = employment_type

            posted_at = _first_str(node.get("datePosted"))
            if posted_at:
                result["posted_at"] = posted_at

            closing_at = _first_str(node.get("validThrough"))
            if closing_at:
                result["closing_at"] = closing_at

            location_type = _first_str(node.get("jobLocationType")).upper()
            if location_type == "TELECOMMUTE":
                result["remote"] = True
                result["remote_type"] = "remote"

            return result

    return {}
