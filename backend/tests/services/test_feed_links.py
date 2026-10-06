from sqlalchemy import func, select, text

from app.models import Preference, UserJob
from app.services.feed import sync_all_feeds, sync_user_feed
from tests.conftest import signed_in

MANY = 12_000  # over asyncpg's 32,767-parameter limit at 3 parameters per link


async def test_a_very_broad_feed_still_links_and_unlinks(db):
    user, client = await signed_in(db, "broad@example.com")
    await client.aclose()
    await db.execute(
        text(
            "INSERT INTO companies (id, name, normalized_name) "
            "VALUES ('00000000-0000-0000-0000-0000000000c1', 'Acme', 'acme')"
        )
    )
    await db.execute(
        text(
            "INSERT INTO jobs (id, company_id, title, company_name, locations, sources) "
            "SELECT gen_random_uuid(), '00000000-0000-0000-0000-0000000000c1', "
            "'Software Engineer', 'Acme', '[]'::jsonb, '{}' FROM generate_series(1, :n)"
        ),
        {"n": MANY},
    )
    preference = Preference(
        user_id=user.id,
        titles=["Software Engineer"],
        locations=[{"city": None, "country": "IN"}],
        work_modes=["onsite"],
    )
    db.add(preference)
    await db.commit()

    await sync_all_feeds(db)
    await db.commit()
    count = select(func.count()).select_from(UserJob).where(UserJob.user_id == user.id)
    assert await db.scalar(count) == MANY

    preference.titles = ["Data Engineer"]
    await db.commit()
    assert await sync_user_feed(db, user.id) == 0
    await db.commit()
    assert await db.scalar(count) == 0
