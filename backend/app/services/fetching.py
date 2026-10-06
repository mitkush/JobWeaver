"""Fetch orchestration (FR-B3 to FR-B11). Every Source runs in isolation (ADR-0003):
a failure marks that Source Degraded and the run moves on to the next one."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.ats_urls import parse_ats_url
from app.adapters.base import (
    FetchResult,
    FetchWindow,
    Location,
    NormalizedPosting,
    SnapshotSourceAdapter,
    SourceAdapter,
    SourceQuery,
    WindowedSourceAdapter,
    WorkMode,
)
from app.adapters.errors import (
    BoardNotFound,
    SourceBadResponse,
    SourceError,
    SourceNotConfigured,
    SourceUnavailable,
)
from app.adapters.normalize import normalize_company
from app.adapters.registry import get_adapter_class, registered_adapters
from app.core.config import Settings, get_settings
from app.models.fetch import FetchRun, QueryWatermark, RunStatus
from app.models.posting import AtsBoard, Company, Posting
from app.models.preference import Preference
from app.models.source import Source, SourceState

logger = logging.getLogger(__name__)

# Any constant works; it only has to be unique to "the fetch runner" in this database.
FETCH_LOCK_ID = 7_201_026
BOARD_DAILY = timedelta(hours=20)
BOARD_STALE_AFTER = timedelta(days=30)
BOARD_WEEKLY = timedelta(days=7)
MANUAL_RUNS_PER_DAY = 4

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
    """One query per distinct (title, location) across all users (FR-B4 AC1)."""
    queries: dict[str, SourceQuery] = {}
    for pref in preferences:
        modes = set(pref.work_modes)
        remote_only = modes == {WorkMode.REMOTE.value}
        for title in pref.titles:
            for loc in pref.locations:
                country = loc.get("country")
                location = Location(city=loc.get("city"), country=country, remote=remote_only)
                query = SourceQuery(keywords=title, location=location)
                queries.setdefault(query.key, query)
                if WorkMode.REMOTE.value in modes and not remote_only:
                    remote = SourceQuery(
                        keywords=title, location=Location(country=country, remote=True)
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
    session: AsyncSession, adapter: type[SourceAdapter], now: datetime
) -> Budget | None:
    """Spend, month-end projection and the most expensive queries (FR-B5)."""
    if adapter.monthly_allowance is None:
        return None
    start = period_start(now, adapter.renewal_day)
    renews = next_renewal(now, adapter.renewal_day)
    in_period = (FetchRun.source == adapter.name, FetchRun.created_at >= start)
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
    if daily > 0 and spent < adapter.monthly_allowance:
        runs_out = now + timedelta(days=(adapter.monthly_allowance - spent) / daily)
        if runs_out >= renews:
            runs_out = None
    elif spent >= adapter.monthly_allowance:
        runs_out = now
    return Budget(
        allowance=adapter.monthly_allowance,
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
        company = await _company(session, item.company, companies)
        posting = (
            await session.execute(
                select(Posting).where(
                    Posting.source == source, Posting.source_job_id == item.source_job_id
                )
            )
        ).scalar_one_or_none()
        if posting is None:
            posting = Posting(source=source, source_job_id=item.source_job_id, first_seen_at=now)
            session.add(posting)
            new += 1
        posting.company_id = company.id
        posting.ats_board_id = board.id if board else posting.ats_board_id
        posting.title = item.title[:500]
        posting.description = item.description
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


# --- Runner -----------------------------------------------------------------------------


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
    ) -> None:
        self.sessionmaker = sessionmaker
        self.http = http or get_sources_http()
        self.settings = settings or get_settings()
        self.clock = clock
        self.adapter_factory = adapter_factory or (lambda cls, http, settings: cls(http, settings))

    async def sync_sources(self) -> None:
        async with self.sessionmaker() as session:
            existing = set((await session.execute(select(Source.name))).scalars())
            for cls in registered_adapters():
                if cls.name not in existing:
                    session.add(Source(name=cls.name))
            await session.commit()

    async def run_all(self, trigger: str = "schedule") -> list[SourceOutcome] | None:
        """Runs every enabled Source once. Returns None if another run holds the lock."""
        await self.sync_sources()
        async with self.sessionmaker() as lock_session:
            got = await lock_session.scalar(text(f"SELECT pg_try_advisory_lock({FETCH_LOCK_ID})"))
            if not got:
                logger.info("Fetch run skipped: another run is in progress")
                return None
            try:
                outcomes = [
                    await self.run_source(cls.name, trigger) for cls in registered_adapters()
                ]
                async with self.sessionmaker() as session:
                    closed = await expire_postings(session, self.clock(), self.settings)
                    await session.commit()
                logger.info("Fetch run finished: %s; %s postings expired", outcomes, closed)
                return outcomes
            finally:
                await lock_session.execute(text(f"SELECT pg_advisory_unlock({FETCH_LOCK_ID})"))
                await lock_session.commit()

    async def run_source(self, name: str, trigger: str = "schedule") -> SourceOutcome:
        cls = get_adapter_class(name)
        async with self.sessionmaker() as session:
            source = await self._source_row(session, name)
            if not source.enabled:
                return SourceOutcome(name, "skipped", "disabled")
            now = self.clock()
            if cls.min_interval_hours and trigger == "schedule":
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
            source = Source(name=name)
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
        budget = await budget_for(session, type(adapter), self.clock())
        if budget and budget.exhausted:
            raise SourceErrorBudget(
                f"Free allowance used up ({budget.spent}/{budget.allowance} {budget.unit}); "
                f"renews {budget.renews_on:%d %b %Y}"
            )

    async def _run_windowed(
        self,
        session: AsyncSession,
        adapter: WindowedSourceAdapter,
        trigger: str,
        outcome: SourceOutcome,
    ) -> None:
        if adapter.per_query:
            preferences = list((await session.execute(select(Preference))).scalars())
            queries: list[SourceQuery | None] = list(queries_from_preferences(preferences))
        else:
            queries = [None]
        for query in queries:
            await self._check_budget(session, adapter)
            key = query.key if query else "all"
            now = self.clock()
            watermark = (
                await session.execute(
                    select(QueryWatermark).where(
                        QueryWatermark.source == adapter.name, QueryWatermark.query_key == key
                    )
                )
            ).scalar_one_or_none()
            if watermark is None:
                since = now - timedelta(days=self.settings.backfill_days)
            else:
                since = watermark.last_until - timedelta(hours=self.settings.window_overlap_hours)
            window = FetchWindow(since=since, until=now)
            run = FetchRun(
                source=adapter.name,
                status=RunStatus.RUNNING,
                trigger=trigger,
                query_key=key,
                window_since=since,
                window_until=now,
            )
            session.add(run)
            await session.flush()
            try:
                result = await _guarded(adapter, adapter.fetch_window(query, window))
            except SourceError as exc:
                run.status, run.error, run.finished_at = RunStatus.FAILED, exc.message, self.clock()
                await session.commit()
                raise
            new, seen = await save_postings(session, adapter.name, result.postings, now)
            run.status, run.finished_at = RunStatus.SUCCEEDED, self.clock()
            run.postings_found, run.postings_new, run.credits_used = (
                len(seen),
                new,
                result.credits_used,
            )
            if watermark is None:
                session.add(QueryWatermark(source=adapter.name, query_key=key, last_until=now))
            else:
                watermark.last_until = now
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
            (AtsBoard.last_fetched_at < now - BOARD_DAILY)
            & or_(
                AtsBoard.last_nonempty_at.is_(None),
                AtsBoard.last_nonempty_at >= now - BOARD_STALE_AFTER,
            ),
            AtsBoard.last_fetched_at < now - BOARD_WEEKLY,
        )
        query = select(AtsBoard).where(AtsBoard.ats == adapter.ats, AtsBoard.enabled.is_(True))
        if trigger == "schedule":
            query = query.where(due)
        boards = list((await session.execute(query.order_by(AtsBoard.slug))).scalars())
        for board in boards:
            run = FetchRun(
                source=adapter.name, status=RunStatus.RUNNING, trigger=trigger, board_id=board.id
            )
            session.add(run)
            await session.flush()
            try:
                result = await _guarded(adapter, adapter.fetch_board(board.slug))
            except BoardNotFound as exc:
                board.enabled = False
                run.status, run.error, run.finished_at = RunStatus.FAILED, exc.message, self.clock()
                await session.commit()
                continue
            except SourceError as exc:
                run.status, run.error, run.finished_at = RunStatus.FAILED, exc.message, self.clock()
                await session.commit()
                raise
            now = self.clock()
            new, seen = await save_postings(
                session, adapter.name, result.postings, now, board=board
            )
            closed = await session.execute(
                update(Posting)
                .where(
                    Posting.ats_board_id == board.id,
                    Posting.closed_at.is_(None),
                    Posting.source_job_id.not_in(seen) if seen else text("true"),
                )
                .values(closed_at=now, closed_reason="board")
            )
            board.last_fetched_at = now
            if seen:
                board.last_nonempty_at = now
            run.status, run.finished_at = RunStatus.SUCCEEDED, now
            run.postings_found, run.postings_new = len(seen), new
            run.postings_closed = closed.rowcount or 0
            await session.commit()
            outcome.postings_new += new

    async def manual_run(self, name: str) -> SourceOutcome:
        """Admin "Run now" (FR-B11), limited per Source per day."""
        today = self.clock().date().isoformat()
        get_adapter_class(name)
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
        return await self.run_source(name, trigger="manual")


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
