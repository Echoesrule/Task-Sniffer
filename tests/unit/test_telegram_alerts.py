"""Phase 3: Telegram alert idempotency, links, and bounded retries.

All sends use an in-memory fake bot - no live Telegram message is ever sent.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.models.database import (
    Database,
    Job,
    Source,
    TelegramAlert,
    TelegramUser,
)
from backend.telegram.notify import DEFAULT_MAX_ATTEMPTS, MAX_MESSAGE_LENGTH, send_job_alerts


def _run(coro):
    return asyncio.run(coro)


class FakeBot:
    def __init__(self, fail_chat_ids=()):
        self.sent: list[tuple[str, str]] = []
        self.calls: list[dict] = []
        self._fail = set(fail_chat_ids)

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append({"chat_id": chat_id, "text": text, "kwargs": kwargs})
        if chat_id in self._fail:
            raise RuntimeError("send failed")
        self.sent.append((chat_id, text))


class FlakyBot(FakeBot):
    """Fails the first send, then succeeds."""

    def __init__(self):
        super().__init__()
        self._n = 0

    async def send_message(self, chat_id, text, **kwargs):
        self._n += 1
        self.calls.append({"chat_id": chat_id, "text": text, "kwargs": kwargs})
        if self._n == 1:
            raise RuntimeError("transient failure")
        self.sent.append((chat_id, text))


async def _add_user(session, chat_id="1001", **kw):
    kw.setdefault("is_active", True)
    user = TelegramUser(chat_id=chat_id, **kw)
    session.add(user)
    await session.flush()
    return user


async def _add_job(session, source_id, **overrides):
    values = {
        "source_id": source_id,
        "source_job_id": f"job-{overrides.get('title', 'x')}",
        "title": "Backend Engineer",
        "company": "Acme",
        "description": "Python and SQL",
        "match_score": 0.8,
        "risk_score": 0.0,
        "url_status": "VALID",
        "source_url": "https://acme.example.com/jobs/1",
    }
    values.update(overrides)
    job = Job(**values)
    session.add(job)
    await session.flush()
    return job


async def _seed(db, *, users=1, jobs=1, job_overrides=None):
    async with db.async_session_factory() as session:
        src = Source(name="acme", url="https://acme.example.com")
        session.add(src)
        await session.flush()
        for i in range(users):
            await _add_user(session, chat_id=str(1000 + i))
        created = []
        for i in range(jobs):
            overrides = dict(job_overrides or {})
            overrides.setdefault("source_job_id", f"job-{i}")
            created.append(await _add_job(session, src.id, **overrides))
        await session.commit()
        return created


def test_alert_sent_once_and_not_resent(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a1.db'}")
    _run(db.init_db())

    async def scenario():
        await _seed(db)
        bot = FakeBot()
        first = await send_job_alerts(bot, db)
        second = await send_job_alerts(bot, db)
        async with db.async_session_factory() as s:
            alerts = (await s.execute(select(TelegramAlert))).scalars().all()
        return first, second, bot, alerts

    first, second, bot, alerts = _run(scenario())
    _run(db.close())

    assert first == 1
    assert second == 0
    assert len(bot.sent) == 1
    assert len(alerts) == 1
    assert alerts[0].status == "SENT"
    assert alerts[0].sent_at is not None


def test_each_user_receives_job_once(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a2.db'}")
    _run(db.init_db())

    async def scenario():
        await _seed(db, users=2)
        bot = FakeBot()
        first = await send_job_alerts(bot, db)
        second = await send_job_alerts(bot, db)
        return first, second, bot

    first, second, bot = _run(scenario())
    _run(db.close())

    assert first == 2
    assert second == 0
    assert {chat for chat, _ in bot.sent} == {"1000", "1001"}


def test_failed_send_retried_then_succeeds(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a3.db'}")
    _run(db.init_db())

    async def scenario():
        await _seed(db)
        bot = FlakyBot()
        first = await send_job_alerts(bot, db)
        second = await send_job_alerts(bot, db)
        async with db.async_session_factory() as s:
            alert = (await s.execute(select(TelegramAlert))).scalars().one()
        return first, second, bot, alert

    first, second, bot, alert = _run(scenario())
    _run(db.close())

    assert first == 0
    assert second == 1
    assert alert.status == "SENT"
    assert alert.attempts == 2


def test_retries_are_bounded(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a4.db'}")
    _run(db.init_db())

    async def scenario():
        await _seed(db)
        bot = FakeBot(fail_chat_ids={"1000"})
        for _ in range(DEFAULT_MAX_ATTEMPTS + 2):
            await send_job_alerts(bot, db)
        async with db.async_session_factory() as s:
            alert = (await s.execute(select(TelegramAlert))).scalars().one()
        return bot, alert

    bot, alert = _run(scenario())
    _run(db.close())

    # exactly max_attempts sends were attempted, then abandoned
    assert len(bot.calls) == DEFAULT_MAX_ATTEMPTS
    assert alert.status == "FAILED"
    assert alert.attempts == DEFAULT_MAX_ATTEMPTS
    assert alert.last_error


def test_missing_link_uses_fallback(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a5.db'}")
    _run(db.init_db())

    async def scenario():
        # not VALID -> no link even though URLs are present
        await _seed(
            db,
            job_overrides={
                "url_status": "NEEDS_REVIEW",
                "application_url": "https://apply.example.com/1",
            },
        )
        bot = FakeBot()
        await send_job_alerts(bot, db)
        return bot

    bot = _run(scenario())
    _run(db.close())

    assert len(bot.sent) == 1
    assert "no verified link available" in bot.sent[0][1]


def test_link_prefers_application_then_canonical(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a6.db'}")
    _run(db.init_db())

    async def scenario():
        async with db.async_session_factory() as s:
            src = Source(name="acme", url="https://acme.example.com")
            s.add(src)
            await s.flush()
            await _add_user(s, chat_id="1000")
            await _add_job(
                s, src.id, source_job_id="with-app",
                application_url="https://apply.example.com/1",
                canonical_url="https://acme.example.com/jobs/1",
            )
            await _add_job(
                s, src.id, source_job_id="no-app", title="Data Analyst",
                application_url=None,
                canonical_url="https://acme.example.com/jobs/2",
            )
            await s.commit()
        bot = FakeBot()
        await send_job_alerts(bot, db)
        return bot

    bot = _run(scenario())
    _run(db.close())

    texts = "\n".join(t for _, t in bot.sent)
    assert "https://apply.example.com/1" in texts
    assert "https://acme.example.com/jobs/2" in texts


def test_unsafe_link_is_rejected(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a7.db'}")
    _run(db.init_db())

    async def scenario():
        await _seed(
            db,
            job_overrides={
                "url_status": "VALID",
                "application_url": "http://127.0.0.1/internal",
                "source_url": None,
            },
        )
        bot = FakeBot()
        await send_job_alerts(bot, db)
        return bot

    bot = _run(scenario())
    _run(db.close())

    assert "127.0.0.1" not in bot.sent[0][1]
    assert "no verified link available" in bot.sent[0][1]


def test_long_message_is_truncated(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a8.db'}")
    _run(db.init_db())

    async def scenario():
        await _seed(db, job_overrides={"title": "X" * 6000})
        bot = FakeBot()
        await send_job_alerts(bot, db)
        return bot

    bot = _run(scenario())
    _run(db.close())

    assert len(bot.sent[0][1]) <= MAX_MESSAGE_LENGTH


def test_untrusted_markup_sent_as_plain_text(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a9.db'}")
    _run(db.init_db())

    async def scenario():
        await _seed(db, job_overrides={"title": "<b>Evil</b> & Co"})
        bot = FakeBot()
        await send_job_alerts(bot, db)
        return bot

    bot = _run(scenario())
    _run(db.close())

    # no HTML parse mode -> markup cannot be interpreted
    assert bot.calls[0]["kwargs"].get("parse_mode") is None
    assert "<b>Evil</b> & Co" in bot.sent[0][1]


def test_no_active_users_sends_nothing(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path/'a10.db'}")
    _run(db.init_db())

    async def scenario():
        async with db.async_session_factory() as s:
            src = Source(name="acme", url="https://acme.example.com")
            s.add(src)
            await s.flush()
            await _add_user(s, chat_id="1000", is_active=False)
            await _add_job(s, src.id)
            await s.commit()
        bot = FakeBot()
        sent = await send_job_alerts(bot, db)
        return sent, bot

    sent, bot = _run(scenario())
    _run(db.close())

    assert sent == 0
    assert bot.calls == []
