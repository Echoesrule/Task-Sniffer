from __future__ import annotations

import asyncio
import re
from typing import Any

from bs4 import BeautifulSoup

from .base import JobSource


class MyJobsKenyaScraper(JobSource):
    """Scraper for MyJobsKenya job listings."""

    name = "myjobskenya"
    tier = 1
    country_focus = "KE"

    BASE_URL = "https://www.myjobskenya.com"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._rate_limit: float = self.config.get("rate_limit", 2.0)

    def _parse_listing_page(self, html: str) -> tuple[list[dict[str, Any]], int]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[dict[str, Any]] = []

        cards = soup.select(
            "div.job-listing, div.job-card, tr.job-row, "
            "div.listing-item, div.job-list-item, article.job"
        )
        if not cards:
            cards = soup.select("a[href*='/job/'], a[href*='/jobs/']")

        for card in cards:
            title_el = card.select_one(
                "h2 a, h3 a, .job-title a, a.job-link, "
                "td.title a, .listing-title a"
            )
            company_el = card.select_one(
                ".company, .employer, td.company, span.company-name"
            )
            location_el = card.select_one(
                ".location, td.location, span.job-location"
            )
            date_el = card.select_one(
                ".date, .posted-date, time, span.date"
            )

            if card.name == "a":
                title_text = card.get_text(strip=True)
                href = card.get("href", "")
            elif title_el:
                title_text = title_el.get_text(strip=True)
                href = title_el.get("href", "")
            else:
                continue

            if not title_text:
                continue

            company = company_el.get_text(strip=True) if company_el else ""
            location = location_el.get_text(strip=True) if location_el else "Nairobi"
            posted = date_el.get_text(strip=True) if date_el else ""
            posted_at = date_el.get("datetime", "") if date_el else posted

            if href and not href.startswith("http"):
                href = f"{self.BASE_URL}{href}"

            jobs.append({
                "title": title_text,
                "company": company,
                "location": location,
                "url": href,
                "posted_at": posted_at,
                "source": self.name,
            })

        total_pages = 1
        pagination = soup.select(
            "ul.pagination a, div.pagination a, a.next, a.page-link"
        )
        for link in pagination:
            text = link.get_text(strip=True)
            if text.isdigit():
                total_pages = max(total_pages, int(text))

        return jobs, total_pages

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []

        first_html = await self.fetch_text(self.BASE_URL)
        if not first_html:
            return []

        jobs, total_pages = self._parse_listing_page(first_html)
        all_jobs.extend(jobs)

        max_pages = self.config.get("max_pages", 5)
        total_pages = min(total_pages, max_pages)

        for page in range(2, total_pages + 1):
            await asyncio.sleep(self._rate_limit)
            page_url = f"{self.BASE_URL}/jobs?page={page}"
            page_html = await self.fetch_text(page_url)
            if not page_html:
                break
            jobs, _ = self._parse_listing_page(page_html)
            if not jobs:
                break
            all_jobs.extend(jobs)

        filtered = [j for j in all_jobs if self.filter_job(j)]
        return filtered

    async def fetch_job_details(self, url: str) -> dict[str, Any] | None:
        html = await self.fetch_text(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.select_one(
            "h1.job-title, h1, .job-header h1, div.detail-header h1"
        )
        desc_el = soup.select_one(
            ".job-description, .description, div.job-detail-content, "
            "div.detail-body, article.job-content"
        )
        req_el = soup.select_one(
            ".requirements, ul.req-list, div.requirements"
        )
        salary_el = soup.select_one(".salary, span.salary, div.salary-range")
        employment_el = soup.select_one(
            ".job-type, .employment-type, span.job-type"
        )

        title = title_el.get_text(strip=True) if title_el else ""
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else ""
        requirements_text = req_el.get_text(separator="\n", strip=True) if req_el else ""
        salary_text = salary_el.get_text(strip=True) if salary_el else ""
        employment_type = employment_el.get_text(strip=True) if employment_el else ""

        skills = self.detect_skills(f"{description} {requirements_text}")
        salary_currency, salary_min, salary_max = self.parse_salary(salary_text)

        return {
            "title": title,
            "description": description,
            "requirements": requirements_text,
            "salary_text": salary_text,
            "salary_currency": salary_currency,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "employment_type": employment_type,
            "skills": skills,
            "url": url,
        }
