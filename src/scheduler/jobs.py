"""Scheduler for periodic job scraping."""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import config
from src.database.models import Database
from src.scrapers.jobicy import JobicyScraper
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.ashby import AshbyScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.jo_bound import JoBoundScraper
from src.scrapers.newjob import NewJobScraper
from src.scrapers.unspook import UnspookScraper

logger = logging.getLogger(__name__)

db = Database()


def get_all_scrapers() -> list:
    """Initialize all scrapers based on config."""
    scrapers = []
    sources = config.sources

    if sources.get("jobicy", {}).get("enabled", True):
        scrapers.append(JobicyScraper(sources["jobicy"]))

    if sources.get("greenhouse", {}).get("enabled", True):
        scrapers.append(GreenhouseScraper(sources["greenhouse"]))

    if sources.get("ashby", {}).get("enabled", True):
        scrapers.append(AshbyScraper(sources["ashby"]))

    if sources.get("lever", {}).get("enabled", True):
        scrapers.append(LeverScraper(sources["lever"]))

    if sources.get("jo_bound", {}).get("enabled", True):
        scrapers.append(JoBoundScraper(sources["jo_bound"]))

    if sources.get("newjob", {}).get("enabled", True):
        scrapers.append(NewJobScraper(sources["newjob"]))

    if sources.get("unspook", {}).get("enabled", True):
        scrapers.append(UnspookScraper(sources["unspook"]))

    return scrapers


async def run_scraper(scraper) -> int:
    """Run a single scraper and store results. Returns count of new jobs."""
    try:
        jobs = await scraper.run()
        new_count = 0

        for job_data in jobs:
            if db.add_job(job_data):
                new_count += 1

        db.update_scraper_state(
            source=scraper.source_name,
            last_run=datetime.utcnow(),
            jobs_found=new_count,
        )

        return new_count
    except Exception as e:
        logger.error(f"Scraper {scraper.source_name} failed: {e}")
        db.update_scraper_state(
            source=scraper.source_name,
            last_run=datetime.utcnow(),
        )
        return 0


async def run_all_scrapers() -> dict[str, int]:
    """Run all enabled scrapers. Returns dict of source -> new job count."""
    scrapers = get_all_scrapers()
    results = {}

    for scraper in scrapers:
        logger.info(f"Running scraper: {scraper.source_name}")
        new_jobs = await run_scraper(scraper)
        results[scraper.source_name] = new_jobs
        logger.info(f"{scraper.source_name}: {new_jobs} new jobs")

    return results


async def scheduled_scrape_job() -> None:
    """Scheduled job to run all scrapers."""
    logger.info("Starting scheduled scrape job")
    results = await run_all_scrapers()

    total_new = sum(results.values())
    logger.info(f"Scrape complete. Total new jobs: {total_new}")

    if total_new > 0:
        try:
            from src.bot.handlers import send_job_alerts
            from telegram import Bot

            bot = Bot(token=config.telegram_token)
            await send_job_alerts(bot)
        except Exception as e:
            logger.error(f"Failed to send alerts: {e}")


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the job scheduler."""
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        scheduled_scrape_job,
        trigger=IntervalTrigger(minutes=config.scraping_interval),
        id="main_scrape_job",
        name="Run all scrapers",
        replace_existing=True,
    )

    sources = config.sources
    for source_name, source_config in sources.items():
        if source_config.get("enabled", True):
            interval = source_config.get("interval_minutes", config.scraping_interval)

            async def run_specific_source(name=source_name, cfg=source_config):
                scraper_class = {
                    "jobicy": JobicyScraper,
                    "greenhouse": GreenhouseScraper,
                    "ashby": AshbyScraper,
                    "lever": LeverScraper,
                    "jo_bound": JoBoundScraper,
                    "newjob": NewJobScraper,
                    "unspook": UnspookScraper,
                }.get(name)

                if scraper_class:
                    scraper = scraper_class(cfg)
                    await run_scraper(scraper)

            scheduler.add_job(
                run_specific_source,
                trigger=IntervalTrigger(minutes=interval),
                id=f"scrape_{source_name}",
                name=f"Scrape {source_name}",
                replace_existing=True,
            )

    logger.info("Scheduler created successfully")
    return scheduler
