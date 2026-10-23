import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.adapters.base import FetchWindow, Location, SourceQuery
from app.adapters.errors import SourceUnavailable
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


async def test_process_output_normalized_without_running_blocking_library_in_server(monkeypatch):
    seen = []

    async def communicate(payload):
        seen.append(json.loads(payload))
        process.returncode = 0
        return json.dumps({"jobs": [ROW, ROW]}).encode(), None

    process = SimpleNamespace(returncode=None, communicate=communicate)
    create = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    async with httpx.AsyncClient() as http:
        result = await LinkedInJobSpyAdapter(http, Settings()).fetch_window(QUERY, WINDOW)
    assert seen[0]["location"] == "India"
    assert seen[0]["keywords"] == "Rails remote"
    assert seen[0]["hours_old"] == 24
    assert create.call_args.args[-1] == "app.adapters.jobspy_worker"
    assert len(result.postings) == 1 and result.credits_used == 0
    posting = result.postings[0]
    assert posting.source_job_id == "12345"
    assert posting.contact_email == "jobs@example.com"
    assert posting.work_mode == "remote"
    assert posting.locations[0].country == "IN"


@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_or_cancellation_kills_and_reaps_worker(monkeypatch, cancel):
    started = asyncio.Event()

    async def communicate(payload):
        started.set()
        await asyncio.Event().wait()

    def kill():
        process.returncode = -9

    process = SimpleNamespace(returncode=None, communicate=communicate, kill=kill, wait=AsyncMock())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    async with httpx.AsyncClient() as http:
        adapter = LinkedInJobSpyAdapter(http, Settings(jobspy_timeout_seconds=1))
        task = asyncio.create_task(adapter.fetch_window(QUERY, WINDOW))
        await started.wait()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else SourceUnavailable):
            await task
    assert process.returncode == -9
    process.wait.assert_awaited_once()


@pytest.mark.parametrize(
    "response", [{"error": "blocked"}, {"jobs": [dict(ROW, description=None)]}]
)
async def test_blocked_or_missing_details_fail_instead_of_advancing_window(monkeypatch, response):
    monkeypatch.setattr(LinkedInJobSpyAdapter, "_collect", AsyncMock(return_value=response))
    async with httpx.AsyncClient() as http:
        with pytest.raises(SourceUnavailable):
            await LinkedInJobSpyAdapter(http, Settings()).fetch_window(QUERY, WINDOW)


def test_worker_reports_library_errors_and_serializes_rows(monkeypatch):
    import pandas as pd

    calls = []
    frame = pd.DataFrame([ROW])

    def scrape_jobs(**kwargs):
        calls.append(kwargs)
        return frame

    monkeypatch.setitem(sys.modules, "jobspy", SimpleNamespace(scrape_jobs=scrape_jobs))
    payload = {"keywords": "Rails", "location": "India", "hours_old": 24}
    assert collect(payload)["jobs"][0]["id"] == "li-12345"
    assert calls[0]["fetch_description"] is True
    assert calls[0]["site_name"] == ["linkedin"]
    frame.attrs["errors"] = {"linkedin": "429"}
    assert "error" in collect(payload)


def test_no_key_required_and_library_not_loaded_in_parent():
    assert LinkedInJobSpyAdapter.default_enabled is False
    assert LinkedInJobSpyAdapter.standby_for == "linkedin-scrapingdog"
    assert LinkedInJobSpyAdapter.site == "LinkedIn"
