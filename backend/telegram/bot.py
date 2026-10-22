"""Telegram bot application setup."""

import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    ConversationHandler,
    filters,
)
from telegram.ext import PicklePersistence
import os

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
    link_account,
    unlink_account,
    menu_callback,
    profile_start,
    profile_handle,
    PROFILE_WAIT,
)

logger = logging.getLogger(__name__)


def create_bot_app() -> Application:
    """Create and configure the Telegram bot application."""
    settings = get_settings()
    token = settings.telegram_bot_token

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    persistence_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "tg_persistence.pkl")
    os.makedirs(os.path.dirname(persistence_path), exist_ok=True)
    persistence = PicklePersistence(filepath=persistence_path)

    application = (
        Application.builder()
        .token(token)
        .persistence(persistence)
        .build()
    )

    profile_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(profile_start, pattern=r"^profile:start$")],
        states={
            PROFILE_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_handle)],
        },
        fallbacks=[CommandHandler("cancel", start)],
        name="profile_conv",
        persistent=True,
    )

    application.add_handler(profile_conv)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("settings", settings_cmd))
    application.add_handler(CommandHandler("set_keywords", set_keywords))
    application.add_handler(CommandHandler("set_exclude", set_exclude))
    application.add_handler(CommandHandler("set_salary", set_salary))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("sources", sources))
    application.add_handler(CommandHandler("link", link_account))
    application.add_handler(CommandHandler("unlink", unlink_account))
    application.add_handler(CommandHandler("apply", apply_job))
    application.add_handler(CommandHandler("my_applications", my_applications))
    application.add_handler(CommandHandler("update_status", update_status))
    application.add_handler(CommandHandler("top", top_jobs))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))

    logger.info("Telegram bot created successfully")
    return application
