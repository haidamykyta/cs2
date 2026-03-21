"""
CS2 Analytics Bot — Main Runner

Starts Telegram bot + scheduler together.

Usage:
    # Step 1 (first time only): collect historical data
    python data_collector.py bootstrap 12

    # Step 2 (first time only): train models
    python model.py train

    # Step 3: run the bot
    python main.py

    # Optional: backtest
    python backtester.py 3
"""

import asyncio
import logging

import database as db
from telegram_bot import bot, dp, set_commands
from scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    db.init_db()
    await set_commands()

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started (%d jobs)", len(scheduler.get_jobs()))

    logger.info("Starting CS2 Analytics Bot...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
