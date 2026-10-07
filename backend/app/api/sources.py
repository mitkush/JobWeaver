import asyncio
import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AuthError, ForbiddenError, NotFoundError
from app.models.user import Role, User
from app.schemas.ai_usage import AIUsageOut
from app.schemas.sources import (
    AtsBoardIn,
    AtsBoardOut,
    FetchRunOut,
    RunOutcomeOut,
    SourceNotice,
    SourceStatusOut,
    SourceUpdate,
)
from app.services import ai_usage, source_status
from app.services.fetching import Fetcher
from app.services.pipeline import build_fetcher

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sources"])
_background: set[asyncio.Task[object]] = set()


def admin_user(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise ForbiddenError("Only the admin can manage sources")
    return user


AdminUser = Annotated[User, Depends(admin_user)]


def get_fetcher() -> Fetcher:
    return build_fetcher()


FetcherDep = Annotated[Fetcher, Depends(get_fetcher)]


@router.get("/admin/ai-usage")
async def ai_usage_summary(db: DbSession, _: AdminUser) -> AIUsageOut:
    """Calls against each provider's free daily quota, and the last week by task (FR-G4)."""
    return await ai_usage.summary(db)


@router.get("/admin/sources")
async def list_sources(db: DbSession, _: AdminUser, fetcher: FetcherDep) -> list[SourceStatusOut]:
    await fetcher.sync_sources()
    return await source_status.list_statuses(db)


@router.patch("/admin/sources/{name}")
async def update_source(
    db: DbSession, _: AdminUser, name: str, body: SourceUpdate
) -> list[SourceStatusOut]:
    await source_status.set_enabled(db, name, body.enabled)
    await db.commit()
    return await source_status.list_statuses(db)


@router.post("/admin/sources/{name}/run")
async def run_source(_: AdminUser, name: str, fetcher: FetcherDep) -> RunOutcomeOut:
    try:
        outcome = await fetcher.start_manual_run(name)
    except KeyError as exc:
        raise NotFoundError("Unknown source") from exc
    return RunOutcomeOut(**outcome.__dict__)


@router.get("/admin/fetch-runs")
async def fetch_runs(
    db: DbSession,
    _: AdminUser,
    source: str | None = None,
    limit: Annotated[int, Query(le=200)] = 50,
) -> list[FetchRunOut]:
    return await source_status.recent_runs(db, source, limit)


@router.get("/sources/notices")
async def notices(db: DbSession, _: CurrentUser) -> list[SourceNotice]:
    return await source_status.notices(db)


@router.get("/ats-boards")
async def list_boards(db: DbSession, _: CurrentUser) -> list[AtsBoardOut]:
    return await source_status.list_boards(db)


@router.post("/ats-boards", status_code=201)
async def add_board(db: DbSession, user: CurrentUser, body: AtsBoardIn) -> AtsBoardOut:
    board = await source_status.add_board(db, user, body.url)
    await db.commit()
    return next(b for b in await source_status.list_boards(db) if b.id == board.id)


@router.post("/internal/fetch", status_code=202)
async def cron_fetch(
    fetcher: FetcherDep, x_cron_secret: Annotated[str, Header()] = ""
) -> dict[str, str]:
    """External cron fallback when the host sleeps through the schedule (ADR-0008)."""
    secret = get_settings().internal_cron_secret
    if not secret or not hmac.compare_digest(x_cron_secret, secret):
        raise AuthError("Invalid cron secret")
    task = asyncio.create_task(fetcher.run_all(trigger="cron"))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"status": "started"}
