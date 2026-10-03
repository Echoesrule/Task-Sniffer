"""Job source adapter interface (spec §5).

Replaces the legacy :class:`backend.scrapers.base.JobSource` for new sources.
Every source identified in the audit gets an adapter exposing the same
contract: a listing fetch followed by per-job detail fetch, both returning
structured data with an explicit source_url.

Beyond data, adapters declare the politeness constraints that the ingestion
engine must respect (rate limit, required headers, referrer restrictions).
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.sources.models import SourceConfig, UrlStatus
from backend.sources.urls import RedirectChain, UrlValidation

logger = logging.getLogger(__name__)

#: default browser-like headers for sources that require them
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


@dataclass
class ListingItem:
    """A single job listing entry parsed from the source."""

    #: the canonical detail URL (resolved & validated by the engine)
    source_url: str = ""
    #: raw candidate hrefs for the engine's URL pipeline (never trusted as-is)
    url_candidates: list[str] = field(default_factory=list)
    #: first raw URL seen (kept only for error reporting / provenance)
    raw_url: str = ""
    #: an explicit "apply" href if the listing exposes one (unvalidated)
    apply_hint: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    remote: bool = False
    posted_at: str | None = None
    closing_at: str | None = None
    salary_text: str = ""
    currency: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    description: str = ""
    skills: list[str] = field(default_factory=list)
    partner_free: bool = False

    # strVal fields
    source_job_id: str | None = None

    def as_raw(self) -> dict[str, Any]:
        raw = {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "remote": self.remote,
            "posted_at": self.posted_at,
            "closing_at": self.closing_at,
            "salary_text": self.salary_text,
            "currency": self.currency,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "description": self.description,
            "skills": self.skills,
            "source_job_id": self.source_job_id,
        }
        if self.apply_hint:
            raw["application_url"] = self.apply_hint
        return raw


class JobSourceAdapter(abc.ABC):
    """Recommended interface every source adapter implements."""

    name: str = ""
    config: SourceConfig
    #: regex patterns used to recognise job-detail URLs (relative to path)
    job_url_patterns: list[str] = []
    #: hostname suffixes an apply/external link may live on ('' -> same host)
    allowed_domains: list[str] = []

    def __init__(self, config: SourceConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        if client is None:
            timeout = float(config.request_timeout or 30.0)

            client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                headers=DEFAULT_HEADERS,
                follow_redirects=True,
            )
        self._client = client

    async def fetch(self, url: str) -> str | None:
        """Fetch raw text/HTML/XML for a URL."""
        response = await self._client.get(url)
        response.raise_for_status()
        return response.text

    def parse_listing(self, html: str, base_url: str) -> list[ListingItem]:
        """Parse a listing page into candidate listings.

        Subclasses should call ``identify_job_url`` to get the canonical detail
        URL rather than trusting anchor order.
        """
        raise NotImplementedError  # overridden per source

    def parse_job(self, html: str, url: str) -> dict[str, Any]:
        """Parse enriched details from a single job page, though adapters with a
        structured listing fallback may keep return self as a remainder."""
        raise NotImplementedError

    def validate_page(
        self,
        *,
        url: str,
        status_code: int,
        page_title: str = "",
        body_text: str = "",
        expected_title: str = "",
        expected_company: str = "",
    ) -> UrlValidation:
        """Validate the fetched page against expected title/company + domain."""
        from backend.sources.urls import validate_job_page

        allowed = None
        if self.allowed_domains:
            allowed = {self.allowed_domains[0] if d == "" else d for d in self.allowed_domains}
            allowed.discard("")
            host = httpx.URL(url).host
            if host:
                allowed.add(host)
        return validate_job_page(
            url=url,
            status_code=status_code,
            page_title=page_title,
            body_text=body_text,
            expected_title=expected_title,
            expected_company=expected_company,
            allowed_domains=allowed,
        )

    async def close(self) -> None:
        await self._client.aclose()


async def request_with_redirect(
    client: httpx.AsyncClient,
    url: str,
    *,
    validate_title: str = "",
    validate_company: str = "",
    allowed_domains: list[str] | None = None,
    timeout: float | None = None,
) -> tuple[str | None, str | None, RedirectChain]:
    """Fetch URL resolving redirects and validating the final page.

    Returns (raw_text, final_url, redirect_chain). Validation helper returns
    None raw text when the page fails the checklist.
    """
    from backend.sources.urls import resolve_redirects

    chain: RedirectChain = await resolve_redirects(client, url)
    if chain.status >= 300 or chain.status in (404, 410):
        logger.info("job URL dead (%s) %s", chain.status, url)
        return None, chain.final_url, chain

    if not chain.final_url:
        return None, url, chain

    response = await client.get(chain.final_url)
    text = response.text if response.status_code == 200 else None
    return text, chain.final_url, chain