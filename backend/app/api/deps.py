from typing import Annotated

from fastapi import Cookie, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AuthError
from app.gateway.base import BaseAIGateway
from app.gateway.factory import build_gateway
from app.models.extension import ExtensionCredential
from app.models.user import User
from app.services import extension as extension_service
from app.services.auth import resolve_session
from app.services.google_oauth import GoogleOAuthClient, get_google_client

SESSION_COOKIE = "jw_session"
CSRF_COOKIE = "jw_csrf"
CSRF_HEADER = "X-CSRF-Token"

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def current_user(db: DbSession, jw_session: Annotated[str | None, Cookie()] = None) -> User:
    if not jw_session:
        raise AuthError("Please sign in")
    return await resolve_session(db, jw_session)


async def extension_caller(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    origin: Annotated[str | None, Header()] = None,
) -> tuple[ExtensionCredential, User]:
    """The /api/ext/ surface: bearer credential only, never the session cookie (ADR-0017)."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("Connect the extension to JobWeaver")
    return await extension_service.resolve(db, token, origin)


def get_gateway() -> BaseAIGateway:
    return build_gateway()


CurrentUser = Annotated[User, Depends(current_user)]
ExtensionCaller = Annotated[tuple[ExtensionCredential, User], Depends(extension_caller)]
Gateway = Annotated[BaseAIGateway, Depends(get_gateway)]
Google = Annotated[GoogleOAuthClient, Depends(get_google_client)]
