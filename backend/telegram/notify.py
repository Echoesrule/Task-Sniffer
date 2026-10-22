"""Per-candidate Telegram job alerts with durable claims and bounded retries.

Telegram sends and a local database commit cannot be one atomic transaction.
If Telegram accepts a message and the process dies before recording ``sent``,
the expired ``sending`` claim is retried and a duplicate remains possible.
Retries are retained to favor eventual delivery; the ambiguity is logged and
delayed to reduce, but cannot eliminate, duplicates.
"""

import logging
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from telegram import Bot
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter

from backend.models.database import (
    CandidateJobScore,
    Database,
    Job,
    TelegramAlertDelivery,
    TelegramUser,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
CLAIM_LEASE = timedelta(minutes=5)


def _matches_keywords(job: Job, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text = f"{job.title} {job.company} {job.description or ''} {job.skills or ''}".lower()
    return any(kw in text for kw in keywords)


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _matches_exclude(job: Job, exclude: list[str]) -> bool:
    if not exclude:
        return False
    text = f"{job.title} {job.description or ''}".lower()
    return any(ex in text for ex in exclude)


def _format_job_alert(job: Job, score: float) -> str:
    skills = job.skills_list[:5]
    skills_str = ", ".join(skills) if skills else "Not specified"
    salary = ""
    if job.salary_min and job.salary_max:
        salary = f"Salary: {job.salary_min:,}-{job.salary_max:,} {job.salary_currency or 'KES'}\n"
    elif job.salary_min:
        salary = f"Salary: {job.salary_min:,}+ {job.salary_currency or 'KES'}\n"
    remote = " [Remote]" if job.remote else ""
    risk = f"Risk: {job.risk_level} ({job.risk_score:.0f})\n" if job.risk_score and job.risk_score >= 40 else ""
    return (
        f"New Job Match!\n\n{job.title}{remote}\n{job.company}\n{salary}"
        f"Match: {score:.0%}\n{risk}Skills: {skills_str}\nID: {job.id[:8]}\n\n"
        f"Use /apply {job.id[:8]} to track"
    )


def _retry_delay(attempt: int, *, uncertain: bool = False) -> timedelta:
    seconds = min(30 * (2 ** max(0, attempt - 1)), 1800)
    if uncertain:
        seconds = max(seconds, 300)
    return timedelta(seconds=seconds)


async def _claim_delivery(session, user_id: str, job_id: str, now: datetime) -> tuple[str, int] | None:
    delivery_id = (
        await session.execute(
            select(
                TelegramAlertDelivery.id,
                TelegramAlertDelivery.status,
                TelegramAlertDelivery.claim_until,
                TelegramAlertDelivery.attempts,
            ).where(
                TelegramAlertDelivery.telegram_user_id == user_id,
                TelegramAlertDelivery.job_id == job_id,
            )
        )
    ).first()
    if delivery_id is None:
        delivery_pk = str(uuid.uuid4())
        session.add(TelegramAlertDelivery(
            id=delivery_pk,
            telegram_user_id=user_id,
            job_id=job_id,
            status="pending",
            attempts=0,
            created_at=now,
        ))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
    else:
        delivery_pk, prior_status, claim_until, prior_attempts = delivery_id
        if claim_until is not None and claim_until.tzinfo is None:
            claim_until = claim_until.replace(tzinfo=timezone.utc)
        if prior_status == "sending" and (claim_until is None or claim_until <= now):
            if prior_attempts >= MAX_ATTEMPTS:
                await session.execute(
                    update(TelegramAlertDelivery)
                    .where(TelegramAlertDelivery.id == delivery_pk, TelegramAlertDelivery.status == "sending")
                    .values(
                        status="dead",
                        claim_token=None,
                        claim_until=None,
                        last_error="claim_expired_after_max_attempts",
                        updated_at=now,
                    )
                )
                await session.commit()
                return None
            logger.warning("Recovering expired Telegram alert claim; prior delivery outcome may be ambiguous: delivery=%s", delivery_pk)

    claim_token = str(uuid.uuid4())
    claim = await session.execute(
        update(TelegramAlertDelivery)
        .where(
            TelegramAlertDelivery.id == delivery_pk,
            TelegramAlertDelivery.status.not_in(("sent", "dead")),
            TelegramAlertDelivery.attempts < MAX_ATTEMPTS,
            or_(
                TelegramAlertDelivery.status != "sending",
                TelegramAlertDelivery.claim_until.is_(None),
                TelegramAlertDelivery.claim_until <= now,
            ),
            or_(
                TelegramAlertDelivery.next_attempt_at.is_(None),
                TelegramAlertDelivery.next_attempt_at <= now,
            ),
        )
        .values(
            status="sending",
            attempts=TelegramAlertDelivery.attempts + 1,
            claim_token=claim_token,
            claim_until=now + CLAIM_LEASE,
            last_attempt_at=now,
            last_error=None,
            next_attempt_at=None,
            updated_at=now,
        )
    )
    if claim.rowcount != 1:
        await session.rollback()
        return None
    attempts = (
        await session.execute(
            select(TelegramAlertDelivery.attempts).where(
                TelegramAlertDelivery.id == delivery_pk,
                TelegramAlertDelivery.claim_token == claim_token,
            )
        )
    ).scalar_one()
    await session.commit()
    return delivery_pk, claim_token, attempts


async def _finish_delivery(session, delivery_id: str, claim_token: str, **values) -> bool:
    result = await session.execute(
        update(TelegramAlertDelivery)
        .where(
            TelegramAlertDelivery.id == delivery_id,
            TelegramAlertDelivery.claim_token == claim_token,
        )
        .values(claim_token=None, claim_until=None, updated_at=datetime.now(timezone.utc), **values)
    )
    await session.commit()
    return result.rowcount == 1


async def send_job_alerts(bot: Bot, db: Database) -> None:
    """Send alerts only when a Telegram user is linked to a candidate profile."""
    async with db.async_session_factory() as session:
        users = (await session.execute(
            select(
                TelegramUser.id,
                TelegramUser.chat_id,
                TelegramUser.candidate_id,
                TelegramUser.min_salary,
                TelegramUser.keywords,
                TelegramUser.exclude_keywords,
            ).where(TelegramUser.is_active.is_(True), TelegramUser.candidate_id.is_not(None))
        )).all()

        for user_id, chat_id, candidate_id, min_salary, keywords, exclude_keywords in users:
            rows = (await session.execute(
                select(Job, CandidateJobScore)
                .join(CandidateJobScore, CandidateJobScore.job_id == Job.id)
                .where(
                    CandidateJobScore.candidate_id == candidate_id,
                    CandidateJobScore.score >= 0.6,
                    Job.risk_score < 40,
                )
                .order_by(CandidateJobScore.score.desc())
                .limit(10)
            )).all()

            sent = 0
            for job, candidate_score in rows:
                if min_salary and (job.salary_min is None or job.salary_min < min_salary):
                    continue
                if not _matches_keywords(job, _json_list(keywords)) or _matches_exclude(job, _json_list(exclude_keywords)):
                    continue

                now = datetime.now(timezone.utc)
                claimed = await _claim_delivery(session, user_id, job.id, now)
                if not claimed:
                    continue
                delivery_id, claim_token, attempts = claimed

                try:
                    await bot.send_message(chat_id=chat_id, text=_format_job_alert(job, candidate_score.score))
                except Exception as exc:  # Telegram/network exceptions have varied provider subclasses.
                    permanent = isinstance(exc, (Forbidden, BadRequest))
                    uncertain = isinstance(exc, NetworkError)
                    if isinstance(exc, RetryAfter):
                        raw_delay = exc.retry_after
                        retry_delay = raw_delay.total_seconds() if isinstance(raw_delay, timedelta) else float(raw_delay)
                        delay = timedelta(seconds=max(1.0, retry_delay)) if attempts < MAX_ATTEMPTS else None
                    else:
                        delay = None if permanent or attempts >= MAX_ATTEMPTS else _retry_delay(attempts, uncertain=uncertain)
                    state = "dead" if delay is None else ("uncertain" if uncertain else "failed")
                    logger.warning(
                        "Telegram alert send failed: delivery=%s state=%s attempt=%d error=%s",
                        delivery_id, state, attempts, type(exc).__name__,
                    )
                    try:
                        await _finish_delivery(
                            session,
                            delivery_id,
                            claim_token,
                            status=state,
                            last_error=type(exc).__name__,
                            next_attempt_at=now + delay if delay else None,
                        )
                    except Exception:
                        await session.rollback()
                        logger.exception("Could not persist Telegram alert failure state: delivery=%s", delivery_id)
                    continue

                try:
                    recorded = await _finish_delivery(
                        session,
                        delivery_id,
                        claim_token,
                        status="sent",
                        last_error=None,
                        next_attempt_at=None,
                    )
                    if recorded:
                        sent += 1
                    else:
                        logger.warning(
                            "Telegram accepted alert but its claim was no longer owned; delivery state is ambiguous: delivery=%s",
                            delivery_id,
                        )
                except Exception:
                    await session.rollback()
                    retry_at = datetime.now(timezone.utc) + _retry_delay(attempts, uncertain=True)
                    logger.exception(
                        "Telegram accepted alert but success persistence failed; later retry may duplicate: delivery=%s",
                        delivery_id,
                    )
                    try:
                        await _finish_delivery(
                            session,
                            delivery_id,
                            claim_token,
                            status="uncertain",
                            last_error="success_persistence_failed",
                            next_attempt_at=retry_at,
                        )
                    except Exception:
                        await session.rollback()
                        logger.exception("Could not persist ambiguous Telegram alert state: delivery=%s", delivery_id)

            if sent:
                await session.execute(
                    update(TelegramUser)
                    .where(TelegramUser.id == user_id)
                    .values(last_notified_at=datetime.now(timezone.utc))
                )
                await session.commit()
