"""In-process scheduler (ADR-0008): the daily Fetch Run on the kept-warm instance."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.db import get_sessionmaker

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def daily_fetch() -> None:
    from app.services.fetching import Fetcher

    await Fetcher(get_sessionmaker()).run_all(trigger="schedule")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        settings = get_settings()
        _scheduler = AsyncIOScheduler(timezone="UTC")
        _scheduler.add_job(
            daily_fetch,
            CronTrigger(hour=settings.fetch_hour_utc, minute=settings.fetch_minute_utc),
            id="daily_fetch",
            # A run missed while the host slept still happens once it wakes (FR-B3 AC1).
            misfire_grace_time=12 * 3600,
            coalesce=True,
            max_instances=1,
        )
        _scheduler.start()
        logger.info(
            "Scheduler started: daily fetch at %02d:%02d UTC",
            settings.fetch_hour_utc,
            settings.fetch_minute_utc,
        )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
