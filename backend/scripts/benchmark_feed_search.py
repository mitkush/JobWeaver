"""Measure existing Feed queries without changing database data or schema.

Run from backend with PYTHONPATH=. python scripts/benchmark_feed_search.py.
Only plan summaries are printed; job content and user identifiers stay in the database.
"""

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import dialect

from app.core.db import get_sessionmaker
from app.models import Posting, Preference, User, UserJob
from app.schemas.feed import FeedQuery
from app.services import feed
from app.tailoring.skills import spellings


def walk(node, counts):
    counts[node["Node Type"]] += 1
    for child in node.get("Plans", []):
        walk(child, counts)


async def main(chunks: int, repetitions: int):
    async with get_sessionmaker()() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await session.execute(text("SET LOCAL statement_timeout = '15s'"))
        preferences = list((await session.scalars(select(Preference))).all())
        jobs = await feed._open_jobs(session)
        rules = {p.user_id: feed.rule_of(p) for p in preferences}
        pending = {}
        for p in preferences:
            if rules[p.user_id] is None:
                continue
            for j in jobs:
                if feed.place_matches(j.locations, j.work_mode, p):
                    pending.setdefault(j.id, []).append(feed.title_matches(j.title, p.titles or []))
        core = {
            s
            for r in rules.values()
            if r
            for k in r.keywords
            if k.core
            for s in spellings(k.canonical)
            if s
        }
        mentions = or_(
            text("false"),
            *(
                Posting.description.ilike("%" + feed._like_literal(t) + "%", escape="\\")
                for t in core
            ),
        )
        by_id = {j.id: j for j in jobs}

        async def measure(label, stmt):
            sql = str(
                stmt.compile(
                    dialect=dialect(paramstyle="named"), compile_kwargs={"literal_binds": True}
                )
            )
            values = []
            for _ in range(repetitions):
                plan = (
                    await (await session.connection()).exec_driver_sql(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql
                    )
                ).scalar_one()[0]
                nodes = Counter()

                walk(plan["Plan"], nodes)
                values.append(
                    {
                        "execution_ms": plan["Execution Time"],
                        "planning_ms": plan["Planning Time"],
                        "rows": plan["Plan"]["Actual Rows"],
                        "shared_hit": plan["Plan"].get("Shared Hit Blocks", 0),
                        "shared_read": plan["Plan"].get("Shared Read Blocks", 0),
                        "nodes": dict(nodes),
                    }
                )
            print(json.dumps({"query": label, "runs": values}), flush=True)

        ids = list(pending)
        print(
            json.dumps(
                {
                    "open_jobs": len(jobs),
                    "candidate_jobs": len(ids),
                    "preferences": len(preferences),
                }
            ),
            flush=True,
        )
        for num, start in enumerate(range(0, min(len(ids), chunks * 1000), 1000)):
            chunk = [by_id[i] for i in ids[start : start + 1000]]
            posting_ids = [j.primary_posting_id for j in chunk if j.primary_posting_id]
            titled = [
                j.primary_posting_id for j in chunk if j.primary_posting_id and any(pending[j.id])
            ]
            old = select(Posting.id, Posting.description).where(
                Posting.id.in_(posting_ids),
                or_(
                    mentions,
                    (Posting.id.in_(titled))
                    & (func.length(Posting.description) < feed.SHORT_DESCRIPTION_READ),
                ),
            )
            candidates = (
                select(Posting.id)
                .where(Posting.id.in_(posting_ids), mentions)
                .union(
                    select(Posting.id).where(
                        Posting.id.in_(titled),
                        func.length(Posting.description) < feed.SHORT_DESCRIPTION_READ,
                    )
                )
            )
            new = select(Posting.id, Posting.description).where(Posting.id.in_(candidates))
            await measure(f"description_chunk_{num + 1}_original", old)
            await measure(f"description_chunk_{num + 1}_union", new)
        uid = await session.scalar(
            select(UserJob.user_id).group_by(UserJob.user_id).order_by(func.count().desc()).limit(1)
        )
        user = await session.get(User, uid) if uid else None
        if user:
            for q in ("Rails", "Go", "Engineer"):
                stmt = feed._filtered(user, FeedQuery(q=q), datetime.now(UTC))
                stmt = feed._section(feed._match(stmt, "title"), True)
                await measure(
                    "feed_" + q + "_count", select(func.count()).select_from(stmt.subquery())
                )
                await measure(
                    "feed_" + q + "_page",
                    stmt.order_by(feed.Job.posted_at.desc().nullslast(), feed.Job.id.desc()).limit(
                        20
                    ),
                )
        await session.rollback()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--repetitions", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()

    async def bounded():
        async with asyncio.timeout(120):
            await main(args.chunks, args.repetitions)

    asyncio.run(bounded())
