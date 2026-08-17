"""Work Hunter Bot - Main entry point."""

import asyncio
import logging
import signal
import sys

import httpx

from src.config import config
from src.database.models import Database
from src.bot.telegram_bot import create_bot, post_init, post_shutdown
from src.scheduler.jobs import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("work_hunter.log"),
    ],
)
logger = logging.getLogger(__name__)

db = Database()


async def clear_telegram_state(token: str) -> None:
    """Clear any existing webhook and pending updates."""
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true")
        await client.get(f"https://api.telegram.org/bot{token}/getUpdates?offset=-1")
    logger.info("Cleared Telegram state")


async def main() -> None:
    """Main function to run the bot and scheduler."""
    logger.info("Starting Work Hunter Bot...")

    await clear_telegram_state(config.telegram_token)

    bot_app = create_bot()
    scheduler = create_scheduler()
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await post_init(bot_app)
    scheduler.start()

    logger.info("Bot and scheduler started. Press Ctrl+C to stop.")

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

    try:
        await shutdown_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Shutting down...")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        await post_shutdown(bot_app)
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
