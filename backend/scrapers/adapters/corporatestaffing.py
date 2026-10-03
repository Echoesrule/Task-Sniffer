"""Corporate Staffing Kenya adapter (APPROVED via HTML).

Audited access: robots.txt allows normal crawling (Bingbot has a crawl-delay,
which is irrelevant to our politeness policy); WordPress site. Job posts are
linked from the /jobs/ archive.
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

_DETAIL = re.compile(r"/(job|jobs|vacancy|vacancies|position|opportunity)[s]?/[^/?#]+/?$", re.IGNORECASE)


class CorporateStaffingAdapter(JobSourceAdapter):
    name = "corporatestaffing"
    job_url_patterns = [r"/(job|jobs|vacancy|vacancies|position|opportunity)/[^/?#]+/?$"]
    allowed_domains = ["corporatestaffing.co.ke"]

    def __init__(self, config: SourceConfig, client=None) -> None:
        super().__init__(config, client=client)
        self.archive_url = (config.url or "").strip() or "https://www.corporatestaffing.co.ke/jobs/"

    async def fetch_listings(self, *, limit: int | None = None, limiter: RateLimiter | None = None) -> list[ListingItem]:
        html = await self._fetch(self.archive_url, limiter)
        items = self._parse_page(html, self.archive_url)
        return dedupe_by_url(items)[:limit] if limit else dedupe_by_url(items)

    async def _fetch(self, url: str, limiter: RateLimiter | None) -> str:
        if limiter is not None:
            await limiter.wait_slot()
        try:
            return await self.fetch(url) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[corporatestaffing] fetch failed %s: %s", url, exc)
            return ""

    def _parse_page(self, html: str, base_url: str) -> list[ListingItem]:
        if not html:
            return []
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        items: list[ListingItem] = []

        seen_titles: dict[str, ListingItem] = {}
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            if not href or href.startswith(("javascript:", "#", "mailto:")):
                continue
            full = absolute(base_url, href)
            if not full or not _DETAIL.search(urlparse(full).path or "/"):
                continue

            title = job_title_from_container(anchor)
            if not title:
                title = clean_text(anchor.get_text(" ", strip=True))
            if not title:
                continue

            item = ListingItem(
                title=title,
                company="",
                location="",
                raw_url=full,
                url_candidates=[full],
                source_url=full,
            )

            # attach company/location hints from nearby card node
            card = anchor.find_parent(["article", "li", "div", "tr"])
            if card is not None:
                for cls in ("company", "employer", "org"):
                    el = card.select_one(f".{cls}")
                    if el:
                        item.company = clean_text(el.get_text(" ", strip=True))
                        break
                loc_el = card.select_one(".location") or card.select_one(".job-location")
                if loc_el is not None:
                    item.location = clean_text(loc_el.get_text(" ", strip=True))

            seen_titles.setdefault(title.lower(), item)
            items.append(item)

        return list(seen_titles.values())

    async def parse_detail(self, html: str, url: str) -> dict:
        import re as _re
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        detail: dict = {}

        article = soup.select_one("article") or soup.select_one(".entry-content") or soup.select_one(".job-content")
        if article is not None:
            detail["description"] = clean_text(article.get_text(" ", strip=True))

        meta = soup.select_one(".entry-meta") or soup.select_one(".job-meta")
        if meta is not None:
            text = meta.get_text(" ", strip=True)
            loc_match = _re.search(r"(?:location|where)[:\s]+([^|,]+)", text, _re.I)
            if loc_match:
                detail["location"] = loc_match.group(1).strip()
        return detail