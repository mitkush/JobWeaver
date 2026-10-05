from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AuthError
from app.gateway.base import BaseAIGateway
from app.gateway.factory import build_gateway
from app.models.user import User
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


def get_gateway(db: DbSession) -> BaseAIGateway:
    return build_gateway(db)


CurrentUser = Annotated[User, Depends(current_user)]
Gateway = Annotated[BaseAIGateway, Depends(get_gateway)]
Google = Annotated[GoogleOAuthClient, Depends(get_google_client)]
