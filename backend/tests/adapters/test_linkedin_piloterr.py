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
}


def http(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestLinkedInPiloterr:
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
        posting = LinkedInPiloterrAdapter.to_posting(
            {**RECORD, "workplace_type": "Remote", "description": "Build products."}
        )
        assert posting is not None
        assert posting.work_mode == WorkMode.REMOTE
        assert posting.description == "Build products."
