"""Telegram bot command handlers."""

import json
import logging
from datetime import datetime

from telegram import Bot, Update
from telegram.ext import ContextTypes

from src.config import config
from src.database.models import Application, Database, Job, UserPreferences

logger = logging.getLogger(__name__)

db = Database()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - Register user for alerts."""
    chat_id = str(update.effective_chat.id)

    session = db.get_session()
    try:
        existing = session.query(UserPreferences).filter_by(chat_id=chat_id).first()
        if existing:
            existing.is_active = True
            session.commit()
            await update.message.reply_text(
                "Welcome back! You're already registered for job alerts.\n"
                "Use /settings to configure your preferences."
            )
        else:
            prefs = UserPreferences(
                chat_id=chat_id,
                keywords=json.dumps(config.filters.get("keywords", [])),
                exclude_keywords=json.dumps(config.filters.get("exclude_keywords", [])),
                min_salary=config.filters.get("min_salary", 0),
            )
            session.add(prefs)
            session.commit()
            await update.message.reply_text(
                "Welcome to Work Hunter Bot!\n\n"
                "You'll receive alerts for remote jobs matching your criteria.\n\n"
                "Commands:\n"
                "/settings - Configure preferences\n"
                "/search <query> - Search jobs\n"
                "/apply <job_url> - Track application\n"
                "/my_applications - View tracked apps\n"
                "/update_status <id> <status> - Update app status\n"
                "/stats - View statistics\n"
                "/sources - List active sources\n"
                "/stop - Stop notifications"
            )
    finally:
        session.close()


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command - Unregister user from alerts."""
    chat_id = str(update.effective_chat.id)

    session = db.get_session()
    try:
        prefs = session.query(UserPreferences).filter_by(chat_id=chat_id).first()
        if prefs:
            prefs.is_active = False
            session.commit()
            await update.message.reply_text(
                "You've been unsubscribed from job alerts.\n"
                "Use /start to re-enable notifications."
            )
        else:
            await update.message.reply_text("You're not registered. Use /start to begin.")
    finally:
        session.close()


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - Show and configure preferences."""
    chat_id = str(update.effective_chat.id)

    session = db.get_session()
    try:
        prefs = session.query(UserPreferences).filter_by(chat_id=chat_id).first()
        if not prefs:
            await update.message.reply_text("Please use /start first to register.")
            return

        keywords = json.loads(prefs.keywords) if prefs.keywords else []
        exclude = json.loads(prefs.exclude_keywords) if prefs.exclude_keywords else []

        text = (
            "Your current settings:\n\n"
            f"Keywords: {', '.join(keywords) if keywords else 'None'}\n"
            f"Exclude: {', '.join(exclude) if exclude else 'None'}\n"
            f"Min Salary: ${prefs.min_salary:,}" if prefs.min_salary else "Min Salary: Not set"
            f"\n\nTo update, use:\n"
            "/set_keywords python,javascript,react\n"
            "/set_exclude intern,junior\n"
            "/set_salary 100000"
        )
        await update.message.reply_text(text)
    finally:
        session.close()


async def set_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /set_keywords command."""
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("Usage: /set_keywords python,javascript,react")
        return

    keywords = ",".join(context.args).split(",")
    keywords = [k.strip() for k in keywords if k.strip()]

    session = db.get_session()
    try:
        prefs = session.query(UserPreferences).filter_by(chat_id=chat_id).first()
        if prefs:
            prefs.keywords = json.dumps(keywords)
            session.commit()
            await update.message.reply_text(f"Keywords updated: {', '.join(keywords)}")
        else:
            await update.message.reply_text("Please use /start first.")
    finally:
        session.close()


async def set_exclude(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /set_exclude command."""
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("Usage: /set_exclude intern,junior")
        return

    exclude = ",".join(context.args).split(",")
    exclude = [e.strip() for e in exclude if e.strip()]

    session = db.get_session()
    try:
        prefs = session.query(UserPreferences).filter_by(chat_id=chat_id).first()
        if prefs:
            prefs.exclude_keywords = json.dumps(exclude)
            session.commit()
            await update.message.reply_text(f"Excluded keywords updated: {', '.join(exclude)}")
        else:
            await update.message.reply_text("Please use /start first.")
    finally:
        session.close()


async def set_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /set_salary command."""
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("Usage: /set_salary 100000")
        return

    try:
        salary = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid number.")
        return

    session = db.get_session()
    try:
        prefs = session.query(UserPreferences).filter_by(chat_id=chat_id).first()
        if prefs:
            prefs.min_salary = salary
            session.commit()
            await update.message.reply_text(f"Minimum salary set to ${salary:,}")
        else:
            await update.message.reply_text("Please use /start first.")
    finally:
        session.close()


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /search command - Search stored jobs."""
    if not context.args:
        await update.message.reply_text("Usage: /search python react")
        return

    query = " ".join(context.args).lower()

    session = db.get_session()
    try:
        jobs = (
            session.query(Job)
            .filter(
                Job.title.ilike(f"%{query}%")
                | Job.company.ilike(f"%{query}%")
                | Job.description.ilike(f"%{query}%")
            )
            .order_by(Job.scraped_at.desc())
            .limit(10)
            .all()
        )

        if not jobs:
            await update.message.reply_text(f"No jobs found matching '{query}'")
            return

        text = f"Search results for '{query}':\n\n"
        for i, job in enumerate(jobs, 1):
            text += (
                f"{i}. {job.title}\n"
                f"   Company: {job.company}\n"
                f"   Source: {job.source}\n"
                f"   URL: {job.url}\n\n"
            )

        await update.message.reply_text(text)
    finally:
        session.close()


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - Show job statistics."""
    session = db.get_session()
    try:
        from sqlalchemy import func

        total = session.query(Job).count()
        sources = session.query(Job.source, func.count(Job.id)).group_by(Job.source).all()
        recent = (
            session.query(Job)
            .filter(Job.scraped_at >= datetime.utcnow().replace(hour=0, minute=0, second=0))
            .count()
        )

        text = "Job Statistics:\n\n"
        text += f"Total jobs: {total}\n"
        text += f"Today: {recent}\n\n"
        text += "By source:\n"
        for source, count in sources:
            text += f"  {source}: {count}\n"

        await update.message.reply_text(text)
    finally:
        session.close()


async def sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sources command - List active sources."""
    sources_config = config.sources

    text = "Active Job Sources:\n\n"
    for name, settings in sources_config.items():
        status = "Enabled" if settings.get("enabled", True) else "Disabled"
        interval = settings.get("interval_minutes", 60)
        text += f"  {name}: {status} (every {interval} min)\n"

    await update.message.reply_text(text)


async def format_job_alert(job: Job) -> str:
    """Format a job for Telegram notification."""
    tech_stack = json.loads(job.tech_stack) if job.tech_stack else []
    tech_str = ", ".join(tech_stack[:5]) if tech_stack else "Not specified"

    salary_str = ""
    if job.salary_min and job.salary_max:
        salary_str = f"Salary: ${job.salary_min:,} - ${job.salary_max:,}\n"
    elif job.salary_min:
        salary_str = f"Salary: ${job.salary_min:,}+\n"

    match_str = ""
    if hasattr(job, "match_score") and job.match_score is not None:
        match_str = f"Match: {job.match_score:.0f}/100\n"

    risk_str = ""
    if hasattr(job, "risk_score") and job.risk_score is not None:
        if job.risk_score >= 60:
            risk_str = f"Risk: {job.risk_score:.0f}/100 (Warning)\n"

    text = (
        f"New Job Found!\n\n"
        f"{job.title}\n"
        f"{job.company}\n"
        f"{salary_str}"
        f"{match_str}{risk_str}"
        f"Tech: {tech_str}\n"
        f"Apply: {job.url}\n\n"
        f"Source: {job.source} | Posted: {job.scraped_at.strftime('%Y-%m-%d')}"
    )
    return text


async def send_job_alerts(bot: Bot) -> None:
    """Send job alerts to all active users."""
    session = db.get_session()
    try:
        unnotified = session.query(Job).filter_by(notified=False).limit(10).all()
        active_users = session.query(UserPreferences).filter_by(is_active=True).all()

        if not unnotified or not active_users:
            return

        for job in unnotified:
            alert_text = await format_job_alert(job)

            for user in active_users:
                try:
                    await bot.send_message(
                        chat_id=user.chat_id,
                        text=alert_text,
                        parse_mode=None,
                    )
                except Exception as e:
                    logger.error(f"Failed to send alert to {user.chat_id}: {e}")

            job.notified = True

        session.commit()
    finally:
        session.close()


async def apply_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /apply command - Track a job application."""
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text(
            "Usage: /apply <job_url_or_id>\n"
            "Tracks that you've applied to this job."
        )
        return

    job_ref = context.args[0]

    session = db.get_session()
    try:
        job = session.query(Job).filter(
            (Job.id == job_ref) | (Job.url == job_ref)
        ).first()

        if not job:
            await update.message.reply_text(f"Job not found: {job_ref}")
            return

        match_score = getattr(job, "match_score", 0) or 0
        risk_score = getattr(job, "risk_score", 0) or 0

        success = db.add_application(
            job_id=job.id,
            chat_id=chat_id,
            match_score=match_score,
            risk_score=risk_score,
        )

        if success:
            await update.message.reply_text(
                f"Application tracked!\n\n"
                f"Job: {job.title}\n"
                f"Company: {job.company}\n"
                f"Status: applied\n\n"
                f"Use /my_applications to see all tracked applications."
            )
        else:
            await update.message.reply_text("You've already tracked this application.")
    finally:
        session.close()


async def my_applications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /my_applications command - Show tracked applications."""
    chat_id = str(update.effective_chat.id)

    status_filter = context.args[0] if context.args else None
    applications = db.get_user_applications(chat_id, status=status_filter)

    if not applications:
        await update.message.reply_text(
            "No applications tracked yet.\n"
            "Use /apply <job_url> to start tracking."
        )
        return

    text = "Your Applications:\n\n"
    for app in applications:
        text += (
            f"- {app.job_id[:12]}... | {app.status}\n"
            f"  Score: {app.match_score:.0f}/100 | Risk: {app.risk_score:.0f}/100\n"
        )

    text += (
        "\nUse /update_status <job_id> <status>\n"
        f"Valid statuses: {', '.join(Application.STATUSES)}"
    )
    await update.message.reply_text(text)


async def update_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /update_status command - Update application status."""
    chat_id = str(update.effective_chat.id)

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /update_status <job_id> <status>\n"
            f"Valid statuses: {', '.join(Application.STATUSES)}"
        )
        return

    job_ref = context.args[0]
    new_status = context.args[1]

    if new_status not in Application.STATUSES:
        await update.message.reply_text(
            f"Invalid status: {new_status}\n"
            f"Valid statuses: {', '.join(Application.STATUSES)}"
        )
        return

    success = db.update_application_status(job_ref, chat_id, new_status)
    if success:
        await update.message.reply_text(f"Application status updated to: {new_status}")
    else:
        await update.message.reply_text("Application not found. Use /apply first.")
