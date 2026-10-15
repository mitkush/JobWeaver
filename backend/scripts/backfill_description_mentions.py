"""Run from backend: PYTHONPATH=. python scripts/backfill_description_mentions.py.

Each batch commits independently. Re-run to resume; already-current rows are skipped.
"""

import argparse
import asyncio

from sqlalchemy import text

from app.core.db import dispose_engine, get_sessionmaker
from app.services.description_mentions import backfill_batch


async def main(batch_size: int, max_batches: int) -> None:
    try:
        for batch in range(max_batches):
            async with get_sessionmaker()() as session:
                await session.execute(text("SET LOCAL lock_timeout = '2s'"))
                await session.execute(text("SET LOCAL statement_timeout = '30s'"))
                count = await backfill_batch(session, batch_size)
                await session.commit()
            print(f"Batch {batch + 1}: cached {count} Postings", flush=True)
            if not count:
                # May also mean remaining stale rows are locked by another worker.
                break
            await asyncio.sleep(0.1)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, choices=range(1, 501), default=100)
    parser.add_argument("--max-batches", type=int, choices=range(1, 10001), default=1)
    args = parser.parse_args()
    asyncio.run(main(args.batch_size, args.max_batches))
