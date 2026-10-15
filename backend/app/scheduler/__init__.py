"""In-process scheduler (ADR-0008): the daily Fetch Run on the kept-warm instance."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.db import get_sessionmaker

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def daily_fetch() -> None:
    from app.services.pipeline import build_fetcher

    await build_fetcher().run_all(trigger="schedule")


async def process_queues() -> None:
    from app.services.pipeline import process_queues as run

    await run()


async def catch_up_after_restart() -> bool:
    """Runs the daily fetch now if a restart made the scheduler miss it (FR-B3 AC1)."""
    from app.services.fetching import daily_run_missed, utcnow

    async with get_sessionmaker()() as session:
        missed = await daily_run_missed(session, utcnow())
    if missed:
        logger.info("Daily fetch was missed (restart or first start); running it now")
        await daily_fetch()
    return missed


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
        # Embeddings and skills that waited for an AI provider. Every 6 hours keeps the
        # free database's compute hours low (COSTS.md: Neon sleeps when idle).
        _scheduler.add_job(
            process_queues,
            "interval",
            hours=6,
            id="process_queues",
            coalesce=True,
            max_instances=1,
        )
        # Give the app a couple of minutes to settle after a deploy before catching up.
        _scheduler.add_job(
            catch_up_after_restart,
            "date",
            run_date=datetime.now(UTC) + timedelta(minutes=2),
            id="catch_up_after_restart",
        )
        # Soon after a deploy, so caches retired by a new version start refilling at once
        # rather than at the next 6-hourly run.
        _scheduler.add_job(
            process_queues,
            "date",
            run_date=datetime.now(UTC) + timedelta(minutes=5),
            id="process_queues_after_restart",
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
