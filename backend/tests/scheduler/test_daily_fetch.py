import asyncio
from unittest.mock import AsyncMock

import pytest

from app import scheduler
from app.services import pipeline


@pytest.mark.parametrize("outcomes", [[None, []], [None, None, []]])
async def test_daily_fetch_waits_for_queue_lock_then_runs(monkeypatch, outcomes):
    run_all = AsyncMock(side_effect=outcomes)
    fetcher = type("Fetcher", (), {"run_all": run_all})()
    monkeypatch.setattr(pipeline, "build_fetcher", lambda: fetcher)
    sleep = AsyncMock()
    monkeypatch.setattr(scheduler.asyncio, "sleep", sleep)
    await scheduler.daily_fetch()
    assert run_all.await_count == len(outcomes)
    assert sleep.await_count == len(outcomes) - 1
    assert all(call.kwargs == {"trigger": "schedule"} for call in run_all.await_args_list)


async def test_provider_failure_outcomes_are_not_retried(monkeypatch):
    run_all = AsyncMock(return_value=[{"status": "failed"}])
    monkeypatch.setattr(pipeline, "build_fetcher", lambda: type("F", (), {"run_all": run_all})())
    sleep = AsyncMock()
    monkeypatch.setattr(scheduler.asyncio, "sleep", sleep)
    await scheduler.daily_fetch()
    run_all.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_busy_lock_expiry_is_an_error_not_success(monkeypatch):
    run_all = AsyncMock(return_value=None)
    monkeypatch.setattr(pipeline, "build_fetcher", lambda: type("F", (), {"run_all": run_all})())
    monkeypatch.setattr(scheduler, "LOCK_ATTEMPTS", 3)
    monkeypatch.setattr(scheduler.asyncio, "sleep", AsyncMock())
    with pytest.raises(RuntimeError, match="pipeline lock"):
        await scheduler.daily_fetch()
    assert run_all.await_count == 3


async def test_shutdown_cancels_wait_without_starting_another_fetch(monkeypatch):
    run_all = AsyncMock(return_value=None)
    monkeypatch.setattr(pipeline, "build_fetcher", lambda: type("F", (), {"run_all": run_all})())
    monkeypatch.setattr(scheduler.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await scheduler.daily_fetch()
    run_all.assert_awaited_once()
