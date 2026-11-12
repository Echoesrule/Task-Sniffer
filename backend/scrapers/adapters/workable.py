"""Workable public jobs adapter.

The unauthenticated account endpoint is documented for rendering published
jobs on a company's careers site. Collection remains REVIEW/disabled by default
until Task Sniffer's downstream use is approved for the configured account.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from backend.scrapers.adapter import JobSourceAdapter, ListingItem
from backend.sources.models import SourceConfig
from backend.sources.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

_ACCOUNT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
_DETAIL = re.compile(r"^/[^/?#]+/j/[^/?#]+/?$", re.IGNORECASE)
PUBLIC_JOBS_API = "https://www.workable.com/api/accounts"


class WorkableAdapter(JobSourceAdapter):
    """Parse published public jobs for explicitly configured Workable accounts."""

    name = "workable"
    job_url_patterns = [r"/(?:[^/?#]+/)?j/[^/?#]+/?$", r"/jobs/[^/?#]+/?$"]
    allowed_domains = ["apply.workable.com", "workable.com"]

    def __init__(self, config: SourceConfig, client=None) -> None:
        super().__init__(config, client=client)
        self.accounts = [
            account for account in config.extra_urls if _ACCOUNT.fullmatch(account)
        ]

    async def fetch_listings(
        self,
        *,
        limit: int | None = None,
        limiter: RateLimiter | None = None,
    ) -> list[ListingItem]:
        if not self.accounts:
            raise ValueError(
                "Workable requires account subdomains in WORKABLE_ACCOUNT_SUBDOMAINS"
            )

        items: list[ListingItem] = []
        for account in self.accounts:
            if limiter is not None:
                await limiter.wait_slot()
            response = await self._client.get(
                f"{PUBLIC_JOBS_API}/{account}",
                params={"details": "true"},
            )
            # In particular, do not fall back to scraping when this API fails.
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                logger.warning("[workable] malformed jobs response for account %s", account)
                continue

            company = str(payload.get("name") or "").strip()
            for job in payload["jobs"]:
                if not isinstance(job, dict):
                    continue
                title = str(job.get("title") or "").strip()
                # Workable's public careers endpoint documents `url` as the
                # job detail page and `application_url` as the application form.
                detail_url = str(job.get("url") or job.get("shortlink") or "").strip()
                if not title or not _is_detail_url(detail_url):
                    logger.warning(
                        "[workable] skipping malformed public job for account %s",
                        account,
                    )
                    continue

                location = job.get("location")
                location = location if isinstance(location, dict) else job
                location_parts = [
                    str(location.get(key) or "").strip()
                    for key in ("city", "state", "country")
                    if str(location.get(key) or "").strip()
                ]
                shortcode = str(job.get("shortcode") or job.get("code") or "").strip()
                items.append(
                    ListingItem(
                        title=title,
                        company=str(job.get("company") or company or account).strip(),
                        location=", ".join(location_parts),
                        remote=bool(job.get("telecommuting") or location.get("telecommuting"))
                        or str(job.get("workplace_type") or "").lower() == "remote",
                        posted_at=job.get("published_on") or job.get("created_at"),
                        description=str(job.get("description") or ""),
                        source_job_id=shortcode or None,
                        source_url=detail_url,
                        raw_url=detail_url,
                        url_candidates=[detail_url],
                        apply_hint=str(job.get("application_url") or "").strip(),
                    )
                )
                if limit is not None and len(items) >= limit:
                    return items
        return items

    async def parse_detail(self, html: str, url: str) -> dict:
        # The public endpoint already supplies the job description; this is an
        # optional enrichment path for HTML detail pages.
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        description = soup.select_one("[data-ui='job-description'], .job-description, main")
        if description is None:
            return {}
        return {"description": description.get_text(" ", strip=True)}


def _is_detail_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and (
            parsed.hostname == "apply.workable.com"
            or parsed.hostname == "workable.com"
            or parsed.hostname.endswith(".workable.com")
        )
        and (
            bool(_DETAIL.fullmatch(parsed.path or ""))
            or bool(re.fullmatch(r"/jobs/[^/?#]+/?", parsed.path or "", re.IGNORECASE))
        )
    )
