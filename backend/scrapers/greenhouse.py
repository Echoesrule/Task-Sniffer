from __future__ import annotations

import logging
import re
from typing import Any

from .base import JobSource

logger = logging.getLogger(__name__)

#: hosted Greenhouse job board (individual postings live under /<board>/jobs/<id>)
JOB_BOARDS_BASE = "https://job-boards.greenhouse.io"

#: a path that denotes an *individual* posting, e.g. /acme/jobs/123 or /jobs/123
_DETAIL_PATH_RE = re.compile(r"(?:^|/)(?:[^/]+/)?jobs/\d+/?$")


def is_greenhouse_detail_url(url: str) -> bool:
    """True only for individual Greenhouse postings, never search/company pages.

    Guards against ``absolute_url`` pointing at a company search page, which is
    the documented defect behind the historical ``careers.airbnb.com`` rows.
    """
    if not url:
        return False
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host and not (host == "greenhouse.io" or host.endswith(".greenhouse.io")):
        return False
    return bool(_DETAIL_PATH_RE.search(parsed.path or ""))


class GreenhouseScraper(JobSource):
    """Scraper for Greenhouse ATS job boards."""

    name = "greenhouse"
    tier = 2
    country_focus = "GLOBAL"

    BOARDS_BASE = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._boards: list[str] = self.config.get("boards", [])
        #: per-board outcome of the last ``fetch_jobs`` call, so "zero jobs" is
        #: diagnosable (which board was tried, whether it responded, how many
        #: postings it returned).
        self.board_stats: list[dict[str, Any]] = []

    def _detail_url(self, board: str, job_id: str) -> str:
        return f"{JOB_BOARDS_BASE}/{board}/jobs/{job_id}"

    async def _fetch_board(self, board: str) -> list[dict[str, Any]] | None:
        """Fetch one board. Returns None when the API gave no usable response
        (invalid board identifier / API error) as distinct from a valid 200 with
        zero postings (returns ``[]``)."""
        url = f"{self.BOARDS_BASE}/{board}/jobs"
        data = await self.fetch(url)
        if data is None:
            return None

        raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []
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

            job_id = str(item.get("id", "") or "").strip()
            absolute_url = item.get("absolute_url", "") or ""
            # Prefer the canonical hosted posting derived from board+id. Only
            # fall back to the provider-supplied URL when it is verifiably an
            # individual posting; otherwise emit no URL (fail-closed) rather
            # than persisting a search/company-careers link.
            if job_id:
                detail_url = self._detail_url(board, job_id)
            elif is_greenhouse_detail_url(absolute_url):
                detail_url = absolute_url
            else:
                detail_url = ""
                logger.warning(
                    "[greenhouse] %s: no job id and unusable absolute_url %r; "
                    "withholding URL", board, absolute_url,
                )

            result.append({
                "title": item.get("title", ""),
                "company": board,
                "location": location_name,
                "url": detail_url,
                "source_job_id": job_id or None,
                "department": ", ".join(dept_names),
                "posted_at": item.get("updated_at", ""),
                "source": self.name,
            })

        return result

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []
        self.board_stats = []

        boards = self._boards or self.config.get("boards", [])
        if not boards:
            logger.warning(
                "[greenhouse] no boards configured; set verified board slugs to "
                "fetch postings (see ATS_BOARD_CONFIG)"
            )
            return []

        for board in boards:
            try:
                board_jobs = await self._fetch_board(board)
            except Exception as exc:  # noqa: BLE001 - one board never blocks the rest
                logger.warning("[greenhouse] board %s failed: %s", board, exc)
                self.board_stats.append(
                    {"board": board, "ok": False, "jobs": 0, "error": str(exc)}
                )
                continue
            if board_jobs is None:
                logger.warning(
                    "[greenhouse] board %s: no API response (invalid board id or "
                    "API error)", board,
                )
                self.board_stats.append(
                    {"board": board, "ok": False, "jobs": 0, "error": "no response"}
                )
                continue
            self.board_stats.append({"board": board, "ok": True, "jobs": len(board_jobs)})
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
