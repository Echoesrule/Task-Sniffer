"""Local job-ingestion scheduler.

An APScheduler-based alternative to Celery beat for single-machine use (no
Redis/broker required). Runs one ingestion pass immediately on startup, then
every ``SCRAPE_INTERVAL_MINUTES`` (default 60).

Usage:
    .venv/bin/python scheduler.py
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")


async def run_ingestion_pass() -> None:
    from backend.services.runner import scrape_all_crawlable_sources

    logger.info("Starting ingestion pass over crawlable sources...")
    results = await scrape_all_crawlable_sources()
    new_jobs = sum(r.get("new_jobs", 0) for r in results.values())
    failed = sum(1 for r in results.values() if "error" in r)
    logger.info(
        "Ingestion pass complete: %d sources, %d new jobs, %d failed",
        len(results),
        new_jobs,
        failed,
    )


async def main() -> None:
    interval = max(1, get_settings().scrape_interval_minutes)

    await run_ingestion_pass()

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_ingestion_pass,
        "interval",
        minutes=interval,
        id="scrape_all_sources",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler started (every %d minutes). Ctrl+C to stop.", interval)

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
