from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.adapters import registry
from app.adapters.base import FetchResult, NormalizedPosting, SnapshotSourceAdapter
from app.api.sources import get_fetcher
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import AtsBoard, FetchRun, Source, SourceState
from app.services.fetching import Fetcher
from tests.conftest import signed_in


class Board(SnapshotSourceAdapter):
    name = "greenhouse-test"
    label = "Greenhouse (test)"
    priority = 3
    ats = "greenhouse"

    async def fetch_board(self, slug):
        return FetchResult(
            postings=[NormalizedPosting(source_job_id="1", title="Engineer", company="Acme")]
        )


@pytest.fixture(autouse=True)
def only_test_board(monkeypatch):
    monkeypatch.setattr(registry, "_REGISTRY", {})
    registry.register_adapter(Board)


@pytest.fixture
async def admin(db):
    user, client = await signed_in(db, "admin@example.com")  # in ADMIN_EMAILS for tests
    async with client:
        yield user, client


async def test_admin_endpoints_are_admin_only(alice):
    _, client = alice
    assert (await client.get("/api/admin/sources")).status_code == 403
    assert (await client.post("/api/admin/sources/greenhouse-test/run")).status_code == 403


async def test_source_status_and_run_now(admin, db):
    _, client = admin
    db.add(AtsBoard(ats="greenhouse", slug="acme", discovered_from="manual"))
    await db.commit()

    statuses = (await client.get("/api/admin/sources")).json()
    assert statuses[0]["name"] == "greenhouse-test"
    assert statuses[0]["boards"] == 1 and statuses[0]["budget"] is None
    assert statuses[0]["manual_runs_left"] == 4

    outcome = (await client.post("/api/admin/sources/greenhouse-test/run")).json()
    assert outcome["status"] == "succeeded" and outcome["postings_new"] == 1
    after = (await client.get("/api/admin/sources")).json()[0]
    assert after["open_postings"] == 1 and after["manual_runs_left"] == 3

    runs = (await client.get("/api/admin/fetch-runs")).json()
    assert runs[0]["board"] == "acme" and runs[0]["status"] == "succeeded"


async def test_disable_and_enable(admin):
    _, client = admin
    off = await client.patch("/api/admin/sources/greenhouse-test", json={"enabled": False})
    assert off.json()[0]["state"] == "disabled" and off.json()[0]["next_run_at"] is None
    on = await client.patch("/api/admin/sources/greenhouse-test", json={"enabled": True})
    assert on.json()[0]["state"] == "healthy"
    assert (
        await client.patch("/api/admin/sources/nope", json={"enabled": True})
    ).status_code == 404


async def test_users_see_notices_only_after_a_day_of_degradation(alice, db):
    _, client = alice
    db.add(
        Source(
            name="greenhouse-test",
            state=SourceState.DEGRADED,
            degraded_since=datetime.now(UTC) - timedelta(hours=2),
        )
    )
    await db.commit()
    assert (await client.get("/api/sources/notices")).json() == []
    source = (await db.execute(select(Source))).scalar_one()
    source.degraded_since = datetime.now(UTC) - timedelta(days=2)
    await db.commit()
    notice = (await client.get("/api/sources/notices")).json()[0]
    assert notice["message"] == "Greenhouse (test) jobs are delayed; other sources are up to date."


async def test_users_add_company_boards_by_link(alice):
    _, client = alice
    added = await client.post(
        "/api/ats-boards", json={"url": "https://jobs.lever.co/netflix/abc/apply"}
    )
    assert added.status_code == 201
    assert added.json() | {"id": None, "last_fetched_at": None} == {
        "id": None,
        "ats": "lever",
        "slug": "netflix",
        "company": None,
        "discovered_from": "manual",
        "enabled": True,
        "fetched": True,
        "last_fetched_at": None,
        "open_postings": 0,
    }
    again = await client.post("/api/ats-boards", json={"url": "jobs.lever.co/netflix"})
    assert again.json()["id"] == added.json()["id"]
    bad = await client.post("/api/ats-boards", json={"url": "https://www.linkedin.com/jobs/1"})
    assert bad.status_code == 422
    assert "Greenhouse, Lever" in bad.json()["error"]["message"]
    assert len((await client.get("/api/ats-boards")).json()) == 1


async def test_cron_endpoint_needs_its_secret(anon, monkeypatch):
    from app.main import app

    calls = []

    class FakeFetcher(Fetcher):
        async def run_all(self, trigger="schedule"):
            calls.append(trigger)
            return []

    app.dependency_overrides[get_fetcher] = lambda: FakeFetcher(get_sessionmaker())
    assert (await anon.post("/api/internal/fetch")).status_code == 401
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "s3cret")
    get_settings.cache_clear()
    wrong = await anon.post("/api/internal/fetch", headers={"X-Cron-Secret": "nope"})
    assert wrong.status_code == 401
    # No CSRF token needed: cron is not a browser.
    ok = await anon.post(
        "/api/internal/fetch", headers={"X-Cron-Secret": "s3cret", "X-CSRF-Token": ""}
    )
    assert ok.status_code == 202
    import asyncio

    await asyncio.sleep(0)
    assert calls == ["cron"]


async def test_budget_is_reported_for_metered_sources(admin, db, monkeypatch):
    monkeypatch.setattr(Board, "monthly_allowance", 100)
    monkeypatch.setattr(Board, "allowance_unit", "credits")
    db.add(FetchRun(source="greenhouse-test", status="succeeded", query_key="q", credits_used=30))
    await db.commit()
    _, client = admin
    budget = (await client.get("/api/admin/sources")).json()[0]["budget"]
    assert budget["spent"] == 30 and budget["allowance"] == 100
    assert budget["top_queries"] == [{"query_key": "q", "spent": 30}]
