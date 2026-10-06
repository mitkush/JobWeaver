import enum
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import GoogleFlowError, JobWeaverError
from app.core.security import decrypt, encrypt
from app.models.oauth_credential import OAuthCredential
from app.models.user import User
from app.services.google_oauth import GMAIL_COMPOSE_SCOPE, GoogleOAuthClient, GoogleTokens

logger = logging.getLogger(__name__)
EXPIRES_SOON = timedelta(hours=24)


class GmailState(enum.StrEnum):
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    EXPIRES_SOON = "expires_soon"
    EXPIRED = "expired"


async def _credential(session: AsyncSession, user: User) -> OAuthCredential | None:
    query = select(OAuthCredential).where(
        OAuthCredential.user_id == user.id, OAuthCredential.provider == "gmail"
    )
    return (await session.execute(query)).scalar_one_or_none()


async def store_gmail_credential(session: AsyncSession, user: User, tokens: GoogleTokens) -> None:
    if GMAIL_COMPOSE_SCOPE not in tokens.scope.split():
        raise GoogleFlowError(
            "gmail_scope", "Gmail access was not granted. Tick the Gmail box on Google's screen."
        )
    if not tokens.refresh_token:
        raise GoogleFlowError(
            "gmail_token", "Google did not return a Gmail token. Please connect Gmail again."
        )
    credential = await _credential(session, user) or OAuthCredential(user_id=user.id)
    credential.provider = "gmail"
    credential.refresh_token_encrypted = encrypt(tokens.refresh_token)
    credential.scopes = tokens.scope
    credential.granted_at = datetime.now(UTC)
    session.add(credential)
    await session.flush()


async def gmail_status(session: AsyncSession, user: User) -> tuple[GmailState, datetime | None]:
    """In testing mode, Google expires the grant 7 days after consent (ADR-0006)."""
    credential = await _credential(session, user)
    if credential is None:
        return GmailState.NOT_CONNECTED, None
    lifetime = get_settings().gmail_token_lifetime_days
    if lifetime <= 0:
        return GmailState.CONNECTED, None
    expires_at = credential.granted_at + timedelta(days=lifetime)
    now = datetime.now(UTC)
    if expires_at <= now:
        return GmailState.EXPIRED, expires_at
    if expires_at - now <= EXPIRES_SOON:
        return GmailState.EXPIRES_SOON, expires_at
    return GmailState.CONNECTED, expires_at


async def disconnect_gmail(session: AsyncSession, user: User, google: GoogleOAuthClient) -> None:
    credential = await _credential(session, user)
    if credential is None:
        return
    try:
        token = decrypt(credential.refresh_token_encrypted)
    except JobWeaverError:
        logger.warning("Could not decrypt Gmail token for revocation; deleting it anyway")
    else:
        await google.revoke(token)
    await session.execute(delete(OAuthCredential).where(OAuthCredential.id == credential.id))
