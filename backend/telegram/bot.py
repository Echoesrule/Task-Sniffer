"""Telegram bot application setup."""

import logging
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from backend.config import get_settings
from backend.telegram.handlers import (
    start,
    stop,
    settings_cmd,
    set_keywords,
    set_exclude,
    set_salary,
    search,
    stats,
    sources,
    apply_job,
    my_applications,
    update_status,
    top_jobs,
)

logger = logging.getLogger(__name__)


def create_bot_app() -> Application:
    """Create and configure the Telegram bot application."""
    settings = get_settings()
    token = settings.telegram_bot_token

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    application = (
        Application.builder()
        .token(token)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("settings", settings_cmd))
    application.add_handler(CommandHandler("set_keywords", set_keywords))
    application.add_handler(CommandHandler("set_exclude", set_exclude))
    application.add_handler(CommandHandler("set_salary", set_salary))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("sources", sources))
    application.add_handler(CommandHandler("apply", apply_job))
    application.add_handler(CommandHandler("my_applications", my_applications))
    application.add_handler(CommandHandler("update_status", update_status))
    application.add_handler(CommandHandler("top", top_jobs))

    logger.info("Telegram bot created successfully")
    return application
