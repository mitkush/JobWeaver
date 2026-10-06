from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.adapters import registry
from app.adapters.base import (
    FetchResult,
    FetchWindow,
    Location,
    NormalizedPosting,
    SnapshotSourceAdapter,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import BoardNotFound, SourceUnavailable
from app.core.config import Settings
from app.core.db import get_sessionmaker
from app.models import AtsBoard, FetchRun, Posting, Preference, Source, SourceState
from app.services.fetching import (
    FETCH_LOCK_ID,
    Fetcher,
    next_renewal,
    period_start,
    queries_from_preferences,
)
from tests.conftest import signed_in

START = datetime(2026, 10, 5, 1, 17, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def posting(job_id: str, company: str = "Acme Corp", apply_url: str | None = None, **extra):
    return NormalizedPosting(
        source_job_id=job_id,
        title=extra.pop("title", "Backend Engineer"),
        company=company,
        description="Python",
        locations=[Location(city="Bengaluru", country="IN")],
        apply_url=apply_url,
        **extra,
    )


class FakeSearch(WindowedSourceAdapter):
    name = "fake-search"
    label = "Fake Search"
    priority = 1
    monthly_allowance = 10
    allowance_unit = "credits"
    windows: list[tuple[str, FetchWindow]] = []
    results: list[FetchResult | Exception] = []

    async def fetch_window(self, query, window):
        type(self).windows.append((query.key if query else "all", window))
        result = type(self).results.pop(0) if type(self).results else FetchResult(postings=[])
        if isinstance(result, Exception):
            raise result
        return result


class FakeBoard(SnapshotSourceAdapter):
    name = "fake-board"
    label = "Fake Board"
    priority = 3
    ats = "greenhouse"
    boards: dict[str, FetchResult | Exception] = {}

    async def fetch_board(self, slug):
        result = type(self).boards[slug]
        if isinstance(result, Exception):
            raise result
        return result


class Unconfigured(WindowedSourceAdapter):
    name = "fake-keyless"
    label = "Keyless"
    priority = 9

    def is_configured(self):
        return False

    async def fetch_window(self, query, window):
        raise AssertionError("must not be called")


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(registry, "_REGISTRY", {})
    for cls in (FakeSearch, FakeBoard, Unconfigured):
        registry.register_adapter(cls)
    FakeSearch.windows, FakeSearch.results, FakeBoard.boards = [], [], {}


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def fetcher(clock):
    return Fetcher(get_sessionmaker(), settings=Settings(), clock=clock)


async def add_preferences(db, email="a@example.com", titles=("Backend Engineer",)):
    user, client = await signed_in(db, email)
    await client.aclose()
    db.add(
        Preference(
            user_id=user.id,
            titles=list(titles),
            keywords=[],
            locations=[{"city": "Bengaluru", "country": "IN"}],
            work_modes=["hybrid", "remote"],
        )
    )
    await db.commit()


async def source_row(db, name) -> Source:
    db.expire_all()
    return (await db.execute(select(Source).where(Source.name == name))).scalar_one()


def test_queries_are_shared_across_users_and_include_remote():
    a = Preference(titles=["Backend Engineer"], locations=[{"city": "Bengaluru", "country": "IN"}],
                   work_modes=["hybrid", "remote"])  # fmt: skip
    b = Preference(titles=["backend engineer"], locations=[{"city": "Bengaluru", "country": "IN"}],
                   work_modes=["onsite"])  # fmt: skip
    keys = [q.key for q in queries_from_preferences([a, b])]
    assert keys == [
        "backend engineer@Bengaluru|IN|False",
        "backend engineer@|IN|True",
    ]


def test_billing_period():
    now = datetime(2026, 10, 5, tzinfo=UTC)
    assert period_start(now, 1) == datetime(2026, 10, 1, tzinfo=UTC)
    assert period_start(now, 20) == datetime(2026, 9, 20, tzinfo=UTC)
    assert next_renewal(now, 20) == datetime(2026, 10, 20, tzinfo=UTC)
    assert next_renewal(datetime(2026, 12, 3, tzinfo=UTC), 1) == datetime(2027, 1, 1, tzinfo=UTC)


async def test_backfill_then_daily_windows_then_catch_up(db, fetcher, clock):
    await add_preferences(db)
    FakeSearch.results = [FetchResult(postings=[posting("1")], credits_used=1)] * 2
    await fetcher.run_source("fake-search")
    first = {key: window for key, window in FakeSearch.windows}
    assert all(w.since == START - timedelta(days=14) for w in first.values())

    FakeSearch.windows.clear()
    clock.now = START + timedelta(days=1)
    await fetcher.run_source("fake-search")
    assert all(w.since == START - timedelta(hours=2) for _, w in FakeSearch.windows)

    # The host slept for two days: the next window starts at the last success, not 24h ago.
    FakeSearch.windows.clear()
    clock.now = START + timedelta(days=3)
    await fetcher.run_source("fake-search")
    assert all(w.since == START + timedelta(days=1, hours=-2) for _, w in FakeSearch.windows)


async def test_refetching_never_duplicates_postings(db, fetcher, clock):
    await add_preferences(db)
    FakeSearch.results = [FetchResult(postings=[posting("1"), posting("1")])] * 4
    await fetcher.run_source("fake-search")
    clock.now += timedelta(days=1)
    await fetcher.run_source("fake-search")
    assert await db.scalar(select(func.count()).select_from(Posting)) == 1
    runs = list((await db.execute(select(FetchRun).order_by(FetchRun.created_at))).scalars())
    assert [r.postings_new for r in runs][-1] == 0


async def test_failing_source_is_degraded_and_others_still_run(db, fetcher):
    await add_preferences(db)
    FakeSearch.results = [SourceUnavailable("Fake Search is down")] * 2
    FakeBoard.boards = {"acme": FetchResult(postings=[posting("gh-1")])}
    db.add(AtsBoard(ats="greenhouse", slug="acme", discovered_from="manual"))
    await db.commit()

    outcomes = await fetcher.run_all()
    by_name = {o.source: o for o in outcomes}
    assert by_name["fake-search"].status == "failed"
    assert by_name["fake-board"].status == "succeeded"
    assert by_name["fake-keyless"].status == "failed"
    search = await source_row(db, "fake-search")
    assert search.state == SourceState.DEGRADED and search.last_error == "Fake Search is down"
    keyless = await source_row(db, "fake-keyless")
    assert "not configured" in keyless.last_error
    assert await db.scalar(select(func.count()).select_from(Posting)) == 1


async def test_recovery_clears_the_degraded_state(db, fetcher, clock):
    await add_preferences(db)
    FakeSearch.results = [SourceUnavailable("down"), FetchResult(postings=[])]
    await fetcher.run_source("fake-search")
    clock.now += timedelta(days=1)
    await fetcher.run_source("fake-search")
    source = await source_row(db, "fake-search")
    assert source.state == SourceState.HEALTHY and source.degraded_since is None


async def test_exhausted_budget_skips_calls_until_renewal(db, fetcher):
    await add_preferences(db)
    db.add(FetchRun(source="fake-search", status="succeeded", query_key="x", credits_used=10))
    await db.commit()
    outcome = await fetcher.run_source("fake-search")
    assert outcome.status == "failed"
    assert "renews 01 Nov 2026" in outcome.message
    assert FakeSearch.windows == []


async def test_snapshot_closes_and_reopens_postings(db, fetcher, clock):
    db.add(AtsBoard(ats="greenhouse", slug="acme", discovered_from="manual"))
    await db.commit()
    FakeBoard.boards = {"acme": FetchResult(postings=[posting("1"), posting("2")])}
    await fetcher.run_source("fake-board")

    clock.now += timedelta(days=1)
    FakeBoard.boards = {"acme": FetchResult(postings=[posting("1")])}
    await fetcher.run_source("fake-board")
    db.expire_all()
    closed = (await db.execute(select(Posting).where(Posting.source_job_id == "2"))).scalar_one()
    assert closed.closed_reason == "board"

    clock.now += timedelta(days=1)
    FakeBoard.boards = {"acme": FetchResult(postings=[posting("1"), posting("2")])}
    await fetcher.run_source("fake-board")
    db.expire_all()
    reopened = (await db.execute(select(Posting).where(Posting.source_job_id == "2"))).scalar_one()
    assert reopened.closed_at is None


async def test_missing_board_is_disabled_without_degrading_the_source(db, fetcher):
    db.add(AtsBoard(ats="greenhouse", slug="gone", discovered_from="apply_url"))
    await db.commit()
    FakeBoard.boards = {"gone": BoardNotFound("no board")}
    outcome = await fetcher.run_source("fake-board")
    assert outcome.status == "succeeded"
    db.expire_all()
    board = (await db.execute(select(AtsBoard))).scalar_one()
    assert board.enabled is False


async def test_boards_are_discovered_from_apply_urls_then_fetched(db, fetcher, clock):
    await add_preferences(db)
    url = "https://boards.greenhouse.io/acme/jobs/1"
    FakeSearch.results = [FetchResult(postings=[posting("li-1", apply_url=url)])] * 2
    await fetcher.run_source("fake-search")
    board = (await db.execute(select(AtsBoard))).scalar_one()
    assert (board.ats, board.slug, board.discovered_from) == ("greenhouse", "acme", "apply_url")

    FakeBoard.boards = {"acme": FetchResult(postings=[posting("gh-1")])}
    await fetcher.run_source("fake-board")
    assert await db.scalar(select(func.count()).select_from(Posting)) == 2


async def test_quiet_boards_are_fetched_weekly(db, fetcher, clock):
    db.add(
        AtsBoard(
            ats="greenhouse",
            slug="quiet",
            discovered_from="manual",
            last_fetched_at=START - timedelta(days=2),
            last_nonempty_at=START - timedelta(days=40),
        )
    )
    await db.commit()
    FakeBoard.boards = {"quiet": FetchResult(postings=[])}
    await fetcher.run_source("fake-board")
    assert await db.scalar(select(func.count()).select_from(FetchRun)) == 0
    clock.now = START + timedelta(days=6)
    await fetcher.run_source("fake-board")
    assert await db.scalar(select(func.count()).select_from(FetchRun)) == 1


async def test_old_windowed_postings_expire_but_board_postings_do_not(db, fetcher, clock):
    await add_preferences(db)
    old = START - timedelta(days=40)
    FakeSearch.results = [FetchResult(postings=[posting("old", posted_at=old), posting("new")])] * 2
    db.add(AtsBoard(ats="greenhouse", slug="acme", discovered_from="manual"))
    await db.commit()
    FakeBoard.boards = {"acme": FetchResult(postings=[posting("gh-old", posted_at=old)])}
    await fetcher.run_all()
    db.expire_all()
    status = {
        p.source_job_id: p.closed_reason for p in (await db.execute(select(Posting))).scalars()
    }
    assert status == {"old": "age", "new": None, "gh-old": None}


async def test_only_one_run_at_a_time(db, fetcher):
    async with get_sessionmaker()() as other:
        await other.execute(text(f"SELECT pg_advisory_lock({FETCH_LOCK_ID})"))
        assert await fetcher.run_all() is None
        await other.execute(text(f"SELECT pg_advisory_unlock({FETCH_LOCK_ID})"))


async def test_manual_runs_are_limited_per_day(db, fetcher):
    await fetcher.sync_sources()
    outcomes = [await fetcher.manual_run("fake-board") for _ in range(5)]
    assert [o.status for o in outcomes[:4]] == ["succeeded"] * 4
    assert outcomes[4].status == "skipped"


async def test_min_interval_is_respected_for_scheduled_runs(db, fetcher, clock, monkeypatch):
    monkeypatch.setattr(FakeSearch, "per_query", False)
    monkeypatch.setattr(FakeSearch, "min_interval_hours", 6)
    await fetcher.sync_sources()
    await fetcher.run_source("fake-search")
    clock.now += timedelta(hours=2)
    assert (await fetcher.run_source("fake-search")).message == "ran recently"
    assert FakeSearch.windows[0][0] == "all"


async def test_budget_projection(db, clock):
    from app.services.fetching import budget_for

    db.add(FetchRun(source="fake-search", status="succeeded", query_key="q1", credits_used=4))
    db.add(FetchRun(source="fake-search", status="succeeded", query_key="q2", credits_used=1))
    await db.commit()
    budget = await budget_for(db, FakeSearch, START)
    assert (budget.spent, budget.allowance) == (5, 10)
    assert budget.top_queries[0] == ("q1", 4)
    assert budget.runs_out_on is not None and budget.runs_out_on < budget.renews_on


def test_windowed_query_key_is_stable():
    query = SourceQuery(keywords="Backend Engineer", location=Location(country="IN", remote=True))
    assert query.key == "backend engineer@|IN|True"


async def test_network_errors_and_bad_data_never_stop_the_run(db, fetcher):
    import httpx

    await add_preferences(db)
    FakeSearch.results = [httpx.ConnectError("connection refused")] * 2
    FakeBoard.boards = {"acme": ValueError("bad json")}
    db.add(AtsBoard(ats="greenhouse", slug="acme", discovered_from="manual"))
    await db.commit()
    outcomes = {o.source: o for o in await fetcher.run_all()}
    assert outcomes["fake-search"].message == "Fake Search could not be reached (ConnectError)"
    assert outcomes["fake-board"].message == (
        "1 of 1 Fake Board boards failed "
        "(last: acme: Fake Board returned data JobWeaver could not read)"
    )
    runs = list((await db.execute(select(FetchRun))).scalars())
    assert {r.status.value for r in runs} == {"failed"}


async def test_unexpected_errors_degrade_only_that_source(db, fetcher, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr("app.services.fetching.save_postings", boom)
    await add_preferences(db)
    FakeSearch.results = [FetchResult(postings=[posting("1")])] * 2
    outcomes = {o.source: o for o in await fetcher.run_all()}
    assert outcomes["fake-search"].status == "failed"
    assert "unexpectedly" in outcomes["fake-search"].message
    assert outcomes["fake-board"].status == "succeeded"


async def test_restart_catch_up_runs_only_when_the_daily_run_was_missed(db, monkeypatch):
    from app import scheduler
    from app.services.fetching import daily_run_missed

    now = datetime.now(UTC)
    assert await daily_run_missed(db, now) is True  # first start: nothing has run yet
    calls = []

    async def fake_daily():
        calls.append("run")

    monkeypatch.setattr(scheduler, "daily_fetch", fake_daily)
    assert await scheduler.catch_up_after_restart() is True and calls == ["run"]

    db.add(FetchRun(source="x", status="succeeded", trigger="schedule"))
    await db.commit()
    assert await scheduler.catch_up_after_restart() is False and calls == ["run"]

    # Manual runs do not count as the daily run.
    assert await daily_run_missed(db, now + timedelta(hours=27)) is True


def test_scheduler_registers_the_daily_job_and_a_catch_up():
    import asyncio

    from app.scheduler import start_scheduler, stop_scheduler

    async def check():
        jobs = {job.id for job in start_scheduler().get_jobs()}
        stop_scheduler()
        return jobs

    assert asyncio.run(check()) == {"daily_fetch", "catch_up_after_restart"}


# --- Review fixes: board isolation, credits, trigger limits, manual-run lock -----------


async def add_boards(db, *slugs):
    for slug in slugs:
        db.add(AtsBoard(ats="greenhouse", slug=slug, discovered_from="manual"))
    await db.commit()


async def test_one_broken_board_does_not_stop_the_boards_after_it(db, fetcher):
    await add_boards(db, "acme", "beta", "gamma")
    FakeBoard.boards = {
        "acme": SourceUnavailable("Greenhouse rejected the API key (HTTP 403)"),
        "beta": FetchResult(postings=[posting("b1")]),
        "gamma": FetchResult(postings=[posting("g1")]),
    }
    outcome = await fetcher.run_source("fake-board")
    assert outcome.status == "succeeded" and outcome.postings_new == 2
    assert (await source_row(db, "fake-board")).state == SourceState.HEALTHY
    statuses = {r.status.value for r in (await db.execute(select(FetchRun))).scalars()}
    assert statuses == {"failed", "succeeded"}


async def test_most_boards_failing_degrades_the_source(db, fetcher):
    await add_boards(db, "a", "b", "c")
    FakeBoard.boards = {
        "a": SourceUnavailable("down"),
        "b": SourceUnavailable("down"),
        "c": FetchResult(postings=[posting("c1")]),
    }
    outcome = await fetcher.run_source("fake-board")
    assert outcome.status == "failed"
    assert outcome.message == "2 of 3 Fake Board boards failed (last: b: down)"
    assert await db.scalar(select(func.count()).select_from(Posting)) == 1


async def test_rate_limit_stops_the_ats_for_the_day(db, fetcher):
    from app.adapters.errors import SourceRateLimited

    await add_boards(db, "a", "b")
    FakeBoard.boards = {"a": SourceRateLimited("slow down"), "b": FetchResult(postings=[])}
    outcome = await fetcher.run_source("fake-board")
    assert outcome.status == "failed"
    assert await db.scalar(select(func.count()).select_from(FetchRun)) == 1  # "b" not tried


async def test_spend_is_recorded_even_when_saving_fails(db, fetcher, monkeypatch):
    await add_preferences(db)

    async def boom(*args, **kwargs):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr("app.services.fetching.save_postings", boom)
    FakeSearch.results = [FetchResult(postings=[posting("1")], credits_used=7)] * 2
    await fetcher.run_source("fake-search")
    db.expire_all()
    runs = list((await db.execute(select(FetchRun))).scalars())
    # The first search was billed (7 credits); the failure then stops this source.
    assert [(r.status.value, r.credits_used) for r in runs] == [("failed", 7)]


async def test_spend_on_a_failed_call_is_recorded(db, fetcher):
    await add_preferences(db)
    FakeSearch.results = [SourceUnavailable("HTTP 500", credits_used=1)] * 2
    await fetcher.run_source("fake-search")
    run = (await db.execute(select(FetchRun))).scalars().first()
    assert (run.status.value, run.credits_used) == ("failed", 1)


async def test_cron_after_the_daily_run_repeats_nothing(db, fetcher, clock):
    await add_preferences(db)
    await add_boards(db, "acme")
    FakeBoard.boards = {"acme": FetchResult(postings=[posting("g1")])}
    FakeSearch.results = [FetchResult(postings=[])] * 10
    await fetcher.run_all(trigger="schedule")
    calls_after_schedule = len(FakeSearch.windows)
    runs_after_schedule = await db.scalar(select(func.count()).select_from(FetchRun))

    clock.now += timedelta(hours=3)
    await fetcher.run_all(trigger="cron")
    assert len(FakeSearch.windows) == calls_after_schedule
    assert await db.scalar(select(func.count()).select_from(FetchRun)) == runs_after_schedule

    # The admin's "Run now" deliberately repeats searches and boards.
    await fetcher.manual_run("fake-search")
    await fetcher.manual_run("fake-board")
    assert len(FakeSearch.windows) > calls_after_schedule
    assert await db.scalar(select(func.count()).select_from(FetchRun)) > runs_after_schedule


async def test_provider_call_limits_apply_to_manual_runs_too(db, fetcher, clock, monkeypatch):
    monkeypatch.setattr(FakeSearch, "per_query", False)
    monkeypatch.setattr(FakeSearch, "min_interval_hours", 6)
    await fetcher.run_source("fake-search")
    clock.now += timedelta(hours=1)
    assert (await fetcher.manual_run("fake-search")).message == "ran recently"
    assert len(FakeSearch.windows) == 1


async def test_manual_run_waits_for_the_daily_run(db, fetcher):
    await fetcher.sync_sources()
    async with get_sessionmaker()() as other:
        await other.execute(text(f"SELECT pg_advisory_lock({FETCH_LOCK_ID})"))
        outcome = await fetcher.manual_run("fake-board")
        await other.execute(text(f"SELECT pg_advisory_unlock({FETCH_LOCK_ID})"))
    assert outcome.status == "skipped" and "already running" in outcome.message
    assert (await source_row(db, "fake-board")).manual_runs_today == 0
