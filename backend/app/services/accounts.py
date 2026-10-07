from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import PreconditionError
from app.models.document import Document
from app.models.user import User
from app.schemas.me import GmailStatus, MeOut, OnboardingStatus
from app.services.gmail import GmailState, disconnect_gmail, gmail_status
from app.services.google_oauth import GoogleOAuthClient
from app.services.preferences import get_preferences
from app.services.regions import ai_region_blocked


def ensure_ai_allowed(user: User) -> None:
    """No document reaches an AI provider before these checks pass (FR-A5 AC2, FR-A1 AC4)."""
    if user.ai_notice_accepted_at is None:
        raise PreconditionError("Accept the AI data notice before uploading documents")
    if user.country is None:
        raise PreconditionError("Tell us which country you are in first")
    if ai_region_blocked(user.country, get_settings().gemini_free_tier):
        raise PreconditionError(
            "JobWeaver cannot process documents for users in the EEA, Switzerland or the UK "
            "while it runs on free AI tiers."
        )


async def accept_ai_notice(session: AsyncSession, user: User) -> None:
    if user.ai_notice_accepted_at is None:
        user.ai_notice_accepted_at = datetime.now(UTC)
        await session.flush()


async def set_country(session: AsyncSession, user: User, country: str) -> None:
    user.country = country.upper()
    await session.flush()


async def build_me(session: AsyncSession, user: User) -> MeOut:
    documents = await session.scalar(
        select(func.count()).select_from(Document).where(Document.user_id == user.id)
    )
    preferences = await get_preferences(session, user)
    gmail_state, gmail_expires = await gmail_status(session, user)
    blocked = ai_region_blocked(user.country, get_settings().gemini_free_tier)
    status = {
        "ai_notice_accepted": user.ai_notice_accepted_at is not None,
        "country_set": user.country is not None,
        "ai_region_blocked": blocked,
        "documents_uploaded": bool(documents),
        "fact_bank_reviewed": user.fact_bank_reviewed_at is not None,
        "preferences_set": preferences is not None,
        "gmail_connected": gmail_state in (GmailState.CONNECTED, GmailState.EXPIRES_SOON),
    }
    steps = [
        ("ai_notice", status["ai_notice_accepted"]),
        ("country", status["country_set"]),
        ("region_blocked", not blocked),
        ("documents", status["documents_uploaded"]),
        ("review", status["fact_bank_reviewed"]),
        ("preferences", status["preferences_set"]),
    ]
    next_step = next((name for name, done in steps if not done), "done")
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture_url=user.picture_url,
        role=user.role,
        country=user.country,
        onboarding=OnboardingStatus(**status, next_step=next_step),
        gmail=GmailStatus(state=gmail_state, expires_at=gmail_expires),
        follow_up_days=user.follow_up_days,
    )


async def delete_account(session: AsyncSession, user: User, google: GoogleOAuthClient) -> None:
    """Removes every user-owned row via ON DELETE CASCADE; shared job data is untouched."""
    await disconnect_gmail(session, user, google)
    await session.execute(delete(User).where(User.id == user.id))
