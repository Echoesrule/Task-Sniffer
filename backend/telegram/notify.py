"""Job alert notification system for Telegram.

Delivery is idempotent and durable: each ``(telegram_user, job)`` pair is
recorded in :class:`TelegramAlert` with a unique constraint, so a successful
alert is never resent on a later scheduler/alert-loop cycle. Failed sends are
retried a bounded number of times and never marked delivered before the send
succeeds.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from telegram import Bot

from backend.models.database import Database, Job, TelegramAlert, TelegramUser
from backend.sources.urls import is_safe_fetch_url

logger = logging.getLogger(__name__)

ALERT_STATUS_PENDING = "PENDING"
ALERT_STATUS_SENT = "SENT"
ALERT_STATUS_FAILED = "FAILED"

#: how many times a failed send is retried before it is abandoned
DEFAULT_MAX_ATTEMPTS = 3

#: Telegram hard limit is 4096 chars; keep a margin
MAX_MESSAGE_LENGTH = 4000


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


def _clean(text: str | None) -> str:
    """Collapse untrusted text to a single line (no markup is interpreted)."""
    return " ".join((text or "").split())


def _verified_job_link(job: Job) -> str | None:
    """Return a safe, verified link for a job, or None.

    Prefers the validated application URL, then the canonical/detail URLs. Only
    links from a job that passed URL validation (``url_status == VALID``) and
    that pass the URL safety policy are used - a link is never fabricated.
    """
    if (job.url_status or "") != "VALID":
        return None
    for candidate in (
        job.application_url,
        job.canonical_url,
        job.source_url,
        job.final_url,
    ):
        if candidate and is_safe_fetch_url(candidate, resolve_dns=False):
            return candidate
    return None


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

    short_id = (job.id or "")[:8]
    link = _verified_job_link(job)
    if link:
        footer = f"Apply/View: {link}\n\nUse /apply {short_id} to track"
    else:
        footer = f"Use /apply {short_id} to track (no verified link available)"

    text = (
        f"New Job Match!\n\n"
        f"{_clean(job.title)}{remote}\n"
        f"{_clean(job.company)}\n"
        f"{salary}"
        f"Match: {(job.match_score or 0.0):.0%}\n"
        f"{risk}"
        f"Skills: {skills_str}\n"
        f"ID: {short_id}\n\n"
        f"{footer}"
    )
    return _truncate(text, MAX_MESSAGE_LENGTH)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


async def _claim_delivery(
    session, user_id: str, job_id: str, max_attempts: int
) -> bool:
    """Atomically claim the right to send ``job`` to ``user``.

    Returns True only for the caller that should send. Uses the unique
    ``(telegram_user_id, job_id)`` constraint plus an atomic UPDATE so repeated
    and concurrent runs cannot both send; already-sent or exhausted records are
    skipped.
    """
    row = TelegramAlert(
        telegram_user_id=user_id,
        job_id=job_id,
        status=ALERT_STATUS_FAILED,
        attempts=1,
    )
    try:
        session.add(row)
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()

    result = await session.execute(
        update(TelegramAlert)
        .where(
            TelegramAlert.telegram_user_id == user_id,
            TelegramAlert.job_id == job_id,
            TelegramAlert.status != ALERT_STATUS_SENT,
            TelegramAlert.attempts < max_attempts,
        )
        .values(attempts=TelegramAlert.attempts + 1, status=ALERT_STATUS_PENDING)
    )
    await session.commit()
    return result.rowcount == 1


async def _mark_sent(session, user_id: str, job_id: str) -> None:
    await session.execute(
        update(TelegramAlert)
        .where(
            TelegramAlert.telegram_user_id == user_id,
            TelegramAlert.job_id == job_id,
        )
        .values(
            status=ALERT_STATUS_SENT,
            sent_at=datetime.now(timezone.utc),
            last_error=None,
        )
    )
    await session.commit()


async def _mark_failed(session, user_id: str, job_id: str, exc: Exception) -> None:
    await session.execute(
        update(TelegramAlert)
        .where(
            TelegramAlert.telegram_user_id == user_id,
            TelegramAlert.job_id == job_id,
        )
        .values(status=ALERT_STATUS_FAILED, last_error=str(exc)[:500])
    )
    await session.commit()


async def send_job_alerts(
    bot: Bot, db: Database, *, max_attempts: int = DEFAULT_MAX_ATTEMPTS
) -> int:
    """Send job alerts to all active users with matching criteria.

    Returns the number of messages actually sent. A given user/job pair is sent
    at most once (bounded retries for transient failures).
    """
    total_sent = 0

    async with db.async_session_factory() as session:
        users_result = await session.execute(
            select(TelegramUser).where(TelegramUser.is_active == True)
        )
        active_users = users_result.scalars().all()

        if not active_users:
            return 0

        # Snapshot user criteria before any commit: delivery bookkeeping commits
        # between sends, and re-reading ORM attributes afterwards is unsafe.
        user_specs = [
            {
                "id": user.id,
                "chat_id": user.chat_id,
                "keywords": user.keywords_list,
                "exclude": user.exclude_keywords_list,
                "min_salary": user.min_salary,
            }
            for user in active_users
        ]

        for spec in user_specs:
            query = select(Job).where(
                Job.match_score >= 0.6,
                Job.risk_score < 40,
            )

            if spec["min_salary"]:
                query = query.where(Job.salary_min >= spec["min_salary"])

            query = query.order_by(Job.match_score.desc()).limit(10)
            result = await session.execute(query)
            jobs = result.scalars().all()

            sent = 0
            for job in jobs:
                if not _matches_keywords(job, spec["keywords"]):
                    continue
                if _matches_exclude(job, spec["exclude"]):
                    continue

                # Format before claiming: the claim commits, after which ORM
                # attributes may no longer be readable without another round trip.
                job_id = job.id
                message = _format_job_alert(job)

                if not await _claim_delivery(session, spec["id"], job_id, max_attempts):
                    continue

                try:
                    await bot.send_message(chat_id=spec["chat_id"], text=message)
                except Exception as e:  # noqa: BLE001 - record and retry later
                    logger.warning(
                        "Failed to send alert to %s for job %s: %s",
                        spec["chat_id"], job_id, e,
                    )
                    await _mark_failed(session, spec["id"], job_id, e)
                    continue

                await _mark_sent(session, spec["id"], job_id)
                sent += 1

            if sent > 0:
                await session.execute(
                    update(TelegramUser)
                    .where(TelegramUser.id == spec["id"])
                    .values(last_notified_at=datetime.now(timezone.utc))
                )
                await session.commit()
            total_sent += sent

    return total_sent
