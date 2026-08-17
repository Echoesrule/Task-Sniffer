"""Job alert notification system for Telegram."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from telegram import Bot

from backend.models.database import Database, Job, TelegramUser

logger = logging.getLogger(__name__)


def _matches_keywords(job: Job, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = f"{job.title} {job.company} {job.description or ''} {job.skills or ''}".lower()
    return any(kw in text for kw in keywords)


def _matches_exclude(job: Job, exclude: list[str]) -> bool:
    if not exclude:
        return False
    text = f"{job.title} {job.description or ''}".lower()
    return any(ex in text for ex in exclude)


def _format_job_alert(job: Job) -> str:
    skills = job.skills_list[:5]
    skills_str = ", ".join(skills) if skills else "Not specified"

    salary = ""
    if job.salary_min and job.salary_max:
        salary = f"Salary: {job.salary_min:,}-{job.salary_max:,} {job.salary_currency or 'KES'}\n"
    elif job.salary_min:
        salary = f"Salary: {job.salary_min:,}+ {job.salary_currency or 'KES'}\n"

    remote = " [Remote]" if job.remote else ""

    risk = ""
    if job.risk_score and job.risk_score >= 40:
        risk = f"Risk: {job.risk_level} ({job.risk_score:.0f})\n"

    text = (
        f"New Job Match!\n\n"
        f"{job.title}{remote}\n"
        f"{job.company}\n"
        f"{salary}"
        f"Match: {job.match_score:.0%}\n"
        f"{risk}"
        f"Skills: {skills_str}\n"
        f"ID: {job.id[:8]}\n\n"
        f"Use /apply {job.id[:8]} to track"
    )
    return text


async def send_job_alerts(bot: Bot, db: Database) -> None:
    """Send job alerts to all active users with matching criteria."""
    async with db.async_session_factory() as session:
        users_result = await session.execute(
            select(TelegramUser).where(TelegramUser.is_active == True)
        )
        active_users = users_result.scalars().all()

        if not active_users:
            return

        for user in active_users:
            query = select(Job).where(
                Job.match_score >= 0.6,
                Job.risk_score < 40,
            )

            if user.min_salary:
                query = query.where(Job.salary_min >= user.min_salary)

            query = query.order_by(Job.match_score.desc()).limit(10)
            result = await session.execute(query)
            jobs = result.scalars().all()

            sent = 0
            for job in jobs:
                if not _matches_keywords(job, user.keywords_list):
                    continue
                if _matches_exclude(job, user.exclude_keywords_list):
                    continue

                try:
                    alert_text = _format_job_alert(job)
                    await bot.send_message(chat_id=user.chat_id, text=alert_text)
                    sent += 1
                except Exception as e:
                    logger.error(f"Failed to send alert to {user.chat_id}: {e}")

            if sent > 0:
                user.last_notified_at = datetime.now(timezone.utc)
                await session.commit()
