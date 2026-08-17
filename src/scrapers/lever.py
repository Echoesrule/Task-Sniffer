"""Lever ATS scraper - Public job board API."""

import logging
from typing import Any

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class LeverScraper(BaseScraper):
    """Scrape jobs from Lever ATS public boards."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("lever", config)
        self.boards = config.get("boards", [])
        self.base_url = "https://api.lever.co/v0/postings"

    async def scrape(self) -> list[dict]:
        """Fetch jobs from all configured Lever boards."""
        all_jobs = []

        for board in self.boards:
            url = f"{self.base_url}/{board}"
            params = {"mode": "json"}
            data = await self.fetch(url, params=params)

            if not data or not isinstance(data, list):
                logger.warning(f"No jobs from Lever board: {board}")
                continue

            for item in data:
                job = self._parse_job(item, board)
                if job:
                    all_jobs.append(self.prepare_job(job))

            logger.info(f"Lever {board}: found {len(data)} jobs")

        return all_jobs

    def _parse_job(self, item: dict, board: str) -> dict | None:
        """Parse a Lever job listing."""
        try:
            categories = item.get("categories", {})
            location = categories.get("team", "") or item.get("categories", {}).get("location", "")
            is_remote = "remote" in location.lower() or item.get("remote", False)

            commitment = categories.get("commitment", "")
            job_type_map = {
                "full-time": "full_time",
                "part-time": "part_time",
                "contract": "contract",
                "internship": "internship",
            }
            job_type = job_type_map.get(commitment.lower(), "full_time")

            description_plain = item.get("descriptionPlain", "")
            description_html = item.get("description", "")

            return {
                "title": item.get("text", ""),
                "company": board.title(),
                "url": item.get("hostedUrl", ""),
                "location": location,
                "remote": is_remote,
                "salary_min": None,
                "salary_max": None,
                "tech_stack": self.detect_tech_stack(
                    f"{item.get('text', '')} {description_plain}"
                ),
                "job_type": job_type,
                "description": (description_plain or description_html)[:2000],
            }
        except Exception as e:
            logger.error(f"Failed to parse Lever job: {e}")
            return None
