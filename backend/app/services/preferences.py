from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preference import Preference
from app.models.user import User
from app.schemas.preferences import PreferencesIn


async def get_preferences(session: AsyncSession, user: User) -> Preference | None:
    query = select(Preference).where(Preference.user_id == user.id)
    return (await session.execute(query)).scalar_one_or_none()


async def save_preferences(session: AsyncSession, user: User, data: PreferencesIn) -> Preference:
    preference = await get_preferences(session, user) or Preference(user_id=user.id)
    preference.titles = data.titles
    preference.keywords = data.keywords
    preference.locations = [loc.model_dump() for loc in data.locations]
    preference.work_modes = [mode.value for mode in data.work_modes]
    session.add(preference)
    await session.flush()
    return preference
