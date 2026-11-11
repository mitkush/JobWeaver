from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.adapters.base import FetchWindow, Location, SourceQuery
from app.adapters.errors import SourceUnavailable
from app.adapters.linkedin_brightdata import LinkedInBrightDataAdapter
from app.core.config import Settings

NOW = datetime(2026, 11, 11, 1, 17, tzinfo=UTC)
WINDOW = FetchWindow(since=NOW - timedelta(hours=24), until=NOW)
QUERY = SourceQuery(keywords="Software OR Developer", location=Location(country="IN"))
SETTINGS = Settings(brightdata_api_key="test-key")


@pytest.mark.parametrize("failure", [httpx.ConnectTimeout, httpx.ConnectError])
async def test_trigger_retries_only_connection_failures_before_send(failure):
    attempts = 0
    accepted = 0

    def handler(request):
        nonlocal attempts, accepted
        if request.method == "POST":
            attempts += 1
            assert request.extensions["timeout"]["connect"] == 30
            if attempts < 3:
                raise failure("connect failed", request=request)
            accepted += 1
            return httpx.Response(200, json={"snapshot_id": "one-snapshot"})
        if "/progress/" in request.url.path:
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(200, json=[])

    sleep = AsyncMock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LinkedInBrightDataAdapter(client, SETTINGS, sleep=sleep)
        await adapter.fetch_window(QUERY, WINDOW)
    assert attempts == 3 and accepted == 1
    assert [call.args[0] for call in sleep.call_args_list] == [1.0, 2.0]


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout])
async def test_uncertain_trigger_timeout_never_replays_post(failure):
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        raise failure("uncertain request", request=request)

    sleep = AsyncMock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LinkedInBrightDataAdapter(client, SETTINGS, sleep=sleep)
        with pytest.raises(failure):
            await adapter.fetch_window(QUERY, WINDOW)
    assert attempts == 1
    sleep.assert_not_awaited()


@pytest.mark.parametrize("phase", ["progress", "snapshot"])
async def test_read_only_timeout_retries_same_collection(phase):
    reads = 0
    posts = 0

    def handler(request):
        nonlocal reads, posts
        if request.method == "POST":
            posts += 1
            return httpx.Response(200, json={"snapshot_id": "one-snapshot"})
        assert request.url.path.endswith("/one-snapshot")
        if f"/{phase}/" in request.url.path:
            reads += 1
            if reads < 3:
                raise httpx.ReadTimeout("temporary read timeout", request=request)
        if "/progress/" in request.url.path:
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LinkedInBrightDataAdapter(client, SETTINGS, sleep=AsyncMock())
        await adapter.fetch_window(QUERY, WINDOW)
    assert posts == 1 and reads == 3


async def test_connection_retry_limit_is_bounded():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("unreachable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LinkedInBrightDataAdapter(client, SETTINGS, sleep=AsyncMock())
        with pytest.raises(httpx.ConnectTimeout):
            await adapter.fetch_window(QUERY, WINDOW)
    assert calls == 3


@pytest.mark.parametrize("stays_preparing", [False, True])
async def test_ready_progress_but_download_202_keeps_collection(stays_preparing):
    posts = 0
    downloads = 0
    checkpoints = []

    async def checkpoint(value):
        checkpoints.append(value)

    def handler(request):
        nonlocal posts, downloads
        if request.method == "POST":
            posts += 1
            return httpx.Response(200, json={"snapshot_id": "same-snapshot"})
        if "/progress/" in request.url.path:
            return httpx.Response(200, json={"status": "ready"})
        downloads += 1
        assert request.url.path.endswith("/same-snapshot")
        if stays_preparing or downloads < 3:
            return httpx.Response(202, json={"status": "building"})
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LinkedInBrightDataAdapter(client, SETTINGS, sleep=AsyncMock())
        adapter.checkpoint_collection = checkpoint
        if stays_preparing:
            with pytest.raises(SourceUnavailable, match="same collection"):
                await adapter.fetch_window(QUERY, WINDOW)
        else:
            await adapter.fetch_window(QUERY, WINDOW)
    assert posts == 1 and downloads == 3
    assert checkpoints == ["same-snapshot"]
