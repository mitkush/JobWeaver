"""Bounded backfill; callers commit each batch and can safely resume later."""

import asyncio
import logging

from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.posting import Posting
from app.tailoring.description_mentions import CACHE_VERSION, describe

logger = logging.getLogger(__name__)
# Background runs (scheduler) cache this many Postings at most, in batches.
ROWS_PER_RUN = 5000
BATCH_SIZE = 200


async def backfill_batch(session: AsyncSession, batch_size: int = 100) -> int:
    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be between 1 and 500")
    # Lock the selected rows until commit, so a concurrent ingest cannot replace the
    # description between reading it and writing its cache. Other workers skip locks.
    rows = (
        await session.execute(
            select(Posting.id, Posting.description)
            .where(
                or_(
                    Posting.description_mentions_version.is_distinct_from(CACHE_VERSION),
                    Posting.description_mentions.is_(None),
                    Posting.description_usable.is_(None),
                )
            )
            .order_by(Posting.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    ).all()
    # Regex matching is CPU work: keep it off the event loop so requests stay responsive.
    caches = await asyncio.to_thread(lambda: [describe(row.description) for row in rows])
    for row, cache in zip(rows, caches, strict=True):
        await session.execute(
            update(Posting)
            .where(Posting.id == row.id)
            .values(
                description_mentions=cache.skills,
                description_usable=cache.usable,
                description_mentions_version=cache.version,
            )
        )
    return len(rows)


async def backfill(
    sessionmaker: async_sessionmaker[AsyncSession],
    max_rows: int = ROWS_PER_RUN,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Caches up to max_rows missing or stale Postings, committing each batch. The
    scheduler calls this, so the cache fills by itself after a deploy and refills after
    a vocabulary change; the command line does the same on demand."""
    done = 0
    while done < max_rows:
        async with sessionmaker() as session:
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            await session.execute(text("SET LOCAL statement_timeout = '30s'"))
            count = await backfill_batch(session, min(batch_size, max_rows - done))
            await session.commit()
        if not count:
            break
        done += count
    if done:
        logger.info("Cached description mentions for %s Postings", done)
    return done
