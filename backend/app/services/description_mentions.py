"""Bounded backfill; callers commit each batch and can safely resume later."""

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.posting import Posting
from app.tailoring.description_mentions import CACHE_VERSION, describe


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
    for row in rows:
        cache = describe(row.description)
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
