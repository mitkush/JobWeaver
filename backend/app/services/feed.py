"""Feed (Epic D): each User's links to the shared Jobs that match their Preferences.

A Feed entry is a `user_jobs` row, never a copy of the Job (ADR-0002). Every query here is
scoped by user_id; nothing a User does to their Feed changes another User's (ADR-0001)."""

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, any_, delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import registered_adapters
from app.core.db import among
from app.core.errors import NotFoundError
from app.dedup.scoring import clean_title
from app.models.draft import Application, Draft
from app.models.fact import Fact, FactKind
from app.models.fetch import FetchRun, RunStatus
from app.models.job import Job, MatchPair, PairStatus, UserJob
from app.models.posting import Posting
from app.models.preference import Preference
from app.models.user import User
from app.schemas.feed import (
    FeedCard,
    FeedCounts,
    FeedOut,
    FeedQuery,
    JobDetailOut,
    LocationOut,
    PossibleDuplicateOut,
    PostingOut,
    SourceBadge,
)
from app.tailoring.skills import UserSkills, skill_gaps, user_skills

LINK_CHUNK = 1000

# Two-word spellings that are one word in other titles ("Dev-Ops" = "DevOps"), joined
# before single words are mapped, so both sides end up with the same words.
_JOINED: dict[tuple[str, str], str] = {
    ("dev", "ops"): "devops",
    ("back", "end"): "backend",
    ("front", "end"): "frontend",
    ("full", "stack"): "fullstack",
    ("machine", "learning"): "ml",
}
# Spellings that name the same role word ("Backend Developer" = "Backend Engineer").
_TITLE_WORDS: dict[str, tuple[str, ...]] = {
    "developer": ("engineer",),
    "dev": ("engineer",),
    "programmer": ("engineer",),
    "engg": ("engineer",),
    "sde": ("software", "engineer"),
    "swe": ("software", "engineer"),
    "sr": ("senior",),
    "jr": ("junior",),
}


def title_words(title: str) -> set[str]:
    raw = clean_title(title).split()
    joined: list[str] = []
    i = 0
    while i < len(raw):
        pair = (raw[i], raw[i + 1]) if i + 1 < len(raw) else None
        if pair in _JOINED:
            joined.append(_JOINED[pair])  # type: ignore[index]
            i += 2
        else:
            joined.append(raw[i])
            i += 1
    words: set[str] = set()
    for word in joined:
        words.update(_TITLE_WORDS.get(word, (word,)))
    return words


def title_matches(job_title: str, wanted: Sequence[str]) -> bool:
    """Every word of one wanted title appears in the Job's title, in any order."""
    have = title_words(job_title)
    return any(want and want <= have for want in (title_words(t) for t in wanted))


def location_matches(
    job_locations: Sequence[dict[str, object]],
    job_work_mode: str | None,
    wanted: Sequence[dict[str, str | None]],
    work_modes: Sequence[str],
) -> bool:
    """Any of the Job's places matches any wanted place; no wanted place means Global.

    The listed place is the office location; work mode is checked separately. For a
    remote (WFH) Job only the country has to match: its office city does not matter to
    someone working from home. For onsite and hybrid Jobs the city must match too."""
    if not wanted:
        return True
    if not job_locations:
        return True  # unknown place: shown rather than silently missed
    for location in job_locations:
        city = str(location.get("city") or "").lower()
        country = str(location.get("country") or "").upper()
        remote = job_work_mode == "remote" or bool(location.get("remote"))
        if not country and not city:
            return True
        for place in wanted:
            want_country = str(place.get("country") or "").upper()
            want_city = str(place.get("city") or "").lower()
            if country and country != want_country:
                continue
            if want_city and city and city != want_city and not remote:
                continue
            return True
    return False


def job_matches(
    title: str,
    locations: Sequence[dict[str, object]],
    work_mode: str | None,
    preference: Preference,
) -> bool:
    """Title, places and work mode (FR-D1). Keywords never narrow the Feed."""
    modes = preference.work_modes or []
    if work_mode and modes and work_mode not in modes:
        return False
    return title_matches(title, preference.titles or []) and location_matches(
        locations, work_mode, preference.locations or [], modes
    )


# --- Linking --------------------------------------------------------------------------------


async def _open_jobs(session: AsyncSession, job_ids: Iterable[uuid.UUID] | None = None):  # noqa: ANN202
    query = select(Job.id, Job.title, Job.locations, Job.work_mode).where(Job.expired_at.is_(None))
    if job_ids is not None:
        query = query.where(Job.id.in_(list(job_ids)))
    return (await session.execute(query)).all()


async def _apply_links(
    session: AsyncSession,
    user_id: uuid.UUID,
    matching: set[uuid.UUID],
    considered: set[uuid.UUID] | None,
) -> None:
    """Adds matching Jobs; removes considered Jobs that no longer match, unless the User
    hid them (their choice is kept if the Job comes back)."""
    rows = [{"id": uuid.uuid4(), "user_id": user_id, "job_id": j} for j in matching]
    # Three parameters per row; chunks stay far below asyncpg's 32,767 per statement.
    for start in range(0, len(rows), LINK_CHUNK):
        await session.execute(
            insert(UserJob)
            .values(rows[start : start + LINK_CHUNK])
            .on_conflict_do_nothing(index_elements=["user_id", "job_id"])
        )
    stale = delete(UserJob).where(
        UserJob.user_id == user_id,
        UserJob.hidden_at.is_(None),
        ~among(UserJob.job_id, matching),
    )
    if considered is not None:
        stale = stale.where(UserJob.job_id.in_(considered))
    await session.execute(stale)


async def sync_user_feed(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Rebuilds one User's Feed from their current Preferences. Returns its size."""
    preference = await session.scalar(select(Preference).where(Preference.user_id == user_id))
    jobs = await _open_jobs(session)
    matching = (
        {j.id for j in jobs if job_matches(j.title, j.locations, j.work_mode, preference)}
        if preference
        else set()
    )
    await _apply_links(session, user_id, matching, None)
    return len(matching)


async def sync_all_feeds(session: AsyncSession) -> None:
    jobs = await _open_jobs(session)
    for preference in (await session.execute(select(Preference))).scalars():
        matching = {
            j.id for j in jobs if job_matches(j.title, j.locations, j.work_mode, preference)
        }
        await _apply_links(session, preference.user_id, matching, None)


async def sync_job_for_all(session: AsyncSession, job_id: uuid.UUID) -> None:
    """After a merge or split, links one Job for every User it now matches."""
    jobs = await _open_jobs(session, [job_id])
    for preference in (await session.execute(select(Preference))).scalars():
        matching = {
            j.id for j in jobs if job_matches(j.title, j.locations, j.work_mode, preference)
        }
        await _apply_links(session, preference.user_id, matching, {job_id})


# --- Reading the Feed -------------------------------------------------------------------------


def _labels() -> dict[str, str]:
    return {cls.name: cls.label for cls in registered_adapters()}


async def load_user_skills(session: AsyncSession, user: User) -> UserSkills:
    facts = (
        await session.execute(select(Fact.kind, Fact.text).where(Fact.user_id == user.id))
    ).all()
    return user_skills((f.text for f in facts if f.kind == FactKind.SKILL), (f.text for f in facts))


def _filtered(user: User, query: FeedQuery, now: datetime) -> Select[tuple[Job, UserJob]]:
    stmt = (
        select(Job, UserJob)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(UserJob.user_id == user.id, Job.expired_at.is_(None))
    )
    stmt = stmt.where(
        UserJob.hidden_at.is_not(None) if query.hidden else UserJob.hidden_at.is_(None)
    )
    if query.q:
        pattern = f"%{query.q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(pattern), Job.company_name.ilike(pattern)))
    if query.work_mode:
        stmt = stmt.where(Job.work_mode == query.work_mode.value)
    if query.source:
        stmt = stmt.where(query.source == any_(Job.sources))
    if query.posted_within_days:
        stmt = stmt.where(Job.posted_at >= now - timedelta(days=query.posted_within_days))
    if query.location:
        stmt = stmt.where(
            text(
                "EXISTS (SELECT 1 FROM jsonb_array_elements(jobs.locations) AS l "
                "WHERE l->>'city' ILIKE :loc OR upper(l->>'country') = upper(:loc))"
            ).bindparams(loc=query.location.strip())
        )
    return stmt


def _section(stmt: Select[tuple[Job, UserJob]], with_email: bool) -> Select[tuple[Job, UserJob]]:
    return stmt.where(Job.contact_email.is_not(None) if with_email else Job.contact_email.is_(None))


async def _count(session: AsyncSession, stmt: Select[tuple[Job, UserJob]]) -> int:
    return int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


async def _possible_duplicates(
    session: AsyncSession, job_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Jobs with an open Medium pair to a Posting of another Job (FR-C3)."""
    if not job_ids:
        return set()
    rows = await session.execute(
        text(
            "SELECT pa.job_id, pb.job_id FROM match_pairs m "
            "JOIN postings pa ON pa.id = m.posting_a_id "
            "JOIN postings pb ON pb.id = m.posting_b_id "
            "WHERE m.status = 'open' AND pa.job_id <> pb.job_id "
            "AND (pa.job_id = ANY(:ids) OR pb.job_id = ANY(:ids))"
        ),
        {"ids": list(job_ids)},
    )
    flagged = {job for pair in rows.all() for job in pair}
    return flagged & set(job_ids)


def _locations(job: Job) -> list[LocationOut]:
    return [LocationOut.model_validate(loc) for loc in job.locations or []]


APPLIED_RECENTLY = timedelta(days=90)


async def package_states(
    session: AsyncSession,
    user: User,
    jobs: list[Job],
    now: datetime | None = None,
) -> tuple[dict[uuid.UUID, uuid.UUID], dict[uuid.UUID, str], set[uuid.UUID]]:
    """Each Job's Draft and Application status, and the Jobs that get the "Already applied
    to this Company" warning: the User applied to another Job at the same Company in the
    last 90 days (FR-D5). Always scoped to this User."""
    if not jobs:
        return {}, {}, set()
    now = now or datetime.now(UTC)
    job_ids = [job.id for job in jobs]
    company_ids = {job.company_id for job in jobs}
    drafts = await session.scalars(
        select(Draft)
        .where(Draft.user_id == user.id, Draft.job_id.in_(job_ids))
        .order_by(Draft.created_at.desc(), Draft.id.desc())
    )
    draft_ids: dict[uuid.UUID, uuid.UUID] = {}
    for draft in drafts:
        draft_ids.setdefault(draft.job_id, draft.id)
    applications = await session.execute(
        select(Application, Job.company_id)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id, Job.company_id.in_(company_ids))
    )
    states: dict[uuid.UUID, str] = {}
    applied_jobs: dict[uuid.UUID, set[uuid.UUID]] = {}
    for application, company_id in applications:
        states[application.job_id] = application.status
        # "Applied or later" (FR-D5): every status past Drafted keeps applied_at set.
        if application.applied_at and application.applied_at >= now - APPLIED_RECENTLY:
            applied_jobs.setdefault(company_id, set()).add(application.job_id)
    warned = {job.id for job in jobs if applied_jobs.get(job.company_id, set()) - {job.id}}
    return draft_ids, states, warned


async def last_updated(session: AsyncSession) -> datetime | None:
    return await session.scalar(
        select(func.max(FetchRun.finished_at)).where(FetchRun.status == RunStatus.SUCCEEDED)
    )


async def list_feed(
    session: AsyncSession, user: User, query: FeedQuery, now: datetime | None = None
) -> FeedOut:
    now = now or datetime.now(UTC)
    base = _filtered(user, query, now)
    counts = FeedCounts(
        with_email=await _count(session, _section(base, True)),
        apply_link_only=await _count(session, _section(base, False)),
    )
    stmt = (
        _section(base, query.section == "email")
        .order_by(Job.posted_at.desc().nulls_last(), Job.id)
        .limit(query.limit)
        .offset(query.offset)
    )
    rows = (await session.execute(stmt)).all()
    skills = await load_user_skills(session, user)
    duplicates = await _possible_duplicates(session, [job.id for job, _ in rows])
    labels = _labels()
    draft_ids, application_states, applied_companies = await package_states(
        session, user, [job for job, _ in rows]
    )
    items = [
        FeedCard(
            job_id=job.id,
            title=job.title,
            company=job.company_name,
            locations=_locations(job),
            work_mode=job.work_mode,
            posted_at=job.posted_at,
            sources=[SourceBadge(name=s, label=labels.get(s, s)) for s in job.sources],
            contact_email=job.contact_email,
            apply_url=job.apply_url,
            skill_gaps=None
            if job.required_skills is None
            else skill_gaps(job.required_skills, skills),
            possible_duplicate=job.id in duplicates,
            hidden=link.hidden_at is not None,
            draft_id=draft_ids.get(job.id),
            application_status=application_states.get(job.id),
            company_applied=job.id in applied_companies,
        )
        for job, link in rows
    ]
    total = counts.with_email if query.section == "email" else counts.apply_link_only
    return FeedOut(
        items=items,
        total=total,
        counts=counts,
        last_updated_at=await last_updated(session),
        sources=[SourceBadge(name=cls.name, label=cls.label) for cls in registered_adapters()],
    )


async def _link(session: AsyncSession, user: User, job_id: uuid.UUID) -> UserJob:
    link = await session.scalar(
        select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == job_id)
    )
    if link is None:
        raise NotFoundError("Job not found in your feed")
    return link


async def set_hidden(session: AsyncSession, user: User, job_id: uuid.UUID, hidden: bool) -> None:
    """Hiding is personal: other Users' Feeds are untouched (FR-D6)."""
    link = await _link(session, user, job_id)
    link.hidden_at = datetime.now(UTC) if hidden else None
    await session.flush()


# --- Correspondence view (FR-C6) ----------------------------------------------------------------


def _posting_out(posting: Posting, labels: dict[str, str], primary: uuid.UUID | None) -> PostingOut:
    return PostingOut(
        id=posting.id,
        source=SourceBadge(name=posting.source, label=labels.get(posting.source, posting.source)),
        title=posting.title,
        locations=[LocationOut.model_validate(loc) for loc in posting.locations or []],
        work_mode=posting.work_mode,
        posted_at=posting.posted_at,
        first_seen_at=posting.first_seen_at,
        apply_url=posting.apply_url,
        contact_email=posting.contact_email,
        closed=posting.closed_at is not None,
        primary=posting.id == primary,
    )


async def _postings_of(session: AsyncSession, job_id: uuid.UUID) -> list[Posting]:
    rows = await session.execute(
        select(Posting).where(Posting.job_id == job_id).order_by(Posting.first_seen_at)
    )
    return list(rows.scalars())


async def job_detail(session: AsyncSession, user: User, job_id: uuid.UUID) -> JobDetailOut:
    """The full stack of Postings for one Job in the User's Feed, whatever their priority,
    plus its open Possible Duplicates."""
    link = await _link(session, user, job_id)
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found in your feed")
    labels = _labels()
    draft_ids, application_states, applied_companies = await package_states(session, user, [job])
    priorities = {cls.name: cls.priority for cls in registered_adapters()}
    postings = await _postings_of(session, job_id)
    postings.sort(key=lambda p: (p.id != job.primary_posting_id, priorities.get(p.source, 99)))
    primary = next((p for p in postings if p.id == job.primary_posting_id), None)
    posting_ids = [p.id for p in postings]
    pairs = (
        await session.execute(
            select(MatchPair).where(
                MatchPair.status == PairStatus.OPEN,
                or_(
                    MatchPair.posting_a_id.in_(posting_ids),
                    MatchPair.posting_b_id.in_(posting_ids),
                ),
            )
        )
    ).scalars()
    duplicates: list[PossibleDuplicateOut] = []
    for pair in pairs:
        mine, other_id = (
            (pair.posting_a_id, pair.posting_b_id)
            if pair.posting_a_id in posting_ids
            else (pair.posting_b_id, pair.posting_a_id)
        )
        other = await session.get(Posting, other_id)
        if other is None or other.job_id == job_id or other.job_id is None:
            continue
        other_job = await session.get(Job, other.job_id)
        in_feed = await session.scalar(
            select(UserJob.id).where(
                and_(UserJob.user_id == user.id, UserJob.job_id == other.job_id)
            )
        )
        duplicates.append(
            PossibleDuplicateOut(
                pair_id=pair.id,
                posting_id=mine,
                other_job_id=other.job_id,
                other_job_in_feed=in_feed is not None,
                other_title=other_job.title if other_job else other.title,
                other_company=other_job.company_name if other_job else "",
                other_postings=[
                    _posting_out(p, labels, other_job.primary_posting_id if other_job else None)
                    for p in await _postings_of(session, other.job_id)
                ],
                title_similarity=_signal(pair.signals, "title"),
                description_similarity=_signal(pair.signals, "description"),
            )
        )
    skills = await load_user_skills(session, user)
    return JobDetailOut(
        job_id=job.id,
        title=job.title,
        company=job.company_name,
        company_id=job.company_id,
        description=primary.description if primary else "",
        locations=_locations(job),
        work_mode=job.work_mode,
        posted_at=job.posted_at,
        contact_email=job.contact_email,
        apply_url=job.apply_url,
        sources=[SourceBadge(name=s, label=labels.get(s, s)) for s in job.sources],
        required_skills=job.required_skills,
        skill_gaps=None if job.required_skills is None else skill_gaps(job.required_skills, skills),
        hidden=link.hidden_at is not None,
        expired=job.expired_at is not None,
        postings=[_posting_out(p, labels, job.primary_posting_id) for p in postings],
        possible_duplicates=duplicates,
        draft_id=draft_ids.get(job.id),
        application_status=application_states.get(job.id),
        company_applied=job.id in applied_companies,
    )


def _signal(signals: dict[str, object], key: str) -> float | None:
    value = signals.get(key)
    return float(value) if isinstance(value, int | float) else None
