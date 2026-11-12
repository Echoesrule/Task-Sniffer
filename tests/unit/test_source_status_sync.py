from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.api import app as api_app
from backend.api.routes import sources as sources_api
from backend.models.database import Database, Source
from backend.sources.models import AccessMethod, PermissionStatus, SourceConfig, SourceStatus
from backend.sources.registry import SourceRegistry


def _run(coro):
    return asyncio.run(coro)


def test_startup_sync_overwrites_stale_enabled_but_preserves_job_history(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'sync.db'}")

    async def scenario():
        await db.init_db()
        registry = SourceRegistry(overrides={})
        registry.register(SourceConfig(
            name="review-source", access_method=AccessMethod.HTML,
            permission_status=PermissionStatus.REVIEW,
            source_status=SourceStatus.DISABLED,
        ))
        async with db.async_session_factory() as session:
            row = Source(name="review-source", url="https://review.example", enabled=True, jobs_found=7)
            session.add(row)
            await session.commit()
            await api_app.sync_registry_sources(session, registry)
            refreshed = (
                await session.execute(select(Source).where(Source.name == "review-source"))
            ).scalar_one()
            result = (refreshed.enabled, refreshed.jobs_found, refreshed.url)
        await db.close()
        return result

    result = _run(scenario())
    assert result == (False, 7, "https://review.example")


def test_source_api_uses_registry_eligibility_not_stale_database_flag(tmp_path, monkeypatch):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    registry = SourceRegistry(overrides={})
    registry.register(SourceConfig(
        name="blocked", access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.RESTRICTED,
    ))
    registry.register(SourceConfig(
        name="active", access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED,
    ))
    monkeypatch.setattr(sources_api, "default_registry", registry)

    async def scenario():
        await db.init_db()
        async with db.async_session_factory() as session:
            session.add_all([
                Source(name="blocked", url="https://blocked.example", enabled=True),
                Source(name="active", url="https://active.example", enabled=False),
            ])
            await session.commit()
            response = await sources_api.list_sources(
                session, current_user={"role": "admin", "user_id": "test"}
            )
            result = {source.name: source for source in response.sources}
        await db.close()
        return result

    rows = _run(scenario())
    assert rows["blocked"].enabled is False
    assert rows["blocked"].crawlable is False
    assert rows["active"].enabled is True
    assert rows["active"].crawlable is True
