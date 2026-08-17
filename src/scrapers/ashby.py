"""Ashby ATS scraper - Public job board API with compensation data."""

import logging
from typing import Any

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class AshbyScraper(BaseScraper):
    """Scrape jobs from Ashby ATS public boards."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("ashby", config)
        self.boards = config.get("boards", [])
        self.base_url = "https://api.ashbyhq.com/posting-api/job-board"

    async def scrape(self) -> list[dict]:
        """Fetch jobs from all configured Ashby boards."""
        all_jobs = []

        for board in self.boards:
            url = f"{self.base_url}/{board}"
            params = {"includeCompensation": "true"}
            data = await self.fetch(url, params=params)

            if not data or "jobs" not in data:
                logger.warning(f"No jobs from Ashby board: {board}")
                continue

            for item in data["jobs"]:
                if not item.get("isListed", True):
                    continue
                job = self._parse_job(item, board)
                if job:
                    all_jobs.append(self.prepare_job(job))

            logger.info(f"Ashby {board}: found {len(data['jobs'])} jobs")

        return all_jobs

    def _parse_job(self, item: dict, board: str) -> dict | None:
        """Parse an Ashby job listing with compensation data."""
        try:
            location = item.get("locationName", "")
            is_remote = (
                item.get("isRemote", False)
                or item.get("workplaceType", "").lower() == "remote"
                or "remote" in location.lower()
            )

            employment_type = item.get("employmentType", "FullTime")
            job_type_map = {
                "FullTime": "full_time",
                "PartTime": "part_time",
                "Contract": "contract",
                "Intern": "internship",
                "Temporary": "contract",
            }
            job_type = job_type_map.get(employment_type, "full_time")

            salary_min, salary_max = None, None
            compensation = item.get("compensation", {})
            for component in compensation.get("summaryComponents", []):
                if component.get("compensationType") == "Salary":
                    salary_min = component.get("minValue")
                    salary_max = component.get("maxValue")
                    break

            description = item.get("descriptionPlain", "") or item.get("descriptionHtml", "")
            job_url = item.get("jobUrl", "") or item.get("applyUrl", "")

            return {
                "title": item.get("title", ""),
                "company": board.title(),
                "url": job_url,
                "location": location,
                "remote": is_remote,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "tech_stack": self.detect_tech_stack(
                    f"{item.get('title', '')} {description}"
                ),
                "job_type": job_type,
                "description": description[:2000],
            }
        except Exception as e:
            logger.error(f"Failed to parse Ashby job: {e}")
            return None
