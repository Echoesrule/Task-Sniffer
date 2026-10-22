"""Background task definitions."""

from backend.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3)
def scrape_all_sources(self):
    """Run the ingestion engine over every crawlable registered source."""
    import asyncio
    asyncio.run(_scrape_all())


async def _scrape_all():
    from backend.services.runner import scrape_all_crawlable_sources

    await scrape_all_crawlable_sources()


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
    """Disabled: risk and match analysis run as part of ingestion."""
    return {"status": "disabled", "reason": "analysis is performed during ingestion"}


@celery_app.task(bind=True, max_retries=3)
def update_source_stats(self):
    """Disabled: source metrics are updated by the ingestion engine."""
    return {"status": "disabled", "reason": "metrics are updated during ingestion"}


@celery_app.task(bind=True, max_retries=3)
def match_job_to_candidate(self, job_id: str, candidate_id: str):
    """Disabled until personalized match results have a per-user store."""
    return {"status": "disabled", "reason": "per-user match persistence is not implemented"}


@celery_app.task(bind=True, max_retries=3)
def process_cv_upload(self, candidate_id: str, cv_path: str):
    """Disabled until CV parsing is implemented and explicitly enabled."""
    return {"status": "disabled", "reason": "CV parsing is not implemented"}
