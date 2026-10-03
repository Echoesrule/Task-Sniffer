"""Adapter factory: SourceConfig -> JobSourceAdapter.

New adapters (backend.scrapers.adapters) implement the spec §5 contract
directly. The legacy scrapers (greenhouse/ashby/jobicy/myjobskenya) are wrapped
so they stay crawlable under the same engine without being rewritten.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.scrapers.adapter import JobSourceAdapter, ListingItem
from backend.sources.models import SourceConfig

logger = logging.getLogger(__name__)

_LEGACY_SCRAPERS: dict[str, str] = {
    "greenhouse": "GreenhouseScraper",
    "ashby": "AshbyScraper",
    "jobicy": "JobicyScraper",
    "myjobskenya": "MyJobsKenyaScraper",
}


def build_adapter(config: SourceConfig) -> JobSourceAdapter:
    """Return the adapter for a source config, raising for unsupported sources."""
    from backend.scrapers.adapters import ADAPTER_CLASSES

    if config.name in ADAPTER_CLASSES:
        return ADAPTER_CLASSES[config.name](config)

    if config.name in _LEGACY_SCRAPERS:
        return _LegacyAdapter(config, _LEGACY_SCRAPERS[config.name])

    raise KeyError(f"no adapter registered for source '{config.name}'")


class _LegacyAdapter(JobSourceAdapter):
    """Wrap a legacy :class:`backend.scrapers.base.JobSource` in the new contract."""

    job_url_patterns: list[str] = []
    allowed_domains: list[str] = []

    def __init__(self, config: SourceConfig, legacy_class: str) -> None:
        super().__init__(config)
        self._legacy_class = legacy_class
        self._legacy: Any = self._make_legacy()

    def _make_legacy(self) -> Any:
        from backend.scrapers.greenhouse import GreenhouseScraper
        from backend.scrapers.ashby import AshbyScraper
        from backend.scrapers.jobicy import JobicyScraper
        from backend.scrapers.myjobs import MyJobsKenyaScraper

        classes = {
            "GreenhouseScraper": GreenhouseScraper,
            "AshbyScraper": AshbyScraper,
            "JobicyScraper": JobicyScraper,
            "MyJobsKenyaScraper": MyJobsKenyaScraper,
        }
        kwargs: dict[str, Any] = {}
        if self._legacy_class in ("GreenhouseScraper", "AshbyScraper"):
            boards = [b for b in (self.config.extra_urls or []) if b]
            if boards:
                kwargs["boards"] = boards
        return classes[self._legacy_class](kwargs)

    async def fetch_listings(self, *, limit: int | None = None, limiter=None) -> list[ListingItem]:
        try:
            raw_jobs = await self._legacy.fetch_jobs() or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] legacy fetch_jobs failed: %s", self.name, exc)
            return []
        items: list[ListingItem] = []
        for job in raw_jobs:
            items.append(
                ListingItem(
                    title=job.get("title", ""),
                    company=job.get("company", ""),
                    location=job.get("location", ""),
                    remote=bool(job.get("remote", False)),
                    description=job.get("description", ""),
                    posted_at=job.get("posted_at", ""),
                    salary_text=job.get("salary_text", ""),
                    currency=job.get("salary_currency"),
                    salary_min=job.get("salary_min"),
                    salary_max=job.get("salary_max"),
                    source_job_id=job.get("source_job_id"),
                    url_candidates=([job["url"]] if job.get("url") else []),
                    raw_url=job.get("url", ""),
                    source_url=job.get("url", ""),
                )
            )
        return items[:limit] if limit else items

    async def parse_detail(self, html: str, url: str) -> dict:
        # legacy detail enrichment is best-effort and optional
        try:
            details = await self._legacy.fetch_job_details(url)
        except Exception:  # noqa: BLE001
            return {}
        if not details or not isinstance(details, dict):
            return {}
        return {k: v for k, v in details.items() if k not in ("url",)}