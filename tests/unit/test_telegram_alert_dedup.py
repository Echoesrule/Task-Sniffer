"""Per-candidate Telegram delivery claims, retries and ambiguous-send behavior."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from backend.models.database import (
    Candidate,
    CandidateJobScore,
    Database,
    Job,
    Source,
    TelegramAlertDelivery,
    TelegramUser,
    User,
)
from backend.telegram import notify
from backend.telegram.notify import send_job_alerts


class _Bot:
    def __init__(self, failures: int = 0, delay: float = 0):
        self.failures = failures
        self.delay = delay
        self.sent: list[str] = []

    async def send_message(self, *, chat_id: str, text: str):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("temporary Telegram failure")
        self.sent.append(chat_id)


def _run(coro):
    return asyncio.run(coro)


def _make_db(path):
    db = Database(f"sqlite+aiosqlite:///{path}")
    _run(db.init_db())

    async def seed():
        async with db.async_session_factory() as session:
            source = Source(name="fixture", url="https://fixture.example")
            web_users = [
                User(email="one@example.com", hashed_password="x"),
                User(email="two@example.com", hashed_password="x"),
            ]
            session.add_all([source, *web_users])
            await session.flush()
            candidates = [
                Candidate(user_id=web_users[0].id, name="One", email=web_users[0].email),
                Candidate(user_id=web_users[1].id, name="Two", email=web_users[1].email),
            ]
            session.add_all(candidates)
            await session.flush()
            telegram_users = [
                TelegramUser(chat_id="101", is_active=True, candidate_id=candidates[0].id),
                TelegramUser(chat_id="202", is_active=True, candidate_id=candidates[1].id),
            ]
            job = Job(source_id=source.id, source_job_id="job-1", title="Engineer", company="Acme", risk_score=10)
            session.add_all([*telegram_users, job])
            await session.flush()
            session.add_all([
                CandidateJobScore(candidate_id=candidates[0].id, job_id=job.id, score=0.8, breakdown="{}"),
                CandidateJobScore(candidate_id=candidates[1].id, job_id=job.id, score=0.75, breakdown="{}"),
            ])
            await session.commit()
    _run(seed())
    return db


def test_successful_user_job_alert_is_sent_once_per_user(tmp_path):
    db = _make_db(tmp_path / "alert_dedup.db")
    bot = _Bot()
    try:
        _run(send_job_alerts(bot, db))
        _run(send_job_alerts(bot, db))
        assert sorted(bot.sent) == ["101", "202"]

        async def verify():
            async with db.async_session_factory() as session:
                records = (await session.execute(select(TelegramAlertDelivery))).scalars().all()
                assert len(records) == 2
                assert all(record.status == "sent" and record.attempts == 1 for record in records)
                assert all(record.claim_token is None and record.claim_until is None for record in records)
        _run(verify())
    finally:
        _run(db.close())


def test_failed_alert_can_retry_after_backoff_and_becomes_deduplicated(tmp_path):
    db = _make_db(tmp_path / "alert_retry.db")
    bot = _Bot(failures=1)
    try:
        _run(send_job_alerts(bot, db))

        async def release_backoff():
            async with db.async_session_factory() as session:
                await session.execute(update(TelegramAlertDelivery).where(
                    TelegramAlertDelivery.status == "failed"
                ).values(next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
                await session.commit()
        _run(release_backoff())
        _run(send_job_alerts(bot, db))
        _run(send_job_alerts(bot, db))
        assert sorted(bot.sent) == ["101", "202"]

        async def verify():
            async with db.async_session_factory() as session:
                records = (await session.execute(select(TelegramAlertDelivery))).scalars().all()
                assert len(records) == 2
                assert all(record.status == "sent" for record in records)
                assert sorted(record.attempts for record in records) == [1, 2]
        _run(verify())
    finally:
        _run(db.close())


def test_concurrent_workers_do_not_claim_the_same_alert(tmp_path):
    db = _make_db(tmp_path / "alert_concurrent.db")
    bot = _Bot(delay=0.05)
    try:
        async def run_workers():
            await asyncio.gather(send_job_alerts(bot, db), send_job_alerts(bot, db))
        _run(run_workers())
        assert sorted(bot.sent) == ["101", "202"]
    finally:
        _run(db.close())


def test_expired_sending_claim_is_recovered(tmp_path):
    db = _make_db(tmp_path / "alert_expired_claim.db")
    bot = _Bot()

    async def expire_first_users_claim():
        async with db.async_session_factory() as session:
            first_user = (await session.execute(
                select(TelegramUser).where(TelegramUser.chat_id == "101")
            )).scalar_one()
            job = (await session.execute(select(Job))).scalars().first()
            session.add(TelegramAlertDelivery(
                telegram_user_id=first_user.id,
                job_id=job.id,
                status="sending",
                attempts=1,
                claim_token="old-claim",
                claim_until=datetime.now(timezone.utc) - timedelta(minutes=1),
            ))
            await session.commit()

    try:
        _run(expire_first_users_claim())
        _run(send_job_alerts(bot, db))
        assert sorted(bot.sent) == ["101", "202"]

        async def verify():
            async with db.async_session_factory() as session:
                records = (await session.execute(
                    select(TelegramAlertDelivery, TelegramUser.chat_id)
                    .join(TelegramUser, TelegramUser.id == TelegramAlertDelivery.telegram_user_id)
                )).all()
                first = next(record for record, chat_id in records if chat_id == "101")
                assert first.status == "sent"
                assert first.attempts == 2
        _run(verify())
    finally:
        _run(db.close())


def test_success_persistence_failure_records_ambiguous_delivery_and_retry_can_duplicate(tmp_path, monkeypatch):
    db = _make_db(tmp_path / "alert_ambiguous.db")
    bot = _Bot()
    real_finish = notify._finish_delivery
    failed_once = False

    async def fail_first_success_commit(session, delivery_id, claim_token, **values):
        nonlocal failed_once
        if values.get("status") == "sent" and not failed_once:
            failed_once = True
            raise RuntimeError("simulated database failure after provider accepted the send")
        return await real_finish(session, delivery_id, claim_token, **values)

    monkeypatch.setattr(notify, "_finish_delivery", fail_first_success_commit)
    try:
        _run(send_job_alerts(bot, db))
        assert len(bot.sent) == 2

        async def inspect_ambiguous_and_release():
            async with db.async_session_factory() as session:
                records = (await session.execute(select(TelegramAlertDelivery))).scalars().all()
                ambiguous = next(record for record in records if record.status == "uncertain")
                assert ambiguous.last_error == "success_persistence_failed"
                await session.execute(update(TelegramAlertDelivery).where(
                    TelegramAlertDelivery.id == ambiguous.id
                ).values(next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
                await session.commit()
                return ambiguous.telegram_user_id

        _run(inspect_ambiguous_and_release())
        _run(send_job_alerts(bot, db))
        assert len(bot.sent) == 3  # duplicate is the documented at-least-once trade-off
    finally:
        _run(db.close())
