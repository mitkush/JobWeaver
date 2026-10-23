import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.adapters.base import FetchWindow, Location, SourceQuery
from app.adapters.jobspy_worker import collect
from app.adapters.linkedin_jobspy import LinkedInJobSpyAdapter
from app.core.config import Settings

NOW = datetime(2026, 10, 23, tzinfo=UTC)
WINDOW = FetchWindow(since=NOW - timedelta(days=1), until=NOW)
QUERY = SourceQuery(keywords="Rails", location=Location(country="IN", remote=True))
ROW = {
    "id": "li-12345",
    "title": "Rails Developer",
    "company": "Example",
    "location": "Bengaluru, India",
    "description": "Build Rails apps. jobs@example.com",
    "job_url": "https://www.linkedin.com/jobs/view/12345",
    "is_remote": True,
    "date_posted": "2026-10-23",
}


@pytest.fixture(autouse=True)
def configured_without_optional_dependency(monkeypatch):
    monkeypatch.setattr(LinkedInJobSpyAdapter, "is_configured", lambda self: True)


def worker(frames, *, eof=True):
    stdout = asyncio.StreamReader()
    for frame in frames:
        stdout.feed_data((json.dumps(frame) + "\n").encode())
    if eof:
        stdout.feed_eof()
    process = SimpleNamespace(
        returncode=None,
        stdout=stdout,
        stdin=SimpleNamespace(write=MagicMock(), drain=AsyncMock(), close=MagicMock()),
    )

    def kill():
        process.returncode = -9

    async def wait():
        if process.returncode is None:
            process.returncode = 0

    process.kill = MagicMock(side_effect=kill)
    process.wait = AsyncMock(side_effect=wait)
    return process


@pytest.mark.parametrize("error", [False, True])
async def test_process_output_normalized_without_discarding_rows_on_error(monkeypatch, error):
    process = worker([{"jobs": [ROW, ROW]}, {"jobs": [], "complete": not error, "error": error}])
    create = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    async with httpx.AsyncClient() as http:
        result = await LinkedInJobSpyAdapter(http, Settings()).fetch_window(QUERY, WINDOW)
    payload = json.loads(process.stdin.write.call_args.args[0])
    assert payload["location"] == "India"
    assert payload["keywords"] == "Rails remote"
    assert payload["hours_old"] == 24
    assert payload["max_results"] == 50
    assert create.call_args.args[-1] == "app.adapters.jobspy_worker"
    assert len(result.postings) == 1 and result.credits_used == 0
    assert result.complete is not error
    posting = result.postings[0]
    assert posting.source_job_id == "12345"
    assert posting.contact_email == "jobs@example.com"
    assert posting.work_mode == "remote"
    assert posting.locations[0].country == "IN"


@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_or_cancellation_kills_and_reaps_worker(monkeypatch, cancel):
    started = asyncio.Event()
    process = worker([{"jobs": [ROW], "complete": False}], eof=False)

    async def drain():
        started.set()

    process.stdin.drain = drain
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    async with httpx.AsyncClient() as http:
        adapter = LinkedInJobSpyAdapter(http, Settings(jobspy_timeout_seconds=1))
        task = asyncio.create_task(adapter.fetch_window(QUERY, WINDOW))
        await started.wait()
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            result = await task
            assert len(result.postings) == 1 and not result.complete
    assert process.returncode == -9
    process.wait.assert_awaited_once()


@pytest.mark.parametrize("error", [False, True])
async def test_partial_rows_survive_search_error_or_missing_description(monkeypatch, error):
    response = {
        "jobs": [ROW, dict(ROW, id="li-54321", description=None)],
        "error": error,
        "complete": True,
    }
    monkeypatch.setattr(LinkedInJobSpyAdapter, "_collect", AsyncMock(return_value=response))
    async with httpx.AsyncClient() as http:
        result = await LinkedInJobSpyAdapter(http, Settings()).fetch_window(QUERY, WINDOW)
    assert len(result.postings) == 1 and not result.complete


def test_worker_reports_library_errors_and_serializes_rows(monkeypatch):
    calls = []
    frame = SimpleNamespace(attrs={}, to_json=lambda **kwargs: json.dumps([ROW]))

    def scrape_jobs(**kwargs):
        calls.append(kwargs)
        return frame

    monkeypatch.setitem(sys.modules, "jobspy", SimpleNamespace(scrape_jobs=scrape_jobs))
    payload = {"keywords": "Rails", "location": "India", "hours_old": 24}
    assert collect(payload)["jobs"][0]["id"] == "li-12345"
    assert calls[0]["fetch_description"] is True
    assert calls[0]["site_name"] == ["linkedin"]
    frame.attrs["errors"] = {"linkedin": "429"}
    result = collect(payload)
    assert result["error"] and result["jobs"][0]["id"] == "li-12345"


def test_worker_checkpoints_each_page_and_stops_at_configured_limit(monkeypatch):
    calls, checkpoints = [], []

    def scrape_jobs(**kwargs):
        calls.append(kwargs)
        rows = [dict(ROW, id=f"li-{kwargs['offset'] + i}") for i in range(25)]
        return SimpleNamespace(attrs={}, to_json=lambda **kw: json.dumps(rows))

    monkeypatch.setitem(sys.modules, "jobspy", SimpleNamespace(scrape_jobs=scrape_jobs))
    result = collect(
        {"keywords": "Rails", "location": "India", "hours_old": 24}, checkpoints.append
    )
    assert [call["offset"] for call in calls] == [0, 25]
    assert [len(frame["jobs"]) for frame in checkpoints] == [25, 25]
    assert len(result["jobs"]) == 50 and not result["complete"]


@pytest.mark.parametrize("stop", ["exception", "deadline"])
def test_worker_keeps_completed_page_when_later_work_cannot_finish(monkeypatch, stop):
    import app.adapters.jobspy_worker as worker_module

    calls = []

    def scrape_jobs(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise RuntimeError("blocked")
        rows = [dict(ROW, id=f"li-{i}") for i in range(25)]
        return SimpleNamespace(attrs={}, to_json=lambda **kw: json.dumps(rows))

    if stop == "deadline":
        ticks = iter([0, 0, 10])
        monkeypatch.setattr(worker_module, "monotonic", lambda: next(ticks))
    monkeypatch.setitem(sys.modules, "jobspy", SimpleNamespace(scrape_jobs=scrape_jobs))
    result = collect({"keywords": "Rails", "location": "India", "hours_old": 24, "time_budget": 1})
    assert len(result["jobs"]) == 25 and result["error"] and not result["complete"]
    assert len(calls) == (1 if stop == "deadline" else 2)


async def test_worldwide_query_does_not_leave_location_to_ip_inference(monkeypatch):
    collector = AsyncMock(return_value={"jobs": [], "complete": True})
    monkeypatch.setattr(LinkedInJobSpyAdapter, "_collect", collector)
    async with httpx.AsyncClient() as http:
        await LinkedInJobSpyAdapter(http, Settings()).fetch_window(
            SourceQuery(keywords="Rails", location=Location(remote=True)), WINDOW
        )
    assert collector.call_args.args[0]["location"] == "Worldwide"
    assert collector.call_args.args[0]["keywords"] == "Rails remote"


def test_no_key_required_and_library_not_loaded_in_parent():
    assert LinkedInJobSpyAdapter.default_enabled is False
    assert LinkedInJobSpyAdapter.standby_for == "linkedin-scrapingdog"
    assert LinkedInJobSpyAdapter.site == "LinkedIn"
