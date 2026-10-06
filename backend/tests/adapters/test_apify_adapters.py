"""Naukri and LinkedIn through Apify: run lifecycle, spend, limits and malformed data."""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.adapters.base import FetchWindow, Location, SourceQuery, WorkMode
from app.adapters.errors import (
    SourceBadResponse,
    SourceNotConfigured,
    SourceQuotaExhausted,
    SourceUnavailable,
)
from app.adapters.linkedin_apify import LinkedInApifyAdapter, search_url
from app.adapters.naukri_apify import NaukriApifyAdapter, freshness_for
from app.adapters.registry import pool_of
from app.core.config import Settings

NOW = datetime(2026, 10, 5, 1, 17, tzinfo=UTC)
DAY = FetchWindow(since=NOW - timedelta(hours=26), until=NOW)
QUERY = SourceQuery(keywords="Backend Engineer", location=Location(city="Bengaluru", country="IN"))
SETTINGS = Settings(apify_token="apify-token")

NAUKRI_RECORD = {
    "jobId": "051025500123",
    "title": "Python Developer",
    "companyName": "Acme Technologies Pvt Ltd",
    "placeholders": [
        {"type": "experience", "label": "3-5 Yrs"},
        {"type": "location", "label": "Bengaluru, Pune"},
    ],  # fmt: skip
    "jobDescription": "<p>Django and Postgres. Mail hr@acme.in</p>",
    "jdURL": "/job-listings-python-developer-acme-051025500123",
    "createdDate": 1759622400000,
}


async def no_sleep(_: float) -> None:
    return None


class FakeApify:
    """Apify's run API: start, poll (finishing on the second poll), dataset items."""

    def __init__(self, records, final_status="SUCCEEDED", usage=0.0123):
        self.records = records
        self.final_status = final_status
        self.usage = usage
        self.requests: list[httpx.Request] = []
        self.polls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/runs"):
            return httpx.Response(201, json={"data": {"id": "run1", "status": "READY"}})
        if path.endswith("/actor-runs/run1"):
            self.polls += 1
            status = self.final_status if self.polls > 1 else "RUNNING"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "run1",
                        "status": status,
                        "defaultDatasetId": "ds1",
                        "usageTotalUsd": self.usage,
                    }
                },  # fmt: skip
            )
        if "/datasets/ds1/items" in path:
            return httpx.Response(200, json=self.records)
        return httpx.Response(404)


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestNaukri:
    async def test_run_poll_download_and_normalise(self):
        api = FakeApify([NAUKRI_RECORD, {"jobId": "x"}])
        async with client(api) as http:
            adapter = NaukriApifyAdapter(http, SETTINGS, sleep=no_sleep)
            adapter.allowance_left = 250
            result = await adapter.fetch_window(QUERY, DAY)

        start = api.requests[0]
        assert start.headers["authorization"] == "Bearer apify-token"
        assert start.url.path == "/v2/acts/muhammetakkurtt~naukri-job-scraper/runs"
        # Apify stops the run at what is left of the shared allowance.
        assert start.url.params["maxTotalChargeUsd"] == "2.50"
        body = json.loads(start.read())
        assert body["keyword"] == "Backend Engineer Bengaluru" and body["freshness"] == "1"
        # 1.23 cents rounds up: the Credit Budget never reads low (FR-B5).
        assert result.credits_used == 2
        assert len(result.postings) == 1
        job = result.postings[0]
        assert (
            job.apply_url
            == "https://www.naukri.com/job-listings-python-developer-acme-051025500123"
        )
        assert [loc.city for loc in job.locations] == ["Bengaluru", "Pune"]
        assert all(loc.country == "IN" for loc in job.locations)
        assert job.contact_email == "hr@acme.in" and job.posted_at.year == 2025

    async def test_other_countries_are_skipped_for_free(self):
        us = SourceQuery(keywords="Backend Engineer", location=Location(country="US"))
        api = FakeApify([])
        async with client(api) as http:
            result = await NaukriApifyAdapter(http, SETTINGS).fetch_window(us, DAY)
        assert result.postings == [] and result.credits_used == 0 and api.requests == []

    async def test_failed_run_still_reports_its_cost(self):
        api = FakeApify([], final_status="FAILED", usage=0.05)
        async with client(api) as http:
            with pytest.raises(SourceUnavailable) as caught:
                await NaukriApifyAdapter(http, SETTINGS, sleep=no_sleep).fetch_window(QUERY, DAY)
        assert caught.value.credits_used == 5

    async def test_used_up_allowance_and_malformed_dataset(self):
        def broke(request):
            return httpx.Response(
                402, json={"error": {"type": "not-enough-usage-to-run-paid-actor"}}
            )

        async with client(broke) as http:
            with pytest.raises(SourceQuotaExhausted):
                await NaukriApifyAdapter(http, SETTINGS).fetch_window(QUERY, DAY)
        api = FakeApify({"not": "a list"})
        async with client(api) as http:
            with pytest.raises(SourceBadResponse) as caught:
                await NaukriApifyAdapter(http, SETTINGS, sleep=no_sleep).fetch_window(QUERY, DAY)
        assert caught.value.credits_used == 2

    async def test_needs_a_token(self):
        async with client(FakeApify([])) as http:
            with pytest.raises(SourceNotConfigured):
                await NaukriApifyAdapter(http, Settings()).fetch_window(QUERY, DAY)

    def test_freshness(self):
        assert freshness_for(DAY) == "1"  # a daily window plus its 2-hour overlap
        assert freshness_for(FetchWindow(since=NOW - timedelta(hours=30), until=NOW)) == "3"
        assert freshness_for(FetchWindow(since=NOW - timedelta(hours=20), until=NOW)) == "1"
        assert freshness_for(FetchWindow(since=NOW - timedelta(days=14), until=NOW)) == "15"
        assert freshness_for(FetchWindow(since=NOW - timedelta(days=60), until=NOW)) == "all"


class TestLinkedInApify:
    RECORD = {
        "id": "4012345678",
        "title": "Senior Backend Engineer",
        "companyName": "Acme Corp",
        "location": "Bengaluru, Karnataka, India (Hybrid)",
        "descriptionText": "Build APIs in Python.",
        "postedAt": "2026-10-04",
        "applyUrl": "https://boards.greenhouse.io/acme/jobs/987",
    }

    async def test_searches_the_exact_window_and_normalises(self):
        api = FakeApify([self.RECORD])
        async with client(api) as http:
            result = await LinkedInApifyAdapter(http, SETTINGS, sleep=no_sleep).fetch_window(
                QUERY, DAY
            )
        body = json.loads(api.requests[0].read())
        url = parse_qs(urlparse(body["urls"][0]).query)
        assert url["f_TPR"] == ["r93600"] and url["location"] == ["Bengaluru, India"]
        # ADR-0009: the whole search, not a budget-sized slice of it.
        assert body["count"] == 1000
        job = result.postings[0]
        assert job.work_mode == WorkMode.HYBRID and job.locations[0].city == "Bengaluru"

    def test_remote_searches_use_linkedins_remote_filter(self):
        remote = SourceQuery(keywords="SRE", location=Location(country="IN", remote=True))
        assert "f_WT=2" in search_url(remote, DAY)
        assert "location=Worldwide" in search_url(SourceQuery(keywords="SRE"), DAY)

    def test_is_a_standby_sharing_the_apify_pool(self):
        import app.adapters  # noqa: F401  registers every Source

        assert LinkedInApifyAdapter.standby_for == "linkedin"
        assert pool_of(LinkedInApifyAdapter) == {"linkedin-apify", "naukri"}


async def test_a_run_past_its_timeout_is_aborted():
    clock = iter([0.0, 0.0, 10_000.0])

    class Endless(FakeApify):
        def __call__(self, request):
            if request.url.path.endswith("/actor-runs/run1"):
                self.requests.append(request)
                return httpx.Response(200, json={"data": {"id": "run1", "status": "RUNNING",
                                                          "usageTotalUsd": 0.02}})  # fmt: skip
            return super().__call__(request)

    api = Endless([])
    async with client(api) as http:
        adapter = NaukriApifyAdapter(http, SETTINGS, sleep=no_sleep)
        adapter.monotonic = lambda: next(clock)
        with pytest.raises(SourceUnavailable) as caught:
            await adapter.fetch_window(QUERY, DAY)
    assert any(r.url.path.endswith("/actor-runs/run1/abort") for r in api.requests)
    assert caught.value.credits_used == 2


async def test_a_network_failure_after_the_run_keeps_its_cost():
    class Flaky(FakeApify):
        def __call__(self, request):
            if "/datasets/" in request.url.path:
                raise httpx.ReadTimeout("slow dataset", request=request)
            return super().__call__(request)

    async with client(Flaky([], usage=0.05)) as http:
        with pytest.raises(SourceUnavailable) as caught:
            await NaukriApifyAdapter(http, SETTINGS, sleep=no_sleep).fetch_window(QUERY, DAY)
    assert caught.value.credits_used == 5


async def test_the_settled_cost_is_read_again_after_the_run_finishes():
    class Settling(FakeApify):
        def __call__(self, request):
            response = super().__call__(request)
            # Apify's first terminal answer can carry a preliminary cost.
            if request.url.path.endswith("/actor-runs/run1") and self.polls > 2:
                return httpx.Response(200, json={"data": {"id": "run1", "status": "SUCCEEDED",
                                                          "usageTotalUsd": 0.071}})  # fmt: skip
            return response

    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    api = Settling([NAUKRI_RECORD], usage=0.0123)
    async with client(api) as http:
        result = await NaukriApifyAdapter(http, SETTINGS, sleep=sleep).fetch_window(QUERY, DAY)
    assert result.credits_used == 8 and 10.0 in slept


def test_naukri_uses_the_actors_own_filters():
    adapter = NaukriApifyAdapter(
        httpx.AsyncClient(), Settings(apify_token="t", apify_naukri_city_ids={"Bengaluru": "97"})
    )
    mapped = adapter.actor_input(QUERY, DAY)
    assert mapped["cities"] == ["97"] and mapped["keyword"] == "Backend Engineer"
    assert mapped["fetchDetails"] is True
    remote = SourceQuery(keywords="SRE", location=Location(country="IN", remote=True))
    assert adapter.actor_input(remote, DAY)["workMode"] == ["remote"]
    pune = SourceQuery(keywords="SRE", location=Location(city="Pune", country="IN"))
    unmapped = adapter.actor_input(pune, DAY)
    assert "cities" not in unmapped and unmapped["keyword"] == "SRE Pune"


async def test_each_search_records_its_own_runs_cost():
    """The fetcher reuses one adapter for every query: costs must not carry over."""

    class TwoRuns(FakeApify):
        def __init__(self):
            super().__init__([NAUKRI_RECORD])
            self.started = 0

        def __call__(self, request):
            self.requests.append(request)
            path = request.url.path
            run_id = f"run{self.started}"
            if path.endswith("/runs"):
                self.started += 1
                return httpx.Response(201, json={"data": {"id": f"run{self.started}",
                                                          "status": "READY"}})  # fmt: skip
            if "/actor-runs/" in path:
                usage = {"run1": 0.05, "run2": 0.12}[path.rsplit("/", 1)[1]]
                return httpx.Response(200, json={"data": {"id": run_id, "status": "SUCCEEDED",
                                                          "defaultDatasetId": "ds1",
                                                          "usageTotalUsd": usage}})  # fmt: skip
            return httpx.Response(200, json=self.records)

    async with client(TwoRuns()) as http:
        adapter = NaukriApifyAdapter(http, SETTINGS, sleep=no_sleep)
        first = await adapter.fetch_window(QUERY, DAY)
        second = await adapter.fetch_window(QUERY, DAY)
    assert (first.credits_used, second.credits_used) == (5, 12)
