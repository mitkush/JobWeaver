from datetime import UTC, datetime, timedelta

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ats_urls import parse_ats_url
from app.adapters.base import SnapshotSourceAdapter
from app.adapters.registry import get_adapter_class, pool_of, registered_adapters
from app.core.config import get_settings
from app.core.db import among
from app.core.errors import NotFoundError, ValidationFailedError
from app.models.fetch import FetchRun, RunStatus
from app.models.posting import AtsBoard, Company, Posting
from app.models.source import Source, SourceState
from app.models.user import User
from app.schemas.sources import (
    AtsBoardOut,
    BudgetOut,
    FetchRunOut,
    QuerySpend,
    SourceNotice,
    SourceStatusOut,
)
from app.services.account_balances import account_status
from app.services.fetching import MANUAL_RUNS_PER_DAY, budget_for, get_sources_http
from app.services.provider_credentials import active_primary_pause, credentials

NOTICE_AFTER = timedelta(days=1)


def next_run_at(now: datetime) -> datetime:
    settings = get_settings()
    run = now.replace(
        hour=settings.fetch_hour_utc, minute=settings.fetch_minute_utc, second=0, microsecond=0
    )
    return run if run > now else run + timedelta(days=1)


async def list_statuses(
    session: AsyncSession, now: datetime | None = None
) -> list[SourceStatusOut]:
    now = now or datetime.now(UTC)
    rows = {s.name: s for s in (await session.execute(select(Source))).scalars()}
    open_counts = dict(
        (
            await session.execute(
                select(Posting.source, func.count())
                .where(Posting.closed_at.is_(None))
                .group_by(Posting.source)
            )
        ).all()
    )
    labels = {cls.name: cls.label for cls in registered_adapters()}
    out = []
    for cls in registered_adapters():
        source = rows.get(cls.name)
        adapter = cls(get_sources_http(), get_settings())
        account = (
            await account_status(cls, get_sources_http(), get_settings(), now)
            if adapter.is_configured()
            else None
        )
        options = credentials(cls, get_settings())
        tracked = None
        if options:
            latest = await session.scalar(
                select(FetchRun.credential_fingerprint)
                .where(FetchRun.source.in_(pool_of(cls)))
                .order_by(FetchRun.created_at.desc())
                .limit(1)
            )
            tracked = next((c for c in options if c.fingerprint == latest), options[0])
            if account and (
                cls.account_balance_required
                or (
                    cls.primary_credential_pause_setting
                    and active_primary_pause(cls, get_settings(), now)
                )
            ):
                tracked = next((c for c in options if c.label == account.account_label), tracked)
            # When the provider cannot verify balances, its default account label is not
            # evidence of which key was last used. Keep the account summary aligned with
            # the credential whose JobWeaver spend is shown below it.
            if account and account.status != "live" and tracked:
                account = account.model_copy(update={"account_label": tracked.label})
        budget = await budget_for(
            session,
            cls,
            now,
            credential_fingerprint=tracked.fingerprint if tracked else None,
            include_legacy=tracked.primary if tracked else False,
        )
        boards = None
        if issubclass(cls, SnapshotSourceAdapter):
            boards = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AtsBoard)
                    .where(AtsBoard.ats == cls.ats, AtsBoard.enabled)
                )
                or 0
            )
        today = now.date().isoformat()
        used = source.manual_runs_today if source and source.manual_runs_date == today else 0
        enabled = source.enabled if source else cls.default_enabled
        out.append(
            SourceStatusOut(
                name=cls.name,
                label=cls.label,
                site=cls.site,
                priority=cls.priority,
                mode=cls.mode.value,
                enabled=enabled,
                configured=adapter.is_configured(),
                state=SourceState.DISABLED
                if not enabled
                else (source.state if source else SourceState.HEALTHY),
                last_success_at=source.last_success_at if source else None,
                last_error=source.last_error if source else None,
                last_error_at=source.last_error_at if source else None,
                degraded_since=source.degraded_since if source else None,
                next_run_at=next_run_at(now) if enabled else None,
                open_postings=int(open_counts.get(cls.name, 0)),
                boards=boards,
                budget=None
                if budget is None
                else BudgetOut(
                    account=account,
                    tracked_account=tracked.label if tracked else None,
                    allowance=budget.allowance,
                    unit=budget.unit,
                    spent=budget.spent,
                    projected=budget.projected,
                    period_start=budget.period_start,
                    renews_on=budget.renews_on,
                    runs_out_on=budget.runs_out_on,
                    top_queries=[QuerySpend(query_key=k, spent=v) for k, v in budget.top_queries],
                ),
                manual_runs_left=max(MANUAL_RUNS_PER_DAY - used, 0),
                standby_for=labels.get(cls.standby_for, cls.standby_for)
                if cls.standby_for
                else None,
                shares_budget_with=sorted(labels[n] for n in pool_of(cls) - {cls.name}),
                disabled_reason=cls.disabled_reason,
            )
        )
    return out


async def set_enabled(session: AsyncSession, name: str, enabled: bool) -> None:
    try:
        get_adapter_class(name)
    except KeyError as exc:
        raise NotFoundError("Unknown source") from exc
    source = (await session.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
    if source is None:
        source = Source(name=name)
        session.add(source)
    source.enabled = enabled
    if enabled and source.state == SourceState.DISABLED:
        source.state = SourceState.HEALTHY
    await session.flush()


async def recent_runs(
    session: AsyncSession, source: str | None, limit: int = 50
) -> list[FetchRunOut]:
    query = (
        select(FetchRun, AtsBoard.slug)
        .outerjoin(AtsBoard, AtsBoard.id == FetchRun.board_id)
        .order_by(FetchRun.created_at.desc())
        .limit(limit)
    )
    if source:
        query = query.where(FetchRun.source == source)
    return [
        FetchRunOut(
            id=run.id,
            source=run.source,
            status=run.status,
            trigger=run.trigger,
            query_key=run.query_key,
            board=slug,
            created_at=run.created_at,
            finished_at=run.finished_at,
            postings_found=run.postings_found,
            postings_new=run.postings_new,
            postings_closed=run.postings_closed,
            credits_used=run.credits_used,
            error=run.error,
        )
        for run, slug in (await session.execute(query)).all()
    ]


async def notices(session: AsyncSession, now: datetime | None = None) -> list[SourceNotice]:
    """Explain prolonged source failures, distinguishing a full outage from partial success."""
    now = now or datetime.now(UTC)
    rows = (
        await session.execute(
            select(Source).where(
                Source.enabled.is_(True),
                Source.state == SourceState.DEGRADED,
                Source.degraded_since <= now - NOTICE_AFTER,
            )
        )
    ).scalars()
    labels = {cls.name: cls.label for cls in registered_adapters()}
    covered = await _covered_by_standby(session)
    affected = [
        source
        for source in rows
        if source.degraded_since is not None and source.name not in covered
    ]
    latest_success: dict[str, datetime] = {}
    if affected:
        latest_success = dict(
            (
                await session.execute(
                    select(FetchRun.source, func.max(FetchRun.finished_at))
                    .where(
                        FetchRun.source.in_([source.name for source in affected]),
                        FetchRun.status == RunStatus.SUCCEEDED,
                    )
                    .group_by(FetchRun.source)
                )
            ).all()
        )
    return [
        SourceNotice(
            label=labels.get(s.name, s.name),
            since=s.degraded_since,
            message=(
                f"Some {labels.get(s.name, s.name)} searches are failing; successful searches "
                "are still updating."
                if latest_success.get(s.name) is not None
                and now - latest_success[s.name] < NOTICE_AFTER
                else f"No successful {labels.get(s.name, s.name)} searches in over a day; "
                "jobs from this source may be delayed."
            ),
        )
        for s in affected
    ]


async def _covered_by_standby(session: AsyncSession) -> set[str]:
    """Main Sources whose standby is enabled and healthy: users are not missing jobs."""
    standbys = {cls.name: cls.standby_for for cls in registered_adapters() if cls.standby_for}
    if not standbys:
        return set()
    rows = (
        await session.execute(
            select(Source.name).where(
                among(Source.name, standbys, String()),
                Source.enabled.is_(True),
                Source.state == SourceState.HEALTHY,
                Source.last_success_at.is_not(None),
            )
        )
    ).scalars()
    return {standbys[name] for name in rows}


async def list_boards(session: AsyncSession) -> list[AtsBoardOut]:
    enabled = {s.name: s.enabled for s in (await session.execute(select(Source))).scalars()}
    # Boards of an ATS whose Source an admin turned off (or that is off by default) wait.
    fetched_ats = {
        cls.ats
        for cls in registered_adapters()
        if issubclass(cls, SnapshotSourceAdapter) and enabled.get(cls.name, cls.default_enabled)
    }
    counts = dict(
        (
            await session.execute(
                select(Posting.ats_board_id, func.count())
                .where(Posting.closed_at.is_(None), Posting.ats_board_id.is_not(None))
                .group_by(Posting.ats_board_id)
            )
        ).all()
    )
    rows = await session.execute(
        select(AtsBoard, Company.name)
        .outerjoin(Company, Company.id == AtsBoard.company_id)
        .order_by(AtsBoard.ats, AtsBoard.slug)
    )
    return [
        AtsBoardOut(
            id=board.id,
            ats=board.ats,
            slug=board.slug,
            company=company,
            discovered_from=board.discovered_from,
            enabled=board.enabled,
            fetched=board.ats in fetched_ats,
            last_fetched_at=board.last_fetched_at,
            open_postings=int(counts.get(board.id, 0)),
        )
        for board, company in rows.all()
    ]


async def add_board(session: AsyncSession, user: User, url: str) -> AtsBoard:
    """Users add a company's board by pasting any link to it (FR-B7 AC2)."""
    found = parse_ats_url(url.strip())
    if found is None:
        raise ValidationFailedError(
            "Paste a link to a company's job board on Greenhouse, Lever, Ashby, "
            "SmartRecruiters, Workable, Recruitee or Workday."
        )
    ats, slug = found
    board = (
        await session.execute(select(AtsBoard).where(AtsBoard.ats == ats, AtsBoard.slug == slug))
    ).scalar_one_or_none()
    if board is None:
        board = AtsBoard(ats=ats, slug=slug, discovered_from="manual", added_by_user_id=user.id)
        session.add(board)
    board.enabled = True
    await session.flush()
    return board
