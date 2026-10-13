"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func as sa_func

from backend.api.deps import set_db
from backend.api.routes import applications, analytics, candidates, jobs, sources
from backend.config import get_settings
from backend.models.database import Database, Source

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    db = Database(settings.database_url)
    await db.init_db()
    set_db(db)

    async with db.async_session_factory() as session:
        # Sync audited registry -> DB rows (upsert, preserving any manual state)
        from backend.sources.registry import default_registry

        existing = {s.name: s for s in (await session.execute(select(Source))).scalars().all()}
        for config in default_registry.all():
            row = existing.get(config.name)
            if row is None:
                row = Source(
                    name=config.name,
                    url=config.url or f"https://{config.name}",
                    tier=config.tier,
                    enabled=config.source_status.value != "DISABLED",
                    country_focus=config.country_focus,
                    access_method=config.access_method.value,
                    permission_status=config.permission_status.value,
                    robots_status=config.robots_status.value,
                    terms_status=config.terms_status.value,
                    provenance=config.provenance.value,
                    rate_limit=config.rate_limit,
                    requires_auth=config.requires_auth,
                    last_audited=config.last_audited,
                )
                session.add(row)
            else:
                row.access_method = config.access_method.value
                row.permission_status = config.permission_status.value
                row.robots_status = config.robots_status.value
                row.terms_status = config.terms_status.value
                row.provenance = config.provenance.value
                row.rate_limit = config.rate_limit
                row.requires_auth = config.requires_auth
                row.last_audited = config.last_audited
        await session.commit()

    # Start Telegram bot
    telegram_task = None
    if settings.telegram_bot_token:
        try:
            from backend.telegram.bot import create_bot_app
            from backend.telegram.handlers import set_db as set_tg_db
            from backend.telegram.notify import send_job_alerts

            set_tg_db(db)
            tg_app = create_bot_app()
            await tg_app.initialize()
            await tg_app.start()
            await tg_app.updater.start_polling()
            logger.info("Telegram bot started")

            # Periodic alert sender
            async def alert_loop():
                while True:
                    try:
                        await send_job_alerts(tg_app.bot, db)
                    except Exception as e:
                        logger.error(f"Alert loop error: {e}")
                    await asyncio.sleep(300)  # every 5 minutes

            telegram_task = asyncio.create_task(alert_loop())
        except Exception as e:
            logger.warning(f"Telegram bot failed to start: {e}")

    yield

    # Shutdown
    if telegram_task:
        telegram_task.cancel()
        try:
            await telegram_task
        except asyncio.CancelledError:
            pass

    if settings.telegram_bot_token:
        try:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
            logger.info("Telegram bot stopped")
        except Exception:
            pass

    await db.close()


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = FastAPI(
        title="Work-Bot Hunter",
        version="0.1.0",
        description="Job intelligence platform API",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
    app.include_router(sources.router, prefix="/sources", tags=["sources"])
    app.include_router(candidates.router, prefix="/candidate", tags=["candidates"])
    app.include_router(applications.router, prefix="/applications", tags=["applications"])
    app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
