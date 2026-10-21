"""Telegram bot command handlers."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func as sa_func

from telegram import Update
from telegram.ext import ContextTypes

from backend.config import get_settings
from backend.models.database import (
    Database,
    Job,
    Source,
    Application,
    ApplicationStatusChange,
    Candidate,
    TelegramUser,
    User,
)
from backend.security import verify_password

logger = logging.getLogger(__name__)

_db: Database | None = None


def set_db(db: Database) -> None:
    global _db
    _db = db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def _get_user(chat_id: str) -> TelegramUser | None:
    db = get_db()
    async with db.async_session_factory() as session:
        result = await session.execute(
            select(TelegramUser).where(TelegramUser.chat_id == chat_id)
        )
        return result.scalars().first()


async def _ensure_user(update: Update) -> TelegramUser | None:
    chat_id = str(update.effective_chat.id)
    user = await _get_user(chat_id)
    if not user:
        await update.message.reply_text("Please use /start first to register.")
        return None
    return user


async def _get_linked_candidate(user: TelegramUser, session):
    """Return the linked Candidate if the TelegramUser is linked and exists."""
    if not user.candidate_id:
        return None
    result = await session.execute(select(Candidate).where(Candidate.id == user.candidate_id))
    return result.scalars().first()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    db = get_db()

    async with db.async_session_factory() as session:
        result = await session.execute(
            select(TelegramUser).where(TelegramUser.chat_id == chat_id)
        )
        existing = result.scalars().first()

        if existing:
            existing.is_active = True
            await session.commit()
            await update.message.reply_text(
                "Welcome back! You're already registered for job alerts.\n"
                "Use /settings to configure your preferences."
            )
        else:
            new_user = TelegramUser(
                chat_id=chat_id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
            )
            session.add(new_user)
            await session.commit()
            await update.message.reply_text(
                "Welcome to Task Sniffer!\n\n"
                "You'll receive alerts for jobs matching your criteria.\n\n"
                "Commands:\n"
                "/top - Latest high-match jobs\n"
                "/search <query> - Search jobs\n"
                "/link <email> <password> - Link your web account\n"
                "/unlink - Unlink your web account\n"
                "/apply <job_id> - Track application\n"
                "/my_applications - View tracked apps\n"
                "/update_status <app_id> <status> - Update status\n"
                "/settings - Configure preferences\n"
                "/stats - View statistics\n"
                "/sources - List active sources\n"
                "/stop - Stop notifications"
            )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    db = get_db()

    async with db.async_session_factory() as session:
        result = await session.execute(
            select(TelegramUser).where(TelegramUser.chat_id == chat_id)
        )
        user = result.scalars().first()
        if user:
            user.is_active = False
            await session.commit()
            await update.message.reply_text(
                "Unsubscribed from job alerts.\nUse /start to re-enable."
            )
        else:
            await update.message.reply_text("You're not registered. Use /start to begin.")


async def link_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /link <email> <password>")
        return

    email = context.args[0].strip().lower()
    password = " ".join(context.args[1:])

    db = get_db()
    async with db.async_session_factory() as session:
        result = await session.execute(select(TelegramUser).where(TelegramUser.id == user.id))
        tg_user = result.scalars().first()
        if not tg_user:
            await update.message.reply_text("Please use /start first to register.")
            return

        if tg_user.candidate_id:
            candidate_res = await session.execute(
                select(Candidate).where(Candidate.id == tg_user.candidate_id)
            )
            linked = candidate_res.scalars().first()
            label = linked.email if linked and linked.email else tg_user.candidate_id
            await update.message.reply_text(f"This account is already linked to {label}. Use /unlink first.")
            return

        user_res = await session.execute(select(User).where(User.email == email))
        web_user = user_res.scalars().first()
        if not web_user or not verify_password(password, web_user.hashed_password):
            await update.message.reply_text("Invalid email or password. Account not linked.")
            return
        if not web_user.is_active:
            await update.message.reply_text("That web account is inactive. Account not linked.")
            return

        cand_res = await session.execute(select(Candidate).where(Candidate.user_id == web_user.id))
        candidate = cand_res.scalars().first()
        if not candidate:
            candidate = Candidate(
                user_id=web_user.id,
                name=web_user.email.split("@")[0],
                email=web_user.email,
            )
            session.add(candidate)
            await session.flush()

        tg_user.candidate_id = candidate.id
        await session.commit()
        await update.message.reply_text(f"Linked to {web_user.email}. You can now use /apply and /my_applications.")


async def unlink_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    db = get_db()
    async with db.async_session_factory() as session:
        result = await session.execute(select(TelegramUser).where(TelegramUser.id == user.id))
        tg_user = result.scalars().first()
        if not tg_user:
            await update.message.reply_text("Please use /start first to register.")
            return
        if not tg_user.candidate_id:
            await update.message.reply_text("No linked web account.")
            return
        tg_user.candidate_id = None
        await session.commit()
        await update.message.reply_text("Account unlinked.")


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    keywords = user.keywords_list
    exclude = user.exclude_keywords_list

    salary_str = f"{user.min_salary:,}" if user.min_salary else "Not set"
    keywords_str = ", ".join(keywords) if keywords else "None"
    exclude_str = ", ".join(exclude) if exclude else "None"

    text = (
        "Your settings:\n\n"
        f"Keywords: {keywords_str}\n"
        f"Exclude: {exclude_str}\n"
        f"Min Salary: {salary_str} KES\n\n"
        "To update:\n"
        "/set_keywords python,javascript,react\n"
        "/set_exclude intern,junior\n"
        "/set_salary 200000"
    )
    await update.message.reply_text(text)


async def set_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    if not context.args:
        await update.message.reply_text("Usage: /set_keywords python,javascript,react")
        return

    keywords = ",".join(context.args).split(",")
    keywords = [k.strip().lower() for k in keywords if k.strip()]

    db = get_db()
    async with db.async_session_factory() as session:
        result = await session.execute(
            select(TelegramUser).where(TelegramUser.chat_id == user.chat_id)
        )
        db_user = result.scalars().first()
        if db_user:
            db_user.keywords_list = keywords
            await session.commit()
            await update.message.reply_text(f"Keywords updated: {', '.join(keywords)}")


async def set_exclude(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    if not context.args:
        await update.message.reply_text("Usage: /set_exclude intern,junior")
        return

    exclude = ",".join(context.args).split(",")
    exclude = [e.strip().lower() for e in exclude if e.strip()]

    db = get_db()
    async with db.async_session_factory() as session:
        result = await session.execute(
            select(TelegramUser).where(TelegramUser.chat_id == user.chat_id)
        )
        db_user = result.scalars().first()
        if db_user:
            db_user.exclude_keywords_list = exclude
            await session.commit()
            await update.message.reply_text(f"Excluded keywords updated: {', '.join(exclude)}")


async def set_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    if not context.args:
        await update.message.reply_text("Usage: /set_salary 200000")
        return

    try:
        salary = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid number.")
        return

    db = get_db()
    async with db.async_session_factory() as session:
        result = await session.execute(
            select(TelegramUser).where(TelegramUser.chat_id == user.chat_id)
        )
        db_user = result.scalars().first()
        if db_user:
            db_user.min_salary = salary
            await session.commit()
            await update.message.reply_text(f"Minimum salary set to {salary:,} KES")


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /search python react")
        return

    query = " ".join(context.args).lower()
    db = get_db()

    async with db.async_session_factory() as session:
        result = await session.execute(
            select(Job).where(
                Job.title.ilike(f"%{query}%")
                | Job.company.ilike(f"%{query}%")
                | Job.description.ilike(f"%{query}%")
            ).order_by(Job.created_at.desc()).limit(10)
        )
        jobs = result.scalars().all()

        if not jobs:
            await update.message.reply_text(f"No jobs found matching '{query}'")
            return

        lines = [f"Results for '{query}':\n"]
        for i, job in enumerate(jobs, 1):
            lines.append(
                f"{i}. {job.title}\n"
                f"   {job.company} | {job.location or 'N/A'}\n"
                f"   Match: {job.match_score:.0%} | Risk: {job.risk_level or 'pending'}\n"
                f"   ID: {job.id[:8]}"
            )

        await update.message.reply_text("\n\n".join(lines))


async def top_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show top matching jobs."""
    user = await _ensure_user(update)
    db = get_db()

    async with db.async_session_factory() as session:
        result = await session.execute(
            select(Job)
            .where(Job.status == "discovered")
            .order_by(Job.match_score.desc())
            .limit(5)
        )
        jobs = result.scalars().all()

        if not jobs:
            await update.message.reply_text("No jobs found yet. Run a scan first.")
            return

        lines = ["Top matching jobs:\n"]
        for i, job in enumerate(jobs, 1):
            salary = ""
            if job.salary_min and job.salary_max:
                salary = f" | {job.salary_min:,}-{job.salary_max:,} {job.salary_currency or 'KES'}"
            elif job.salary_min:
                salary = f" | {job.salary_min:,}+ {job.salary_currency or 'KES'}"

            remote = " [Remote]" if job.remote else ""
            lines.append(
                f"{i}. {job.title}\n"
                f"   {job.company}{remote}{salary}\n"
                f"   Match: {job.match_score:.0%} | Risk: {job.risk_level or 'pending'}\n"
                f"   ID: {job.id[:8]}"
            )

        await update.message.reply_text("\n\n".join(lines))


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db()

    async with db.async_session_factory() as session:
        total_result = await session.execute(select(sa_func.count(Job.id)))
        total = total_result.scalar() or 0

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_result = await session.execute(
            select(sa_func.count(Job.id)).where(Job.created_at >= today_start)
        )
        today = today_result.scalar() or 0

        source_result = await session.execute(
            select(Source.name, sa_func.count(Job.id))
            .join(Job, Source.id == Job.source_id)
            .group_by(Source.name)
        )
        sources_data = source_result.all()

        app_result = await session.execute(sa_func.count(Application.id))
        apps = app_result.scalar() or 0

        lines = [
            "Task Sniffer Stats:\n",
            f"Total jobs: {total}",
            f"Today: {today}",
            f"Applications: {apps}",
            "\nBy source:",
        ]
        for name, count in sources_data:
            lines.append(f"  {name}: {count}")

        await update.message.reply_text("\n".join(lines))


async def sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db()

    async with db.async_session_factory() as session:
        result = await session.execute(select(Source).order_by(Source.tier))
        sources_list = result.scalars().all()

        if not sources_list:
            await update.message.reply_text("No sources configured.")
            return

        lines = ["Active Sources:\n"]
        for s in sources_list:
            status = "Enabled" if s.enabled else "Disabled"
            lines.append(
                f"Tier {s.tier} | {s.name}\n"
                f"  {status} | {s.jobs_found} jobs found"
            )

        await update.message.reply_text("\n".join(lines))


async def apply_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /apply <job_id>\n"
            "Use /top or /search to find job IDs.\n"
            "You must be linked with /link <email> <password> first."
        )
        return

    job_ref = context.args[0]
    db = get_db()

    async with db.async_session_factory() as session:
        tg_res = await session.execute(select(TelegramUser).where(TelegramUser.id == user.id))
        tg_user = tg_res.scalars().first()
        if not tg_user:
            await update.message.reply_text("Please use /start first to register.")
            return
        candidate = await _get_linked_candidate(tg_user, session)
        if not candidate:
            await update.message.reply_text("No linked web account. Use /link <email> <password> to link your profile.")
            return

        result = await session.execute(
            select(Job).where(Job.id.startswith(job_ref))
        )
        job = result.scalars().first()

        if not job:
            await update.message.reply_text(f"Job not found: {job_ref}")
            return

        existing_app = await session.execute(
            select(Application).where(
                Application.candidate_id == candidate.id,
                Application.job_id == job.id,
            )
        )
        if existing_app.scalars().first():
            await update.message.reply_text("You've already tracked this application.")
            return

        app = Application(
            candidate_id=candidate.id,
            job_id=job.id,
            status="shortlisted",
            applied_at=datetime.now(timezone.utc),
            match_score=job.match_score,
            risk_score=job.risk_score,
        )
        session.add(app)
        await session.commit()

        await update.message.reply_text(
            f"Application tracked!\n\n"
            f"Job: {job.title}\n"
            f"Company: {job.company}\n"
            f"Status: shortlisted\n\n"
            f"Use /my_applications to see all tracked apps."
        )


async def my_applications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    db = get_db()
    async with db.async_session_factory() as session:
        tg_res = await session.execute(select(TelegramUser).where(TelegramUser.id == user.id))
        tg_user = tg_res.scalars().first()
        if not tg_user:
            await update.message.reply_text("Please use /start first to register.")
            return
        candidate = await _get_linked_candidate(tg_user, session)
        if not candidate:
            await update.message.reply_text("No linked web account. Use /link <email> <password> to link your profile.")
            return

        result = await session.execute(
            select(Application)
            .where(Application.candidate_id == candidate.id)
            .order_by(Application.created_at.desc())
        )
        apps = result.scalars().all()

        if not apps:
            await update.message.reply_text(
                "No applications tracked yet.\nUse /apply <job_id> to start."
            )
            return

        lines = ["Your Applications:\n"]
        for app in apps:
            job_result = await session.execute(select(Job).where(Job.id == app.job_id))
            job = job_result.scalars().first()
            job_title = job.title if job else "Unknown"
            job_company = job.company if job else "Unknown"

            if app.match_score is not None:
                match_str = f"{app.match_score:.0%}"
            else:
                match_str = "N/A"
            lines.append(
                f"- {job_title} @ {job_company}\n"
                f"  Status: {app.status} | Match: {match_str}\n"
                f"  App ID: {app.id[:8]}"
            )

        lines.append(
            "\nUse /update_status <app_id> <status>\n"
            "Statuses: shortlisted, applied, interview, offer, rejected, withdrawn"
        )
        await update.message.reply_text("\n".join(lines))


async def update_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _ensure_user(update)
    if not user:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /update_status <app_id> <status>\n"
            "Statuses: shortlisted, applied, interview, offer, rejected, withdrawn"
        )
        return

    app_ref = context.args[0]
    new_status = context.args[1]
    valid_statuses = ["shortlisted", "applied", "interview", "offer", "rejected", "withdrawn"]

    if new_status not in valid_statuses:
        await update.message.reply_text(
            f"Invalid status: {new_status}\nValid: {', '.join(valid_statuses)}"
        )
        return

    db = get_db()
    async with db.async_session_factory() as session:
        tg_res = await session.execute(select(TelegramUser).where(TelegramUser.id == user.id))
        tg_user = tg_res.scalars().first()
        if not tg_user:
            await update.message.reply_text("Please use /start first to register.")
            return
        candidate = await _get_linked_candidate(tg_user, session)
        if not candidate:
            await update.message.reply_text("No linked web account. Use /link <email> <password> to link your profile.")
            return

        result = await session.execute(
            select(Application).where(
                Application.candidate_id == candidate.id,
                Application.id.startswith(app_ref),
            )
        )
        app = result.scalars().first()

        if not app:
            await update.message.reply_text("Application not found. Use /apply first.")
            return

        old_status = app.status
        app.status = new_status

        change = ApplicationStatusChange(
            application_id=app.id,
            old_status=old_status,
            new_status=new_status,
        )
        session.add(change)
        await session.commit()

        await update.message.reply_text(f"Application status updated: {old_status} -> {new_status}")
