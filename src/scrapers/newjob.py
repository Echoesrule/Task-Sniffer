"""NewJob scraper - Startup jobs with no ghost jobs."""

import logging
import re
from typing import Any

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class NewJobScraper(BaseScraper):
    """Scrape startup jobs from NewJob."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("newjob", config)
        self.base_url = config.get("url", "https://newjob.tech")
        self.max_pages = config.get("max_pages", 3)

    async def scrape(self) -> list[dict]:
        """Fetch jobs from NewJob."""
        all_jobs = []

        for page in range(1, self.max_pages + 1):
            url = f"{self.base_url}/search?page={page}"
            html = await self.fetch_text(url)

            if not html:
                logger.warning(f"Failed to fetch NewJob page {page}")
                continue

            jobs = self._parse_page(html)
            if not jobs:
                break

            all_jobs.extend(jobs)
            logger.info(f"NewJob page {page}: found {len(jobs)} jobs")

        return all_jobs

    def _parse_page(self, html: str) -> list[dict]:
        """Parse job listings from HTML."""
        jobs = []

        job_pattern = re.compile(
            r'<a[^>]*href="(/job/[^"]+)"[^>]*>.*?'
            r'<h[23][^>]*>(.*?)</h[23]>.*?'
            r'(?:<span[^>]*>(.*?)</span>)?',
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
                logger.error(f"Failed to parse NewJob job: {e}")
                continue

        return jobs
