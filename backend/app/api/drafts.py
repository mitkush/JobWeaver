import uuid
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy import select

from app.adapters.gmail import GmailClient, get_gmail_client
from app.adapters.links import get_link_http
from app.api.deps import CurrentUser, DbSession, Gateway, Google
from app.core.errors import ConflictError
from app.models import DraftVersion
from app.schemas.drafts import (
    AppliedIn,
    DiffLine,
    DraftChat,
    DraftCreate,
    DraftOut,
    DraftRecheck,
    DraftSave,
    EmailCheck,
    HandoffIn,
    HandoffOut,
    RestoreVersion,
    VersionOut,
)
from app.services import drafting
from app.services.email_check import check_recipient
from app.tailoring.content import DraftContent, FactSnapshot
from app.tailoring.diff import resume_diff

router = APIRouter(prefix="/api/drafts", tags=["drafts"])
Gmail = Annotated[GmailClient, Depends(get_gmail_client)]


@router.post("", status_code=202)
async def create(
    db: DbSession,
    user: CurrentUser,
    body: DraftCreate,
    gateway: Gateway,
    background: BackgroundTasks,
    link_http: Annotated[httpx.AsyncClient, Depends(get_link_http)],
) -> DraftOut:
    await drafting.ensure_link_open(db, user, body.job_id, link_http)
    draft = await drafting.create(db, user, body.job_id)
    await db.commit()
    result = await drafting.detail(db, user, draft.id)
    background.add_task(drafting.generate, draft.id, user.id, gateway)
    return result


@router.get("/{draft_id}")
async def detail(db: DbSession, user: CurrentUser, draft_id: uuid.UUID) -> DraftOut:
    return await drafting.detail(db, user, draft_id)


@router.post("/{draft_id}/retry", status_code=202)
async def retry(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    gateway: Gateway,
    background: BackgroundTasks,
) -> DraftOut:
    draft = await drafting.owned_draft(db, user, draft_id, lock=True)
    if draft.state != "failed":
        raise ConflictError("Only a failed generation can be retried")
    draft.state, draft.error, draft.progress = "queued", None, "Reading the job"
    await db.commit()
    result = await drafting.detail(db, user, draft_id)
    background.add_task(drafting.generate, draft.id, user.id, gateway)
    return result


@router.delete("/{draft_id}", status_code=204)
async def delete(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    expected_version: Annotated[int, Query(ge=0)],
) -> None:
    draft = await drafting.owned_draft(db, user, draft_id, lock=True)
    if draft.state in ("queued", "generating"):
        raise ConflictError("Wait for generation to finish before deleting this Draft")
    if draft.current_version != expected_version:
        raise ConflictError("The Draft changed. Reload it before deleting.")
    await db.delete(draft)
    await db.commit()


@router.put("/{draft_id}")
async def save(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    body: DraftSave,
) -> DraftOut:
    await drafting.save(db, user, draft_id, body.expected_version, body.content)
    await db.commit()
    return await drafting.detail(db, user, draft_id)


@router.post("/{draft_id}/recheck")
async def recheck(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    body: DraftRecheck,
) -> DraftOut:
    await drafting.recheck(db, user, draft_id, body.expected_version)
    await db.commit()
    return await drafting.detail(db, user, draft_id)


@router.post("/{draft_id}/chat")
async def chat(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    body: DraftChat,
    gateway: Gateway,
) -> DraftOut:
    await drafting.chat(
        db, user, draft_id, body.expected_version, body.message, body.overwrite_manual, gateway
    )
    await db.commit()
    return await drafting.detail(db, user, draft_id)


@router.get("/{draft_id}/versions")
async def versions(db: DbSession, user: CurrentUser, draft_id: uuid.UUID) -> list[VersionOut]:
    draft = await drafting.owned_draft(db, user, draft_id)
    rows = await db.scalars(
        select(DraftVersion)
        .where(
            DraftVersion.draft_id == draft.id,
            DraftVersion.user_id == user.id,
        )
        .order_by(DraftVersion.number.desc())
    )
    return [drafting.version_out(row) for row in rows]


@router.post("/{draft_id}/restore")
async def restore(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    body: RestoreVersion,
) -> DraftOut:
    await drafting.restore(db, user, draft_id, body.expected_version, body.number)
    await db.commit()
    return await drafting.detail(db, user, draft_id)


@router.get("/{draft_id}/diff")
async def diff(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    number: Annotated[int | None, Query(ge=1)] = None,
) -> list[DiffLine]:
    draft = await drafting.owned_draft(db, user, draft_id)
    row = await drafting.version(db, draft, number)
    return resume_diff(
        DraftContent.model_validate(row.content),
        [FactSnapshot.model_validate(fact) for fact in row.facts],
    )


@router.get("/{draft_id}/pdf")
async def pdf(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    kind: Literal["resume", "cover_letter"] = "resume",
    template: Literal["standard", "compact"] = "standard",
    number: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    data, name = await drafting.pdf(db, user, draft_id, kind, template, number)
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{draft_id}/email-check")
async def email_check(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    recipient: Annotated[str, Query(min_length=1, max_length=320)],
) -> EmailCheck:
    await drafting.owned_draft(db, user, draft_id)
    return await check_recipient(recipient)


@router.post("/{draft_id}/handoff")
async def handoff(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    body: HandoffIn,
    google: Google,
    gmail: Gmail,
) -> HandoffOut:
    result = await drafting.handoff(db, user, draft_id, body, google, gmail)
    await db.commit()
    return result


@router.post("/{draft_id}/applied", status_code=204)
async def applied(
    db: DbSession,
    user: CurrentUser,
    draft_id: uuid.UUID,
    body: AppliedIn,
) -> None:
    await drafting.mark_applied(db, user, draft_id, body.expected_version)
    await db.commit()
