"""Greenhouse ATS scraper - Public job board API."""

import logging
import re
from typing import Any

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class GreenhouseScraper(BaseScraper):
    """Scrape jobs from Greenhouse ATS public boards."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("greenhouse", config)
        self.boards = config.get("boards", [])
        self.base_url = "https://boards-api.greenhouse.io/v1/boards"

    async def scrape(self) -> list[dict]:
        """Fetch jobs from all configured Greenhouse boards."""
        all_jobs = []

        for board in self.boards:
            url = f"{self.base_url}/{board}/jobs"
            data = await self.fetch(url)

            if not data or "jobs" not in data:
                logger.warning(f"No jobs from Greenhouse board: {board}")
                continue

            for item in data["jobs"]:
                job = self._parse_job(item, board)
                if job:
                    all_jobs.append(self.prepare_job(job))

            logger.info(f"Greenhouse {board}: found {len(data['jobs'])} jobs")

        return all_jobs

    def _parse_job(self, item: dict, board: str) -> dict | None:
        """Parse a Greenhouse job listing."""
        try:
            location = item.get("location", {}).get("name", "")
            is_remote = "remote" in location.lower() or "anywhere" in location.lower()

            absolute_url = item.get("absolute_url", "")
            if not absolute_url:
                return None

            description = item.get("content", "")
            if description:
                description = re.sub(r"<[^>]+>", " ", description)
                description = re.sub(r"\s+", " ", description).strip()

            return {
                "title": item.get("title", ""),
                "company": board.title(),
                "url": absolute_url,
                "location": location,
                "remote": is_remote,
                "salary_min": None,
                "salary_max": None,
                "tech_stack": self.detect_tech_stack(
                    f"{item.get('title', '')} {description}"
                ),
                "job_type": "full_time",
                "description": description[:2000],
            }
        except Exception as e:
            logger.error(f"Failed to parse Greenhouse job: {e}")
            return None
