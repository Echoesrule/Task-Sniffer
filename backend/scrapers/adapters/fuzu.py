"""Fuzu adapter (Kenya, APPROVED via HTML/sitemap).

Audited access: robots.txt allows normal crawling; the site publishes a job
sitemap. Detail pages are hydration-driven, so the adapter treats the listing
page as the source of truth and lets the engine validate detail URLs.
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

_DETAIL = re.compile(r"/jobs/[a-z0-9-]+/?$", re.IGNORECASE)


class FuzuAdapter(JobSourceAdapter):
    name = "fuzu"
    job_url_patterns = [r"/jobs/[a-z0-9-]+/?$"]
    allowed_domains = ["fuzu.com"]

    def __init__(self, config: SourceConfig, client=None) -> None:
        super().__init__(config, client=client)
        self.listing_url = (config.url or "").strip() or (
            "https://www.fuzu.com/kenya/jobs"
        )

    async def fetch_listings(self, *, limit: int | None = None, limiter: RateLimiter | None = None) -> list[ListingItem]:
        html = await self._fetch_page(self.listing_url, limiter)
        items = self._parse_page(html, self.listing_url)

        if limiter is not None and (limit is None or len(items) < limit):
            next_page = self._next_page_url(html)
            if next_page and len(items) < (limit or float("inf")):
                page_html = await self._fetch_page(next_page, limiter)
                items.extend(self._parse_page(page_html, next_page))

        return dedupe_by_url(items)[:limit] if limit else dedupe_by_url(items)

    async def _fetch_page(self, url: str, limiter: RateLimiter | None) -> str:
        if limiter is not None:
            await limiter.wait_slot()
        try:
            text = await self.fetch(url)
            return text or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[fuzu] listing fetch failed %s: %s", url, exc)
            return ""

    def _parse_page(self, html: str, base_url: str) -> list[ListingItem]:
        if not html:
            return []
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        items: list[ListingItem] = []

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

            title = job_title_from_container(anchor)
            if not title:
                title = clean_text(anchor.get_text(" ", strip=True))
            if not title:
                continue

            company = ""
            location = ""
            for cls in ("company", "employer", "job-company", "organization"):
                el = anchor.select_one(f".{cls}")
                if el:
                    company = clean_text(el.get_text(" ", strip=True))
                    if company:
                        break

            loc_el = anchor.select_one(".job-location") or anchor.select_one(".location")
            if loc_el:
                location = clean_text(loc_el.get_text(" ", strip=True))

            items.append(
                ListingItem(
                    title=title,
                    company=company,
                    location=location,
                    raw_url=full,
                    url_candidates=[full],
                    source_url=full,
                )
            )

        return items

    def _next_page_url(self, html: str) -> str | None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            text = clean_text(anchor.get("aria-label", "") + " " + anchor.get_text(" ", strip=True)).lower()
            if "next" in text:
                return absolute(self.listing_url, str(anchor["href"]))
        return None

    async def parse_detail(self, html: str, url: str) -> dict:
        import json
        import re as _re
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        detail: dict = {}

        # JSON-LD JobPosting if present
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                blob = json.loads(script.string or "null") if script.string else None
            except json.JSONDecodeError:
                blob = None
            blob_list = blob if isinstance(blob, list) else [blob]
            for node in blob_list:
                if not isinstance(node, dict) or node.get("@type", "").lower() not in (
                    "jobposting", ["jobposting"],
                ):
                    continue
                if isinstance(node.get("@type"), list):
                    if "JobPosting" not in node["@type"]:
                        continue
                title = node.get("title") or node.get("jobTitle")
                if title:
                    detail["title"] = clean_text(str(title))
                company = ""
                hirer = node.get("hiringOrganization") or {}
                if isinstance(hirer, dict):
                    company = hirer.get("name", "")
                if company:
                    detail["company"] = clean_text(str(company))
                desc = node.get("description")
                if desc:
                    detail["description"] = clean_text(str(desc))
                loc = node.get("jobLocation") or {}
                addr = (loc or {}).get("address") if isinstance(loc, dict) else {}
                if isinstance(addr, dict) and addr.get("addressLocality"):
                    detail["location"] = clean_text(str(addr["addressLocality"]))
                if node.get("datePosted"):
                    detail["posted_at"] = str(node["datePosted"])
                sal = node.get("baseSalary")
                if isinstance(sal, dict):
                    try:
                        detail["salary_min"] = detail["salary_max"] = float(sal.get("value", 0))
                    except (TypeError, ValueError):
                        pass
                return detail

        # fallback: pull the largest text block as description
        article = soup.select_one("article") or soup.select_one(".job-description")
        if article is not None:
            detail["description"] = clean_text(article.get_text(" ", strip=True))
        return detail