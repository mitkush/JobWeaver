from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.adapters.base import FetchWindow, Location, SourceQuery, WorkMode
from app.adapters.errors import (
    SourceBadResponse,
    SourceNotConfigured,
    SourceQuotaExhausted,
    SourceRateLimited,
)
from app.adapters.linkedin_piloterr import LinkedInPiloterrAdapter
from app.core.config import Settings

NOW = datetime(2026, 10, 14, 1, 17, tzinfo=UTC)
DAY = FetchWindow(since=NOW - timedelta(hours=24), until=NOW)
QUERY = SourceQuery(
    keywords="Ruby on Rails Developer",
    location=Location(city="Bengaluru", country="IN", remote=True),
)
RECORD = {
    "id": 4388669042,
    "url": "https://www.linkedin.com/jobs/view/4388669042",
    "title": "Ruby on Rails Developer",
    "location": "Bengaluru, India",
    "list_date": "2026-10-13 00:00:00",
    "company_url": "https://www.linkedin.com/company/example",
    "company_name": "Example Tech",
    "description": "Build reliable software products.",
}


def http(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestLinkedInPiloterr:
    def test_is_third_linkedin_provider_without_changing_posting_priority(self):
        assert LinkedInPiloterrAdapter.standby_for == "linkedin-apify"
        assert LinkedInPiloterrAdapter.priority == 20

    async def test_search_maps_results_and_counts_each_paid_page(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[RECORD])

        async with http(handler) as client:
            adapter = LinkedInPiloterrAdapter(
                client,
                Settings(
                    piloterr_api_key="piloterr-secret",
                    piloterr_linkedin_geo_ids={"Bengaluru": "12345", "IN": "102713980"},
                ),
            )
            result = await adapter.fetch_window(QUERY, DAY)

        request = requests[0]
        assert request.url.host == "api.piloterr.com"
        assert request.url.path == "/v2/linkedin/job/search"
        assert request.headers["x-api-key"] == "piloterr-secret"
        assert request.url.params["keyword"] == "Ruby on Rails Developer"
        assert request.url.params["geo_id"] == "12345"
        assert request.url.params["when"] == "day"
        assert request.url.params["flexibility"] == "remote"
        assert result.credits_used == 1
        assert len(result.postings) == 1
        posting = result.postings[0]
        assert posting.source_job_id == "4388669042"
        assert posting.company == "Example Tech"
        assert posting.apply_url == RECORD["url"]
        assert posting.posted_at == datetime(2026, 10, 13, tzinfo=UTC)

    async def test_uses_month_filter_for_two_week_backfill_and_no_city_guess(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=[])

        window = FetchWindow(since=NOW - timedelta(days=14), until=NOW)
        async with http(handler) as client:
            adapter = LinkedInPiloterrAdapter(client, Settings(piloterr_api_key="key"))
            await adapter.fetch_window(
                SourceQuery(keywords="Engineer", location=Location(city="Toronto", country="CA")),
                window,
            )

        assert seen[0].url.params["when"] == "month"
        assert "geo_id" not in seen[0].url.params

    async def test_unconfigured_source_fails_cleanly(self):
        async with http(lambda _: pytest.fail("should not call Piloterr")) as client:
            adapter = LinkedInPiloterrAdapter(client, Settings())
            with pytest.raises(SourceNotConfigured):
                await adapter.fetch_window(QUERY, DAY)

    @pytest.mark.parametrize(
        ("status", "body", "error"),
        [
            (402, {"error": "Payment required"}, SourceQuotaExhausted),
            (429, {"error": "Rate limit exceeded"}, SourceRateLimited),
            (200, {"unexpected": "shape"}, SourceBadResponse),
        ],
    )
    async def test_provider_errors_are_reported(self, status, body, error):
        async with http(lambda _: httpx.Response(status, json=body)) as client:
            adapter = LinkedInPiloterrAdapter(client, Settings(piloterr_api_key="key"))
            with pytest.raises(error):
                await adapter.fetch_window(QUERY, DAY)

    def test_adapter_is_opt_in_and_search_result_supports_work_mode(self):
        assert LinkedInPiloterrAdapter.default_enabled is False
        assert LinkedInPiloterrAdapter.priority > 1
        assert LinkedInPiloterrAdapter.monthly_allowance == 500
        assert LinkedInPiloterrAdapter.allowance_unit == "credits"
        posting = LinkedInPiloterrAdapter.to_posting(
            {**RECORD, "workplace_type": "Remote", "description": "Build products."}
        )
        assert posting is not None
        assert posting.work_mode == WorkMode.REMOTE
        assert posting.description == "Build products."
        assert (
            LinkedInPiloterrAdapter.to_posting(
                {key: value for key, value in RECORD.items() if key != "description"}
            )
            is None
        )

    async def test_caps_pages_to_remaining_allowance(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[RECORD | {"description": "Build products."}] * 25)

        async with http(handler) as client:
            adapter = LinkedInPiloterrAdapter(
                client,
                Settings(piloterr_api_key="key", piloterr_linkedin_pages_per_query=5),
            )
            adapter.allowance_left = 2
            result = await adapter.fetch_window(QUERY, DAY)

        assert len(requests) == 2
        assert [request.url.params["page"] for request in requests] == ["1", "2"]
        assert result.credits_used == 2


STUB = {key: value for key, value in RECORD.items() if key != "description"}
DETAIL = {**STUB, "job_description": "<p>Build Ruby APIs and test PostgreSQL transactions.</p>"}


async def test_missing_descriptions_are_bought_from_job_info_and_each_request_is_counted():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[STUB] if request.url.path.endswith("/search") else DETAIL)

    async with http(handler) as client:
        adapter = LinkedInPiloterrAdapter(client, Settings(piloterr_api_key="key"))
        result = await adapter.fetch_window(QUERY, DAY)
    assert len(requests) == 2
    assert requests[1].url.path == "/v2/linkedin/job/info"
    assert requests[1].url.params["query"] == str(STUB["id"])
    assert requests[1].headers["x-api-key"] == "key"
    assert result.credits_used == 2 and result.complete
    assert result.postings[0].description == "Build Ruby APIs and test PostgreSQL transactions."


async def test_known_usable_jobs_and_duplicate_ids_do_not_buy_details_twice():
    requests = []
    other = STUB | {"id": "new-job"}

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=[STUB, other, other]
            if request.url.path.endswith("/search")
            else DETAIL | {"id": "new-job"},
        )

    async def known(ids):
        assert ids == {str(STUB["id"]), "new-job"}
        return {str(STUB["id"])}

    async with http(handler) as client:
        adapter = LinkedInPiloterrAdapter(client, Settings(piloterr_api_key="key"))
        adapter.known_postings = known
        result = await adapter.fetch_window(QUERY, DAY)
    assert len(requests) == 2
    assert result.credits_used == 2 and len(result.postings) == 1
    assert result.postings[0].source_job_id == "new-job"


async def test_detail_budget_cap_keeps_partial_jobs_and_requests_window_retry():
    requests = []
    other = STUB | {"id": "next-job"}

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json=[STUB, other] if request.url.path.endswith("/search") else DETAIL
        )

    async with http(handler) as client:
        adapter = LinkedInPiloterrAdapter(client, Settings(piloterr_api_key="key"))
        adapter.allowance_left = 2
        result = await adapter.fetch_window(QUERY, DAY)
    assert len(requests) == result.credits_used == 2
    assert len(result.postings) == 1 and not result.complete
    assert adapter.retry_incomplete_window


@pytest.mark.parametrize("failure", [429, 500, "bad_json", "missing", "wrong_id", "timeout"])
async def test_detail_failures_preserve_prior_jobs_and_actual_spend(failure):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=[STUB, STUB | {"id": "next-job"}])
        if calls == 2:
            return httpx.Response(200, json=DETAIL)
        if failure == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if failure == "bad_json":
            return httpx.Response(200, text="not-json")
        if failure == "missing":
            return httpx.Response(200, json=STUB | {"id": "next-job"})
        if failure == "wrong_id":
            return httpx.Response(200, json=DETAIL | {"id": "different-job"})
        return httpx.Response(failure, json={"error": "provider failed"})

    async with http(handler) as client:
        adapter = LinkedInPiloterrAdapter(client, Settings(piloterr_api_key="key"))
        result = await adapter.fetch_window(QUERY, DAY)
    assert len(result.postings) == 1 and not result.complete
    assert result.credits_used == (3 if failure in {"bad_json", "missing", "wrong_id"} else 2)


async def test_detail_error_before_any_job_records_search_credit_and_old_jobs_skip_details():
    from app.adapters.errors import SourceUnavailable

    async with http(
        lambda request: (
            httpx.Response(200, json=[STUB])
            if request.url.path.endswith("/search")
            else httpx.Response(500)
        )
    ) as client:
        adapter = LinkedInPiloterrAdapter(client, Settings(piloterr_api_key="key"))
        with pytest.raises(SourceUnavailable) as exc:
            await adapter.fetch_window(QUERY, DAY)
    assert exc.value.credits_used == 1

    requests = []

    def old(request):
        requests.append(request)
        return httpx.Response(200, json=[STUB | {"list_date": "2026-09-01"}])

    async with http(old) as client:
        result = await LinkedInPiloterrAdapter(
            client, Settings(piloterr_api_key="key")
        ).fetch_window(QUERY, DAY)
    assert len(requests) == result.credits_used == 1
    assert not result.postings and result.complete


async def test_full_page_at_configured_cap_is_incomplete_even_when_all_ids_are_known():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[STUB | {"id": str(i)} for i in range(1, 26)])

    async def known(ids):
        return ids

    async with http(handler) as client:
        adapter = LinkedInPiloterrAdapter(client, Settings(piloterr_api_key="key"))
        adapter.known_postings = known
        result = await adapter.fetch_window(QUERY, DAY)
    assert len(requests) == result.credits_used == 1
    assert not result.postings and not result.complete
