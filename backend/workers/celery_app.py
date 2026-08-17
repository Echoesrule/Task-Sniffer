"""Celery application and periodic tasks."""

from celery import Celery
from celery.schedules import crontab

from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "work_bot_hunter",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Nairobi",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "scrape-all-sources": {
        "task": "backend.workers.tasks.scrape_all_sources",
        "schedule": crontab(minute=0, hour="*/1"),
    },
    "analyze-new-jobs": {
        "task": "backend.workers.tasks.analyze_new_jobs",
        "schedule": crontab(minute=15, hour="*/1"),
    },
    "update-source-stats": {
        "task": "backend.workers.tasks.update_source_stats",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}

celery_app.autodiscover_tasks(["backend.workers"])
