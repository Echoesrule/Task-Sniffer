from __future__ import annotations

import logging
import re
from typing import Any

from .base import JobSource

logger = logging.getLogger(__name__)

JOB_BOARD_BASE = "https://jobs.ashbyhq.com"

#: /<board>/<posting-id> where the posting id is a UUID-ish opaque id
_DETAIL_PATH_RE = re.compile(r"^/[^/]+/[0-9a-fA-F-]{8,}/?$")


def is_ashby_detail_url(url: str) -> bool:
    """True only for individual Ashby postings (host + /<board>/<id> shape)."""
    if not url:
        return False
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host and not (host == "ashbyhq.com" or host.endswith(".ashbyhq.com")):
        return False
    return bool(_DETAIL_PATH_RE.match(parsed.path or ""))


class AshbyScraper(JobSource):
    """Scraper for Ashby ATS job boards."""

    name = "ashby"
    tier = 2
    country_focus = "GLOBAL"

    API_BASE = "https://api.ashbyhq.com/posting-api/job-board"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._boards: list[str] = self.config.get("boards", [])

    def _detail_url(self, board: str, job_id: str) -> str:
        return f"{JOB_BOARD_BASE}/{board}/{job_id}"

    async def _fetch_board(self, board: str) -> list[dict[str, Any]]:
        url = f"{self.API_BASE}/{board}"
        data = await self.fetch(url)
        if data is None:
            return []

        job_listings = data.get("jobs", data.get("jobPostings", []))
        result: list[dict[str, Any]] = []

        for item in job_listings:
            location = ""
            loc_obj = item.get("locationName") or item.get("location")
            if isinstance(loc_obj, str):
                location = loc_obj

            employment_type = ""
            emp_el = item.get("employmentType") or item.get("employment_level", "")
            if isinstance(emp_el, str):
                employment_type = emp_el

            team = ""
            team_el = item.get("teamName") or item.get("departmentName", "")
            if isinstance(team_el, str):
                team = team_el

            posted = item.get("publishedAt") or item.get("updatedAt", "")

            job_id = str(item.get("id", "") or "").strip()
            provided_url = item.get("jobUrl") or item.get("url") or ""
            if job_id:
                detail_url = self._detail_url(board, job_id)
            elif is_ashby_detail_url(provided_url):
                detail_url = provided_url
            else:
                detail_url = ""
                logger.warning(
                    "[ashby] %s: no job id and unusable URL %r; withholding URL",
                    board, provided_url,
                )

            result.append({
                "title": item.get("title", ""),
                "company": board,
                "location": location,
                "url": detail_url,
                "source_job_id": job_id or None,
                "department": team,
                "employment_type": employment_type,
                "posted_at": posted,
                "source": self.name,
            })

        return result

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []

        boards = self._boards or self.config.get("boards", [])
        for board in boards:
            board_jobs = await self._fetch_board(board)
            all_jobs.extend(board_jobs)

        filtered = [j for j in all_jobs if self.filter_job(j)]
        return filtered

    async def fetch_job_details(self, url: str) -> dict[str, Any] | None:
        data = await self.fetch(url)
        if data is None:
            return None

        title = data.get("title", "")
        description = data.get("descriptionHtml", "") or data.get("description", "")
        location = data.get("locationName", "") or data.get("location", "")
        employment_type = data.get("employmentType", "")

        skills = self.detect_skills(description)

        return {
            "title": title,
            "description": description,
            "location": str(location),
            "employment_type": str(employment_type),
            "skills": skills,
            "url": url,
        }
