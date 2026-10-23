"""Application Extension connection (ADR-0017).

/api/extension/ is used by the signed-in web app (cookie session and CSRF): approve a
connection, list and revoke connections. /api/ext/ is used only by the extension's service
worker with a bearer credential; it is exempt from the cookie CSRF check because it never
reads cookies."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Header

from app.api.deps import CurrentUser, DbSession, ExtensionCaller
from app.core.errors import JobWeaverError
from app.schemas.extension import (
    ExtensionApproveIn,
    ExtensionConnectionOut,
    ExtensionGrantOut,
    ExtensionTokenIn,
    ExtensionTokenOut,
    ExtensionUserOut,
)
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
