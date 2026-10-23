import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.adapters.base import FetchWindow, Location, SourceQuery
from app.adapters.errors import (
    SourceBadResponse,
    SourceNotConfigured,
    SourceQuotaExhausted,
    SourceUnavailable,
)
from app.adapters.linkedin_scrapingdog import LinkedInScrapingdogAdapter
from app.core.config import Settings

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)
WINDOW = FetchWindow(since=NOW - timedelta(days=1), until=NOW)
QUERY = SourceQuery(keywords="Ruby on Rails", location=Location(country="IN", remote=True))
LISTING = {
    "job_id": "12345",
    "job_position": "Rails Developer",
    "company_name": "Example",
    "job_location": "Bengaluru, India (Remote)",
    "job_posting_date": "2026-10-23",
    "job_link": "https://www.linkedin.com/jobs/view/12345",
}
DETAIL = {"job_description_html": "<p>Build Rails apps. Apply: jobs@example.com</p>"}


def adapter(http, **settings):
    return LinkedInScrapingdogAdapter(http, Settings(scrapingdog_api_key="secret", **settings))


async def test_search_fetches_full_details_and_counts_both_calls(caplog):
    caplog.set_level(logging.INFO, logger="httpx")
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/account":
            return httpx.Response(200, json={"requestLimit": 100, "requestUsed": 0})
        return httpx.Response(200, json=[DETAIL] if "job_id" in request.url.params else [LISTING])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await adapter(http).fetch_window(QUERY, WINDOW)
    assert result.credits_used == 10 and result.complete
    [posting] = result.postings
    assert posting.source_job_id == "12345"
    assert posting.contact_email == "jobs@example.com"
    assert posting.locations[0].country == "IN"
    assert posting.work_mode == "remote"
    assert posting.posted_at == datetime(2026, 10, 23, tzinfo=UTC)
    assert seen[1].url.params["sort_by"] == "day"
    assert seen[1].url.params["location"] == "India"
    assert seen[1].url.params["work_type"] == "remote"
    assert "secret" not in caplog.text
    assert "[redacted]" in caplog.text


async def test_pages_and_deduplicates_before_fetching_details():
    details = []

    def handler(request):
        if request.url.path == "/account":
            return httpx.Response(200, json={"requestLimit": 1000, "requestUsed": 0})
        if "job_id" in request.url.params:
            details.append(request.url.params["job_id"])
            return httpx.Response(200, json=[DETAIL])
        rows = (
            [dict(LISTING, job_id=str(i)) for i in range(10)]
            if request.url.params["page"] == "1"
            else [dict(LISTING, job_id="0"), LISTING]
        )
        return httpx.Response(200, json=rows)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = adapter(http, scrapingdog_monthly_credits=1000)
        result = await source.fetch_window(QUERY, WINDOW)
    assert len(result.postings) == 11
    assert len(details) == len(set(details)) == 11
    assert result.credits_used == 65


async def test_budget_exhaustion_is_visible_and_no_request_overruns_remaining_credit():
    charged = []

    def handler(request):
        if request.url.path == "/account":
            return httpx.Response(200, json={"requestLimit": 100, "requestUsed": 85})
        charged.append(request)
        rows = (
            [DETAIL]
            if "job_id" in request.url.params
            else [dict(LISTING, job_id=str(i)) for i in range(10)]
        )
        return httpx.Response(200, json=rows)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await adapter(http).fetch_window(QUERY, WINDOW)
    assert not result.complete and len(result.postings) == 2
    assert len(charged) == 3 and result.credits_used == 15


async def test_local_budget_tighter_than_provider_balance():
    def handler(request):
        if request.url.path == "/account":
            return httpx.Response(200, json={"requestLimit": 4000, "requestUsed": 0})
        pytest.fail("No paid call may start without enough local allowance")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        source = adapter(http)
        source.allowance_left = 5
        with pytest.raises(SourceQuotaExhausted):
            await source.fetch_window(QUERY, WINDOW)


@pytest.mark.parametrize("payload", [{}, {"requestLimit": True, "requestUsed": 0}])
async def test_unverifiable_balance_fails_closed(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as http:
        with pytest.raises(SourceUnavailable):
            await adapter(http).fetch_window(QUERY, WINDOW)


@pytest.mark.parametrize("failure", ["server", "malformed", "timeout"])
async def test_detail_failures_preserve_paid_search_cost(failure):
    def handler(request):
        if request.url.path == "/account":
            return httpx.Response(200, json={"requestLimit": 100, "requestUsed": 0})
        if "job_id" not in request.url.params:
            return httpx.Response(200, json=[LISTING])
        if failure == "timeout":
            raise httpx.ReadTimeout("secret", request=request)
        return httpx.Response(503) if failure == "server" else httpx.Response(200, text="bad JSON")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises((SourceUnavailable, SourceBadResponse)) as caught:
            await adapter(http).fetch_window(QUERY, WINDOW)
    assert caught.value.credits_used == (10 if failure == "malformed" else 5)
    assert "secret" not in caught.value.message


async def test_no_key_means_no_http_requests():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("No requests"))
    ) as http:
        with pytest.raises(SourceNotConfigured):
            await LinkedInScrapingdogAdapter(http, Settings()).fetch_window(QUERY, WINDOW)


def test_registered_as_optional_linkedin_fallback():
    from app.adapters.registry import family_of, run_order

    assert LinkedInScrapingdogAdapter.site == "LinkedIn"
    assert not LinkedInScrapingdogAdapter.default_enabled
    family = family_of(LinkedInScrapingdogAdapter)
    assert {
        "linkedin",
        "linkedin-apify",
        "linkedin-piloterr",
        "linkedin-scrapingdog",
        "linkedin-jobspy",
    } <= family
    names = [source.name for source in run_order()]
    assert (
        names.index("linkedin-piloterr")
        < names.index("linkedin-scrapingdog")
        < names.index("linkedin-jobspy")
    )


async def test_configured_credit_ceiling_used_by_budget_service(db):
    from app.services.fetching import budget_for

    budget = await budget_for(
        db, LinkedInScrapingdogAdapter, NOW, settings=Settings(scrapingdog_monthly_credits=4000)
    )
    assert budget.allowance == 4000
