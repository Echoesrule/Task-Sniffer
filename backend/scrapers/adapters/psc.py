"""PSC (Public Service Commission Kenya) adapter, provenance=official.

Audited access: publicservice.go.ke/jobs/ publishes vacancy announcements;
actual applications run through the psckjobs.go.ke portal with an account, so
``requires_auth`` applies to APPLYING only. We never invent application URLs.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from backend.scrapers.adapter import JobSourceAdapter, ListingItem
from backend.sources.models import SourceConfig
from backend.sources.rate_limit import RateLimiter

from ._common import absolute, clean_text, dedupe_by_url, job_title_from_container

logger = logging.getLogger(__name__)

_DETAIL = re.compile(r"/(job|jobs|vacancy|vacancies|advert|announcement|career|careers|posting|position)[^/?#]*/[^/?#]+/?$", re.IGNORECASE)


class PscAdapter(JobSourceAdapter):
    name = "psc"
    job_url_patterns = [r"/(job|jobs|vacancy|vacancies|advert|announcement|career|careers|posting|position)[^/?#]*/[^/?#]+/?$"]
    allowed_domains = ["publicservice.go.ke", "psckjobs.go.ke"]

    def __init__(self, config: SourceConfig, client=None) -> None:
        super().__init__(config, client=client)
        self.jobs_url = (config.url or "").strip() or "https://www.publicservice.go.ke/jobs/"

    async def fetch_listings(self, *, limit: int | None = None, limiter: RateLimiter | None = None) -> list[ListingItem]:
        html = await self._fetch(self.jobs_url, limiter)
        items = self._parse_page(html, self.jobs_url)
        return dedupe_by_url(items)[:limit] if limit else dedupe_by_url(items)

    async def _fetch(self, url: str, limiter: RateLimiter | None) -> str:
        if limiter is not None:
            await limiter.wait_slot()
        try:
            return await self.fetch(url) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[psc] jobs fetch failed %s: %s", url, exc)
            return ""

    def _parse_page(self, html: str, base_url: str) -> list[ListingItem]:
        if not html:
            return []
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        items: list[ListingItem] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            if not href or href.startswith(("javascript:", "#", "mailto:")):
                continue
            full = absolute(base_url, href)
            if not full:
                continue
            path = urlparse(full).path or "/"
            if not _DETAIL.search(path):
                continue

            title = job_title_from_container(anchor) or clean_text(anchor.get_text(" ", strip=True))
            if not title:
                continue

            if full in seen:
                continue
            seen.add(full)

            item = ListingItem(
                title=title,
                company="Public Service Commission",
                location="",
                raw_url=full,
                url_candidates=[full],
                source_url=full,
            )
            parent = anchor.find_parent(["tr", "li", "div"])
            if parent is not None:
                text = clean_text(parent.get_text(" ", strip=True))
                m = re.search(
                    r"(?:closes?|deadline|application deadline)\s*[:]?\s*([0-9][^|]*?)(?:\||$)",
                    text, re.I,
                )
                if m:
                    item.closing_at = m.group(1).strip()[:60]
            items.append(item)

        return items

    async def parse_detail(self, html: str, url: str) -> dict:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        detail: dict = {}
        article = (
            soup.select_one("article")
            or soup.select_one(".job-content")
            or soup.select_one(".entry-content")
            or soup.select_one("main")
        )
        if article is not None:
            detail["description"] = clean_text(article.get_text(" ", strip=True))
        return detail