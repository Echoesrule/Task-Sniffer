"""JoBound scraper - Hidden remote SWE jobs."""

import logging
import re
from typing import Any

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class JoBoundScraper(BaseScraper):
    """Scrape remote software engineering jobs from JoBound."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("jo_bound", config)
        self.base_url = config.get("url", "https://jobound.io")
        self.max_pages = config.get("max_pages", 5)

    async def scrape(self) -> list[dict]:
        """Fetch jobs from JoBound."""
        all_jobs = []

        for page in range(1, self.max_pages + 1):
            url = f"{self.base_url}/jobs?page={page}"
            html = await self.fetch_text(url)

            if not html:
                logger.warning(f"Failed to fetch JoBound page {page}")
                continue

            jobs = self._parse_page(html)
            if not jobs:
                break

            all_jobs.extend(jobs)
            logger.info(f"JoBound page {page}: found {len(jobs)} jobs")

        return all_jobs

    def _parse_page(self, html: str) -> list[dict]:
        """Parse job listings from HTML."""
        jobs = []

        job_pattern = re.compile(
            r'<a[^>]*href="(/jobs/[^"]+)"[^>]*>.*?'
            r'<h[23][^>]*>(.*?)</h[23]>.*?'
            r'(?:<span[^>]*class="[^"]*company[^"]*"[^>]*>(.*?)</span>)?',
            re.DOTALL | re.IGNORECASE,
        )

        for match in job_pattern.finditer(html):
            try:
                url_path = match.group(1)
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                company = re.sub(r"<[^>]+>", "", match.group(3)).strip() if match.group(3) else "Unknown"

                full_url = f"{self.base_url}{url_path}" if url_path.startswith("/") else url_path

                job = {
                    "title": title,
                    "company": company,
                    "url": full_url,
                    "location": "Remote",
                    "remote": True,
                    "salary_min": None,
                    "salary_max": None,
                    "tech_stack": self.detect_tech_stack(title),
                    "job_type": "full_time",
                    "description": "",
                }
                jobs.append(self.prepare_job(job))
            except Exception as e:
                logger.error(f"Failed to parse JoBound job: {e}")
                continue

        return jobs

    def _extract_description(self, html: str, start: int) -> str:
        """Extract job description text."""
        desc_pattern = re.compile(r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>', re.DOTALL)
        match = desc_pattern.search(html, start)
        if match:
            text = re.sub(r"<[^>]+>", " ", match.group(1))
            return text.strip()[:2000]
        return ""
