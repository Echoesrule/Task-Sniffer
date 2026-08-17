from __future__ import annotations

from typing import Any

from .base import JobSource


class GreenhouseScraper(JobSource):
    """Scraper for Greenhouse ATS job boards."""

    name = "greenhouse"
    tier = 2
    country_focus = "GLOBAL"

    BOARDS_BASE = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._boards: list[str] = self.config.get("boards", [])

    async def _fetch_board(self, board: str) -> list[dict[str, Any]]:
        url = f"{self.BOARDS_BASE}/{board}/jobs"
        data = await self.fetch(url)
        if data is None:
            return []

        raw_jobs = data.get("jobs", [])
        result: list[dict[str, Any]] = []

        for item in raw_jobs:
            locations = item.get("location", {})
            location_name = ""
            if isinstance(locations, dict):
                location_name = locations.get("name", "")
            elif isinstance(locations, str):
                location_name = locations

            departments = item.get("departments", [])
            dept_names = [
                d.get("name", "") for d in departments if isinstance(d, dict)
            ]

            result.append({
                "title": item.get("title", ""),
                "company": board,
                "location": location_name,
                "url": item.get("absolute_url", f"https://boards.greenhouse.io/{board}/jobs/{item.get('id', '')}"),
                "department": ", ".join(dept_names),
                "posted_at": item.get("updated_at", ""),
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
        description = data.get("description", "")
        location = ""
        loc = data.get("location", {})
        if isinstance(loc, dict):
            location = loc.get("name", "")

        skills = self.detect_skills(description)

        return {
            "title": title,
            "description": description,
            "location": location,
            "skills": skills,
            "url": url,
        }
