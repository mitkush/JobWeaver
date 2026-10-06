"""Correspondence (Epic C): Postings grouped into Jobs by confidence band (ADR-0004).

Every Posting belongs to exactly one Job. A new Posting starts as its own Job and is
compared with recent Postings of the same Company: Exact and High pairs group at once,
Medium pairs become Possible Duplicates, Low pairs are dropped. Rejected Pairs are
checked before any grouping and never proposed again.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.registry import registered_adapters
from app.core.config import Settings, get_settings
from app.core.db import among
from app.core.errors import (
    ConflictError,
    GatewayError,
    NotFoundError,
    ValidationFailedError,
)
from app.dedup.scoring import (
    PostingView,
    Thresholds,
    band_for,
    embedding_text,
    exact_reason,
    locations_compatible,
    title_similarity,
)
from app.gateway.base import BaseAIGateway
from app.gateway.schemas import EmbedRequest, ExtractSkillsRequest, JobAdvert
from app.models.draft import Application, Draft
from app.models.job import Band, Job, MatchPair, PairStatus, RejectedPair, UserJob
from app.models.posting import Company, Posting
from app.models.user import User
from app.services import feed

logger = logging.getLogger(__name__)

# Transaction-level lock around every change to how Postings are grouped, so the daily
# pipeline and a User's Confirm or Split never interleave.
GROUPING_LOCK_ID = 7_201_027
PENDING, AWAITING_EMBEDDING, DONE = "pending", "awaiting_embedding", "done"
# New Postings are always scanned in full; only the embedding backlog is capped, so a long
# Gemini outage can never starve Exact grouping (FR-C1 AC4).
MAX_AWAITING_PER_RUN = 1000
SCAN_CHUNK = 500
MAX_SKILLS = 25

PairKey = tuple[uuid.UUID, uuid.UUID]


def pair_key(a: uuid.UUID, b: uuid.UUID) -> PairKey:
    return (a, b) if a < b else (b, a)


def source_priorities() -> dict[str, int]:
    return {cls.name: cls.priority for cls in registered_adapters()}


async def lock_grouping(session: AsyncSession) -> None:
    await session.execute(text(f"SELECT pg_advisory_xact_lock({GROUPING_LOCK_ID})"))


def thresholds(settings: Settings) -> Thresholds:
    return Thresholds(
        high_title=settings.dedup_high_title,
        high_description=settings.dedup_high_description,
        medium_title=settings.dedup_medium_title,
        medium_description=settings.dedup_medium_description,
    )


# --- Jobs from Postings -------------------------------------------------------------------


def _location_key(location: dict[str, object]) -> tuple[str, str, bool]:
    return (
        str(location.get("city") or "").lower(),
        str(location.get("country") or "").upper(),
        bool(location.get("remote")),
    )


def merge_locations(locations: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Union of places, where "Bengaluru" and "Bengaluru, IN" are one place (FR-C2 AC2)."""
    merged: dict[tuple[str, str, bool], dict[str, object]] = {}
    for location in locations:
        merged.setdefault(_location_key(location), location)
    known = {(city, remote) for city, country, remote in merged if city and country}
    return [
        location
        for (city, country, remote), location in merged.items()
        if country or not city or (city, remote) not in known
    ]


async def refresh_jobs(
    session: AsyncSession, job_ids: Iterable[uuid.UUID], priorities: dict[str, int]
) -> None:
    """Re-derives each Job from its Postings: Primary Posting by Source priority, every
    other field merged so nothing found on a lower-priority Posting is lost (FR-C2)."""
    ids = list(set(job_ids))
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        jobs = {
            job.id: job
            for job in (
                await session.execute(
                    select(Job).where(Job.id.in_(chunk)).execution_options(populate_existing=True)
                )
            ).scalars()
        }
        by_job: dict[uuid.UUID, list[Posting]] = defaultdict(list)
        postings = (
            await session.execute(
                select(Posting)
                .where(Posting.job_id.in_(chunk))
                .execution_options(populate_existing=True)
            )
        ).scalars()
        for posting in postings:
            by_job[posting.job_id].append(posting)  # type: ignore[index]
        company_ids = {p.company_id for group in by_job.values() for p in group}
        names = dict(
            (
                await session.execute(
                    select(Company.id, Company.name).where(among(Company.id, company_ids))
                )
            ).all()
        )
        for job_id, job in jobs.items():
            group = by_job.get(job_id)
            if not group:
                await session.delete(job)
                continue
            _derive(job, group, priorities, names)
    await session.flush()


def _derive(
    job: Job,
    postings: list[Posting],
    priorities: dict[str, int],
    company_names: dict[uuid.UUID, str],
) -> None:
    postings.sort(
        key=lambda p: (p.closed_at is not None, priorities.get(p.source, 99), p.first_seen_at, p.id)
    )
    primary = postings[0]
    open_postings = [p for p in postings if p.closed_at is None]
    job.primary_posting_id = primary.id
    job.company_id = primary.company_id
    job.company_name = company_names.get(primary.company_id, "")[:255]
    job.title = primary.title
    job.apply_url = next((p.apply_url for p in postings if p.apply_url), None)
    job.contact_email = next((p.contact_email for p in postings if p.contact_email), None)
    job.work_mode = next((p.work_mode for p in postings if p.work_mode), None)
    job.locations = merge_locations(loc for p in postings for loc in p.locations or [])
    job.posted_at = min(p.posted_at or p.first_seen_at for p in postings)
    job.sources = list(dict.fromkeys(p.source for p in (open_postings or postings)))
    job.expired_at = (
        None if open_postings else max(p.closed_at for p in postings if p.closed_at is not None)
    )
    # Always bumped, even when nothing changed, so _sync_jobs sees the Job as current.
    job.updated_at = func.now()


async def ensure_jobs(session: AsyncSession, priorities: dict[str, int]) -> int:
    """Every Posting is visible at once as its own Job; grouping happens after."""
    postings = list(
        (await session.execute(select(Posting).where(Posting.job_id.is_(None)))).scalars()
    )
    for posting in postings:
        job = Job(id=uuid.uuid4(), company_id=posting.company_id)
        session.add(job)
        posting.job_id = job.id
    await session.flush()
    await refresh_jobs(session, [p.job_id for p in postings if p.job_id], priorities)
    return len(postings)


async def _posting_ids(session: AsyncSession, job_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (await session.execute(select(Posting.id).where(Posting.job_id == job_id))).scalars()
    )


async def has_rejection(
    session: AsyncSession, left: Sequence[uuid.UUID], right: Sequence[uuid.UUID]
) -> bool:
    found = await session.scalar(
        select(RejectedPair.id)
        .where(
            or_(
                and_(RejectedPair.posting_a_id.in_(left), RejectedPair.posting_b_id.in_(right)),
                and_(RejectedPair.posting_a_id.in_(right), RejectedPair.posting_b_id.in_(left)),
            )
        )
        .limit(1)
    )
    return found is not None


async def merge_jobs(
    session: AsyncSession, a_id: uuid.UUID, b_id: uuid.UUID, priorities: dict[str, int]
) -> uuid.UUID | None:
    """Joins two Jobs; the older one survives with every Posting and every Feed link.
    Returns None when a Rejected Pair stands between them (ADR-0004)."""
    if a_id == b_id:
        return a_id
    a = await session.get(Job, a_id, populate_existing=True)
    b = await session.get(Job, b_id, populate_existing=True)
    if a is None or b is None:
        return None
    if await has_rejection(
        session, await _posting_ids(session, a.id), await _posting_ids(session, b.id)
    ):
        return None
    survivor, gone = (a, b) if (a.created_at, a.id) <= (b.created_at, b.id) else (b, a)
    await session.execute(
        update(Posting)
        .where(Posting.job_id == gone.id)
        .values(job_id=survivor.id)
        .execution_options(synchronize_session=False)
    )
    # A User keeps the Job in their Feed, with their hidden state, whichever side they had.
    await session.execute(
        text(
            "INSERT INTO user_jobs (id, user_id, job_id, hidden_at, created_at, updated_at) "
            "SELECT gen_random_uuid(), user_id, :survivor, hidden_at, now(), now() "
            "FROM user_jobs WHERE job_id = :gone "
            "ON CONFLICT (user_id, job_id) DO NOTHING"
        ),
        {"survivor": survivor.id, "gone": gone.id},
    )
    if survivor.required_skills is None and gone.required_skills is not None:
        survivor.required_skills = gone.required_skills
        survivor.skills_extracted_at = gone.skills_extracted_at
    for model in (Draft, Application):
        await session.execute(
            update(model).where(model.job_id == gone.id).values(job_id=survivor.id)
        )
    await session.delete(gone)
    await session.flush()
    await refresh_jobs(session, [survivor.id], priorities)
    return survivor.id


async def _job_of(session: AsyncSession, posting_id: uuid.UUID) -> uuid.UUID | None:
    return await session.scalar(select(Posting.job_id).where(Posting.id == posting_id))


# --- The pipeline ---------------------------------------------------------------------------


@dataclass
class Report:
    jobs_created: int = 0
    exact_pairs: int = 0
    high_pairs: int = 0
    medium_pairs: int = 0
    embedded: int = 0
    awaiting_embedding: int = 0
    skills_extracted: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class _Candidate:
    title_score: float
    owner: uuid.UUID


Sleep = Callable[[float], Awaitable[None]]


class Correspondence:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        gateway: BaseAIGateway,
        settings: Settings | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.gateway = gateway
        self.settings = settings or get_settings()
        self.clock = clock
        self.sleep = sleep
        self.priorities = source_priorities()

    async def process(self) -> Report:
        """Runs after every fetch and on a timer. Each step is isolated: a failure is
        logged and the next step still runs, so the Feed never stalls on one problem."""
        report = Report()
        for step in (self._group, self._sync_jobs, self._feeds, self._skills):
            try:
                await step(report)
            except Exception as exc:  # noqa: BLE001 - one broken step must not stop the rest
                logger.exception("Correspondence step %s failed", step.__name__)
                report.errors.append(f"{step.__name__}: {type(exc).__name__}")
        logger.info("Correspondence finished: %s", report)
        return report

    async def extract_skills(self) -> Report:
        report = Report()
        await self._skills(report)
        return report

    # Grouping ---------------------------------------------------------------------------

    async def _group(self, report: Report) -> None:
        candidates = await self._exact_pass(report)
        if candidates:
            await self._embed(candidates, report)
        await self._semantic_pass(candidates, report)

    async def _exact_pass(self, report: Report) -> dict[PairKey, _Candidate]:
        """Exact pairs group at once and need no embedding (FR-C1 AC4). Returns the pairs
        whose titles are close enough to be worth a semantic comparison.

        Every new Posting is scanned, in chunks with a commit after each so User actions
        can interleave. Postings already waiting for embeddings are rescanned only up to
        MAX_AWAITING_PER_RUN, after the new ones."""
        candidates: dict[PairKey, _Candidate] = {}
        handled: set[PairKey] = set()
        async with self.sessionmaker() as session:
            await lock_grouping(session)
            report.jobs_created += await ensure_jobs(session, self.priorities)
            order = (Posting.first_seen_at, Posting.id)
            open_ = Posting.closed_at.is_(None)
            new_ids = list(
                (
                    await session.execute(
                        select(Posting.id)
                        .where(Posting.match_state == PENDING, open_)
                        .order_by(*order)
                    )
                ).scalars()
            )
            waiting_ids = list(
                (
                    await session.execute(
                        select(Posting.id)
                        .where(Posting.match_state == AWAITING_EMBEDDING, open_)
                        .order_by(*order)
                        .limit(MAX_AWAITING_PER_RUN)
                    )
                ).scalars()
            )
            await session.commit()
            ids = new_ids + waiting_ids
            for start in range(0, len(ids), SCAN_CHUNK):
                await lock_grouping(session)
                chunk = (
                    await session.execute(
                        select(Posting)
                        .where(Posting.id.in_(ids[start : start + SCAN_CHUNK]))
                        .order_by(*order)
                    )
                ).scalars()
                await self._scan(session, list(chunk), candidates, handled, report)
                await session.commit()
        return candidates

    async def _scan(
        self,
        session: AsyncSession,
        postings: list[Posting],
        candidates: dict[PairKey, _Candidate],
        handled: set[PairKey],
        report: Report,
    ) -> None:
        th = thresholds(self.settings)
        cutoff = self.clock() - timedelta(days=self.settings.dedup_window_days)
        for posting in postings:
            others = (
                await session.execute(
                    select(Posting).where(
                        Posting.company_id == posting.company_id,
                        Posting.id != posting.id,
                        Posting.closed_at.is_(None),
                        func.coalesce(Posting.posted_at, Posting.first_seen_at) >= cutoff,
                    )
                )
            ).scalars()
            handled |= await self._known_pairs(session, posting.id)
            owns_candidate = False
            for other in others:
                key = pair_key(posting.id, other.id)
                if key in handled:
                    continue
                handled.add(key)
                reason = exact_reason(_view(posting), _view(other))
                if reason is not None:
                    session.add(
                        MatchPair(
                            posting_a_id=key[0],
                            posting_b_id=key[1],
                            band=Band.EXACT,
                            status=PairStatus.AUTO,
                            signals={"reason": reason},
                        )
                    )
                    report.exact_pairs += 1
                    await self._merge_postings(session, posting.id, other.id)
                    continue
                if await _job_of(session, posting.id) == await _job_of(session, other.id):
                    continue
                score = title_similarity(posting.title, other.title)
                if score >= th.medium_title:
                    candidates[key] = _Candidate(score, posting.id)
                    owns_candidate = True
            # Postings with a semantic candidate keep their state until _semantic_pass.
            if not owns_candidate:
                posting.match_state = DONE

    @staticmethod
    async def _known_pairs(session: AsyncSession, posting_id: uuid.UUID) -> set[PairKey]:
        known: set[PairKey] = set()
        for model in (MatchPair, RejectedPair):
            rows = await session.execute(
                select(model.posting_a_id, model.posting_b_id).where(
                    or_(model.posting_a_id == posting_id, model.posting_b_id == posting_id)
                )
            )
            known.update((a, b) for a, b in rows.all())
        return known

    async def _merge_postings(self, session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> None:
        job_a, job_b = await _job_of(session, a), await _job_of(session, b)
        if job_a and job_b:
            await merge_jobs(session, job_a, job_b, self.priorities)

    async def _embed(self, candidates: dict[PairKey, _Candidate], report: Report) -> None:
        """Embeds only Postings that have a close-titled rival, in paced batches. On any
        Gemini failure the rest stay queued (ADR-0014)."""
        needed = {posting_id for key in candidates for posting_id in key}
        model = self.gateway.embedding_model
        async with self.sessionmaker() as session:
            rows = (
                await session.execute(
                    select(Posting.id, Posting.title, Posting.description).where(
                        among(Posting.id, needed),
                        or_(Posting.embedding_model.is_(None), Posting.embedding_model != model),
                    )
                )
            ).all()
            size = self.settings.embedding_batch_size
            batches = [rows[i : i + size] for i in range(0, len(rows), size)]
            for number, batch in enumerate(batches[: self.settings.embedding_max_batches_per_run]):
                if number:
                    await self.sleep(self.settings.embedding_batch_pause_seconds)
                try:
                    response = await self.gateway.embed_texts(
                        EmbedRequest(texts=[embedding_text(r.title, r.description) for r in batch])
                    )
                except GatewayError as exc:
                    logger.warning("Embeddings queued: %s", exc.message)
                    break
                for row, vector in zip(batch, response.result.vectors, strict=True):
                    await session.execute(
                        update(Posting)
                        .where(Posting.id == row.id)
                        .values(embedding=vector, embedding_model=response.model)
                    )
                await session.commit()
                report.embedded += len(batch)

    async def _semantic_pass(self, candidates: dict[PairKey, _Candidate], report: Report) -> None:
        th = thresholds(self.settings)
        model = self.gateway.embedding_model
        waiting: set[uuid.UUID] = set()
        async with self.sessionmaker() as session:
            await lock_grouping(session)
            for key, candidate in candidates.items():
                a, b = key
                if (await self._known_pairs(session, a)) & {key}:
                    continue
                if await _job_of(session, a) == await _job_of(session, b):
                    continue
                similarity = await session.scalar(
                    text(
                        "SELECT 1 - (pa.embedding <=> pb.embedding) FROM postings pa, postings pb "
                        "WHERE pa.id = :a AND pb.id = :b "
                        "AND pa.embedding_model = :m AND pb.embedding_model = :m"
                    ),
                    {"a": a, "b": b, "m": model},
                )
                if similarity is None:
                    waiting.add(candidate.owner)
                    continue
                locations = dict(
                    (
                        await session.execute(
                            select(Posting.id, Posting.locations).where(Posting.id.in_(key))
                        )
                    ).all()
                )
                band = band_for(
                    candidate.title_score,
                    float(similarity),
                    locations_compatible(locations.get(a) or [], locations.get(b) or []),
                    th,
                )
                if band is None:
                    continue
                session.add(
                    MatchPair(
                        posting_a_id=a,
                        posting_b_id=b,
                        band=band,
                        status=PairStatus.AUTO if band == Band.HIGH else PairStatus.OPEN,
                        signals={
                            "reason": "similar",
                            "title": round(candidate.title_score, 1),
                            "description": round(float(similarity), 3),
                        },
                    )
                )
                await session.flush()
                if band == Band.HIGH:
                    report.high_pairs += 1
                    await self._merge_postings(session, a, b)
                else:
                    report.medium_pairs += 1
            # Matched on Exact signals only for now; semantic matching runs when the
            # embedding arrives (FR-C1 AC4).
            resolved = {c.owner for c in candidates.values()} - waiting
            if resolved:
                await session.execute(
                    update(Posting).where(among(Posting.id, resolved)).values(match_state=DONE)
                )
            if waiting:
                await session.execute(
                    update(Posting)
                    .where(among(Posting.id, waiting))
                    .values(match_state=AWAITING_EMBEDDING)
                )
            report.awaiting_embedding = len(waiting)
            await session.commit()

    # Keeping Jobs current ----------------------------------------------------------------

    async def _sync_jobs(self, report: Report) -> None:
        """Postings re-seen, changed or closed since their Job was derived (FR-B10)."""
        async with self.sessionmaker() as session:
            await lock_grouping(session)
            stale = (
                await session.execute(
                    select(Posting.job_id)
                    .join(Job, Job.id == Posting.job_id)
                    .where(Posting.updated_at > Job.updated_at)
                    .distinct()
                )
            ).scalars()
            await refresh_jobs(session, [j for j in stale if j], self.priorities)
            await session.commit()

    async def _feeds(self, report: Report) -> None:
        async with self.sessionmaker() as session:
            await feed.sync_all_feeds(session)
            await session.commit()

    # Skills ------------------------------------------------------------------------------

    async def _skills(self, report: Report) -> None:
        """Required skills, extracted once per Job (ADR-0010). Only Jobs that are in some
        User's Feed: nobody looks at the others, so they would only spend quota."""
        size = self.settings.skills_batch_size
        async with self.sessionmaker() as session:
            jobs = list(
                (
                    await session.execute(
                        select(Job)
                        .where(
                            Job.required_skills.is_(None),
                            Job.expired_at.is_(None),
                            exists().where(UserJob.job_id == Job.id),
                        )
                        .order_by(Job.posted_at.desc().nulls_last(), Job.id)
                        .limit(size * self.settings.skills_max_batches_per_run)
                    )
                ).scalars()
            )
            descriptions = dict(
                (
                    await session.execute(
                        select(Posting.id, Posting.description).where(
                            Posting.id.in_([j.primary_posting_id for j in jobs])
                        )
                    )
                ).all()
            )
            for start in range(0, len(jobs), size):
                batch = jobs[start : start + size]
                request = ExtractSkillsRequest(
                    jobs=[
                        JobAdvert(
                            ref=str(i + 1),
                            title=job.title,
                            description=descriptions.get(job.primary_posting_id) or "",
                        )
                        for i, job in enumerate(batch)
                    ]
                )
                try:
                    response = await self.gateway.extract_skills(request)
                except GatewayError as exc:
                    logger.warning("Skill extraction queued: %s", exc.message)
                    break
                found = {item.ref: item.skills for item in response.result.jobs}
                now = self.clock()
                for i, job in enumerate(batch):
                    skills = found.get(str(i + 1))
                    if skills is None:
                        continue  # left out by the model: tried again next run
                    job.required_skills = clean_skills(skills)
                    job.skills_extracted_at = now
                    report.skills_extracted += 1
                await session.commit()


def clean_skills(skills: Iterable[str]) -> list[str]:
    seen: dict[str, str] = {}
    for skill in skills:
        name = " ".join(str(skill).split())[:100]
        if name and name.lower() not in seen:
            seen[name.lower()] = name
    return list(seen.values())[:MAX_SKILLS]


def _view(posting: Posting) -> PostingView:
    return PostingView(
        id=posting.id,
        title=posting.title,
        description=posting.description,
        apply_url=posting.apply_url,
        locations=posting.locations or [],
    )


# --- User decisions (FR-C3, FR-C4) -------------------------------------------------------


async def _feed_job_ids(session: AsyncSession, user: User) -> set[uuid.UUID]:
    rows = await session.execute(select(UserJob.job_id).where(UserJob.user_id == user.id))
    return set(rows.scalars())


async def _open_pair_for(session: AsyncSession, user: User, pair_id: uuid.UUID) -> MatchPair:
    """A Possible Duplicate the User can see: at least one side is in their Feed."""
    pair = await session.get(MatchPair, pair_id, with_for_update=True)
    if pair is None:
        raise NotFoundError("Possible duplicate not found")
    jobs = {await _job_of(session, pair.posting_a_id), await _job_of(session, pair.posting_b_id)}
    if not jobs & await _feed_job_ids(session, user):
        raise NotFoundError("Possible duplicate not found")
    if pair.status != PairStatus.OPEN:
        raise ConflictError("This possible duplicate was already decided")
    return pair


async def confirm_pair(session: AsyncSession, user: User, pair_id: uuid.UUID) -> uuid.UUID:
    """Confirm: the two Postings are one Job, for everyone (FR-C3 AC1, AC3)."""
    await lock_grouping(session)
    pair = await _open_pair_for(session, user, pair_id)
    job_a = await _job_of(session, pair.posting_a_id)
    job_b = await _job_of(session, pair.posting_b_id)
    assert job_a is not None and job_b is not None
    merged = await merge_jobs(session, job_a, job_b, source_priorities())
    if merged is None:
        raise ConflictError(
            "These jobs cannot be merged: someone marked postings in them as different jobs"
        )
    pair.status = PairStatus.CONFIRMED
    pair.decided_by_user_id, pair.decided_at = user.id, datetime.now(UTC)
    await feed.sync_job_for_all(session, merged)
    return merged


async def add_rejected_pair(
    session: AsyncSession,
    a: uuid.UUID,
    b: uuid.UUID,
    *,
    reason: str,
    user_id: uuid.UUID | None,
) -> None:
    """Stores a Rejected Pair once; a pair that is already rejected stays as it is."""
    first, second = pair_key(a, b)
    await session.execute(
        insert(RejectedPair)
        .values(
            id=uuid.uuid4(), posting_a_id=first, posting_b_id=second, reason=reason, user_id=user_id
        )
        .on_conflict_do_nothing(index_elements=["posting_a_id", "posting_b_id"])
    )


async def reject_pair(session: AsyncSession, user: User, pair_id: uuid.UUID) -> None:
    """Not the same Job: stored as a Rejected Pair, never proposed again (FR-C3 AC2)."""
    await lock_grouping(session)
    pair = await _open_pair_for(session, user, pair_id)
    pair.status = PairStatus.REJECTED
    pair.decided_by_user_id, pair.decided_at = user.id, datetime.now(UTC)
    await add_rejected_pair(
        session, pair.posting_a_id, pair.posting_b_id, reason="not_same", user_id=user.id
    )


async def split_posting(
    session: AsyncSession, user: User, job_id: uuid.UUID, posting_id: uuid.UUID
) -> uuid.UUID:
    """Takes one Posting out of a grouped Job into a Job of its own (FR-C4). Rejected
    Pairs with every other Posting keep it from being grouped back."""
    await lock_grouping(session)
    if job_id not in await _feed_job_ids(session, user):
        raise NotFoundError("Job not found")
    others = [p for p in await _posting_ids(session, job_id) if p != posting_id]
    if len(others) == len(await _posting_ids(session, job_id)):
        raise NotFoundError("That posting is not part of this job")
    if not others:
        raise ValidationFailedError("This job has only one posting; there is nothing to split")
    now = datetime.now(UTC)
    for other in others:
        a, b = pair_key(posting_id, other)
        await add_rejected_pair(session, a, b, reason="split", user_id=user.id)
        # A Possible Duplicate left open between former group-mates is decided too, or
        # it would stay on both cards with no way to clear it.
        await session.execute(
            update(MatchPair)
            .where(
                MatchPair.posting_a_id == a,
                MatchPair.posting_b_id == b,
                MatchPair.status == PairStatus.OPEN,
            )
            .values(status=PairStatus.REJECTED, decided_by_user_id=user.id, decided_at=now)
        )
    posting = await session.get(Posting, posting_id)
    assert posting is not None
    new_job = Job(id=uuid.uuid4(), company_id=posting.company_id)
    session.add(new_job)
    posting.job_id = new_job.id
    await session.flush()
    priorities = source_priorities()
    await refresh_jobs(session, [job_id, new_job.id], priorities)
    await feed.sync_job_for_all(session, new_job.id)
    return new_job.id
