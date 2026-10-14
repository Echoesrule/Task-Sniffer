"""Celery-free ingestion runner.

Runs every crawlable source through the shared ingestion engine. Used by the
APScheduler-based ``scheduler.py`` (local/dev, no broker) and by the Celery task
``backend.workers.tasks.scrape_all_sources`` (docker-compose).
"""

from __future__ import annotations

import logging
from typing import Any

from backend.config import get_settings
from backend.models.database import Database
from backend.services.ingestion import IngestionEngine
from backend.sources.registry import default_registry

logger = logging.getLogger(__name__)


async def scrape_all_crawlable_sources(
    db: Database | None = None,
) -> dict[str, dict[str, Any]]:
    """Run the ingestion engine over every crawlable registered source.

    One failing source never blocks the rest. Returns ``{source: result}`` where
    ``result`` is ``SourceRunResult.as_dict()`` or ``{"error": ...}``.
    """
    settings = get_settings()
    owns_db = db is None
    if db is None:
        db = Database(settings.database_url)
        await db.init_db()

    engine = IngestionEngine(
        db.async_session_factory,
        max_jobs_per_source=settings.max_jobs_per_source,
    )

    results: dict[str, dict[str, Any]] = {}
    try:
        for config in default_registry.crawlable():
            try:
                result = await engine.run_source(config.name)
                results[config.name] = result.as_dict()
                logger.info(
                    "[%s] run finished new=%d dup=%d errors=%d paused=%s",
                    config.name,
                    result.new_jobs,
                    result.duplicates,
                    result.errors,
                    result.paused,
                )
            except Exception as exc:  # noqa: BLE001 - one source never blocks the rest
                logger.error("Source %s run failed: %s", config.name, exc)
                results[config.name] = {"error": str(exc)}
    finally:
        if owns_db:
            await db.close()

    return results
