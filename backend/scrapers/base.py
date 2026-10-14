from __future__ import annotations

import abc
import asyncio
import hashlib
import re
from typing import Any

import httpx


class JobSource(abc.ABC):
    """Abstract base class for all job source scrapers."""

    name: str = ""
    tier: int = 3
    country_focus: str = "GLOBAL"
    enabled: bool = True

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
        )

    async def fetch(self, url: str, params: dict[str, Any] | None = None) -> dict | list | None:
        """Fetch JSON data from a URL."""
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
            print(f"[{self.name}] fetch error for {url}: {exc}")
            return None

    async def fetch_text(self, url: str) -> str | None:
        """Fetch raw text/HTML from a URL."""
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
            print(f"[{self.name}] fetch_text error for {url}: {exc}")
            return None

    @abc.abstractmethod
    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Return a list of raw job dicts from the source."""
        ...

    @abc.abstractmethod
    async def fetch_job_details(self, url: str) -> dict[str, Any] | None:
        """Return enriched details for a single job."""
        ...

    @staticmethod
    def generate_fingerprint(company: str, title: str, location: str) -> str:
        """Create a deterministic fingerprint for deduplication."""
        raw = f"{company.strip().lower()}|{title.strip().lower()}|{location.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def parse_salary(text: str) -> tuple[str | None, int | None, int | None]:
        """Parse salary string into (currency, min, max)."""
        if not text:
            return (None, None, None)

        currency_map = {
            "$": "USD",
            "€": "EUR",
            "£": "GBP",
            "KSh": "KES",
            "KES": "KES",
            "UGX": "UGX",
            "TZS": "TZS",
        }

        currency: str | None = None
        for symbol, code in currency_map.items():
            if symbol.lower() in text.lower():
                currency = code
                break

        numbers = re.findall(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
        clean_numbers = [int(float(n.replace(",", ""))) for n in numbers]

        if len(clean_numbers) >= 2:
            lo, hi = min(clean_numbers), max(clean_numbers)
        elif len(clean_numbers) == 1:
            lo = hi = clean_numbers[0]
        else:
            return (currency, None, None)

        if any(k in text.lower() for k in ("k /month", "k/month", "k pm", "k p.m")):
            lo *= 1000
            hi *= 1000

        return (currency, lo, hi)

    @staticmethod
    def detect_skills(text: str) -> list[str]:
        """Detect technical skills mentioned in free text.

        Delegates to the shared deterministic extractor so every caller uses
        the same vocabulary and boundary rules (e.g. ``C++``/``C#`` and the
        ``go``-as-a-word guard).  Returns canonical skill ids.
        """
        from backend.skills import extract_matches

        found = {m.canonical for m in extract_matches(text or "")}
        return sorted(found)

    def filter_job(self, job: dict[str, Any]) -> bool:
        """Return True if the job passes configured include/exclude filters."""
        filters = self.config.get("filters", {})

        exclude_titles = [t.lower() for t in filters.get("exclude_titles", [])]
        if exclude_titles:
            title = (job.get("title") or "").lower()
            if any(excl in title for excl in exclude_titles):
                return False

        include_skills = [s.lower() for s in filters.get("include_skills", [])]
        if include_skills:
            job_skills = [s.lower() for s in job.get("skills", [])]
            if not any(s in job_skills for s in include_skills):
                return False

        exclude_locations = [l.lower() for l in filters.get("exclude_locations", [])]
        if exclude_locations:
            loc = (job.get("location") or "").lower()
            if any(excl in loc for excl in exclude_locations):
                return False

        return True

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
