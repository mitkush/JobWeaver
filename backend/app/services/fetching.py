"""Fetch orchestration (FR-B3 to FR-B11). Every Source runs in isolation (ADR-0003):
a failure marks that Source Degraded and the run moves on to the next one."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import String, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.ats_urls import parse_ats_url
from app.adapters.base import (
    FetchResult,
    FetchWindow,
    Location,
    NormalizedPosting,
    PendingAdvert,
    SnapshotSourceAdapter,
    SourceAdapter,
    SourceQuery,
    WindowedSourceAdapter,
    WorkMode,
)
from app.adapters.errors import (
    BoardNotFound,
    SourceBadResponse,
    SourceCredentialRejected,
    SourceError,
    SourceNotConfigured,
    SourceQuotaExhausted,
    SourceQuotaRejected,
    SourceRateLimited,
    SourceUnavailable,
)
from app.adapters.normalize import normalize_company
from app.adapters.posting_policy import blocked_company
from app.adapters.registry import (
    family_of,
    get_adapter_class,
    pool_of,
    registered_adapters,
    run_order,
    upstream_of,
)
from app.core.config import Settings, get_settings
from app.core.db import among
from app.models.fetch import FetchRun, QueryWatermark, RunStatus
from app.models.posting import AtsBoard, Company, Posting
from app.models.preference import Preference
from app.models.raw_advert import RawAdvert
from app.models.source import Source, SourceState
from app.services.account_balances import account_balance, balance_is_usable
from app.services.provider_credentials import active_primary_pause, credentials
from app.tailoring.description_mentions import CACHE_VERSION, describe
from app.tailoring.job_experience import experience_requirement

logger = logging.getLogger(__name__)

# Any constant works; it only has to be unique to "the fetch runner" in this database.
FETCH_LOCK_ID = 7_201_026
BOARD_DAILY = timedelta(hours=20)
BOARD_STALE_AFTER = timedelta(days=30)
BOARD_WEEKLY = timedelta(days=7)
MANUAL_RUNS_PER_DAY = 4
MANUAL = "manual"
BUSY = "A fetch is already running; try again when it finishes"
# Background manual runs, kept referenced until they finish.
_BACKGROUND: set[asyncio.Task[None]] = set()
# A windowed search done this recently is not repeated by cron or catch-up runs.
ALREADY_FETCHED = timedelta(hours=20)

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


_http = httpx.AsyncClient(
    timeout=httpx.Timeout(60.0, connect=10.0),
    headers={"User-Agent": "JobWeaver/0.1 (personal job search assistant)"},
    follow_redirects=True,
)


def get_sources_http() -> httpx.AsyncClient:
    return _http


# --- Queries -----------------------------------------------------------------------------


def queries_from_preferences(preferences: list[Preference]) -> list[SourceQuery]:
    """One query per distinct (title, location) across all users (FR-B4 AC1), plus one per
    core keyword for Users who chose to search by keywords too (FR-A3)."""
    queries: dict[str, SourceQuery] = {}
    for pref in preferences:
        modes = set(pref.work_modes)
        remote_only = modes == {WorkMode.REMOTE.value}
        terms = list(pref.titles) + (list(pref.core_keywords or []) if pref.search_keywords else [])
        for title in terms:
            # Global preferences still produce searches, without a country/city filter.
            for loc in pref.locations or [{"city": None, "country": None}]:
                country = loc.get("country")
                location = Location(city=loc.get("city"), country=country, remote=remote_only)
                query = SourceQuery(keywords=title, location=location)
                queries.setdefault(query.key, query)
                if WorkMode.REMOTE.value in modes and not remote_only:
                    remote = SourceQuery(
                        keywords=title,
                        location=Location(city=loc.get("city"), country=country, remote=True),
                    )
                    queries.setdefault(remote.key, remote)
    return sorted(queries.values(), key=lambda q: q.key)


# --- Budget -----------------------------------------------------------------------------


def period_start(now: datetime, renewal_day: int) -> datetime:
    start = now.replace(day=min(renewal_day, 28), hour=0, minute=0, second=0, microsecond=0)
    if start > now:
        previous = (start.replace(day=1) - timedelta(days=1)).replace(day=start.day)
        return previous
    return start


def next_renewal(now: datetime, renewal_day: int) -> datetime:
    start = period_start(now, renewal_day)
    month = start.month % 12 + 1
    year = start.year + (1 if start.month == 12 else 0)
    return start.replace(year=year, month=month)


@dataclass
class Budget:
    allowance: int
    unit: str
    spent: int
    projected: int
    period_start: datetime
    renews_on: datetime
    runs_out_on: datetime | None
    top_queries: list[tuple[str, int]]

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.allowance


async def budget_for(
    session: AsyncSession,
    adapter: type[SourceAdapter],
    now: datetime,
    *,
    credential_fingerprint: str | None = None,
    include_legacy: bool = False,
    settings: Settings | None = None,
) -> Budget | None:
    """Spend, month-end projection and the most expensive queries (FR-B5)."""
    allowance = adapter.credit_allowance(settings or get_settings())
    if allowance is None:
        return None
    start = period_start(now, adapter.renewal_day)
    renews = next_renewal(now, adapter.renewal_day)
    in_period = (among(FetchRun.source, pool_of(adapter), String()), FetchRun.created_at >= start)
    if credential_fingerprint is not None:
        scope = FetchRun.credential_fingerprint == credential_fingerprint
        if include_legacy:
            scope = or_(scope, FetchRun.credential_fingerprint.is_(None))
        in_period += (scope,)
    spent = int(
        await session.scalar(
            select(func.coalesce(func.sum(FetchRun.credits_used), 0)).where(*in_period)
        )
        or 0
    )
    rows = await session.execute(
        select(FetchRun.query_key, func.sum(FetchRun.credits_used).label("spent"))
        .where(*in_period, FetchRun.query_key.is_not(None))
        .group_by(FetchRun.query_key)
        .order_by(text("spent DESC"))
        .limit(5)
    )
    elapsed_days = max((now - start).total_seconds() / 86400, 1)
    period_days = (renews - start).total_seconds() / 86400
    daily = spent / elapsed_days
    projected = round(daily * period_days)
    runs_out = None
    if daily > 0 and spent < allowance:
        runs_out = now + timedelta(days=(allowance - spent) / daily)
        if runs_out >= renews:
            runs_out = None
    elif spent >= allowance:
        runs_out = now
    return Budget(
        allowance=allowance,
        unit=adapter.allowance_unit,
        spent=spent,
        projected=projected,
        period_start=start,
        renews_on=renews,
        runs_out_on=runs_out,
        top_queries=[(row.query_key, int(row.spent)) for row in rows if row.spent],
    )


# --- Postings ---------------------------------------------------------------------------


async def _company(session: AsyncSession, name: str, cache: dict[str, Company]) -> Company:
    key = normalize_company(name) or name.lower()
    if key in cache:
        return cache[key]
    company = (
        await session.execute(select(Company).where(Company.normalized_name == key))
    ).scalar_one_or_none()
    if company is None:
        company = Company(name=name.strip()[:255], normalized_name=key[:255])
        session.add(company)
        await session.flush()
    cache[key] = company
    return company


async def _discover_board(session: AsyncSession, apply_url: str | None, company: Company) -> None:
    """Learns company ATS Boards from apply URLs of any Source (ADR-0013)."""
    found = parse_ats_url(apply_url)
    if found is None:
        return
    ats, slug = found
    exists = await session.scalar(
        select(AtsBoard.id).where(AtsBoard.ats == ats, AtsBoard.slug == slug)
    )
    if exists is None:
        session.add(
            AtsBoard(ats=ats, slug=slug, company_id=company.id, discovered_from="apply_url")
        )
        await session.flush()


async def save_postings(
    session: AsyncSession,
    source: str,
    postings: list[NormalizedPosting],
    now: datetime,
    board: AtsBoard | None = None,
) -> tuple[int, set[str]]:
    """Upserts by (source, source_job_id): re-fetches never duplicate (FR-B3 AC2).
    Returns how many were new and the ids seen."""
    companies: dict[str, Company] = {}
    seen: set[str] = set()
    new = 0
    for item in postings:
        if item.source_job_id in seen:
            continue
        seen.add(item.source_job_id)
        if blocked_company(item.company):
            continue
        company = await _company(session, item.company, companies)
        posting = (
            await session.execute(
                select(Posting).where(
                    Posting.source == source, Posting.source_job_id == item.source_job_id
                )
            )
        ).scalar_one_or_none()
        is_new = posting is None
        if posting is None:
            posting = Posting(source=source, source_job_id=item.source_job_id, first_seen_at=now)
            session.add(posting)
            new += 1
        title = item.title[:500]
        if not is_new and (posting.title, posting.description) != (
            title,
            item.description,
        ):
            # The advert changed: its embedding described the old text, so it is
            # recomputed and the Posting compared again (ADR-0014).
            posting.embedding = None
            posting.embedding_model = None
            posting.match_state = "pending"
        if (
            is_new
            or posting.description != item.description
            or posting.description_mentions_version != CACHE_VERSION
            or posting.description_mentions is None
            or posting.description_usable is None
        ):
            cached = describe(item.description)
            posting.description_mentions = cached.skills
            posting.description_usable = cached.usable
            posting.description_mentions_version = cached.version
        posting.company_id = company.id
        posting.ats_board_id = board.id if board else posting.ats_board_id
        posting.title = title
        posting.description = item.description
        posting.experience_requirement = experience_requirement(item.description)
        posting.locations = [loc.model_dump() for loc in item.locations]
        posting.work_mode = item.work_mode.value if item.work_mode else None
        posting.apply_url = item.apply_url[:2048] if item.apply_url else None
        posting.contact_email = item.contact_email
        posting.posted_at = item.posted_at or posting.posted_at
        posting.last_seen_at = now
        if posting.closed_reason in ("board", "age"):
            posting.closed_at = None
            posting.closed_reason = None
        if board is None:
            await _discover_board(session, item.apply_url, company)
    await session.flush()
    return new, seen


async def save_pending(
    session: AsyncSession, source: str, adverts: list[PendingAdvert]
) -> tuple[int, int]:
    """Stores free-text adverts for AI extraction; an edited advert is extracted again.
    Returns how many were new and how many were seen."""
    new = 0
    refs: set[str] = set()
    for advert in adverts:
        if advert.ref in refs:
            continue
        refs.add(advert.ref)
        row = (
            await session.execute(
                select(RawAdvert).where(RawAdvert.source == source, RawAdvert.ref == advert.ref)
            )
        ).scalar_one_or_none()
        if row is None:
            row = RawAdvert(source=source, ref=advert.ref[:255], text=advert.text, attempts=0)
            session.add(row)
            new += 1
        elif row.text != advert.text:
            row.text, row.extracted_at, row.attempts, row.error = advert.text, None, 0, None
        row.url = advert.url[:2048] if advert.url else None
        row.posted_at = advert.posted_at
    await session.flush()
    return new, len(refs)


async def expire_postings(session: AsyncSession, now: datetime, settings: Settings) -> int:
    """Windowed Sources cannot see jobs close, so their Postings expire by age (FR-B10)."""
    cutoff = now - timedelta(days=settings.posting_max_age_days)
    result = await session.execute(
        update(Posting)
        .where(
            Posting.closed_at.is_(None),
            Posting.ats_board_id.is_(None),
            func.coalesce(Posting.posted_at, Posting.first_seen_at) < cutoff,
        )
        .values(closed_at=now, closed_reason="age")
    )
    return result.rowcount or 0


async def daily_run_missed(session: AsyncSession, now: datetime) -> bool:
    """True when no scheduled or cron run started in the last 26 hours.

    The scheduler keeps jobs in memory, so a restart after the daily time would otherwise
    skip that day entirely; the watermark only fixes the window once a run happens."""
    last = await session.scalar(
        select(func.max(FetchRun.created_at)).where(FetchRun.trigger.in_(("schedule", "cron")))
    )
    return last is None or now - last > timedelta(hours=26)


async def fail_running_fetches(
    session: AsyncSession, now: datetime, *, source: str | None = None
) -> int:
    """Close persisted runs left open by an error or an interrupted process."""
    conditions = [FetchRun.status == RunStatus.RUNNING]
    if source is not None:
        conditions.append(FetchRun.source == source)
    result = await session.execute(
        update(FetchRun)
        .where(*conditions)
        .values(
            status=RunStatus.FAILED,
            error="Stopped unexpectedly; retry on the next run",
            finished_at=now,
        )
    )
    return result.rowcount or 0


async def recover_running_fetches(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    """Close unfinished runs only when no other instance owns the fetch lock."""
    async with fetch_lock(sessionmaker) as got:
        if not got:
            logger.info("Fetch recovery skipped: another instance is running a fetch")
            return 0
        async with sessionmaker() as session:
            count = await fail_running_fetches(session, utcnow())
            await session.commit()
    if count:
        logger.warning("Marked %s interrupted fetch runs as failed after restart", count)
    return count


# --- Runner -----------------------------------------------------------------------------


@asynccontextmanager
async def fetch_lock(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[bool]:
    """One fetch or Correspondence run at a time across daily, cron, manual and queue runs
    (and across processes). Yields False when another run holds it."""
    async with sessionmaker() as lock_session:
        got = bool(await lock_session.scalar(text(f"SELECT pg_try_advisory_lock({FETCH_LOCK_ID})")))
        try:
            yield got
        finally:
            if got:
                await lock_session.execute(text(f"SELECT pg_advisory_unlock({FETCH_LOCK_ID})"))
                await lock_session.commit()


@dataclass
class SourceOutcome:
    source: str
    status: str  # succeeded | failed | skipped
    message: str = ""
    postings_new: int = 0
    credits_used: int = 0


class Fetcher:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        http: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
        clock: Clock = utcnow,
        adapter_factory: Callable[[type[SourceAdapter], httpx.AsyncClient, Settings], SourceAdapter]
        | None = None,
        after_fetch: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.http = http or get_sources_http()
        self.settings = settings or get_settings()
        self.clock = clock
        self.adapter_factory = adapter_factory or (lambda cls, http, settings: cls(http, settings))
        # Grouping, Feeds and skills (services.correspondence), run while the lock is held.
        self.after_fetch = after_fetch
        self.manual_task: asyncio.Task[None] | None = None

    async def sync_sources(self) -> None:
        async with self.sessionmaker() as session:
            existing = set((await session.execute(select(Source.name))).scalars())
            for cls in registered_adapters():
                if cls.name not in existing:
                    session.add(Source(name=cls.name, enabled=cls.default_enabled))
            await session.commit()

    def _exclusive(self) -> AbstractAsyncContextManager[bool]:
        return fetch_lock(self.sessionmaker)

    async def run_all(self, trigger: str = "schedule") -> list[SourceOutcome] | None:
        """Runs every enabled Source once. Returns None if another run holds the lock."""
        await self.sync_sources()
        async with self._exclusive() as got:
            if not got:
                logger.info("Fetch run skipped: another run is in progress")
                return None
            outcomes = [await self.run_source(cls.name, trigger) for cls in run_order()]
            async with self.sessionmaker() as session:
                closed = await expire_postings(session, self.clock(), self.settings)
                await session.commit()
            logger.info("Fetch run finished: %s; %s postings expired", outcomes, closed)
            await self._after_fetch()
            return outcomes

    async def _after_fetch(self) -> None:
        if self.after_fetch is None:
            return
        try:
            await self.after_fetch()
        except Exception:
            # Postings are saved; grouping retries on the next run or queue tick.
            logger.exception("Processing fetched postings failed")

    async def run_source(self, name: str, trigger: str = "schedule") -> SourceOutcome:
        cls = get_adapter_class(name)
        if cls.push_only:
            return SourceOutcome(name, "skipped", "This Source only accepts browser captures")
        async with self.sessionmaker() as session:
            source = await self._source_row(session, name)
            if not source.enabled:
                return SourceOutcome(name, "skipped", "disabled")
            if not self.adapter_factory(cls, self.http, self.settings).is_configured():
                # A missing key is a setup choice, not an outage: Source Status says "Not
                # configured", and Users get no "jobs are delayed" notice for it.
                source.state, source.degraded_since, source.last_error = (
                    SourceState.HEALTHY,
                    None,
                    None,
                )
                await session.commit()
                return SourceOutcome(name, "skipped", "not configured")
            if trigger != MANUAL:
                for main_cls in upstream_of(cls):
                    main = await self._source_row(session, main_cls.name)
                    main_works = self.adapter_factory(
                        main_cls, self.http, self.settings
                    ).is_configured()
                    if main.enabled and main_works and main.state != SourceState.DEGRADED:
                        await session.commit()
                        return SourceOutcome(name, "skipped", "standing by")
            now = self.clock()
            # A provider's own call limit (e.g. Remotive: 4 a day) applies to every trigger.
            if cls.min_interval_hours:
                last = source.last_success_at
                if last and now - last < timedelta(hours=cls.min_interval_hours):
                    return SourceOutcome(name, "skipped", "ran recently")
            adapter = self.adapter_factory(cls, self.http, self.settings)
            outcome = SourceOutcome(name, "succeeded")
            try:
                adapter.ensure_configured()
                if isinstance(adapter, WindowedSourceAdapter):
                    await self._run_windowed(session, adapter, trigger, outcome)
                elif isinstance(adapter, SnapshotSourceAdapter):
                    await self._run_snapshot(session, adapter, trigger, outcome)
            except asyncio.CancelledError:
                try:
                    await session.rollback()
                    await fail_running_fetches(session, self.clock(), source=name)
                    await session.commit()
                except Exception:
                    logger.exception("Could not close cancelled fetch runs for %s", name)
                raise
            except SourceError as exc:
                await self._mark_degraded(session, source, exc, now)
                outcome.status = "failed"
                outcome.message = exc.message
                await session.commit()
                return outcome
            except Exception:
                # A bug or database error in one Source must not stop the others (ADR-0003).
                logger.exception("Unexpected error while fetching %s", name)
                await session.rollback()
                source = await self._source_row(session, name)
                await fail_running_fetches(session, self.clock(), source=name)
                error = SourceError(f"{cls.label} failed unexpectedly; see the server logs")
                await self._mark_degraded(session, source, error, now)
                await session.commit()
                return SourceOutcome(name, "failed", error.message)
            source.state = SourceState.HEALTHY
            source.last_success_at = self.clock()
            source.degraded_since = None
            source.last_error = None
            await session.commit()
            return outcome

    @staticmethod
    async def _source_row(session: AsyncSession, name: str) -> Source:
        source = (
            await session.execute(select(Source).where(Source.name == name))
        ).scalar_one_or_none()
        if source is None:
            source = Source(name=name, enabled=get_adapter_class(name).default_enabled)
            session.add(source)
            await session.flush()
        return source

    async def _mark_degraded(
        self, session: AsyncSession, source: Source, exc: SourceError, now: datetime
    ) -> None:
        if source.state != SourceState.DEGRADED:
            source.degraded_since = now
        source.state = SourceState.DEGRADED
        source.last_error = exc.message
        source.last_error_at = now
        if not isinstance(exc, SourceNotConfigured):
            logger.warning("Source %s degraded: %s", source.name, exc.message)

    async def _check_budget(self, session: AsyncSession, adapter: SourceAdapter) -> None:
        options = credentials(type(adapter), self.settings)
        paused_until = active_primary_pause(type(adapter), self.settings, self.clock())
        verified_account = False
        balance_errors: list[str] = []
        for credential in options:
            if credential.primary and paused_until is not None:
                continue
            if credential.fingerprint in adapter.exhausted_credentials:
                continue
            if adapter.credential_limits_from_errors:
                remaining = None
            elif adapter.account_balance_required:
                account = await account_balance(
                    type(adapter), self.http, credential.settings, self.clock(), force=True
                )
                if account is None or account.status != "live" or account.remaining is None:
                    if account and account.message:
                        balance_errors.append(account.message)
                    continue
                verified_account = True
                remaining = account.remaining
                if not balance_is_usable(type(adapter), account):
                    continue
            else:
                budget = await budget_for(
                    session,
                    type(adapter),
                    self.clock(),
                    credential_fingerprint=credential.fingerprint,
                    include_legacy=credential.primary,
                    settings=self.settings,
                )
                remaining = max(budget.allowance - budget.spent, 0)
            if not remaining and not adapter.credential_limits_from_errors:
                continue
            adapter.settings = credential.settings
            adapter.credential_fingerprint = credential.fingerprint
            adapter.allowance_left = remaining
            return
        if options:
            if adapter.account_balance_required and not verified_account:
                detail = (
                    balance_errors[-1]
                    if balance_errors
                    else "Account balance could not be verified"
                )
                raise SourceUnavailable(detail)
            if adapter.credential_limits_from_errors:
                raise SourceErrorBudget(
                    "All available credentials were rejected for this run. "
                    "Credentials are tried again on the next run."
                )
            if paused_until is not None:
                raise SourceErrorBudget(
                    "All available backup accounts have exhausted their credits or tracked "
                    f"allowance. Primary is paused until {paused_until:%d %b %Y %H:%M %Z}."
                )
            raise SourceErrorBudget(
                "All configured accounts have exhausted their credits or tracked "
                "allowance. Primary is checked again on the next run."
            )
        budget = await budget_for(session, type(adapter), self.clock(), settings=self.settings)
        adapter.allowance_left = budget.allowance - budget.spent if budget else None
        if budget and budget.exhausted:
            raise SourceErrorBudget(
                f"Free allowance used up ({budget.spent}/{budget.allowance} {budget.unit}); "
                f"renews {budget.renews_on:%d %b %Y}"
            )

    @staticmethod
    async def _inherited_until(
        session: AsyncSession, family: set[str], keys: list[str]
    ) -> datetime | None:
        """Where a new search may pick up: the oldest watermark among the searches it
        replaces, so no day between them is skipped. None when none of them has run."""
        if not keys:
            return None
        marks = (
            await session.execute(
                select(QueryWatermark.query_key, func.max(QueryWatermark.last_until))
                .where(
                    among(QueryWatermark.source, family, String()),
                    among(QueryWatermark.query_key, set(keys), String()),
                )
                .group_by(QueryWatermark.query_key)
            )
        ).all()
        # Every replaced search must have run; one that never did still needs a Backfill.
        if len(marks) < len(set(keys)):
            return None
        return min(until for _, until in marks)

    async def _run_windowed(
        self,
        session: AsyncSession,
        adapter: WindowedSourceAdapter,
        trigger: str,
        outcome: SourceOutcome,
    ) -> None:
        preference_queries: list[SourceQuery] = []
        if adapter.per_query:
            preferences = list((await session.execute(select(Preference))).scalars())
            preference_queries = queries_from_preferences(preferences)
            queries: list[SourceQuery | None] = list(adapter.search_queries(preference_queries))
        else:
            queries = [None]
        family = family_of(type(adapter))

        async def known_postings(ids: set[str]) -> set[str]:
            if not ids:
                return set()
            # A separate short session releases the connection before another slow
            # provider request. Only the page's IDs and cached usability are read.
            async with self.sessionmaker() as lookup:
                return set(
                    (
                        await lookup.execute(
                            select(Posting.source_job_id).where(
                                among(Posting.source, family, String()),
                                among(Posting.source_job_id, ids, String()),
                                Posting.description_usable.is_(True),
                                Posting.closed_at.is_(None),
                            )
                        )
                    ).scalars()
                )

        adapter.known_postings = known_postings
        # Every search in this run ends its window at the run's start, not when its turn
        # comes: otherwise slow searches before it push each day's window past 24 hours.
        started = self.clock()
        for query in queries:
            key = query.key if query else "all"
            now = self.clock()
            marks = list(
                (
                    await session.execute(
                        select(QueryWatermark).where(
                            among(QueryWatermark.source, family, String()),
                            QueryWatermark.query_key == key,
                        )
                    )
                ).scalars()
            )
            watermark = next((m for m in marks if m.source == adapter.name), None)
            # A main Source and its standby continue from whichever searched last.
            last_until = max((m.last_until for m in marks), default=None)
            if last_until is None and query is not None:
                last_until = await self._inherited_until(
                    session, family, adapter.continues_from(query, preference_queries)
                )
            if last_until is None:
                since = started - timedelta(days=self.settings.backfill_days)
            else:
                # Cron and catch-up runs never repeat a search already done today; only
                # the admin's manual run deliberately does.
                if trigger != MANUAL and now - last_until < ALREADY_FETCHED:
                    continue
                since = last_until - timedelta(hours=self.settings.window_overlap_hours)
            await self._check_budget(session, adapter)
            window = FetchWindow(since=since, until=started)
            run = FetchRun(
                source=adapter.name,
                status=RunStatus.RUNNING,
                trigger=trigger,
                query_key=key,
                window_since=since,
                window_until=started,
            )
            session.add(run)
            await session.flush()
            # Provider polling can take many minutes. Persist the running state and
            # release the database connection before waiting for the provider.
            await session.commit()
            try:
                while True:
                    run.credential_fingerprint = adapter.credential_fingerprint
                    try:
                        result = await _guarded(adapter, adapter.fetch_window(query, window))
                        break
                    except (SourceQuotaRejected, SourceCredentialRejected) as exc:
                        if exc.credits_used or adapter.credential_fingerprint is None:
                            raise
                        adapter.exhausted_credentials.add(adapter.credential_fingerprint)
                        try:
                            await self._check_budget(session, adapter)
                        except SourceErrorBudget as exhausted:
                            # Show that rotation completed, retaining the last provider reason.
                            exc.message = (
                                f"All {len(adapter.exhausted_credentials)} available credentials "
                                f"were rejected. Last: {exc.message}"
                            )
                            raise exc from exhausted
            except SourceError as exc:
                run.status, run.error, run.finished_at = RunStatus.FAILED, exc.message, self.clock()
                run.credits_used = exc.credits_used
                await session.commit()
                raise
            # Record the spend before anything else can fail: it is already billed (FR-B5).
            run.credits_used = result.credits_used
            await session.commit()
            try:
                new, seen = await save_postings(session, adapter.name, result.postings, now)
                pending_new, pending_seen = await save_pending(
                    session, adapter.name, result.pending
                )
            except Exception:
                await session.rollback()
                await session.execute(
                    update(FetchRun)
                    .where(FetchRun.id == run.id)
                    .values(
                        status=RunStatus.FAILED,
                        error="Saving the results failed; see the server logs",
                        finished_at=self.clock(),
                    )
                )
                await session.commit()
                raise
            run.status, run.finished_at = RunStatus.SUCCEEDED, self.clock()
            if not result.complete:
                # Shown in Recent runs: the window is still marked done, but it held more.
                run.error = (
                    "Reached the provider's record cap; some jobs in this window may be "
                    "missing. Split the search or raise its cap."
                )
            # Pending adverts count here; their Postings appear once extracted.
            run.postings_found, run.postings_new, run.credits_used = (
                len(seen) + pending_seen,
                new + pending_new,
                result.credits_used,
            )
            if not result.complete and adapter.retry_incomplete_window:
                run.status = RunStatus.FAILED
                run.error = (
                    "Incomplete search: not all jobs could be collected. Partial postings "
                    "were saved; the search window remains available for retry or fallback."
                )
                outcome.postings_new += new
                outcome.credits_used += result.credits_used
                await session.commit()
                raise SourceUnavailable(run.error)
            if watermark is None:
                session.add(QueryWatermark(source=adapter.name, query_key=key, last_until=started))
            else:
                watermark.last_until = started
            await session.commit()
            outcome.postings_new += new
            outcome.credits_used += result.credits_used

    async def _run_snapshot(
        self,
        session: AsyncSession,
        adapter: SnapshotSourceAdapter,
        trigger: str,
        outcome: SourceOutcome,
    ) -> None:
        now = self.clock()
        due = or_(
            AtsBoard.last_fetched_at.is_(None),
            # Daily while the board had jobs in the last 30 days; a board that never had
            # any counts from when it was added, so it does not stay daily for ever.
            (AtsBoard.last_fetched_at < now - BOARD_DAILY)
            & (
                func.coalesce(AtsBoard.last_nonempty_at, AtsBoard.created_at)
                >= now - BOARD_STALE_AFTER
            ),
            AtsBoard.last_fetched_at < now - BOARD_WEEKLY,
        )
        query = select(AtsBoard).where(AtsBoard.ats == adapter.ats, AtsBoard.enabled.is_(True))
        if trigger != MANUAL:
            query = query.where(due)
        boards = list((await session.execute(query.order_by(AtsBoard.slug))).scalars())
        failures: list[str] = []
        for board in boards:
            run = FetchRun(
                source=adapter.name, status=RunStatus.RUNNING, trigger=trigger, board_id=board.id
            )
            session.add(run)
            await session.flush()
            # A slow board must not keep a database connection idle during HTTP calls.
            await session.commit()
            try:
                result = await _guarded(adapter, adapter.fetch_board(board.slug))
            except BoardNotFound as exc:
                board.enabled = False
                run.status, run.error, run.finished_at = RunStatus.FAILED, exc.message, self.clock()
                await session.commit()
                continue
            except (SourceRateLimited, SourceQuotaExhausted) as exc:
                # The provider is pushing back for everyone: stop this ATS for today.
                run.status, run.error, run.finished_at = RunStatus.FAILED, exc.message, self.clock()
                await session.commit()
                raise
            except SourceError as exc:
                # One broken board must not stop the boards after it (ADR-0003).
                run.status, run.error, run.finished_at = RunStatus.FAILED, exc.message, self.clock()
                await session.commit()
                failures.append(f"{board.slug}: {exc.message}")
                continue
            now = self.clock()
            new, seen = await save_postings(
                session, adapter.name, result.postings, now, board=board
            )
            closed_count = 0
            if result.complete:
                closed = await session.execute(
                    update(Posting)
                    .where(
                        Posting.ats_board_id == board.id,
                        Posting.closed_at.is_(None),
                        ~among(Posting.source_job_id, seen, String()),
                    )
                    .values(closed_at=now, closed_reason="board")
                )
                closed_count = closed.rowcount or 0
            board.last_fetched_at = now
            if seen:
                board.last_nonempty_at = now
            run.status, run.finished_at = RunStatus.SUCCEEDED, now
            run.postings_found, run.postings_new = len(seen), new
            run.postings_closed = closed_count
            await session.commit()
            outcome.postings_new += new
        if failures and len(failures) * 2 > len(boards):
            raise SourceUnavailable(
                f"{len(failures)} of {len(boards)} {adapter.label} boards failed "
                f"(last: {failures[-1]})"
            )

    async def _claim_manual_run(self, name: str) -> SourceOutcome | None:
        """Counts one manual run; returns a skip outcome when today's limit is reached."""
        if get_adapter_class(name).push_only:
            return SourceOutcome(name, "skipped", "This Source only accepts browser captures")
        today = self.clock().date().isoformat()
        async with self.sessionmaker() as session:
            source = await self._source_row(session, name)
            if source.manual_runs_date != today:
                source.manual_runs_date, source.manual_runs_today = today, 0
            if source.manual_runs_today >= MANUAL_RUNS_PER_DAY:
                return SourceOutcome(
                    name, "skipped", f"Limit of {MANUAL_RUNS_PER_DAY} manual runs a day reached"
                )
            source.manual_runs_today += 1
            await session.commit()
        return None

    async def manual_run(self, name: str) -> SourceOutcome:
        """Admin "Run now" (FR-B11), limited per Source per day. Waits for the whole run;
        the API uses start_manual_run instead."""
        get_adapter_class(name)
        async with self._exclusive() as got:
            if not got:
                return SourceOutcome(name, "skipped", BUSY)
            refusal = await self._claim_manual_run(name)
            if refusal is not None:
                return refusal
            outcome = await self.run_source(name, trigger=MANUAL)
            await self._after_fetch()
            return outcome

    async def start_manual_run(self, name: str) -> SourceOutcome:
        """Checks the lock and the daily limit now, then fetches and processes in the
        background: grouping and embeddings can take many minutes, far longer than an
        HTTP request may stay open. Progress shows under Recent runs."""
        get_adapter_class(name)
        stack = AsyncExitStack()
        try:
            got = await stack.enter_async_context(self._exclusive())
            refusal = SourceOutcome(name, "skipped", BUSY) if not got else None
            refusal = refusal or await self._claim_manual_run(name)
        except BaseException:
            await stack.aclose()
            raise
        if refusal is not None:
            await stack.aclose()
            return refusal

        async def run_in_background() -> None:
            async with stack:  # releases the fetch lock when the run ends
                try:
                    await self.run_source(name, trigger=MANUAL)
                    await self._after_fetch()
                except Exception:
                    logger.exception("Manual run of %s failed", name)

        self.manual_task = asyncio.create_task(run_in_background())
        _BACKGROUND.add(self.manual_task)
        self.manual_task.add_done_callback(_BACKGROUND.discard)
        return SourceOutcome(name, "started", "Fetching now; results appear under Recent runs")


async def _guarded(adapter: SourceAdapter, call: Awaitable[FetchResult]) -> FetchResult:
    """Network failures and malformed payloads become SourceErrors with a readable reason."""
    try:
        return await call
    except SourceError:
        raise
    except httpx.TimeoutException as exc:
        raise SourceUnavailable(f"{adapter.label} timed out") from exc
    except httpx.HTTPError as exc:
        raise SourceUnavailable(
            f"{adapter.label} could not be reached ({type(exc).__name__})"
        ) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceBadResponse(f"{adapter.label} returned data JobWeaver could not read") from exc


class SourceErrorBudget(SourceError):
    """The monthly allowance is used up; the Source stays Degraded until renewal."""
