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

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = 1
        max_pages = self.config.get("max_pages", 10)
        tags = self.config.get("tags", "")
        industry = self.config.get("industry", "")

        while page <= max_pages:
            params: dict[str, Any] = {"count": 50}
            if tags:
                params["tag"] = tags
            if industry:
                params["industry"] = industry

            data = await self.fetch(self.API_URL, params=params)
            if data is None:
                break

            job_list = data.get("jobs", [])
            if not job_list:
                break

            for item in job_list:
                salary_min = item.get("annualSalaryMin")
                salary_max = item.get("annualSalaryMax")
                salary_currency = item.get("salaryCurrency", "USD")

                company_name = ""
                if isinstance(item.get("companyName"), str):
                    company_name = item["companyName"]

                location = item.get("jobGeo", "")
                if isinstance(location, list):
                    location = ", ".join(location)

                skills_raw = item.get("jobIndustry", [])
                if isinstance(skills_raw, str):
                    skills_raw = [s.strip() for s in skills_raw.split(",")]

                jobs.append({
                    "title": item.get("jobTitle", ""),
                    "company": company_name,
                    "location": location or "Remote",
                    "url": item.get("url", ""),
                    "description": item.get("jobDescription", ""),
                    "salary_currency": salary_currency,
                    "salary_min": int(salary_min) if salary_min else None,
                    "salary_max": int(salary_max) if salary_max else None,
                    "employment_type": item.get("jobType", ""),
                    "posted_at": item.get("pubDate", ""),
                    "skills": skills_raw,
                    "remote": True,
                    "source": self.name,
                })

            page += 1

        filtered = [j for j in jobs if self.filter_job(j)]
        return filtered

    async def fetch_job_details(self, url: str) -> dict[str, Any] | None:
        data = await self.fetch(url)
        if data is None:
            return None

        job = data if isinstance(data, dict) else None
        if job is None:
            return None

        desc = job.get("jobDescription", "")
        skills = self.detect_skills(desc)

        salary_min = job.get("annualSalaryMin")
        salary_max = job.get("annualSalaryMax")

        return {
            "title": job.get("jobTitle", ""),
            "company": job.get("companyName", ""),
            "location": job.get("jobGeo", "Remote"),
            "description": desc,
            "salary_currency": job.get("salaryCurrency", "USD"),
            "salary_min": int(salary_min) if salary_min else None,
            "salary_max": int(salary_max) if salary_max else None,
            "employment_type": job.get("jobType", ""),
            "skills": skills,
            "remote": True,
            "url": url,
        }
