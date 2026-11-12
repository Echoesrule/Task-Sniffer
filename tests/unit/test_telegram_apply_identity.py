"""Regression tests for Telegram /apply candidate identity (Phase 4)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.models.database import (
    Database,
    TelegramLinkCode,
    TelegramUser,
    User,
    Candidate,
    Job,
    Application,
)
from backend.security import (
    generate_telegram_link_code,
    hash_password,
    hash_telegram_link_code,
)
from backend.telegram import handlers


class _Msg:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text: str):
        self.replies.append(text)


class _Update:
    def __init__(self, chat_id: str = "12345", username: str = "alice"):
        self.effective_chat = SimpleNamespace(id=int(chat_id))
        self.effective_user = SimpleNamespace(username=username, first_name="Alice")
        self.message = _Msg()


class _Context:
    def __init__(self, args=None):
        self.args = args or []


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(tmp_path):
    d = Database(f"sqlite+aiosqlite:///{tmp_path / 'tg4.db'}")
    _run(d.init_db())
    try:
        yield d
    finally:
        _run(d.close())


@pytest.fixture(autouse=True)
def _set_db(db):
    original = handlers._db
    handlers.set_db(db)
    try:
        yield
    finally:
        handlers._db = original


def _seed_user(db: Database):
    async def _do():
        async with db.async_session_factory() as session:
            u = User(email="alice@example.com", hashed_password=hash_password("pass123"), is_active=True)
            session.add(u)
            await session.flush()
            c = Candidate(user_id=u.id, name="Alice", email="alice@example.com")
            session.add(c)
            await session.flush()
            tg = TelegramUser(chat_id="12345", username="alice")
            session.add(tg)
            await session.flush()
            job = Job(
                id="job1",
                source_id=1,
                source_job_id="job1",
                title="Backend Engineer",
                company="Acme",
                description="Python and FastAPI",
                source_url="https://example.com/job1",
                match_score=0.8,
                risk_score=0.1,
                status="discovered",
            )
            session.add(job)
            await session.commit()
            return {"user_id": u.id, "candidate_id": c.id, "job_id": job.id}
    return _run(_do())


def _issue_link_code(db: Database, user_id: str) -> str:
    async def _do():
        async with db.async_session_factory() as session:
            code = generate_telegram_link_code()
            session.add(
                TelegramLinkCode(
                    user_id=user_id,
                    code_hash=hash_telegram_link_code(code),
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
            )
            await session.commit()
            return code
    return _run(_do())


def test_link_rejects_invalid_code(db):
    _seed_user(db)
    upd = _Update(chat_id="12345")
    ctx = _Context(["WRONGCODE"])
    _run(handlers.link_account(upd, ctx))
    assert upd.message.replies
    assert "Invalid or expired" in upd.message.replies[-1]


def test_link_never_accepts_passwords(db):
    _seed_user(db)
    upd = _Update(chat_id="12345")
    ctx = _Context(["alice@example.com", "pass123"])
    _run(handlers.link_account(upd, ctx))
    assert upd.message.replies
    assert "Passwords are never accepted" in upd.message.replies[-1]


def test_link_success_creates_relationship(db):
    data = _seed_user(db)
    code = _issue_link_code(db, data["user_id"])
    upd = _Update(chat_id="12345")
    ctx = _Context([code])
    _run(handlers.link_account(upd, ctx))
    assert upd.message.replies
    assert "Linked" in upd.message.replies[-1]

    async def _check():
        async with db.async_session_factory() as session:
            tg = (await session.execute(select(TelegramUser).where(TelegramUser.chat_id == "12345"))).scalars().first()
            assert tg.candidate_id == data["candidate_id"]
    _run(_check())


def test_link_code_is_single_use(db):
    data = _seed_user(db)
    code = _issue_link_code(db, data["user_id"])
    _run(handlers.link_account(_Update(chat_id="12345"), _Context([code])))
    _run(handlers.unlink_account(_Update(chat_id="12345"), _Context([])))

    replay = _Update(chat_id="12345")
    _run(handlers.link_account(replay, _Context([code])))
    assert "Invalid or expired" in replay.message.replies[-1]


def test_apply_refuses_unlinked(db):
    _seed_user(db)  # linked not done
    upd = _Update(chat_id="12345")
    ctx = _Context(["job1"])
    _run(handlers.apply_job(upd, ctx))
    assert upd.message.replies
    assert "link" in upd.message.replies[-1].lower()


def test_apply_tracks_to_linked_candidate_only(db):
    data = _seed_user(db)
    _run(handlers.link_account(_Update(chat_id="12345"), _Context([_issue_link_code(db, data["user_id"])])))

    upd = _Update(chat_id="12345")
    ctx = _Context(["job1"])
    _run(handlers.apply_job(upd, ctx))
    assert "Application tracked" in upd.message.replies[-1]

    async def _check():
        async with db.async_session_factory() as session:
            apps = (await session.execute(select(Application))).scalars().all()
            assert len(apps) == 1
            assert apps[0].candidate_id == data["candidate_id"]
            assert apps[0].candidate_id != (await session.execute(select(TelegramUser).where(TelegramUser.chat_id == "12345"))).scalars().first().id
    _run(_check())


def test_unlink_revokes_access(db):
    data = _seed_user(db)
    _run(handlers.link_account(_Update(chat_id="12345"), _Context([_issue_link_code(db, data["user_id"])])))
    _run(handlers.unlink_account(_Update(chat_id="12345"), _Context([])))

    upd = _Update(chat_id="12345")
    ctx = _Context(["job1"])
    _run(handlers.apply_job(upd, ctx))
    assert "link" in upd.message.replies[-1].lower()


def test_my_applications_scoped_to_linked_candidate(db):
    data = _seed_user(db)
    _run(handlers.link_account(_Update(chat_id="12345"), _Context([_issue_link_code(db, data["user_id"])])))
    _run(handlers.apply_job(_Update(chat_id="12345"), _Context(["job1"])))

    async def _add_other():
        async with db.async_session_factory() as session:
            other = Candidate(user_id="other", name="X", email="x@x.com")
            session.add(other)
            await session.flush()
            app = Application(candidate_id=other.id, job_id="job1", status="shortlisted")
            session.add(app)
            await session.commit()
    _run(_add_other())

    upd = _Update(chat_id="12345")
    _run(handlers.my_applications(upd, _Context([])))
    text = "\n".join(upd.message.replies)
    assert "Backend Engineer" in text
    assert "Your Applications" in text
    # must not list the other candidate's app as if it belongs to linked user (scoped)
    assert text.count("App ID") == 1


def test_global_telegram_commands_require_admin_chat(db, monkeypatch):
    _seed_user(db)
    denied = _Update(chat_id="12345")
    _run(handlers.stats(denied, _Context([])))
    _run(handlers.sources(denied, _Context([])))
    assert denied.message.replies == ["Administrator access required."] * 2

    monkeypatch.setattr(
        handlers,
        "get_settings",
        lambda: SimpleNamespace(telegram_admin_chat_id_set={"12345"}),
    )
    allowed = _Update(chat_id="12345")
    _run(handlers.stats(allowed, _Context([])))
    _run(handlers.sources(allowed, _Context([])))
    assert "Task Sniffer Stats" in allowed.message.replies[0]
    assert "No sources configured" in allowed.message.replies[1]
