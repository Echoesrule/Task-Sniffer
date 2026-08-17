from __future__ import annotations

from typing import Any

from .base import JobSource


class AshbyScraper(JobSource):
    """Scraper for Ashby ATS job boards."""

    name = "ashby"
    tier = 2
    country_focus = "GLOBAL"

    API_BASE = "https://api.ashbyhq.com/posting-api/job-board"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._boards: list[str] = self.config.get("boards", [])

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

            result.append({
                "title": item.get("title", ""),
                "company": board,
                "location": location,
                "url": item.get("url", f"https://jobs.ashbyhq.com/{board}/{item.get('id', '')}"),
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
