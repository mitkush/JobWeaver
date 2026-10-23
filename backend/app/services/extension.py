"""Application Extension connections (ADR-0017).

The extension opens a signed-in JobWeaver page with a PKCE challenge. The User approves it
there (cookie session, CSRF-checked), which creates a short single-use code bound to the
extension ID and the challenge. The extension exchanges the code, with its verifier and
from its own origin, for an opaque bearer credential. Only hashes are stored."""

import base64
import hashlib
import hmac
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AuthError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from app.core.security import hash_token, new_token
from app.models.extension import ExtensionCredential, ExtensionGrant
from app.models.user import User

GRANT_SECONDS = 120
# What a connected extension can do, shown on the approval page. Adding access raises the
# version: connections approved for an older list are refused until approved again.
SCOPES_VERSION = 2
SCOPES = (
    "See your name and email",
    "Read your reviewed application profile",
    "Read your Saved Answers for a Job",
    "List your Drafts and download their resume and cover letter PDFs",
)
EXTENSION_ID = re.compile(r"[a-p]{32}")
CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43}")
VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}")


def extension_origin(extension_id: str) -> str:
    return f"chrome-extension://{extension_id}"


def s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _allowed(extension_id: str) -> bool:
    return extension_id in get_settings().extension_ids


def _now() -> datetime:
    return datetime.now(UTC)


async def approve(
    session: AsyncSession, user: User, extension_id: str, challenge: str, scopes_version: int
) -> tuple[str, datetime]:
    """The User approved the connection on a signed-in page; returns the one-time code."""
    if not EXTENSION_ID.fullmatch(extension_id) or not CHALLENGE.fullmatch(challenge):
        raise ValidationFailedError(
            "This connection link is not valid. Start again from the extension."
        )
    if not _allowed(extension_id):
        raise ForbiddenError("This extension is not approved for this JobWeaver server")
    if scopes_version != SCOPES_VERSION:
        raise ConflictError("What the extension can access has changed. Reload this page.")
    now = _now()
    await session.execute(
        delete(ExtensionGrant).where(
            ExtensionGrant.user_id == user.id, ExtensionGrant.expires_at < now
        )
    )
    code = new_token()
    expires = now + timedelta(seconds=GRANT_SECONDS)
    session.add(
        ExtensionGrant(
            user_id=user.id,
            extension_id=extension_id,
            code_hash=hash_token(code),
            challenge=challenge,
            scopes_version=scopes_version,
            expires_at=expires,
        )
    )
    await session.flush()
    return code, expires


async def exchange(
    session: AsyncSession, code: str, verifier: str, origin: str | None
) -> tuple[str, ExtensionCredential, User]:
    """Single use: a reused code also revokes what that extension holds for the User."""
    grant = (
        await session.execute(
            select(ExtensionGrant)
            .where(ExtensionGrant.code_hash == hash_token(code))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if grant is None:
        raise AuthError("This connection code is not valid. Start again from the extension.")
    if origin != extension_origin(grant.extension_id) or not _allowed(grant.extension_id):
        raise ForbiddenError("This connection code belongs to another extension")
    now = _now()
    if grant.used_at is not None:
        await _revoke_extension(session, grant.user_id, grant.extension_id, now)
        raise AuthError("This connection code was already used. Start again from the extension.")
    grant.used_at = now
    if grant.expires_at <= now:
        raise AuthError("This connection code expired. Start again from the extension.")
    if not VERIFIER.fullmatch(verifier) or not hmac.compare_digest(s256(verifier), grant.challenge):
        raise AuthError("This connection code does not match the extension's request")
    token = new_token()
    credential = ExtensionCredential(
        user_id=grant.user_id,
        extension_id=grant.extension_id,
        token_hash=hash_token(token),
        expires_at=now + timedelta(hours=get_settings().extension_credential_hours),
        scopes_version=grant.scopes_version,
        last_used_at=now,
    )
    session.add(credential)
    await session.flush()
    user = await session.get(User, grant.user_id)
    assert user is not None  # the grant cascades with its User
    return token, credential, user


async def resolve(
    session: AsyncSession, token: str, origin: str | None
) -> tuple[ExtensionCredential, User]:
    row = (
        await session.execute(
            select(ExtensionCredential, User)
            .join(User, User.id == ExtensionCredential.user_id)
            .where(ExtensionCredential.token_hash == hash_token(token))
        )
    ).one_or_none()
    now = _now()
    if (
        row is None
        or row[0].revoked_at is not None
        or row[0].expires_at <= now
        or not _allowed(row[0].extension_id)
    ):
        raise AuthError("Connect the extension to JobWeaver again")
    credential, user = row
    if credential.scopes_version < SCOPES_VERSION:
        raise AuthError(
            "The extension can do more now. Connect it again to approve the new access."
        )
    # Service-worker requests carry the extension's origin; anything else is refused.
    if origin is not None and origin != extension_origin(credential.extension_id):
        raise ForbiddenError("This credential belongs to another extension")
    credential.last_used_at = now
    return credential, user


async def active_connections(session: AsyncSession, user: User) -> list[ExtensionCredential]:
    return list(
        (
            await session.execute(
                select(ExtensionCredential)
                .where(
                    ExtensionCredential.user_id == user.id,
                    ExtensionCredential.revoked_at.is_(None),
                    ExtensionCredential.expires_at > _now(),
                )
                .order_by(ExtensionCredential.created_at.desc())
            )
        ).scalars()
    )


async def revoke(session: AsyncSession, user: User, credential_id: uuid.UUID) -> None:
    result = await session.execute(
        update(ExtensionCredential)
        .where(
            ExtensionCredential.id == credential_id,
            ExtensionCredential.user_id == user.id,
            ExtensionCredential.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    if not result.rowcount:  # type: ignore[attr-defined]
        raise NotFoundError("Connection not found")


async def disconnect(session: AsyncSession, credential: ExtensionCredential) -> None:
    credential.revoked_at = _now()


async def _revoke_extension(
    session: AsyncSession, user_id: uuid.UUID, extension_id: str, now: datetime
) -> None:
    await session.execute(
        update(ExtensionCredential)
        .where(
            ExtensionCredential.user_id == user_id,
            ExtensionCredential.extension_id == extension_id,
            ExtensionCredential.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
