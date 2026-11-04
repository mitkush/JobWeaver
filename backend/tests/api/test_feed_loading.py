"""Feed loading: one counting pass, the server's choice of section, Server-Timing, and
cache headers for the built frontend."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.core.db import get_engine
from app.main import create_app
from tests.api.test_feed import BACKEND_BLR, seed


@pytest.fixture
def statements():
    """SQL statements sent while the test runs."""
    sent: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        sent.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", record)
    yield sent
    event.remove(engine, "before_cursor_execute", record)


async def test_counts_take_one_statement_and_match_each_section(alice, statements):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    statements.clear()
    body = (await client.get("/api/feed", params={"section": "email"})).json()
    counting = [s for s in statements if s.count("count(*) FILTER") == 5]
    assert len(counting) == 1
    email, link = body["counts"]["with_email"], body["counts"]["apply_link_only"]
    assert (email, link) == (1, 1)
    assert body["total"] == email
    assert (await client.get("/api/feed", params={"section": "link"})).json()["total"] == link


async def test_without_a_section_the_server_opens_the_one_with_jobs(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    email_job = (await client.get("/api/feed")).json()
    assert email_job["section"] == "email" and email_job["items"][0]["contact_email"]
    await client.post(f"/api/feed/{email_job['items'][0]['job_id']}/hide")

    chosen = (await client.get("/api/feed")).json()
    assert chosen["section"] == "link"
    assert chosen["total"] == chosen["counts"]["apply_link_only"] == len(chosen["items"]) == 1
    assert chosen["items"][0]["contact_email"] is None
    # An explicit choice is respected, even when that section is empty.
    asked = (await client.get("/api/feed", params={"section": "email"})).json()
    assert (asked["section"], asked["total"], asked["items"]) == ("email", 0, [])


async def test_api_responses_report_server_timing(alice):
    _, client = alice
    await client.put("/api/preferences", json=BACKEND_BLR)
    await seed()
    timing = (await client.get("/api/feed")).headers["server-timing"]
    names = [entry.split(";")[0] for entry in timing.split(", ")]
    assert names == ["counts", "page", "cards", "app"]
    assert all(";dur=" in entry for entry in timing.split(", "))
    assert "server-timing" in (await client.get("/api/me")).headers


async def test_hashed_assets_are_cached_for_a_year_and_the_page_is_revalidated(tmp_path: Path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<!doctype html>")
    app = create_app(frontend_dist=tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as web:
        asset = await web.get("/assets/index-abc123.js")
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        for path in ("/", "/feed"):
            page = await web.get(path)
            assert page.headers["cache-control"] == "no-cache"
        # Timing is for the API only; static files and pages carry none.
        assert "server-timing" not in asset.headers
