"""Jobicy API scraper - Free remote jobs API."""

import logging
from typing import Any

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class JobicyScraper(BaseScraper):
    """Scrape remote jobs from Jobicy's free API."""

    def __init__(self, config: dict[str, Any]):
        super().__init__("jobicy", config)
        self.api_url = config.get("api_url", "https://jobicy.com/api/v2/remote-jobs")
        self.default_params = config.get("params", {})

    async def scrape(self) -> list[dict]:
        """Fetch jobs from Jobicy API."""
        params = {
            "count": self.default_params.get("count", 50),
            "tag": self.default_params.get("tag", "remote"),
        }

        data = await self.fetch(self.api_url, params=params)
        if not data or "jobs" not in data:
            logger.warning("No jobs returned from Jobicy")
            return []

        jobs = []
        for item in data["jobs"]:
            salary_min, salary_max = self.parse_salary(
                f"${item.get('annualSalaryMin', 0)} - ${item.get('annualSalaryMax', 0)}"
            )

            job = {
                "title": item.get("jobTitle", ""),
                "company": item.get("companyName", "Unknown"),
                "url": item.get("url", ""),
                "location": item.get("jobGeo", ""),
                "remote": True,
                "salary_min": salary_min or item.get("annualSalaryMin"),
                "salary_max": salary_max or item.get("annualSalaryMax"),
                "tech_stack": self.detect_tech_stack(
                    f"{item.get('jobTitle', '')} {item.get('jobDescription', '')}"
                ),
                "job_type": self._map_job_type(item.get("jobType", "")),
                "description": item.get("jobDescription", "")[:2000],
            }
            jobs.append(self.prepare_job(job))

        return jobs

    def _map_job_type(self, job_type) -> str:
        """Map Jobicy job type to standard format."""
        if isinstance(job_type, list):
            job_type = job_type[0] if job_type else ""
        type_map = {
            "full time": "full_time",
            "full-time": "full_time",
            "part time": "part_time",
            "contract": "contract",
            "freelance": "freelance",
            "internship": "internship",
        }
        return type_map.get(str(job_type).lower(), "full_time")
