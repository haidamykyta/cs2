"""
APScheduler-based job scheduler for CS2 bot.

Jobs:
  - 07:00 UTC daily  → send today's matches to Telegram
  - every 30 min     → update HLTV data (upcoming + recent results)
  - every 6 hours    → refresh Glicko-2 ratings
  - weekly Sunday    → retrain models

Run this alongside telegram_bot.py, or integrate into main runner.
"""

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


async def _job_daily_matches():
    """07:00 UTC: push today's match predictions to Telegram."""
    try:
        from telegram_bot import send_daily_matches
        await send_daily_matches()
        logger.info("Daily matches sent.")
    except Exception as e:
        logger.error("daily_matches job failed: %s", e)


async def _job_update_data():
    """Every 30 min: pull latest HLTV results + upcoming matches."""
    try:
        import data_collector
        await data_collector.update_live()
        logger.info("HLTV data updated.")
    except Exception as e:
        logger.error("update_data job failed: %s", e)


async def _job_refresh_glicko():
    """Every 6 hours: recompute Glicko-2 ratings."""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        from model import _refresh_glicko_ratings
        await loop.run_in_executor(None, _refresh_glicko_ratings)
        logger.info("Glicko-2 ratings refreshed.")
    except Exception as e:
        logger.error("refresh_glicko job failed: %s", e)


async def _job_retrain_model():
    """Weekly: retrain models with latest data."""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        from model import train_all
        meta = await loop.run_in_executor(None, train_all)
        logger.info(
            "Models retrained. Match CV: %.1f%%, Map CV: %.1f%%",
            meta["match"]["cv_accuracy_mean"] * 100,
            meta["map"]["cv_accuracy_mean"] * 100,
        )
    except Exception as e:
        logger.error("retrain_model job failed: %s", e)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Daily match digest at 07:00 UTC
    scheduler.add_job(
        _job_daily_matches,
        CronTrigger(hour=7, minute=0),
        id="daily_matches",
        name="Daily match predictions",
        replace_existing=True,
    )

    # HLTV data update every 30 minutes
    scheduler.add_job(
        _job_update_data,
        IntervalTrigger(minutes=30),
        id="update_data",
        name="HLTV data update",
        replace_existing=True,
    )

    # Glicko-2 refresh every 6 hours
    scheduler.add_job(
        _job_refresh_glicko,
        IntervalTrigger(hours=6),
        id="refresh_glicko",
        name="Glicko-2 rating refresh",
        replace_existing=True,
    )

    # Weekly model retraining (Sunday 03:00 UTC)
    scheduler.add_job(
        _job_retrain_model,
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="retrain_model",
        name="Weekly model retraining",
        replace_existing=True,
    )

    return scheduler
