"""Background task definitions."""

import logging

from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def scrape_all_sources(self):
    """Run all enabled scrapers."""
    import asyncio
    asyncio.run(_scrape_all())


async def _scrape_all():
    from backend.scrapers.brightermonday import BrighterMondayScraper
    from backend.scrapers.myjobs import MyJobsKenyaScraper
    from backend.scrapers.jobicy import JobicyScraper
    from backend.scrapers.greenhouse import GreenhouseScraper
    from backend.scrapers.ashby import AshbyScraper
    from backend.services.normalizer import JobNormalizer
    from backend.services.deduplicator import JobDeduplicator
    from backend.risk.engine import RiskEngine
    from backend.matching.engine import MatchingEngine
    from backend.config import get_settings
    from backend.models.database import Database

    settings = get_settings()
    db = Database(settings.database_url)
    normalizer = JobNormalizer()
    risk_engine = RiskEngine()

    scrapers = [
        BrighterMondayScraper({"enabled": True}),
        MyJobsKenyaScraper({"enabled": True}),
        JobicyScraper({"enabled": True}),
        GreenhouseScraper({"enabled": True, "boards": ["airbnb", "discord", "figma", "vercel"]}),
        AshbyScraper({"enabled": True, "boards": ["openai", "linear"]}),
    ]

    for scraper in scrapers:
        if not scraper.enabled:
            continue
        try:
            raw_jobs = await scraper.fetch_jobs()
            for raw_job in raw_jobs:
                normalized = normalizer.normalize(raw_job, scraper.name)
                risk_result = risk_engine.analyze(normalized)
                normalized["risk_score"] = risk_result["risk_score"]
                normalized["risk_level"] = risk_result["risk_level"]
                normalized["risk_flags"] = risk_result["risk_flags"]
            logger.info(f"{scraper.name}: processed {len(raw_jobs)} jobs")
        except Exception as e:
            logger.error(f"Scraper {scraper.name} failed: {e}")
        finally:
            await scraper.close()


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
