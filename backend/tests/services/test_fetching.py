import asyncio
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
from app.models import AtsBoard, FetchRun, Posting, Preference, RunStatus, Source, SourceState
from app.services.fetching import (
    FETCH_LOCK_ID,
    Fetcher,
    next_renewal,
    period_start,
    queries_from_preferences,
    recover_running_fetches,
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
        "backend engineer@Bengaluru|IN|True",
    ]


def test_global_preferences_generate_queries_without_location_filters():
    pref = Preference(titles=["Backend Engineer"], locations=[], work_modes=["onsite", "remote"])
    queries = queries_from_preferences([pref])
    assert len(queries) == 2
    assert {q.location.remote for q in queries} == {False, True}
    assert all(q.location.country is None and q.location.city is None for q in queries)
    pref.work_modes = ["remote"]
    assert len(queries_from_preferences([pref])) == 1
    assert queries_from_preferences([pref])[0].location.remote is True


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
    # A missing key is not an outage: skipped, not Degraded, so Users see no notice.
    assert (by_name["fake-keyless"].status, by_name["fake-keyless"].message) == (
        "skipped",
        "not configured",
    )
    search = await source_row(db, "fake-search")
    assert search.state == SourceState.DEGRADED and search.last_error == "Fake Search is down"
    keyless = await source_row(db, "fake-keyless")
    assert keyless.state == SourceState.HEALTHY and keyless.last_error is None
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


async def test_boards_that_never_had_jobs_go_weekly_after_30_days(db, fetcher, clock):
    db.add(
        AtsBoard(
            ats="greenhouse",
            slug="empty",
            discovered_from="manual",
            created_at=START - timedelta(days=40),
            last_fetched_at=START - timedelta(days=2),
            last_nonempty_at=None,
        )
    )
    db.add(
        AtsBoard(
            ats="greenhouse",
            slug="new-empty",
            discovered_from="manual",
            created_at=START - timedelta(days=3),
            last_fetched_at=START - timedelta(days=2),
            last_nonempty_at=None,
        )
    )
    await db.commit()
    FakeBoard.boards = {"empty": FetchResult(postings=[]), "new-empty": FetchResult(postings=[])}
    await fetcher.run_source("fake-board")
    fetched = (await db.execute(select(FetchRun.board_id))).scalars().all()
    new_board = await db.scalar(select(AtsBoard.id).where(AtsBoard.slug == "new-empty"))
    assert fetched == [new_board]  # the 40-day-old empty board waits for its weekly turn


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


def test_scheduler_registers_daily_fetch_queue_and_catch_up_jobs():
    import asyncio

    from app.scheduler import start_scheduler, stop_scheduler

    async def check():
        jobs = {job.id for job in start_scheduler().get_jobs()}
        stop_scheduler()
        return jobs

    assert asyncio.run(check()) == {"daily_fetch", "process_queues", "catch_up_after_restart"}


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


async def test_windowed_run_is_persisted_before_provider_call(db, fetcher, monkeypatch):
    await add_preferences(db)

    async def fetch_window(self, query, window):
        async with get_sessionmaker()() as observer:
            run = await observer.scalar(
                select(FetchRun).where(
                    FetchRun.source == "fake-search", FetchRun.status == RunStatus.RUNNING
                )
            )
            assert run is not None and run.status.value == "running"
        return FetchResult(postings=[])

    monkeypatch.setattr(FakeSearch, "fetch_window", fetch_window)
    assert (await fetcher.run_source("fake-search")).status == "succeeded"


async def test_unexpected_provider_error_closes_persisted_run(db, fetcher):
    await add_preferences(db)
    FakeSearch.results = [RuntimeError("provider bug")]

    assert (await fetcher.run_source("fake-search")).status == "failed"
    run = await db.scalar(select(FetchRun).where(FetchRun.source == "fake-search"))
    assert run is not None and run.status == RunStatus.FAILED
    assert run.error == "Stopped unexpectedly; retry on the next run"
    assert run.finished_at is not None


async def test_cancelled_provider_call_closes_persisted_run(db, fetcher, monkeypatch):
    await add_preferences(db)
    started = asyncio.Event()

    async def fetch_window(self, query, window):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(FakeSearch, "fetch_window", fetch_window)
    task = asyncio.create_task(fetcher.run_source("fake-search"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    db.expire_all()
    run = await db.scalar(select(FetchRun).where(FetchRun.source == "fake-search"))
    assert run is not None and run.status == RunStatus.FAILED
    assert run.finished_at is not None


async def test_restart_recovers_only_unfinished_fetch_runs(db):
    active = FetchRun(source="fake-search", status=RunStatus.RUNNING, query_key="active")
    done = FetchRun(source="fake-search", status=RunStatus.SUCCEEDED, query_key="done")
    db.add_all([active, done])
    await db.commit()

    assert await recover_running_fetches(get_sessionmaker()) == 1
    db.expire_all()
    rows = {row.query_key: row for row in (await db.execute(select(FetchRun))).scalars()}
    assert rows["active"].status == RunStatus.FAILED
    assert rows["active"].finished_at is not None
    assert rows["done"].status == RunStatus.SUCCEEDED
    assert await recover_running_fetches(get_sessionmaker()) == 0


async def test_board_run_is_persisted_before_provider_call(db, fetcher, monkeypatch):
    await add_boards(db, "acme")

    async def fetch_board(self, slug):
        async with get_sessionmaker()() as observer:
            run = await observer.scalar(
                select(FetchRun).where(
                    FetchRun.source == "fake-board", FetchRun.status == RunStatus.RUNNING
                )
            )
            assert run is not None and run.status.value == "running"
        return FetchResult(postings=[])

    monkeypatch.setattr(FakeBoard, "fetch_board", fetch_board)
    assert (await fetcher.run_source("fake-board")).status == "succeeded"


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


# --- Phase 3: the pipeline after each fetch ------------------------------------------------


async def test_processing_runs_after_daily_and_manual_runs_inside_the_lock(db, clock):
    calls: list[bool] = []

    async def after_fetch():
        async with get_sessionmaker()() as other:
            got = await other.scalar(text(f"SELECT pg_try_advisory_lock({FETCH_LOCK_ID})"))
            calls.append(bool(got))
            if got:
                await other.execute(text(f"SELECT pg_advisory_unlock({FETCH_LOCK_ID})"))

    fetcher = Fetcher(get_sessionmaker(), settings=Settings(), clock=clock, after_fetch=after_fetch)
    await fetcher.run_all()
    await fetcher.manual_run("fake-board")
    assert calls == [False, False]  # ran twice, both times while the fetch held the lock


async def test_a_processing_failure_never_fails_the_fetch(db, clock):
    async def broken():
        raise RuntimeError("boom")

    fetcher = Fetcher(get_sessionmaker(), settings=Settings(), clock=clock, after_fetch=broken)
    outcomes = await fetcher.run_all()
    assert outcomes is not None


async def test_queue_run_is_skipped_while_a_fetch_runs(db):
    from app.services.pipeline import process_queues

    async with get_sessionmaker()() as other:
        await other.execute(text(f"SELECT pg_advisory_lock({FETCH_LOCK_ID})"))
        assert await process_queues() is None
        await other.execute(text(f"SELECT pg_advisory_unlock({FETCH_LOCK_ID})"))
    report = await process_queues()
    assert report is not None and report.errors == []


async def test_started_manual_run_holds_the_lock_until_it_finishes(db, clock):
    import asyncio

    release = asyncio.Event()

    async def slow_processing():
        await release.wait()

    fetcher = Fetcher(
        get_sessionmaker(), settings=Settings(), clock=clock, after_fetch=slow_processing
    )
    await fetcher.sync_sources()
    started = await fetcher.start_manual_run("fake-board")
    assert started.status == "started"
    # A second run (or the daily run) is refused while the first is still processing.
    assert (await fetcher.start_manual_run("fake-board")).status == "skipped"
    release.set()
    await fetcher.manual_task
    async with get_sessionmaker()() as other:
        assert await other.scalar(text(f"SELECT pg_try_advisory_lock({FETCH_LOCK_ID})"))
        await other.execute(text(f"SELECT pg_advisory_unlock({FETCH_LOCK_ID})"))


async def test_started_manual_runs_still_count_against_the_daily_limit(db, fetcher):
    await fetcher.sync_sources()
    for _ in range(4):
        assert (await fetcher.start_manual_run("fake-board")).status == "started"
        await fetcher.manual_task
    assert (await fetcher.start_manual_run("fake-board")).status == "skipped"


class FakeStandby(FakeSearch):
    name = "fake-standby"
    label = "Fake Standby"
    standby_for = "fake-search"
    budget_pool = "fake-pool"
    windows: list[tuple[str, FetchWindow]] = []
    results: list[FetchResult | Exception] = []


class FakePoolMate(FakeSearch):
    name = "fake-pool-mate"
    label = "Fake Pool Mate"
    priority = 2
    budget_pool = "fake-pool"
    windows: list[tuple[str, FetchWindow]] = []
    results: list[FetchResult | Exception] = []


@pytest.fixture
def standby():
    registry.register_adapter(FakeStandby)
    FakeStandby.windows, FakeStandby.results = [], []
    return FakeStandby


async def test_standby_stands_by_while_its_main_source_is_healthy(db, fetcher, standby):
    await add_preferences(db)
    outcomes = {o.source: o for o in await fetcher.run_all()}
    assert outcomes["fake-search"].status == "succeeded"
    assert (outcomes["fake-standby"].status, outcomes["fake-standby"].message) == (
        "skipped",
        "standing by",
    )
    assert standby.windows == []


async def test_standby_runs_after_its_main_degrades_in_the_same_run(db, fetcher, standby):
    await add_preferences(db)
    FakeSearch.results = [SourceUnavailable("down")]
    outcomes = [o.source for o in await fetcher.run_all()]
    # Standbys run last, after their main has had its chance.
    assert outcomes.index("fake-standby") > outcomes.index("fake-search")
    assert len(standby.windows) == 2
    assert (await source_row(db, "fake-standby")).state == SourceState.HEALTHY


async def test_standby_runs_while_its_main_is_disabled(db, fetcher, standby):
    await add_preferences(db)
    await fetcher.sync_sources()
    (await source_row(db, "fake-search")).enabled = False
    await db.commit()
    await fetcher.run_all()
    assert FakeSearch.windows == [] and len(standby.windows) == 2


async def test_main_and_standby_never_pay_twice_for_the_same_window(db, fetcher, clock, standby):
    await add_preferences(db)
    FakeSearch.results = [SourceUnavailable("down")]
    await fetcher.run_all()
    assert len(standby.windows) == 2

    # The main recovers a few hours later: today's searches were already done by the standby.
    clock.now += timedelta(hours=6)
    FakeSearch.windows.clear()
    await fetcher.run_source("fake-search")
    assert FakeSearch.windows == []

    # Next day it continues from where the standby stopped, not from its own backfill.
    clock.now = START + timedelta(days=1)
    await fetcher.run_source("fake-search")
    assert all(w.since == START - timedelta(hours=2) for _, w in FakeSearch.windows)


async def test_manual_run_of_a_standby_is_allowed_while_its_main_is_healthy(db, fetcher, standby):
    await add_preferences(db)
    outcome = await fetcher.manual_run("fake-standby")
    assert outcome.status == "succeeded" and len(standby.windows) == 2


async def test_budget_pool_shares_one_allowance(db, fetcher, standby, clock):
    registry.register_adapter(FakePoolMate)
    from app.services.fetching import budget_for

    db.add(FetchRun(source="fake-pool-mate", status="succeeded", query_key="x", credits_used=10))
    await db.commit()
    budget = await budget_for(db, FakeStandby, clock())
    assert budget.spent == 10 and budget.exhausted
    # The main Source is not in the pool, so its own allowance is untouched.
    assert (await budget_for(db, FakeSearch, clock())).spent == 0


async def test_sources_off_by_default_start_disabled(db, fetcher, monkeypatch):
    monkeypatch.setattr(Unconfigured, "default_enabled", False)
    await fetcher.sync_sources()
    assert (await source_row(db, "fake-keyless")).enabled is False


async def test_a_partial_snapshot_closes_nothing(db, fetcher, clock):
    db.add(AtsBoard(ats="greenhouse", slug="acme", discovered_from="manual"))
    await db.commit()
    FakeBoard.boards = {"acme": FetchResult(postings=[posting("1"), posting("2")])}
    await fetcher.run_source("fake-board")
    clock.now += timedelta(days=1)
    FakeBoard.boards = {"acme": FetchResult(postings=[posting("1")], complete=False)}
    await fetcher.run_source("fake-board")
    db.expire_all()
    still = (await db.execute(select(Posting).where(Posting.source_job_id == "2"))).scalar_one()
    assert still.closed_at is None


async def test_pending_adverts_are_stored_once_and_reopened_when_edited(db, fetcher, clock):
    from app.adapters.base import PendingAdvert
    from app.models import RawAdvert

    advert = PendingAdvert(ref="9001", text="Acme | SRE", url="https://news.ycombinator.com/x")
    FakeSearch.per_query = False
    try:
        FakeSearch.results = [FetchResult(postings=[], pending=[advert, advert])]
        await fetcher.run_source("fake-search")
        row = (await db.execute(select(RawAdvert))).scalar_one()
        row.extracted_at = clock()
        await db.commit()
        run = (await db.execute(select(FetchRun))).scalar_one()
        assert (run.postings_found, run.postings_new) == (1, 1)

        clock.now += timedelta(days=1)
        edited = advert.model_copy(update={"text": "Acme | SRE, now remote"})
        FakeSearch.results = [FetchResult(postings=[], pending=[edited])]
        await fetcher.run_source("fake-search")
        db.expire_all()
        row = (await db.execute(select(RawAdvert))).scalar_one()
        assert row.extracted_at is None and row.text.endswith("now remote")
    finally:
        FakeSearch.per_query = True


async def test_every_search_in_a_run_ends_its_window_at_the_run_start(db, fetcher, clock):
    """Slow searches must not push later ones past a 24 h window the next day."""
    await add_preferences(db)  # two queries: hybrid and remote

    class SlowSearch(FakeSearch):
        async def fetch_window(self, query, window):
            clock.now += timedelta(minutes=40)  # each search takes a while
            return await super().fetch_window(query, window)

    registry._REGISTRY["fake-search"] = SlowSearch
    try:
        await fetcher.run_source("fake-search")
        assert {w.until for _, w in FakeSearch.windows} == {START}
        FakeSearch.windows.clear()
        clock.now = START + timedelta(days=1)
        day_two = clock.now
        await fetcher.run_source("fake-search")
        assert all(w.until == day_two for _, w in FakeSearch.windows)
        assert all(w.within_days(1) for _, w in FakeSearch.windows)
    finally:
        registry._REGISTRY["fake-search"] = FakeSearch


async def test_a_standby_covers_a_main_source_that_has_no_key(db, fetcher, standby, monkeypatch):
    await add_preferences(db)
    # Only the main Source lacks its key; the standby (a subclass) keeps its own.
    monkeypatch.setattr(FakeSearch, "is_configured", lambda self: type(self) is not FakeSearch)
    outcomes = {o.source: o for o in await fetcher.run_all()}
    assert outcomes["fake-search"].message == "not configured"
    assert len(standby.windows) == 2


def test_core_keywords_are_searched_only_when_the_user_chose_it():
    pref = Preference(
        titles=["Backend Engineer"],
        keywords=["Ruby on Rails", "PostgreSQL"],
        core_keywords=["Ruby on Rails"],
        locations=[{"city": "Pune", "country": "IN"}],
        work_modes=["onsite"],
    )
    assert [q.keywords for q in queries_from_preferences([pref])] == ["Backend Engineer"]
    pref.search_keywords = True
    keys = sorted(q.keywords for q in queries_from_preferences([pref]))
    assert keys == ["Backend Engineer", "Ruby on Rails"]


async def test_apify_account_balance_overrides_old_account_ledger(db, fetcher, monkeypatch):
    from app.schemas.account_balances import AccountBalance
    from app.services import fetching

    class AccountSearch(FakeSearch):
        budget_pool = "apify"
        credential_settings = ("apify_token", "apify_tokens")
        account_balance_required = True

    async def account(*args, **kwargs):
        assert kwargs["force"] is True
        return AccountBalance(
            status="live",
            allowance=500,
            spent=100,
            remaining=400,
            renews_on=START + timedelta(days=30),
            message="verified",
        )

    fetcher.settings.apify_token = "test-primary"
    monkeypatch.setattr(fetching, "account_balance", account)
    db.add(
        FetchRun(source=FakeSearch.name, status="succeeded", credits_used=1000, created_at=START)
    )
    await db.flush()
    adapter = AccountSearch(fetcher.http, fetcher.settings)
    await fetcher._check_budget(db, adapter)
    assert adapter.allowance_left == 400


@pytest.mark.parametrize("status,remaining", [("live", 0), ("unavailable", None)])
async def test_apify_unknown_or_exhausted_balance_stops_before_actor_call(
    db, fetcher, monkeypatch, status, remaining
):
    from app.adapters.errors import SourceError
    from app.schemas.account_balances import AccountBalance
    from app.services import fetching

    class AccountSearch(FakeSearch):
        budget_pool = "apify"
        credential_settings = ("apify_token", "apify_tokens")
        account_balance_required = True

    async def account(*args, **kwargs):
        return AccountBalance(
            status=status,
            remaining=remaining,
            renews_on=START + timedelta(days=30),
            message="unverified",
        )

    fetcher.settings.apify_token = "test-primary"
    monkeypatch.setattr(fetching, "account_balance", account)
    with pytest.raises(SourceError):
        await fetcher._check_budget(db, AccountSearch(fetcher.http, fetcher.settings))
    assert FakeSearch.windows == []


async def test_apify_backup_then_primary_after_renewal_preserves_checkpoints(
    db, fetcher, clock, monkeypatch
):
    from app.models.fetch import QueryWatermark
    from app.schemas.account_balances import AccountBalance
    from app.services import fetching

    tokens = []
    renewed = False

    class Accounts(FakeSearch):
        name = "fake-apify"
        budget_pool = "apify"
        credential_settings = ("apify_token", "apify_tokens")
        account_balance_required = True

        async def fetch_window(self, query, window):
            tokens.append((self.settings.apify_token, window))
            return FetchResult(postings=[posting("same-job")], credits_used=1)

    registry.register_adapter(Accounts)
    fetcher.settings.apify_token = "primary"
    fetcher.settings.apify_tokens = "backup"
    await add_preferences(db)

    async def account(cls, http, settings, now, **kwargs):
        remaining = 500 if settings.apify_token == "backup" or renewed else 0
        return AccountBalance(status="live", remaining=remaining, message="verified")

    monkeypatch.setattr(fetching, "account_balance", account)
    assert (await fetcher.run_source(Accounts.name)).status == "succeeded"
    assert all(token == "backup" for token, _ in tokens)
    assert await db.scalar(select(func.count()).select_from(QueryWatermark)) == 2
    tokens.clear()
    # Already fetched: neither backfill nor re-billing when an account changes.
    assert (await fetcher.run_source(Accounts.name)).status == "succeeded"
    assert not tokens
    renewed = True
    clock.now += timedelta(days=1)
    assert (await fetcher.run_source(Accounts.name)).status == "succeeded"
    assert all(
        token == "primary" and window.since == START - timedelta(hours=2)
        for token, window in tokens
    )
    assert await db.scalar(select(func.count()).select_from(Posting)) == 1
    runs = (await db.execute(select(FetchRun))).scalars().all()
    assert len({run.credential_fingerprint for run in runs}) == 2
    assert all(run.credential_fingerprint not in ("primary", "backup", None) for run in runs)


@pytest.mark.parametrize("error", ["quota", "timeout", "billed"])
async def test_only_unbilled_start_quota_rejection_can_retry_with_backup(
    db, fetcher, monkeypatch, error
):
    from app.adapters.errors import SourceQuotaRejected

    calls = []

    class Accounts(FakeSearch):
        name = "linkedin"
        credential_settings = ("brightdata_api_key", "brightdata_api_keys")
        monthly_allowance = 5000

        async def fetch_window(self, query, window):
            calls.append((self.settings.brightdata_api_key, window))
            if self.settings.brightdata_api_key == "primary":
                if error == "quota":
                    raise SourceQuotaRejected("No credits; search not started")
                raise SourceUnavailable(
                    "Failed after start" if error == "billed" else "Timed out",
                    credits_used=3 if error == "billed" else 0,
                )
            return FetchResult(postings=[], credits_used=1)

    registry.register_adapter(Accounts)
    fetcher.settings.brightdata_api_key = "primary"
    fetcher.settings.brightdata_api_keys = "backup"
    await add_preferences(db)
    outcome = await fetcher.run_source(Accounts.name)
    if error == "quota":
        assert outcome.status == "succeeded"
        assert [token for token, _ in calls] == ["primary", "backup", "backup"]
        assert calls[0][1] == calls[1][1]
    else:
        assert outcome.status == "failed"
        assert [token for token, _ in calls] == ["primary"]
    runs = (await db.execute(select(FetchRun))).scalars().all()
    assert sum(run.credits_used for run in runs) == (
        2 if error == "quota" else 3 if error == "billed" else 0
    )


async def test_brightdata_primary_and_backup_have_separate_spend(db, fetcher):
    from app.services.fetching import budget_for
    from app.services.provider_credentials import credentials

    class Accounts(FakeSearch):
        name = "linkedin"
        credential_settings = ("brightdata_api_key", "brightdata_api_keys")

    registry.register_adapter(Accounts)
    fetcher.settings.brightdata_api_key = "primary"
    fetcher.settings.brightdata_api_keys = "backup,backup,primary"
    options = credentials(Accounts, fetcher.settings)
    assert len(options) == 2
    db.add(FetchRun(source="linkedin", status="succeeded", credits_used=10, created_at=START))
    db.add(
        FetchRun(
            source="linkedin",
            status="succeeded",
            credits_used=3,
            created_at=START,
            credential_fingerprint=options[1].fingerprint,
        )
    )
    await db.flush()
    primary = await budget_for(
        db, Accounts, START, credential_fingerprint=options[0].fingerprint, include_legacy=True
    )
    backup = await budget_for(db, Accounts, START, credential_fingerprint=options[1].fingerprint)
    assert primary.spent == 10 and backup.spent == 3
    adapter = Accounts(fetcher.http, fetcher.settings)
    await fetcher._check_budget(db, adapter)
    assert adapter.settings.brightdata_api_key == "backup" and adapter.allowance_left == 7


async def test_new_provider_declares_credentials_and_balance_without_service_branches(db, fetcher):
    from app.schemas.account_balances import AccountBalance
    from app.services.account_balances import account_status

    class NewProvider(FakeSearch):
        name = "third-provider"
        budget_pool = "new-provider-pool"
        credential_settings = ("groq_api_key", "brightdata_api_keys")
        account_balance_required = True

        async def account_balance(self, now, *, force=False):
            return AccountBalance(
                status="live",
                allowance=10,
                spent=0,
                remaining=0 if self.settings.groq_api_key == "primary" else 10,
                message="verified",
            )

    fetcher.settings.groq_api_key = "primary"
    fetcher.settings.brightdata_api_keys = "backup"
    adapter = NewProvider(fetcher.http, fetcher.settings)
    await fetcher._check_budget(db, adapter)
    assert adapter.settings.groq_api_key == "backup" and adapter.allowance_left == 10
    account = await account_status(NewProvider, fetcher.http, fetcher.settings, START)
    assert account.account_label == "Backup account 1"
    assert [a.remaining for a in account.accounts] == [0, 10]
