"""KRA careers adapter (Kenya Revenue Authority, APPROVED, provenance=official).

Audited access: kra.go.ke/careers is public; no robots.txt present (404);
applications happen on the auth-gated erecruitment.kra.go.ke portal, so
``application_url`` is left to the detail page parser and never invented.
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

_DETAIL = re.compile(r"/(career|careers|job|jobs|vacancy|vacancies|position|advert)[^/?#]*/[^/?#]+/?$", re.IGNORECASE)


class KraAdapter(JobSourceAdapter):
    name = "kra"
    job_url_patterns = [r"/(career|careers|job|jobs|vacancy|vacancies|position|advert)[^/?#]*/[^/?#]+/?$"]
    allowed_domains = ["kra.go.ke", "erecruitment.kra.go.ke"]

    def __init__(self, config: SourceConfig, client=None) -> None:
        super().__init__(config, client=client)
        self.careers_url = (config.url or "").strip() or "https://www.kra.go.ke/careers"

    async def fetch_listings(self, *, limit: int | None = None, limiter: RateLimiter | None = None) -> list[ListingItem]:
        html = await self._fetch(self.careers_url, limiter)
        items = self._parse_page(html, self.careers_url)
        return dedupe_by_url(items)[:limit] if limit else dedupe_by_url(items)

    async def _fetch(self, url: str, limiter: RateLimiter | None) -> str:
        if limiter is not None:
            await limiter.wait_slot()
        try:
            return await self.fetch(url) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[kra] careers fetch failed %s: %s", url, exc)
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

            key = full
            if key in seen:
                continue
            seen.add(key)

            item = ListingItem(
                title=title,
                company="Kenya Revenue Authority",
                location="Nairobi",
                raw_url=full,
                url_candidates=[full],
                source_url=full,
            )
            # KRA lists often include closing dates right next to the link
            parent = anchor.find_parent(["tr", "li", "div"])
            if parent is not None:
                text = clean_text(parent.get_text(" ", strip=True))
                m = re.search(r"(?:closes?|deadline|deadline|closing)\s*[:]?\s*([0-9][^|]*)", text, re.I)
                if m:
                    item.closing_at = m.group(1).strip()[:60]
            items.append(item)

        return items

    async def parse_detail(self, html: str, url: str) -> dict:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        detail: dict = {}

        article = soup.select_one("article") or soup.select_one(".content") or soup.select_one("main")
        if article is not None:
            detail["description"] = clean_text(article.get_text(" ", strip=True))
        return detail