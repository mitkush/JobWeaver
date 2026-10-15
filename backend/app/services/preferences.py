from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import WindowedSourceAdapter, WorkMode
from app.adapters.normalize import normalize_city
from app.adapters.registry import registered_adapters
from app.core.config import get_settings
from app.models.preference import Preference
from app.models.source import Source
from app.models.user import User
from app.schemas.preferences import PreferencesIn
from app.services.feed import title_matches, title_words
from app.services.fetching import get_sources_http


async def get_preferences(session: AsyncSession, user: User) -> Preference | None:
    query = select(Preference).where(Preference.user_id == user.id)
    return (await session.execute(query)).scalar_one_or_none()


async def save_preferences(session: AsyncSession, user: User, data: PreferencesIn) -> Preference:
    preference = await get_preferences(session, user) or Preference(user_id=user.id)
    preference.titles = data.titles
    preference.keywords = data.keywords
    preference.core_keywords = data.core_keywords
    preference.keyword_min_matches = data.keyword_min_matches
    preference.search_keywords = data.search_keywords
    # Cities are stored the way Jobs store them ("Bangalore" -> "Bengaluru"), so they match.
    preference.locations = [
        loc.model_dump() | {"city": normalize_city(loc.city)} for loc in data.locations
    ]
    preference.work_modes = [mode.value for mode in data.work_modes]
    session.add(preference)
    await session.flush()
    return preference


# Related titles offered on the Preferences page (FR-A3). A suggestion is only ever added
# by the User; nothing here widens a search on its own.
_TITLE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("Backend Developer", "Software Engineer", "SDE", "Platform Engineer", "API Developer"),
    ("Frontend Developer", "UI Developer", "React Developer", "Web Developer"),
    ("Full Stack Developer", "Software Engineer", "Web Developer", "Backend Developer"),
    ("Ruby on Rails Developer", "Ruby Developer", "Backend Developer", "Full Stack Developer"),
    ("Python Developer", "Django Developer", "Backend Developer", "Software Engineer"),
    ("Java Developer", "Spring Boot Developer", "Backend Developer", "Software Engineer"),
    ("Node.js Developer", "JavaScript Developer", "Backend Developer", "Full Stack Developer"),
    ("Software Engineer", "SDE", "Backend Developer", "Full Stack Developer"),
    ("DevOps Engineer", "Site Reliability Engineer", "Platform Engineer", "Cloud Engineer"),
    ("Data Engineer", "Analytics Engineer", "ETL Developer", "Big Data Engineer"),
    ("Data Scientist", "Machine Learning Engineer", "Data Analyst", "AI Engineer"),
    ("Machine Learning Engineer", "AI Engineer", "Data Scientist", "MLOps Engineer"),
    ("Mobile Developer", "Android Developer", "iOS Developer", "Flutter Developer"),
    ("QA Engineer", "Test Engineer", "SDET", "Automation Engineer"),
    ("Product Manager", "Product Owner", "Technical Product Manager"),
    ("Engineering Manager", "Tech Lead", "Team Lead"),
)
MAX_SUGGESTIONS = 8


def suggested_titles(titles: Sequence[str]) -> list[str]:
    """Related titles the User's titles do not already match, most related first.

    A group applies when its first title is part of a wanted title ("Senior Backend
    Developer" -> the backend group). Titles a wanted one already covers are left out:
    equivalent wording ("Backend Engineer" for "Backend Developer") and the wanted title
    without its extra words ("Backend Developer" for "Senior Backend Developer")."""
    wanted = [title_words(t) for t in titles if t.strip()]
    suggestions: list[str] = []
    seen: list[set[str]] = []
    for group in _TITLE_GROUPS:
        if not any(title_words(group[0]) <= want for want in wanted):
            continue
        for member in group:
            words = title_words(member)
            covered = title_matches(member, titles) or any(words <= want for want in wanted)
            if covered or words in seen:
                continue
            seen.append(words)
            suggestions.append(member)
    return suggestions[:MAX_SUGGESTIONS]


async def searches_per_title(session: AsyncSession, preference: Preference | None) -> int:
    """Searches one more title adds to each daily run: one per metered search Source and
    wanted place. Free and snapshot Sources cost nothing and are not counted."""
    enabled = {s.name: s.enabled for s in (await session.execute(select(Source))).scalars()}
    http, settings = get_sources_http(), get_settings()
    sources = sum(
        1
        for cls in registered_adapters()
        if issubclass(cls, WindowedSourceAdapter)
        and cls.per_query
        and cls.monthly_allowance is not None
        and cls.standby_for is None
        and enabled.get(cls.name, cls.default_enabled)
        and cls(http, settings).is_configured()
        and cls(http, settings).searches_titles()
    )
    places = len(preference.locations or []) if preference else 0
    modes = set(preference.work_modes or []) if preference else set()
    # A remote search is made separately when remote is one of several work modes.
    per_place = 2 if WorkMode.REMOTE.value in modes and len(modes) > 1 else 1
    return sources * max(1, places) * per_place
