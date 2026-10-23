"""Application Extension connection (ADR-0017).

/api/extension/ is used by the signed-in web app (cookie session and CSRF): approve a
connection, list and revoke connections. /api/ext/ is used only by the extension's service
worker with a bearer credential; it is exempt from the cookie CSRF check because it never
reads cookies."""

import uuid
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Header, Query, Response

from app.api.deps import CurrentUser, DbSession, ExtensionCaller
from app.core.errors import JobWeaverError
from app.schemas.application_profile import SavedAnswerOut
from app.schemas.extension import (
    ExtDraftMatch,
    ExtDraftSummary,
    ExtDraftVersion,
    ExtensionApproveIn,
    ExtensionConnectionOut,
    ExtensionGrantOut,
    ExtensionTokenIn,
    ExtensionTokenOut,
    ExtensionUserOut,
    ExtProfileOut,
)
from app.services import application_profile, extension_drafts, saved_answers
from app.services import extension as service

router = APIRouter(tags=["extension"])


@router.post("/api/extension/approve")
async def approve(db: DbSession, user: CurrentUser, body: ExtensionApproveIn) -> ExtensionGrantOut:
    code, expires = await service.approve(db, user, body.extension_id, body.challenge)
    await db.commit()
    return ExtensionGrantOut(code=code, expires_at=expires)


@router.get("/api/extension/connections")
async def connections(db: DbSession, user: CurrentUser) -> list[ExtensionConnectionOut]:
    rows = await service.active_connections(db, user)
    return [ExtensionConnectionOut.model_validate(r, from_attributes=True) for r in rows]


@router.delete("/api/extension/connections/{connection_id}", status_code=204)
async def revoke(db: DbSession, user: CurrentUser, connection_id: uuid.UUID) -> None:
    await service.revoke(db, user, connection_id)
    await db.commit()


@router.post("/api/ext/token")
async def token(
    db: DbSession,
    body: ExtensionTokenIn,
    origin: Annotated[str | None, Header()] = None,
) -> ExtensionTokenOut:
    try:
        secret, credential, user = await service.exchange(db, body.code, body.verifier, origin)
    except JobWeaverError:
        # Keep the code spent (and any replay revocation) even though the call fails.
        await db.commit()
        raise
    await db.commit()
    return ExtensionTokenOut(
        token=secret,
        expires_at=credential.expires_at,
        user=ExtensionUserOut(name=user.name, email=user.email),
    )


@router.get("/api/ext/me")
async def me(db: DbSession, caller: ExtensionCaller) -> ExtensionUserOut:
    _, user = caller
    await db.commit()  # last_used_at
    return ExtensionUserOut(name=user.name, email=user.email)


@router.delete("/api/ext/token", status_code=204)
async def disconnect(db: DbSession, caller: ExtensionCaller) -> None:
    credential, _ = caller
    await service.disconnect(db, credential)
    await db.commit()


@router.get("/api/ext/profile")
async def ext_profile(db: DbSession, caller: ExtensionCaller) -> ExtProfileOut:
    _, user = caller
    result = await application_profile.for_extension(db, user)
    await db.commit()
    return result


@router.get("/api/ext/saved-answers")
async def ext_saved_answers(
    db: DbSession, caller: ExtensionCaller, job_id: uuid.UUID
) -> list[SavedAnswerOut]:
    _, user = caller
    rows = await saved_answers.applicable(db, user, job_id)
    await db.commit()
    return [SavedAnswerOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/api/ext/drafts")
async def ext_drafts(db: DbSession, caller: ExtensionCaller) -> list[ExtDraftSummary]:
    _, user = caller
    result = await extension_drafts.recent(db, user)
    await db.commit()
    return result


@router.get("/api/ext/drafts/match")
async def ext_draft_match(
    db: DbSession,
    caller: ExtensionCaller,
    url: Annotated[str, Query(min_length=1, max_length=2048)],
) -> ExtDraftMatch:
    _, user = caller
    result = await extension_drafts.match(db, user, url)
    await db.commit()
    return ExtDraftMatch(drafts=result)


@router.get("/api/ext/drafts/{draft_id}")
async def ext_draft(
    db: DbSession,
    caller: ExtensionCaller,
    draft_id: uuid.UUID,
    number: Annotated[int | None, Query(ge=1)] = None,
) -> ExtDraftVersion:
    _, user = caller
    result = await extension_drafts.version_detail(db, user, draft_id, number)
    await db.commit()
    return result


@router.get("/api/ext/drafts/{draft_id}/pdf")
async def ext_draft_pdf(
    db: DbSession,
    caller: ExtensionCaller,
    draft_id: uuid.UUID,
    number: Annotated[int, Query(ge=1)],
    kind: Literal["resume", "cover_letter"] = "resume",
    template: Literal["standard", "compact"] | None = None,
) -> Response:
    _, user = caller
    data, name = await extension_drafts.pdf(db, user, draft_id, kind, number, template)
    await db.commit()
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name),
            "Cache-Control": "private, no-store",
        },
    )
