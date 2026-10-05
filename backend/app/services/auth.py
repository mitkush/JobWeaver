from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthError
from app.core.security import hash_token, new_token
from app.models.session import UserSession
from app.models.user import Role, User
from app.services.google_oauth import GoogleProfile


async def upsert_google_user(session: AsyncSession, profile: GoogleProfile) -> User:
    """Sign-up is open (FR-A1 AC3); Google's testing mode limits who can get this far."""
    user = (
        await session.execute(select(User).where(User.google_sub == profile.sub))
    ).scalar_one_or_none()
    if user is None:
        user = User(google_sub=profile.sub, email=profile.email)
        session.add(user)
    user.email = profile.email
    user.name = profile.name
    user.picture_url = profile.picture
    user.role = Role.ADMIN if profile.email in get_settings().admin_emails else Role.USER
    await session.flush()
    return user


async def get_user_by_google_sub(session: AsyncSession, sub: str) -> User | None:
    query = select(User).where(User.google_sub == sub)
    return (await session.execute(query)).scalar_one_or_none()


async def create_session(session: AsyncSession, user: User) -> str:
    token = new_token()
    expires = datetime.now(UTC) + timedelta(days=get_settings().session_days)
    session.add(UserSession(user_id=user.id, token_hash=hash_token(token), expires_at=expires))
    await session.flush()
    return token


async def resolve_session(session: AsyncSession, token: str) -> User:
    row = (
        await session.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_token(token))
        )
    ).one_or_none()
    if row is None or row[0].expires_at <= datetime.now(UTC):
        raise AuthError("Please sign in")
    return row[1]


async def end_session(session: AsyncSession, token: str) -> None:
    await session.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
