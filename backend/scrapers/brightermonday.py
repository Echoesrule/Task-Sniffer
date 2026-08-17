from __future__ import annotations

import asyncio
import re
from typing import Any

from bs4 import BeautifulSoup

from .base import JobSource


class BrighterMondayScraper(JobSource):
    """Scraper for BrighterMonday Kenya job listings."""

    name = "brightermonday"
    tier = 1
    country_focus = "KE"

    BASE_URL = "https://www.brightermonday.com/kenya/jobs"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._rate_limit: float = self.config.get("rate_limit", 2.0)

    async def _get_page(self, page: int = 1) -> str | None:
        params: dict[str, Any] = {}
        if page > 1:
            params["page"] = page
        url = self.BASE_URL
        return await self.fetch_text(url) if not params else await self.fetch_text(f"{url}?page={page}")

    def _parse_listing_page(self, html: str) -> tuple[list[dict[str, Any]], int]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[dict[str, Any]] = []

        cards = soup.select("div.job-listing, div.job-card, article.job-item, div[data-job-id]")
        if not cards:
            cards = soup.select("a[href*='/jobs/']")

        for card in cards:
            title_el = card.select_one("h2, h3, .job-title, .title a, a.job-link")
            company_el = card.select_one(".company-name, .employer, span.company")
            location_el = card.select_one(".location, .job-location, span.location")
            salary_el = card.select_one(".salary, .salary-range, span.salary")
            link_el = card.select_one("a[href]") if card.name != "a" else card

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            location = location_el.get_text(strip=True) if location_el else "Nairobi"
            salary_text = salary_el.get_text(strip=True) if salary_el else ""
            href = link_el.get("href", "") if link_el else ""

            if not title:
                continue

            if href and not href.startswith("http"):
                href = f"https://www.brightermonday.com{href}"

            salary_currency, salary_min, salary_max = self.parse_salary(salary_text)

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "url": href,
                "salary_currency": salary_currency,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "source": self.name,
            })

        pagination = soup.select("ul.pagination li a, nav.pagination a, a.next-page")
        total_pages = 1
        for link in pagination:
            text = link.get_text(strip=True)
            if text.isdigit():
                total_pages = max(total_pages, int(text))

        return jobs, total_pages

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []

        first_page_html = await self._get_page(1)
        if not first_page_html:
            return []

        jobs, total_pages = self._parse_listing_page(first_page_html)
        all_jobs.extend(jobs)

        max_pages = self.config.get("max_pages", 5)
        total_pages = min(total_pages, max_pages)

        for page in range(2, total_pages + 1):
            await asyncio.sleep(self._rate_limit)
            page_html = await self._get_page(page)
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

        title_el = soup.select_one("h1.job-title, h1, .job-header h1")
        description_el = soup.select_one(".job-description, .description, div.job-detail-content, article")
        requirements_el = soup.select_one(".requirements, .job-requirements, ul.requirements")
        salary_el = soup.select_one(".salary, .job-salary, span.salary")

        title = title_el.get_text(strip=True) if title_el else ""
        description = description_el.get_text(separator="\n", strip=True) if description_el else ""
        requirements_text = requirements_el.get_text(separator="\n", strip=True) if requirements_el else ""
        salary_text = salary_el.get_text(strip=True) if salary_el else ""

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
            "skills": skills,
            "url": url,
        }
