from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, update

from app.adapters.base import Location, NormalizedPosting
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import GatewayError
from app.gateway.recorded import RecordedAIGateway
from app.gateway.schemas import ExtractSkillsResult, GatewayResponse, JobSkills
from app.models import Job, MatchPair, PairStatus, Posting, Preference, RejectedPair, UserJob
from app.services import correspondence as service
from app.services.correspondence import Correspondence
from app.services.fetching import save_postings
from tests.conftest import signed_in

NOW = datetime(2026, 10, 6, 2, 0, tzinfo=UTC)
ADVERT = (
    "We are hiring a backend engineer to build payment APIs in Python and PostgreSQL. "
    "You will design services, own reliability, review code and mentor engineers. "
    "Experience with Kubernetes, Kafka and AWS is a plus. Hybrid in Bengaluru."
)
OTHER_ROLE = (
    "We are hiring a data engineer to build pipelines in Spark and Airflow. "
    "You will model warehouses, own data quality and partner with analysts. "
    "Experience with dbt, BigQuery and AWS is a plus. Hybrid in Bengaluru."
)
BLR = Location(city="Bengaluru", country="IN")


def posting(job_id: str, **fields) -> NormalizedPosting:
    data = {
        "source_job_id": job_id,
        "title": "Backend Engineer",
        "company": "Acme Pvt Ltd",
        "description": ADVERT,
        "locations": [BLR],
        "posted_at": NOW - timedelta(days=1),
    }
    data.update(fields)
    return NormalizedPosting(**data)


async def add(source: str, *items: NormalizedPosting) -> None:
    async with get_sessionmaker()() as session:
        await save_postings(session, source, list(items), NOW)
        await session.commit()


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def build(variant: str = "success", gateway=None, sleep=None, **overrides) -> Correspondence:
    settings = get_settings().model_copy(update=overrides)
    gateway = gateway or RecordedAIGateway(Path(settings.gateway_recorded_dir), variant)  # type: ignore[arg-type]
    return Correspondence(
        get_sessionmaker(), gateway, settings, clock=lambda: NOW, sleep=sleep or FakeSleep()
    )


async def jobs(db) -> list[Job]:
    db.expire_all()
    return list((await db.execute(select(Job).order_by(Job.created_at))).scalars())


async def job_of(db, source: str, source_job_id: str):
    return await db.scalar(
        select(Posting.job_id).where(
            Posting.source == source, Posting.source_job_id == source_job_id
        )
    )


async def test_every_posting_becomes_a_job_at_once(db):
    await add(
        "remotive", posting("r1"), posting("r2", title="Data Engineer", description=OTHER_ROLE)
    )
    report = await build().process()
    assert report.jobs_created == 2
    assert len(await jobs(db)) == 2


async def test_same_apply_url_groups_across_sources_with_merged_fields(db):
    # FR-C2: primary by Source priority; email and locations merged from all Postings.
    await add(
        "greenhouse",
        posting(
            "g1",
            title="Software Engineer, Backend",
            description="Short greenhouse text about the role and team.",
            apply_url="https://boards.greenhouse.io/acme/jobs/1",
            contact_email="jobs@acme.com",
            locations=[Location(city="Pune", country="IN")],
        ),
    )
    await add(
        "linkedin",
        posting("l1", apply_url="https://boards.greenhouse.io/acme/jobs/1?gh_src=linkedin"),
    )
    report = await build().process()
    assert report.exact_pairs == 1
    [job] = await jobs(db)
    assert job.title == "Backend Engineer"  # LinkedIn has the highest priority
    assert job.sources == ["linkedin", "greenhouse"]
    assert job.contact_email == "jobs@acme.com"  # only on the lower-priority Posting
    assert {loc["city"] for loc in job.locations} == {"Bengaluru", "Pune"}
    assert job.company_name == "Acme Pvt Ltd"


async def test_same_advert_in_two_cities_is_one_job_with_two_locations(db):
    # FR-C5
    await add(
        "linkedin",
        posting("l1"),
        posting("l2", locations=[Location(city="Hyderabad", country="IN")]),
    )
    await build().process()
    [job] = await jobs(db)
    assert len(job.locations) == 2


async def test_reworded_advert_groups_as_high_and_other_role_stays_apart(db):
    await add("linkedin", posting("l1"))
    await add(
        "jsearch",
        posting("j1", description=ADVERT.replace("a plus", "welcome")),
        posting("j2", title="Data Engineer", description=OTHER_ROLE),
    )
    report = await build().process()
    assert report.high_pairs == 1
    assert await job_of(db, "linkedin", "l1") == await job_of(db, "jsearch", "j1")
    assert await job_of(db, "jsearch", "j2") != await job_of(db, "linkedin", "l1")
    assert len(await jobs(db)) == 2


async def test_medium_pair_becomes_a_possible_duplicate(db):
    await add("linkedin", posting("l1"))
    await add(
        "jsearch",
        posting("j1", title="Backend Engineer II", description=ADVERT + " Join our payments team."),
    )
    report = await build(dedup_high_title=99).process()
    assert report.medium_pairs == 1
    pair = await db.scalar(select(MatchPair))
    assert pair.status == PairStatus.OPEN
    assert len(await jobs(db)) == 2


async def test_only_postings_with_a_close_rival_are_embedded_in_paced_batches(db):
    await add("linkedin", *[posting(f"l{i}", description=ADVERT + f" Team {i}.") for i in range(5)])
    await add("remotive", posting("lonely", company="Solo Labs Inc"))
    sleep = FakeSleep()
    report = await build(
        sleep=sleep, embedding_batch_size=2, embedding_batch_pause_seconds=7
    ).process()
    assert report.embedded == 5
    assert sleep.calls == [7, 7]
    lonely = await db.scalar(select(Posting).where(Posting.source_job_id == "lonely"))
    assert lonely.embedding_model is None


async def test_without_embeddings_exact_still_groups_and_the_rest_waits(db):
    # FR-C1 AC4, ADR-0014
    await add(
        "linkedin", posting("l1"), posting("l2", locations=[Location(city="Pune", country="IN")])
    )
    await add("jsearch", posting("j1", description=ADVERT.replace("a plus", "welcome")))
    report = await build("refusal").process()
    assert report.exact_pairs == 1
    assert report.awaiting_embedding >= 1
    assert len(await jobs(db)) == 2
    states = set((await db.execute(select(Posting.match_state))).scalars())
    assert "awaiting_embedding" in states

    report = await build().process()
    assert report.high_pairs + report.medium_pairs >= 1
    states = set((await db.execute(select(Posting.match_state))).scalars())
    assert states == {"done"}


async def test_a_rejected_pair_is_never_proposed_again(db):
    # FR-C3 AC2
    await add("linkedin", posting("l1"))
    await add(
        "jsearch", posting("j1", title="Backend Engineer II", description=ADVERT + " Payments.")
    )
    await build(dedup_high_title=99).process()
    pair = await db.scalar(select(MatchPair))
    await db.execute(update(MatchPair).values(status=PairStatus.REJECTED))
    db.add(
        RejectedPair(
            posting_a_id=pair.posting_a_id, posting_b_id=pair.posting_b_id, reason="not_same"
        )
    )
    await db.execute(update(Posting).values(match_state="pending"))
    await db.commit()
    await add(
        "jsearch", posting("j1", title="Backend Engineer II", description=ADVERT + " Payments.")
    )
    await build(dedup_high_title=99).process()
    assert await db.scalar(select(func.count()).select_from(MatchPair)) == 1
    assert len(await jobs(db)) == 2


async def test_rejected_pair_blocks_an_exact_merge_too(db):
    await add("linkedin", posting("l1", apply_url="https://jobs.lever.co/acme/1"))
    await build().process()
    await add("jsearch", posting("j1", apply_url="https://jobs.lever.co/acme/1"))
    a = await db.scalar(select(Posting.id).where(Posting.source_job_id == "l1"))
    b = await db.scalar(select(Posting.id).where(Posting.source_job_id == "j1"))
    first, second = service.pair_key(a, b)
    db.add(RejectedPair(posting_a_id=first, posting_b_id=second, reason="split"))
    await db.commit()
    await build().process()
    assert len(await jobs(db)) == 2


async def test_closed_postings_expire_their_job(db):
    await add("linkedin", posting("l1"))
    await build().process()
    await db.execute(update(Posting).values(closed_at=NOW, closed_reason="age"))
    await db.commit()
    await build().process()
    [job] = await jobs(db)
    assert job.expired_at is not None


async def feed_user(db, email="asha@example.com"):
    user, client = await signed_in(db, email)
    await client.aclose()
    db.add(
        Preference(
            user_id=user.id,
            titles=["Backend Engineer"],
            locations=[{"city": "Bengaluru", "country": "IN"}],
            work_modes=["hybrid", "onsite"],
        )
    )
    await db.commit()
    return user


async def test_feeds_link_matching_jobs_and_skills_are_extracted_once(db):
    user = await feed_user(db)
    await add("linkedin", posting("l1"))
    await add("remotive", posting("r2", title="Data Engineer", description=OTHER_ROLE))
    report = await build().process()
    links = list((await db.execute(select(UserJob).where(UserJob.user_id == user.id))).scalars())
    assert len(links) == 1
    # Only the Job in someone's Feed was sent for extraction.
    assert report.skills_extracted == 1
    job = await db.get(Job, links[0].job_id)
    await db.refresh(job)
    assert job.required_skills == ["Python", "PostgreSQL", "Kubernetes", "Go"]
    report = await build().process()
    assert report.skills_extracted == 0


class FailingSkills(RecordedAIGateway):
    async def extract_skills(self, request):
        raise GatewayError("all providers down")


async def test_skills_wait_when_ai_is_unavailable(db):
    await feed_user(db)
    await add("linkedin", posting("l1"))
    gateway = FailingSkills(Path(get_settings().gateway_recorded_dir))
    report = await build(gateway=gateway).process()
    assert report.skills_extracted == 0
    [job] = await jobs(db)
    assert job.required_skills is None


class PartialSkills(RecordedAIGateway):
    async def extract_skills(self, request):
        return GatewayResponse[ExtractSkillsResult](
            result=ExtractSkillsResult(jobs=[JobSkills(ref="9", skills=["X"])]),
            provider="recorded",
            model="x",
        )


async def test_a_job_the_model_skipped_is_retried_later(db):
    await feed_user(db)
    await add("linkedin", posting("l1"))
    report = await build(gateway=PartialSkills(Path(get_settings().gateway_recorded_dir))).process()
    assert report.skills_extracted == 0


async def test_one_failing_step_does_not_stop_the_others(db, monkeypatch):
    await feed_user(db)
    await add("linkedin", posting("l1"))

    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service.Correspondence, "_sync_jobs", broken)
    report = await build().process()
    assert report.errors == ["broken: RuntimeError"]
    assert report.skills_extracted == 1


async def test_merging_keeps_feed_links_and_hidden_state(db):
    user = await feed_user(db)
    await add("linkedin", posting("l1"))
    await build().process()
    job_id = await job_of(db, "linkedin", "l1")
    await db.execute(update(UserJob).values(hidden_at=NOW))
    await db.commit()
    await add("jsearch", posting("j1", locations=[Location(city="Pune", country="IN")]))
    await build().process()
    [link] = (await db.execute(select(UserJob).where(UserJob.user_id == user.id))).scalars()
    assert link.job_id == job_id
    assert link.hidden_at is not None


async def test_vectors_round_trip_through_the_custom_column(db):
    await add("linkedin", posting("l1"))
    vector = [0.5, -0.25] + [0.0] * 766
    await db.execute(update(Posting).values(embedding=vector, embedding_model="m"))
    await db.commit()
    db.expire_all()
    stored = await db.scalar(select(Posting.embedding))
    assert stored[:2] == [0.5, -0.25] and len(stored) == 768


async def test_unchanged_jobs_are_not_refreshed_again(db, monkeypatch):
    await add("linkedin", posting("l1"))
    await build().process()
    await add("linkedin", posting("l1"))  # re-seen: the Posting's updated_at moves
    refreshed: list[int] = []
    original = service.refresh_jobs

    async def spy(session, job_ids, priorities):
        ids = list(job_ids)
        refreshed.append(len(ids))
        await original(session, ids, priorities)

    monkeypatch.setattr(service, "refresh_jobs", spy)
    await build().process()
    await build().process()
    assert refreshed[-1] == 0


def test_a_place_without_its_country_is_not_listed_twice():
    merged = service.merge_locations(
        [
            {"city": "Bengaluru", "country": "IN", "remote": False},
            {"city": "Bengaluru", "country": None, "remote": False},
            {"city": "Pune", "country": None, "remote": False},
            {"city": None, "country": "IN", "remote": True},
        ]
    )
    assert [(m["city"], m["country"]) for m in merged] == [
        ("Bengaluru", "IN"),
        ("Pune", None),
        (None, "IN"),
    ]


async def test_an_embedding_backlog_never_blocks_exact_grouping(db, monkeypatch):
    # A long Gemini outage leaves many Postings waiting for embeddings; new Postings must
    # still reach the Exact pass (FR-C1 AC4).
    monkeypatch.setattr(service, "MAX_AWAITING_PER_RUN", 2)
    await add(
        "linkedin",
        *[
            posting(f"wait{i}", title=f"Backend Engineer {i}", description=f"{ADVERT} Team {i}.")
            for i in range(4)
        ],
    )
    await build("refusal").process()
    waiting = await db.scalar(
        select(func.count()).select_from(Posting).where(Posting.match_state == "awaiting_embedding")
    )
    # Each pair is owned by one side, so the last Posting itself has nothing to wait for.
    assert waiting == 3  # more than the backlog cap of 2

    url = "https://jobs.lever.co/globex/42"
    await add("linkedin", posting("new1", company="Globex", apply_url=url))
    await add("jsearch", posting("new2", company="Globex", apply_url=url))
    report = await build("refusal").process()
    assert report.exact_pairs == 1
    assert await job_of(db, "linkedin", "new1") == await job_of(db, "jsearch", "new2")


async def test_an_edited_advert_is_embedded_and_compared_again(db):
    await add("linkedin", posting("l1"))
    await add(
        "jsearch", posting("j1", title="Backend Engineer II", description=ADVERT + " Payments.")
    )
    await build(dedup_high_title=99).process()
    stored = await db.scalar(select(Posting).where(Posting.source_job_id == "j1"))
    assert stored.embedding_model is not None and stored.match_state == "done"

    await add(
        "jsearch", posting("j1", title="Backend Engineer II", description=ADVERT + " Lending.")
    )
    db.expire_all()
    stored = await db.scalar(select(Posting).where(Posting.source_job_id == "j1"))
    assert (stored.embedding_model, stored.match_state) == (None, "pending")

    await add("linkedin", posting("l1"))  # unchanged text keeps its embedding
    db.expire_all()
    unchanged = await db.scalar(select(Posting).where(Posting.source_job_id == "l1"))
    assert unchanged.embedding_model is not None
    # A new rival is compared with the new text: the edited Posting is embedded again,
    # the unchanged one is not.
    await add("remotive", posting("r1", title="Backend Engineer III", description=ADVERT))
    report = await build(dedup_high_title=99).process()
    assert report.embedded == 2  # j1 again, plus the new r1


async def test_a_split_rules_out_proposals_through_the_rest_of_either_group(db):
    """After "Not the same Job", a newcomer grouped with one side must not be proposed as a
    Possible Duplicate of the other: Confirm would be refused (FR-C3)."""
    await add("linkedin", posting("l1", apply_url="https://acme.dev/apply/1"))
    await add(
        "jsearch", posting("j1", title="Backend Engineer II", description=ADVERT + " Payments.")
    )
    await build(dedup_high_title=99).process()
    pair = await db.scalar(select(MatchPair))
    await db.execute(update(MatchPair).values(status=PairStatus.REJECTED))
    db.add(
        RejectedPair(
            posting_a_id=pair.posting_a_id, posting_b_id=pair.posting_b_id, reason="not_same"
        )
    )
    await db.commit()
    # Same apply URL as l1 (Exact); not word-for-word j1's text, but close enough to be a
    # Medium candidate against it.
    await add(
        "greenhouse",
        posting("g1", title="Backend Engineer II", apply_url="https://acme.dev/apply/1",
                description=ADVERT + " Payments team."),
    )  # fmt: skip
    # High is out of reach, so g1 and j1 can only land in Medium: a Possible Duplicate.
    await build(dedup_high_title=101).process()
    g1 = await job_of(db, "greenhouse", "g1")
    assert g1 == await job_of(db, "linkedin", "l1")
    assert g1 != await job_of(db, "jsearch", "j1")
    open_pairs = await db.scalar(
        select(func.count()).select_from(MatchPair).where(MatchPair.status == PairStatus.OPEN)
    )
    assert open_pairs == 0
