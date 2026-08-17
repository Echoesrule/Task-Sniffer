"""Telegram bot setup and integration."""

import logging
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import config
from src.bot.handlers import (
    start,
    stop,
    settings,
    set_keywords,
    set_exclude,
    set_salary,
    search,
    stats,
    sources,
    apply_job,
    my_applications,
    update_status,
)

logger = logging.getLogger(__name__)


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    token = config.telegram_token

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in config")

    application = (
        Application.builder()
        .token(token)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("set_keywords", set_keywords))
    application.add_handler(CommandHandler("set_exclude", set_exclude))
    application.add_handler(CommandHandler("set_salary", set_salary))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("sources", sources))
    application.add_handler(CommandHandler("apply", apply_job))
    application.add_handler(CommandHandler("my_applications", my_applications))
    application.add_handler(CommandHandler("update_status", update_status))

    logger.info("Telegram bot created successfully")
    return application


async def post_init(application: Application) -> None:
    """Post-init hook for the bot application."""
    logger.info("Bot initialized, ready to receive commands")


async def post_shutdown(application: Application) -> None:
    """Post-shutdown hook for the bot application."""
    logger.info("Bot shutting down")
