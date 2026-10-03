"""Background task definitions."""

import logging

from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def scrape_all_sources(self):
    """Run the ingestion engine over every crawlable registered source."""
    import asyncio
    asyncio.run(_scrape_all())


async def _scrape_all():
    from backend.config import get_settings
    from backend.models.database import Database
    from backend.services.ingestion import IngestionEngine
    from backend.sources.registry import default_registry

    settings = get_settings()
    db = Database(settings.database_url)
    await db.init_db()
    engine = IngestionEngine(db.async_session_factory)

    for config in default_registry.crawlable():
        try:
            result = await engine.run_source(config.name)
            logger.info(
                "[%s] run finished new=%d dup=%d errors=%d paused=%s",
                config.name, result.new_jobs, result.duplicates, result.errors, result.paused,
            )
        except Exception as e:  # noqa: BLE001 - a failing source never blocks the rest
            logger.error("Source %s run failed: %s", config.name, e)

    await db.close()


@celery_app.task(bind=True, max_retries=3)
def ingest_source(self, name: str, force: bool = False, limit: int | None = None):
    """Run a single source through the ingestion engine."""
    import asyncio
    return asyncio.run(_ingest_one(name, force=force, limit=limit))


async def _ingest_one(name: str, *, force: bool, limit: int | None):
    from backend.config import get_settings
    from backend.models.database import Database
    from backend.services.ingestion import IngestionEngine

    settings = get_settings()
    db = Database(settings.database_url)
    await db.init_db()
    engine = IngestionEngine(db.async_session_factory)
    result = await engine.run_source(name, force=force, limit=limit)
    await db.close()
    return result.as_dict()


@celery_app.task(bind=True, max_retries=3)
def analyze_new_jobs(self):
    """Analyze jobs that haven't been analyzed yet."""
    logger.info("Analyzing new jobs...")


@celery_app.task(bind=True, max_retries=3)
def update_source_stats(self):
    """Update source intelligence metrics."""
    logger.info("Updating source stats...")


@celery_app.task(bind=True, max_retries=3)
def match_job_to_candidate(self, job_id: str, candidate_id: str):
    """Match a specific job to a candidate."""
    logger.info(f"Matching job {job_id} to candidate {candidate_id}")


@celery_app.task(bind=True, max_retries=3)
def process_cv_upload(self, candidate_id: str, cv_path: str):
    """Parse and extract structured data from uploaded CV."""
    logger.info(f"Processing CV for candidate {candidate_id}")
