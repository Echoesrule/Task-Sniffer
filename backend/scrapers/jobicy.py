from __future__ import annotations

from typing import Any

from .base import JobSource


class JobicyScraper(JobSource):
    """Scraper for the Jobicy remote jobs REST API."""

    name = "jobicy"
    tier = 2
    country_focus = "GLOBAL"

    API_URL = "https://jobicy.com/api/v2/remote-jobs"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)

    @staticmethod
    def _as_text(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value if item)
        return str(value) if value is not None else ""

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        max_pages = int(self.config.get("max_pages", 10) or 0)
        count = min(int(self.config.get("count", 50) or 50), 50)
        tags = self.config.get("tags", "")
        industry = self.config.get("industry", "")

        # The v2 API paginates with an opaque ``cursor``; a ``page`` parameter
        # is rejected outright. Follow ``nextCursor`` until ``hasMore`` is false.
        cursor: str | None = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"count": count}
            if tags:
                params["tag"] = tags
            if industry:
                params["industry"] = industry
            if cursor:
                params["cursor"] = cursor

            data = await self.fetch(self.API_URL, params=params)
            if not isinstance(data, dict):
                break

            job_list = data.get("jobs") or []
            if not job_list:
                break

            for item in job_list:
                salary_min = item.get("annualSalaryMin")
                salary_max = item.get("annualSalaryMax")
                has_salary = bool(salary_min) or bool(salary_max)

                company_name = ""
                if isinstance(item.get("companyName"), str):
                    company_name = item["companyName"]

                # ``jobIndustry`` is a category (e.g. "Sales"), not a skill
                # list. Using it as skills inflated matches; skills are derived
                # deterministically from the description instead.
                jobs.append({
                    "title": item.get("jobTitle", ""),
                    "company": company_name,
                    "location": self._as_text(item.get("jobGeo", "")),
                    "url": item.get("url", ""),
                    "source_job_id": str(item.get("id")) if item.get("id") is not None else None,
                    "description": item.get("jobDescription", ""),
                    # A currency without an amount is not useful data.
                    "salary_currency": item.get("salaryCurrency") if has_salary else None,
                    "salary_min": int(salary_min) if salary_min else None,
                    "salary_max": int(salary_max) if salary_max else None,
                    "salary_period": "year" if has_salary else "",
                    "employment_type": self._as_text(item.get("jobType", "")),
                    "posted_at": item.get("pubDate", ""),
                    "skills": [],
                    "remote": True,
                    "remote_type": "remote",
                    "source": self.name,
                })

            cursor = data.get("nextCursor")
            if not data.get("hasMore") or not cursor:
                break

        filtered = [j for j in jobs if self.filter_job(j)]
        return filtered

    async def fetch_job_details(self, url: str) -> dict[str, Any] | None:
        """Read a Jobicy detail page.

        Detail URLs serve HTML, not JSON. Parse the page's schema.org
        ``JobPosting`` block; return ``None`` when the page cannot be fetched.
        """
        from .jsonld import extract_jobposting

        html = await self.fetch_text(url)
        if not html:
            return None
        details = extract_jobposting(html)
        if not details:
            return None
        details["url"] = url
        return details
