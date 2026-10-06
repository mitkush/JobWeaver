"""Hacker News comments to Postings through the Correspondence advert step (FR-B8)."""

from datetime import timedelta

from sqlalchemy import select

from app.models import Posting, RawAdvert
from tests.services.test_correspondence import NOW, build

ACME = (
    "Acme Robotics | Senior Backend Engineer, SRE | Berlin, Germany | Hybrid or REMOTE (EU)\n"
    "We build warehouse robots in Go and Rust. Apply at https://acme.dev/careers"
)
TINYCO = "Tinyco | Founding Engineer | Bengaluru, India | ONSITE. Email jobs@tinyco.io"
QUESTION = "Is anyone hiring in Lisbon? Asking for a friend."


async def queue(db, *texts: str, posted=NOW - timedelta(days=1)) -> None:
    for i, text in enumerate(texts):
        db.add(
            RawAdvert(
                source="hackernews",
                ref=str(4100 + i),
                text=text,
                url=f"https://news.ycombinator.com/item?id={4100 + i}",
                posted_at=posted,
                attempts=0,
            )
        )
    await db.commit()


async def postings(db) -> list[Posting]:
    db.expire_all()
    return list((await db.execute(select(Posting).order_by(Posting.source_job_id))).scalars())


async def adverts(db) -> list[RawAdvert]:
    db.expire_all()
    return list((await db.execute(select(RawAdvert).order_by(RawAdvert.ref))).scalars())


async def test_comments_become_postings_checked_against_their_own_text(db):
    await queue(db, ACME, TINYCO, QUESTION)
    report = await build().process()
    assert report.adverts_extracted == 3

    found = await postings(db)
    assert [p.source_job_id for p in found] == ["4100:0", "4100:1", "4101:0"]
    backend, sre, founding = found
    assert backend.title == "Senior Backend Engineer" and backend.work_mode == "hybrid"
    assert backend.locations[0]["country"] == "DE"
    assert backend.apply_url == "https://acme.dev/careers"
    assert sre.locations[0]["remote"] is True
    # The model invented a link that is not in the comment: the comment itself is used.
    assert founding.apply_url == "https://news.ycombinator.com/item?id=4101"
    assert founding.contact_email == "jobs@tinyco.io"
    assert founding.description == TINYCO
    # Extracted Postings are grouped into Jobs in the same run.
    assert all(p.job_id is not None for p in found)
    assert [a.postings for a in await adverts(db)] == [2, 1, 0]


async def test_adverts_wait_while_ai_is_unavailable(db):
    await queue(db, ACME)
    await build("refusal").process()
    assert await postings(db) == []
    waiting = (await adverts(db))[0]
    assert waiting.extracted_at is None and waiting.attempts == 1 and waiting.error

    await build().process()
    assert len(await postings(db)) == 2
    assert (await adverts(db))[0].extracted_at is not None


async def test_adverts_past_the_age_limit_leave_the_queue(db):
    await queue(db, ACME, posted=NOW - timedelta(days=45))
    report = await build().process()
    assert report.adverts_extracted == 0 and await postings(db) == []
