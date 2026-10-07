"""PRD section 7: the Feed loads in under 2 s for 2,000 Jobs. Also the tracker, which
grows with every application. Seeded with set-based SQL so the test itself stays fast."""

import time

from sqlalchemy import text

from tests.conftest import signed_in

JOBS = 2000
BUDGET_SECONDS = 2.0


async def seed(db, user_id) -> None:
    await db.execute(
        text(
            "INSERT INTO companies (id, name, normalized_name) "
            "SELECT gen_random_uuid(), 'Company ' || g, 'company-perf-' || g "
            "FROM generate_series(1, 200) g"
        )
    )
    await db.execute(
        text(
            "INSERT INTO jobs (id, company_id, title, company_name, locations, sources, "
            "  contact_email, posted_at, work_mode, required_skills) "
            "SELECT gen_random_uuid(), c.id, 'Engineer ' || g, c.name, "
            '  \'[{"city": "Bengaluru", "country": "IN", "remote": false}]\'::jsonb, '
            "  ARRAY['linkedin', 'greenhouse'], "
            "  CASE WHEN g % 2 = 0 THEN 'jobs' || g || '@example.com' END, "
            "  now() - (g || ' minutes')::interval, 'hybrid', ARRAY['Python', 'Go'] "
            "FROM generate_series(1, :n) g "
            "JOIN LATERAL (SELECT id, name FROM companies WHERE normalized_name = "
            "  'company-perf-' || (1 + g % 200)) c ON true"
        ),
        {"n": JOBS},
    )
    await db.execute(
        text(
            "INSERT INTO user_jobs (id, user_id, job_id) "
            "SELECT gen_random_uuid(), :user, id FROM jobs"
        ),
        {"user": user_id},
    )
    # Every tenth Job has an Application with history.
    await db.execute(
        text(
            "INSERT INTO applications (id, user_id, job_id, status, applied_at, "
            "  status_changed_at, follow_up_after) "
            "SELECT gen_random_uuid(), :user, id, 'applied', now(), now(), now() "
            "FROM (SELECT id, row_number() OVER () AS r FROM jobs) j WHERE r % 10 = 0"
        ),
        {"user": user_id},
    )
    await db.execute(
        text(
            "INSERT INTO application_events (id, user_id, application_id, status) "
            "SELECT gen_random_uuid(), user_id, id, s FROM applications, "
            "unnest(ARRAY['drafted', 'applied']) s"
        )
    )
    await db.commit()


async def timed(client, url: str) -> tuple[float, dict | list]:
    await client.get(url)  # first request warms connections and caches
    started = time.perf_counter()
    response = await client.get(url)
    assert response.status_code == 200, response.text
    return time.perf_counter() - started, response.json()


async def test_feed_and_tracker_stay_fast_at_2000_jobs(db):
    user, client = await signed_in(db, "perf@example.com")
    await seed(db, user.id)
    async with client:
        seconds, feed = await timed(client, "/api/feed")
        assert feed["counts"]["with_email"] + feed["counts"]["apply_link_only"] == JOBS
        assert seconds < BUDGET_SECONDS, f"Feed took {seconds:.2f}s"

        seconds, _ = await timed(client, "/api/feed?q=Engineer%2019&section=link")
        assert seconds < BUDGET_SECONDS, f"Filtered Feed took {seconds:.2f}s"

        seconds, tracker = await timed(client, "/api/applications")
        assert len(tracker) == JOBS // 10
        assert seconds < BUDGET_SECONDS, f"Tracker took {seconds:.2f}s"

        seconds, reminders = await timed(client, "/api/reminders")
        assert len(reminders) == JOBS // 10
        assert seconds < BUDGET_SECONDS, f"Reminders took {seconds:.2f}s"
