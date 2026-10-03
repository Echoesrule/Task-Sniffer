"""MyJobMag adapter (Kenya, APPROVED).

Audited access: robots.txt PARTIAL. It blocks *every* query-string URL
(``Disallow: /*?``) and ``/search/jobs?*``, ``/apply-now/``, ``/job-application/``.
Therefore this adapter only requests the query-string-free listing page
``/jobs`` and job detail pages ``/job/<slug>``, which robots allows. An RSS
feed URL can be set on the config; when configured it is tried first and the
adapter falls back to HTML if the feed is unavailable or empty.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from backend.scrapers.adapter import JobSourceAdapter, ListingItem
from backend.sources.models import SourceConfig
from backend.sources.rate_limit import RateLimiter

from ._common import absolute, clean_text, dedupe_by_url, job_title_from_container, rss_items

logger = logging.getLogger(__name__)

_JOB_DETAIL = re.compile(r"/job/[a-z0-9-]+$", re.IGNORECASE)


class MyJobMagAdapter(JobSourceAdapter):
    name = "myjobmag"
    job_url_patterns = [r"/job/[a-z0-9-]+$"]
    allowed_domains = ["myjobmag.co.ke"]

    def __init__(self, config: SourceConfig, client=None) -> None:
        super().__init__(config, client=client)
        self.feed_url = (config.feed_url or "").strip()
        self.listing_url = (config.url or "").strip() or "https://www.myjobmag.co.ke/jobs"
        if self.listing_url.replace("https://www.", "https://") == "https://myjobmag.co.ke":
            self.listing_url = "https://www.myjobmag.co.ke/jobs"

    async def fetch_listings(self, *, limit: int | None = None, limiter: RateLimiter | None = None) -> list[ListingItem]:
        if self.feed_url:
            if limiter is not None:
                await limiter.wait_slot()
            feed_items = await self._fetch_feed(limiter)
            if feed_items:
                return dedupe_by_url(feed_items)[:limit] if limit else dedupe_by_url(feed_items)

        html = await self._fetch(self.listing_url, limiter)
        items = self._parse_page(html, self.listing_url)
        return dedupe_by_url(items)[:limit] if limit else dedupe_by_url(items)

    async def _fetch_feed(self, limiter: RateLimiter | None) -> list[ListingItem]:
        try:
            xml = await self.fetch(self.feed_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[myjobmag] feed fetch failed %s: %s", self.feed_url, exc)
            return []
        if not xml:
            return []
        entries = rss_items(xml)
        items: list[ListingItem] = []
        for entry in entries:
            link = entry.get("link") or entry.get("href") or ""
            title = clean_text(entry.get("title", ""))
            if not link or not title:
                continue
            if not re.search(_JOB_DETAIL, urlparse(link).path or "/"):
                continue
            items.append(
                ListingItem(
                    title=title,
                    company="",
                    location=clean_text(entry.get("category", "")),
                    raw_url=link,
                    url_candidates=[link],
                    source_url=link,
                    description=clean_text(entry.get("description", "")),
                    posted_at=entry.get("pubDate") or entry.get("published") or entry.get("updated"),
                )
            )
        return items

    async def _fetch(self, url: str, limiter: RateLimiter | None) -> str:
        if limiter is not None:
            await limiter.wait_slot()
        try:
            return await self.fetch(url) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[myjobmag] listing fetch failed %s: %s", url, exc)
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
            if "?" in href or "/search/" in href:
                continue  # robots.txt Disallow: /*?
            full = absolute(base_url, href)
            if not full or not _JOB_DETAIL.search(urlparse(full).path or "/"):
                continue

            title = job_title_from_container(anchor)
            if not title:
                title = clean_text(anchor.get_text(" ", strip=True))
            if not title:
                continue

            if full in seen:
                continue
            seen.add(full)

            item = ListingItem(
                title=title,
                company="",
                location="",
                raw_url=full,
                url_candidates=[full],
                source_url=full,
            )
            # MyJobMag cards embed company + posted date beside the link
            card = anchor.find_parent(["li", "article", "div", "tr"])
            if card is not None:
                text = clean_text(card.get_text(" ", strip=True))
                item.company = _company_from_card(text, title)
                date_match = re.search(r"\b([0-9]{1,2}\s+\w+\s+[0-9]{4})\b", text)
                if date_match:
                    item.posted_at = date_match.group(1)
            items.append(item)

        return items

    async def parse_detail(self, html: str, url: str) -> dict:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        detail: dict = {}
        article = soup.select_one("article") or soup.select_one(".job-content") or soup.select_one(".content")
        if article is not None:
            detail["description"] = clean_text(article.get_text(" ", strip=True))
        meta = soup.select_one(".job-info") or soup.select_one(".entry-meta")
        if meta is not None:
            text = meta.get_text(" ", strip=True)
            loc = re.search(r"(?:location|county|where)[:\s-]+([A-Za-z ,]+?)(?:\||$|·)", text, re.I)
            if loc:
                detail["location"] = loc.group(1).strip()
        return detail


def _company_from_card(card_text: str, title: str) -> str:
    """Strip the title from a card's text to recover the trailing company name."""
    text = card_text
    t = title.replace("&ndash;", "-").replace("–", "-")
    if t and t in text:
        text = text.split(t, 1)[1]
    # drop date-like leading tokens
    text = re.sub(r"^(Posted\s*)?[0-9]{1,2}\s+\w+\s+[0-9]{4}\s*(\.\s*)?", "", text, flags=re.I)
    text = text.strip(" |·-–")
    return text[:120]