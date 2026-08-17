"""Base scraper class for job sources."""

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for all job scrapers."""

    def __init__(self, source_name: str, config: dict[str, Any]):
        self.source_name = source_name
        self.config = config
        self.enabled = config.get("enabled", True)
        self.interval_minutes = config.get("interval_minutes", 60)
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )

    def generate_job_id(self, url: str, title: str) -> str:
        """Generate a unique job ID from URL and title."""
        content = f"{url}:{title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def parse_salary(self, text: str) -> tuple[int | None, int | None]:
        """Parse salary range from text. Returns (min, max) or (None, None)."""
        import re

        patterns = [
            r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*[-–to]+\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
            r"\$(\d{1,3}(?:,\d{3})*)\s*[-–to]+\s*(\d{1,3}(?:,\d{3})*)\s*k",
            r"(\d{1,3}(?:,\d{3})*)\s*[-–to]+\s*(\d{1,3}(?:,\d{3})*)\s*(?:USD|EUR|GBP)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                min_sal = int(match.group(1).replace(",", "").split(".")[0])
                max_sal = int(match.group(2).replace(",", "").split(".")[0])
                if min_sal < 1000:
                    min_sal *= 1000
                    max_sal *= 1000
                return min_sal, max_sal

        return None, None

    def detect_tech_stack(self, text: str) -> list[str]:
        """Detect technology stack from job description."""
        tech_keywords = {
            "python", "javascript", "typescript", "react", "vue", "angular",
            "node", "express", "fastapi", "django", "flask", "spring",
            "java", "go", "rust", "ruby", "php", "c#", "c++",
            "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
            "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
            "graphql", "rest", "grpc", "kafka", "rabbitmq",
            "react native", "flutter", "swift", "kotlin",
            "nextjs", "nuxt", "svelte", "tailwind",
        }

        import re
        text_clean = re.sub(r'[,;:"\'\[\]{}]', ' ', text)
        text_lower = text_clean.lower()
        found = []
        for tech in tech_keywords:
            pattern = r"\b" + re.escape(tech) + r"\b"
            if re.search(pattern, text_lower):
                found.append(tech)
        return found[:10]

    def filter_job(self, job: dict) -> bool:
        """Check if job matches filters."""
        from src.config import config

        filters = config.filters

        if filters.get("remote_only") and not job.get("remote", False):
            return False

        min_salary = filters.get("min_salary", 0)
        if min_salary and job.get("salary_min"):
            if job["salary_min"] < min_salary:
                return False

        exclude = filters.get("exclude_keywords", [])
        title_lower = job.get("title", "").lower()
        for keyword in exclude:
            if keyword.lower() in title_lower:
                return False

        return True

    async def fetch(self, url: str, params: dict | None = None) -> dict | list | None:
        """Make an HTTP GET request."""
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for {url}")
            return None
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            return None

    async def fetch_text(self, url: str) -> str | None:
        """Make an HTTP GET request and return text."""
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            return None

    @abstractmethod
    async def scrape(self) -> list[dict]:
        """Scrape jobs from the source. Must be implemented by subclasses."""
        pass

    async def run(self) -> list[dict]:
        """Run the scraper and return filtered jobs."""
        if not self.enabled:
            logger.info(f"{self.source_name} is disabled, skipping")
            return []

        logger.info(f"Starting scraper for {self.source_name}")
        try:
            jobs = await self.scrape()
            filtered = [j for j in jobs if self.filter_job(j)]
            logger.info(f"{self.source_name}: found {len(jobs)} jobs, {len(filtered)} after filtering")
            return filtered
        except Exception as e:
            logger.error(f"Scraper {self.source_name} failed: {e}")
            return []
        finally:
            await self.client.aclose()

    def prepare_job(self, data: dict) -> dict:
        """Standardize job data format."""
        url = data.get("url", "")
        title = data.get("title", "")

        return {
            "id": self.generate_job_id(url, title),
            "source": self.source_name,
            "title": title,
            "company": data.get("company", "Unknown"),
            "url": url,
            "location": data.get("location", ""),
            "remote": data.get("remote", True),
            "salary_min": data.get("salary_min"),
            "salary_max": data.get("salary_max"),
            "tech_stack": json.dumps(data.get("tech_stack", [])),
            "job_type": data.get("job_type", "full_time"),
            "description": data.get("description", "")[:2000],
            "scraped_at": datetime.utcnow(),
            "notified": False,
        }
