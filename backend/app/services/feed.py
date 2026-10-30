"""Feed (Epic D): each User's links to the shared Jobs that match their Preferences.

A Feed entry is a `user_jobs` row, never a copy of the Job (ADR-0002). Every query here is
scoped by user_id; nothing a User does to their Feed changes another User's (ADR-0001)."""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, any_, delete, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.adapters.normalize import normalize_city
from app.adapters.posting_policy import BLOCKED_COMPANIES
from app.adapters.registry import registered_adapters
from app.core.db import among
from app.core.errors import NotFoundError
from app.dedup.scoring import clean_title
from app.models.draft import Application, Draft
from app.models.fact import Fact, FactKind
from app.models.fetch import FetchRun, RunStatus
from app.models.job import Job, MatchPair, PairStatus, UserJob
from app.models.posting import Company, Posting
from app.models.preference import Preference
from app.models.user import User
from app.schemas.feed import (
    ArchivedDraftOut,
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
from app.tailoring.description_mentions import CACHE_VERSION, VOCABULARY
from app.tailoring.keywords import (
    MIN_DESCRIPTION_CHARS,
    KeywordMatch,
    KeywordRule,
    has_core,
    has_description,
    keyword_matches,
    keyword_rule,
    mentioned,
    qualifies,
)
from app.tailoring.skills import (
    UserSkills,
    canonical_skill,
    skill_gaps,
    skill_matches,
    spellings,
    user_skills,
)

SITE_SOURCE_PREFIX = "site:"

LINK_CHUNK = 1000

# Two-word spellings that are one word in other titles ("Dev-Ops" = "DevOps"), joined
# before single words are mapped, so both sides end up with the same words.
_JOINED: dict[tuple[str, str], str] = {
    ("dev", "ops"): "devops",
    ("back", "end"): "backend",
    ("front", "end"): "frontend",
    ("full", "stack"): "fullstack",
    ("machine", "learning"): "ml",
    ("server", "side"): "backend",
    ("site", "reliability"): "sre",
    ("quality", "assurance"): "qa",
    ("artificial", "intelligence"): "ai",
    # "Software Development Engineer" = "Software Engineer" = "SDE"
    ("development", "engineer"): "engineer",
}
# Spellings that name the same role word ("Backend Developer" = "Backend Engineer").
_TITLE_WORDS: dict[str, tuple[str, ...]] = {
    "developer": ("engineer",),
    "dev": ("engineer",),
    "programmer": ("engineer",),
    "engg": ("engineer",),
    "eng": ("engineer",),
    "serverside": ("backend",),
    "ui": ("frontend",),
    "sre": ("sre", "engineer"),
    "ror": ("ruby", "on", "rails"),
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


def _city_key(value: object) -> str:
    """Compared the way Jobs store cities, so "Bangalore" matches "Bengaluru" even for
    Preferences saved before cities were normalised."""
    return (normalize_city(str(value)) or "").lower() if value else ""


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
        city = _city_key(location.get("city"))
        country = str(location.get("country") or "").upper()
        remote = job_work_mode == "remote" or bool(location.get("remote"))
        if not country and not city:
            return True
        for place in wanted:
            want_country = str(place.get("country") or "").upper()
            want_city = _city_key(place.get("city"))
            if country and country != want_country:
                continue
            if want_city and city and city != want_city and not remote:
                continue
            return True
    return False


def place_matches(
    locations: Sequence[dict[str, object]], work_mode: str | None, preference: Preference
) -> bool:
    """Places and work mode, which every Feed entry must match, by title or keywords."""
    modes = preference.work_modes or []
    if work_mode and modes and work_mode not in modes:
        return False
    return location_matches(locations, work_mode, preference.locations or [], modes)


def job_matches(
    title: str,
    locations: Sequence[dict[str, object]],
    work_mode: str | None,
    preference: Preference,
) -> bool:
    """Title, places and work mode (FR-D1). Keywords never narrow the Feed."""
    return place_matches(locations, work_mode, preference) and title_matches(
        title, preference.titles or []
    )


def rule_of(preference: Preference) -> KeywordRule | None:
    return keyword_rule(
        preference.keywords or [],
        preference.core_keywords or [],
        preference.keyword_min_matches or 2,
    )


@dataclass(frozen=True)
class FeedMatch:
    kind: str  # "title" | "keywords" | "review"
    keywords: tuple[KeywordMatch, ...] = ()

    def columns(self) -> dict[str, object]:
        return {"match_kind": self.kind, "matched_keywords": [m.as_dict() for m in self.keywords]}


TITLE_MATCH = FeedMatch("title")
# A title match whose advert has no usable description: nothing can confirm a Core skill.
REVIEW_MATCH = FeedMatch("review")


# --- Linking --------------------------------------------------------------------------------


def _allowed_company():  # noqa: ANN202
    return ~Job.company_id.in_(
        select(Company.id).where(Company.normalized_name.in_(BLOCKED_COMPANIES))
    )


async def _open_jobs(session: AsyncSession, job_ids: Iterable[uuid.UUID] | None = None):  # noqa: ANN202
    query = select(
        Job.id,
        Job.title,
        Job.locations,
        Job.work_mode,
        Job.required_skills,
        Job.primary_posting_id,
    ).where(
        Job.expired_at.is_(None),
        _allowed_company(),
        or_(
            ~exists().where(
                Posting.job_id == Job.id,
                Posting.closed_at.is_(None),
                Posting.source.in_([cls.name for cls in registered_adapters() if cls.push_only]),
            ),
            exists().where(
                Posting.job_id == Job.id,
                Posting.closed_at.is_(None),
                Posting.source.not_in([cls.name for cls in registered_adapters() if cls.push_only]),
            ),
        ),
    )
    if job_ids is not None:
        query = query.where(Job.id.in_(list(job_ids)))
    return (await session.execute(query)).all()


# Title-matched adverts shorter than this are always read: has_description may call them
# too short to confirm a Core keyword (Needs review) once whitespace is trimmed.
SHORT_DESCRIPTION_READ = MIN_DESCRIPTION_CHARS * 10


async def _matches(
    session: AsyncSession, jobs: Sequence[Any], preferences: Sequence[Preference]
) -> dict[uuid.UUID, dict[uuid.UUID, FeedMatch]]:
    """User id -> Job id -> why that Job is in the User's Feed.

    Every Job must be in a wanted place and work mode. Then:
    - no Core keyword: a title match is enough;
    - with Core keywords (must-have skills), only the job description's own text counts
      (never the title, nor skills extracted from it alone, which may come from the title):
      - a title match whose description names a Core keyword: "title";
      - a title match without a usable description: "review", shown apart, never as a
        confirmed match;
      - a differently titled Job whose description names a Core keyword and
        keyword_min_matches keywords in total: "keywords".
    Current cached vocabulary mentions need no description reads. Unknown keywords and
    missing/stale caches retain exact description matching as a fallback."""
    result: dict[uuid.UUID, dict[uuid.UUID, FeedMatch]] = {p.user_id: {} for p in preferences}
    rules = {p.user_id: rule_of(p) for p in preferences}
    # Job id -> (user id, rule, whether the title matched) for each keyword check.
    pending: dict[uuid.UUID, list[tuple[uuid.UUID, KeywordRule, bool]]] = {}
    for preference in preferences:
        rule = rules[preference.user_id]
        for job in jobs:
            if not place_matches(job.locations, job.work_mode, preference):
                continue
            titled = title_matches(job.title, preference.titles or [])
            if rule is None:
                if titled:
                    result[preference.user_id][job.id] = TITLE_MATCH
                continue
            pending.setdefault(job.id, []).append((preference.user_id, rule, titled))
    if not pending:
        return result
    terms = frozenset().union(*(r.terms for r in rules.values() if r is not None))
    # A Core mention is required for every confirmed match. Check the literal spellings
    # in PostgreSQL first so unrelated multi-KB descriptions never cross the network.
    # ILIKE is deliberately a broad filter; Python's whole-word and capitalization
    # checks below remain the final authority.
    core_spellings = {
        spelling
        for rule in rules.values()
        if rule is not None
        for keyword in rule.keywords
        if keyword.core
        for spelling in spellings(keyword.canonical)
        if spelling
    }
    mentions_core = or_(
        *(
            Posting.description.ilike(f"%{_like_literal(term)}%", escape="\\")
            for term in core_spellings
        )
    )
    by_id = {job.id: job for job in jobs}
    ids = list(pending)
    for start in range(0, len(ids), LINK_CHUNK):
        chunk = [by_id[i] for i in ids[start : start + LINK_CHUNK]]
        posting_ids = [j.primary_posting_id for j in chunk if j.primary_posting_id]
        titled_ids = [
            j.primary_posting_id
            for j in chunk
            if j.primary_posting_id and any(titled for _, _, titled in pending[j.id])
        ]
        caches = {
            row.id: row
            for row in (
                await session.execute(
                    select(
                        Posting.id,
                        Posting.description_mentions,
                        Posting.description_usable,
                        Posting.description_mentions_version,
                    ).where(Posting.id.in_(posting_ids))
                )
            ).all()
        }
        current = {
            pid: row
            for pid, row in caches.items()
            if row.description_mentions_version == CACHE_VERSION
            and row.description_mentions is not None
            and row.description_usable is not None
        }
        stale = set(posting_ids) - current.keys()
        # Until explicitly backfilled, old/version-mismatched rows keep the existing
        # broad SQL prefilter and exact Python checks. Feed reads never write caches.
        descriptions = {}
        if stale:
            descriptions = dict(
                (
                    await session.execute(
                        select(Posting.id, Posting.description).where(
                            Posting.id.in_(stale),
                            or_(
                                mentions_core,
                                and_(
                                    Posting.id.in_(titled_ids),
                                    func.length(Posting.description) < SHORT_DESCRIPTION_READ,
                                ),
                            ),
                        )
                    )
                ).all()
            )
        unknown = {term for term in terms if canonical_skill(term) not in VOCABULARY}
        # Unknown non-Core terms matter too: they can satisfy min_matches. Restrict
        # fallback to current, usable postings considered for a User with such terms.
        unknown_ids = {
            job.primary_posting_id
            for job in chunk
            if job.primary_posting_id in current
            and current[job.primary_posting_id].description_usable
            and any(
                any(k.canonical not in VOCABULARY for k in rule.keywords)
                for _, rule, _ in pending[job.id]
            )
        }
        unknown_descriptions = {}
        if unknown_ids:
            possible_unknown = or_(
                *(
                    Posting.description.ilike(f"%{_like_literal(spelling)}%", escape="\\")
                    for term in unknown
                    for spelling in spellings(canonical_skill(term))
                )
            )
            unknown_descriptions = dict(
                (
                    await session.execute(
                        select(Posting.id, Posting.description).where(
                            Posting.id.in_(unknown_ids), possible_unknown
                        )
                    )
                ).all()
            )
        for job in chunk:
            pid = job.primary_posting_id
            if pid in current:
                in_description = set(current[pid].description_mentions)
                in_description.update(mentioned(unknown_descriptions.get(pid, ""), unknown))
                described = current[pid].description_usable
            else:
                if pid and pid not in descriptions:
                    continue
                in_description = mentioned(descriptions.get(pid) or "", terms)
                described = has_description(descriptions.get(pid) or "")
            required = list(job.required_skills or [])
            in_requirements = mentioned(", ".join(required), terms) | {
                canonical_skill(s) for s in required
            }
            for user_id, rule, titled in pending[job.id]:
                found = keyword_matches(rule, in_requirements, in_description)
                if titled and not described:
                    result[user_id][job.id] = REVIEW_MATCH
                elif titled and has_core(found):
                    result[user_id][job.id] = FeedMatch("title", tuple(found))
                elif not titled and described and qualifies(rule, found):
                    result[user_id][job.id] = FeedMatch("keywords", tuple(found))
    return result


async def _apply_links(
    session: AsyncSession,
    user_id: uuid.UUID,
    matching: dict[uuid.UUID, FeedMatch],
    considered: set[uuid.UUID] | None,
) -> None:
    """Adds matching Jobs and refreshes why each is there; removes considered Jobs that no
    longer match, unless the User hid or saved them (their choice is kept if the Job comes
    back) or has a Draft or Application for them: those stay reachable from the tracker after the
    Job closes or Preferences change, marked as no longer matching."""
    rows = [
        {"id": uuid.uuid4(), "user_id": user_id, "job_id": job_id, **match.columns()}
        for job_id, match in matching.items()
    ]
    # Five parameters per row; chunks stay far below asyncpg's 32,767 per statement.
    for start in range(0, len(rows), LINK_CHUNK):
        stmt = insert(UserJob).values(rows[start : start + LINK_CHUNK])
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["user_id", "job_id"],
                set_={
                    "match_kind": stmt.excluded.match_kind,
                    "matched_keywords": stmt.excluded.matched_keywords,
                },
                # Unchanged links are not rewritten on every sync.
                where=or_(
                    UserJob.match_kind.is_distinct_from(stmt.excluded.match_kind),
                    UserJob.matched_keywords != stmt.excluded.matched_keywords,
                ),
            )
        )
    gone = [
        UserJob.user_id == user_id,
        ~among(UserJob.job_id, set(matching)),
    ]
    if considered is not None:
        gone.append(UserJob.job_id.in_(considered))
    await session.execute(
        delete(UserJob).where(
            *gone,
            UserJob.hidden_at.is_(None),
            UserJob.saved_at.is_(None),
            UserJob.captured_at.is_(None),
            ~exists().where(Draft.user_id == user_id, Draft.job_id == UserJob.job_id),
            ~exists().where(Application.user_id == user_id, Application.job_id == UserJob.job_id),
        )
    )
    await session.execute(
        update(UserJob)
        .where(*gone, UserJob.match_kind.is_not(None))
        .values(match_kind=None, matched_keywords=[])
    )


async def sync_user_feed(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Rebuilds one User's Feed from their current Preferences. Returns its size."""
    preference = await session.scalar(select(Preference).where(Preference.user_id == user_id))
    matching: dict[uuid.UUID, FeedMatch] = {}
    if preference:
        matching = (await _matches(session, await _open_jobs(session), [preference]))[user_id]
    await _apply_links(session, user_id, matching, None)
    return len(matching)


async def sync_all_feeds(session: AsyncSession) -> None:
    jobs = await _open_jobs(session)
    preferences = list((await session.execute(select(Preference))).scalars())
    for user_id, matching in (await _matches(session, jobs, preferences)).items():
        await _apply_links(session, user_id, matching, None)


async def sync_job_for_all(session: AsyncSession, job_id: uuid.UUID) -> None:
    """After a merge or split, links one Job for every User it now matches."""
    await sync_jobs_for_all(session, {job_id})


async def sync_jobs_for_all(session: AsyncSession, job_ids: set[uuid.UUID]) -> None:
    """Rechecks some Jobs for every User, e.g. once their required skills are extracted,
    so each match reason is current without waiting for the next Fetch Run."""
    if not job_ids:
        return
    jobs = await _open_jobs(session, job_ids)
    preferences = list((await session.execute(select(Preference))).scalars())
    for user_id, matching in (await _matches(session, jobs, preferences)).items():
        await _apply_links(session, user_id, matching, job_ids)


# --- Reading the Feed -------------------------------------------------------------------------


def _labels() -> dict[str, tuple[str, str | None]]:
    return {cls.name: (cls.label, cls.site) for cls in registered_adapters()}


async def load_user_skills(session: AsyncSession, user: User) -> UserSkills:
    facts = (
        await session.execute(select(Fact.kind, Fact.text).where(Fact.user_id == user.id))
    ).all()
    return user_skills((f.text for f in facts if f.kind == FactKind.SKILL), (f.text for f in facts))


def _requirements(job: Job, link: UserJob) -> list[str] | None:
    return link.page_required_skills if link.captured_at is not None else job.required_skills


def _filtered(user: User, query: FeedQuery, now: datetime) -> Select[tuple[Job, UserJob]]:
    stmt = (
        select(Job, UserJob)
        .options(defer(UserJob.page_description))
        .join(UserJob, UserJob.job_id == Job.id)
        .where(UserJob.user_id == user.id, _allowed_company())
    )
    view = _view(query)
    if view == "saved":
        # Every bookmark, hidden or expired included: the User chose to keep it.
        stmt = stmt.where(UserJob.saved_at.is_not(None))
    else:
        stmt = stmt.where(
            Job.expired_at.is_(None),
            UserJob.hidden_at.is_not(None) if view == "hidden" else UserJob.hidden_at.is_(None),
        )
    if query.viewed != "any":
        stmt = stmt.where(
            UserJob.viewed_at.is_not(None)
            if query.viewed == "viewed"
            else UserJob.viewed_at.is_(None)
        )
    if query.q:
        pattern = f"%{_like_literal(query.q.strip())}%"
        stmt = stmt.where(
            or_(
                Job.title.ilike(pattern, escape="\\"),
                Job.company_name.ilike(pattern, escape="\\"),
            )
        )
    if query.work_mode:
        stmt = stmt.where(Job.work_mode == query.work_mode.value)
    if query.source:
        if query.source.startswith(SITE_SOURCE_PREFIX):
            site = query.source[len(SITE_SOURCE_PREFIX) :]
            names = [cls.name for cls in registered_adapters() if cls.site == site]
            stmt = stmt.where(Job.sources.overlap(names)) if names else stmt.where(text("false"))
        else:
            stmt = stmt.where(query.source == any_(Job.sources))
    if query.posted_within_days:
        stmt = stmt.where(Job.posted_at >= now - timedelta(days=query.posted_within_days))
    if query.location:
        stmt = stmt.where(
            text(
                "EXISTS (SELECT 1 FROM jsonb_array_elements(jobs.locations) AS l "
                "WHERE l->>'city' ILIKE :city ESCAPE '\\' OR upper(l->>'country') = upper(:loc))"
            ).bindparams(city=_like_literal(query.location.strip()), loc=query.location.strip())
        )
    return stmt


def _view(query: FeedQuery) -> str:
    return "hidden" if query.hidden and query.view == "all" else query.view


async def saved_count(session: AsyncSession, user: User) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(UserJob)
            .join(Job, Job.id == UserJob.job_id)
            .where(UserJob.user_id == user.id, UserJob.saved_at.is_not(None), _allowed_company())
        )
        or 0
    )


def _like_literal(value: str) -> str:
    """A User's search text matched literally: "%" and "_" are not wildcards."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _match(stmt: Select[tuple[Job, UserJob]], kind: str) -> Select[tuple[Job, UserJob]]:
    """Jobs that no longer match stay with the title matches, where the User found them."""
    if kind in ("keywords", "review"):
        return stmt.where(UserJob.match_kind == kind)
    return stmt.where(or_(UserJob.match_kind.is_(None), UserJob.match_kind == "title"))


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
        .where(Draft.user_id == user.id, Draft.active.is_(True), Draft.job_id.in_(job_ids))
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
    filtered = _filtered(user, query, now)
    saved = await saved_count(session, user)
    if _view(query) == "saved":
        # The shortlist ignores match category and email/link section, so no bookmark
        # can look missing; most recently saved first.
        total = await _count(session, filtered)
        counts = FeedCounts(with_email=0, apply_link_only=0, saved=saved)
        stmt = (
            filtered.order_by(UserJob.saved_at.desc(), Job.id)
            .limit(query.limit)
            .offset(query.offset)
        )
    else:
        base = _match(filtered, query.match)
        counts = FeedCounts(
            with_email=await _count(session, _section(base, True)),
            apply_link_only=await _count(session, _section(base, False)),
            title_matches=await _count(session, _match(filtered, "title")),
            keyword_matches=await _count(session, _match(filtered, "keywords")),
            review_matches=await _count(session, _match(filtered, "review")),
            saved=saved,
        )
        total = counts.with_email if query.section == "email" else counts.apply_link_only
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
            experience_requirement=job.experience_requirement,
            sources=[
                SourceBadge(
                    name=s,
                    label=labels.get(s, (s, None))[0],
                    site=labels.get(s, (s, None))[1],
                )
                for s in job.sources
            ],
            contact_email=job.contact_email,
            apply_url=job.apply_url,
            skill_gaps=None
            if _requirements(job, link) is None
            else skill_gaps(_requirements(job, link) or [], skills),
            skill_matches=None
            if _requirements(job, link) is None
            else skill_matches(_requirements(job, link) or [], skills),
            possible_duplicate=job.id in duplicates,
            hidden=link.hidden_at is not None,
            saved=link.saved_at is not None,
            viewed=link.viewed_at is not None,
            expired=job.expired_at is not None,
            draft_id=draft_ids.get(job.id),
            application_status=application_states.get(job.id),
            company_applied=job.id in applied_companies,
            match=link.match_kind,
            matched_keywords=link.matched_keywords or [],
        )
        for job, link in rows
    ]
    return FeedOut(
        items=items,
        total=total,
        counts=counts,
        last_updated_at=await last_updated(session),
        sources=[
            SourceBadge(name=cls.name, label=cls.label, site=cls.site)
            for cls in registered_adapters()
        ],
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


async def set_saved(session: AsyncSession, user: User, job_id: uuid.UUID, saved: bool) -> None:
    """Saving is personal and separate from hiding: saving never unhides a Job."""
    link = await _link(session, user, job_id)
    if saved and link.saved_at is None:
        link.saved_at = datetime.now(UTC)
    elif not saved:
        link.saved_at = None
    await session.flush()


async def mark_viewed(session: AsyncSession, user: User, job_id: uuid.UUID) -> None:
    """Records the first time the User opened the Job page."""
    link = await _link(session, user, job_id)
    if link.viewed_at is None:
        link.viewed_at = datetime.now(UTC)
        await session.flush()


# --- Correspondence view (FR-C6) ----------------------------------------------------------------


def _posting_out(
    posting: Posting, labels: dict[str, tuple[str, str | None]], primary: uuid.UUID | None
) -> PostingOut:
    return PostingOut(
        id=posting.id,
        source=SourceBadge(
            name=posting.source,
            label=labels.get(posting.source, (posting.source, None))[0],
            site=labels.get(posting.source, (posting.source, None))[1],
        ),
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
        description=str(link.page_description["description"])
        if link.page_description
        else primary.description
        if primary
        else "",
        description_origin={
            "kind": "page",
            "url": link.page_description.get("url"),
            "read_at": link.page_description.get("read_at"),
        }
        if link.page_description
        else {
            "kind": "source",
            "label": labels.get(primary.source, (primary.source, None))[0]
            if primary
            else "Unknown source",
            "url": primary.apply_url if primary else None,
        },
        experience_requirement=job.experience_requirement,
        locations=_locations(job),
        work_mode=job.work_mode,
        posted_at=job.posted_at,
        contact_email=job.contact_email,
        apply_url=job.apply_url,
        sources=[
            SourceBadge(name=s, label=labels.get(s, (s, None))[0], site=labels.get(s, (s, None))[1])
            for s in job.sources
        ],
        required_skills=_requirements(job, link),
        skill_gaps=None
        if _requirements(job, link) is None
        else skill_gaps(_requirements(job, link) or [], skills),
        skill_matches=None
        if _requirements(job, link) is None
        else skill_matches(_requirements(job, link) or [], skills),
        hidden=link.hidden_at is not None,
        expired=job.expired_at is not None,
        saved=link.saved_at is not None,
        viewed=link.viewed_at is not None,
        postings=[_posting_out(p, labels, job.primary_posting_id) for p in postings],
        possible_duplicates=duplicates,
        draft_id=draft_ids.get(job.id),
        archived_drafts=[
            ArchivedDraftOut(id=d.id, created_at=d.created_at, current_version=d.current_version)
            for d in await session.scalars(
                select(Draft)
                .where(Draft.user_id == user.id, Draft.job_id == job.id, Draft.active.is_(False))
                .order_by(Draft.created_at.desc())
            )
        ],
        application_status=application_states.get(job.id),
        company_applied=job.id in applied_companies,
        match=link.match_kind,
        matched_keywords=link.matched_keywords or [],
    )


def _signal(signals: dict[str, object], key: str) -> float | None:
    value = signals.get(key)
    return float(value) if isinstance(value, int | float) else None
