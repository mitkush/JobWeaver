from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update

from app.adapters.base import NormalizedPosting
from app.core.db import get_sessionmaker
from app.models import Posting
from app.services.description_mentions import backfill_batch
from app.services.fetching import save_postings
from app.tailoring.description_mentions import CACHE_VERSION, VOCABULARY, describe
from app.tailoring.keywords import has_description, mentioned

NOW = datetime(2026, 10, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    "description",
    [
        "We use RoR, Postgres, Go and REST APIs. " * 4,
        "guardrails, go to market, at rest, elastic bands, next steps. " * 4,
        "C++, C#, .NET, node.js and next.js; lowercase rails and python. " * 4,
        "\u2003\n Ruby \t",
        "",
    ],
)
def test_cache_uses_exact_feed_matcher(description):
    cached = describe(description)
    assert set(cached.skills) == mentioned(description, VOCABULARY)
    assert cached.usable == has_description(description)
    assert cached.version == CACHE_VERSION
    assert len(cached.skills) == len(set(cached.skills))


def advert(key, description):
    return NormalizedPosting(
        source_job_id=key, title="Engineer", company="Acme", description=description
    )


async def test_ingestion_refreshes_cache_after_edits_and_version_changes(db):
    await save_postings(db, "linkedin", [advert("edit", "Rails and Postgres. " * 10)], NOW)
    row = await db.scalar(select(Posting))
    assert "ruby on rails" in row.description_mentions
    assert row.description_usable is True
    await save_postings(db, "linkedin", [advert("edit", "Python")], NOW)
    assert row.description_mentions == ["python"]
    assert row.description_usable is False
    row.description_mentions_version = "old"
    row.description_mentions = ["incorrect"]
    await db.flush()
    await save_postings(db, "linkedin", [advert("edit", "Python")], NOW)
    assert row.description_mentions == ["python"]
    assert row.description_mentions_version == CACHE_VERSION


async def test_backfill_is_bounded_resumable_and_idempotent(db):
    await save_postings(db, "linkedin", [advert(str(i), "Rails " * 30) for i in range(3)], NOW)
    await db.execute(update(Posting).values(description_mentions_version=None))
    await db.commit()
    assert await backfill_batch(db, 2) == 2
    await db.commit()
    assert await backfill_batch(db, 2) == 1
    await db.commit()
    assert await backfill_batch(db, 2) == 0
    rows = (await db.execute(select(Posting.description_mentions_version))).scalars().all()
    assert rows == [CACHE_VERSION] * 3


async def test_backfill_skips_concurrent_ingestion_locks_and_retries_later(db):
    await save_postings(db, "linkedin", [advert("locked", "Rails " * 30)], NOW)
    await db.execute(update(Posting).values(description_mentions_version=None))
    await db.commit()
    async with get_sessionmaker()() as writer:
        row = await writer.scalar(select(Posting).with_for_update())
        assert await backfill_batch(db) == 0
        await db.rollback()
        # Model an ingest update while the batch cannot lock this Posting.
        row.description = "Python " * 30
        await writer.commit()
    assert await backfill_batch(db) == 1
    await db.commit()
    assert (await db.scalar(select(Posting.description_mentions))) == ["python"]


async def test_background_backfill_stops_at_its_row_limit_and_resumes(db):
    from app.services.description_mentions import backfill

    await save_postings(db, "linkedin", [advert(str(i), "Rails " * 30) for i in range(5)], NOW)
    await db.execute(update(Posting).values(description_mentions_version=None))
    await db.commit()
    assert await backfill(get_sessionmaker(), max_rows=3, batch_size=2) == 3
    assert await backfill(get_sessionmaker(), max_rows=3, batch_size=2) == 2
    assert await backfill(get_sessionmaker(), max_rows=3, batch_size=2) == 0


async def test_queue_run_refills_stale_caches(db):
    """After a deploy retires the cache version, the scheduler's queue run refills it."""
    from app.services.pipeline import process_queues

    await save_postings(db, "linkedin", [advert("q", "Rails " * 30)], NOW)
    await db.execute(update(Posting).values(description_mentions_version="old"))
    await db.commit()
    assert await process_queues() is not None
    db.expire_all()
    assert await db.scalar(select(Posting.description_mentions_version)) == CACHE_VERSION


async def test_queue_run_fills_caches_before_slow_ai_work(db, monkeypatch):
    """A queue run stopped during correspondence (AI waits, a redeploy) has already
    cached its batch."""
    from app.services import pipeline

    await save_postings(db, "linkedin", [advert("first", "Rails " * 30)], NOW)
    await db.execute(update(Posting).values(description_mentions_version="old"))
    await db.commit()

    class Stopped(Exception):
        pass

    class SlowCorrespondence:
        async def process(self):
            raise Stopped

    monkeypatch.setattr(pipeline, "build_correspondence", lambda gateway=None: SlowCorrespondence())
    with pytest.raises(Stopped):
        await pipeline.process_queues()
    db.expire_all()
    assert await db.scalar(select(Posting.description_mentions_version)) == CACHE_VERSION


def test_description_cache_does_not_promote_trade_rails_to_framework():
    description = "Build data, trust and rails to transact across borders. Python and Django. " * 3
    assert "ruby on rails" not in describe(description).skills
    assert "ruby on rails" in describe("Ruby on Rails applications. " * 5).skills
