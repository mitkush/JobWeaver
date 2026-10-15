import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.adapters.base import FetchWindow, Location, SourceQuery, WorkMode
from app.adapters.errors import (
    BoardNotFound,
    SourceNotConfigured,
    SourceQuotaExhausted,
    SourceQuotaRejected,
    SourceRateLimited,
    SourceUnavailable,
)
from app.adapters.greenhouse import GreenhouseAdapter
from app.adapters.jsearch import JSearchAdapter, date_posted_for
from app.adapters.lever import LeverAdapter, company_from_slug
from app.adapters.linkedin_brightdata import LinkedInBrightDataAdapter, time_range_for
from app.adapters.remotive import RemotiveAdapter
from app.core.config import Settings

NOW = datetime(2026, 10, 5, 1, 17, tzinfo=UTC)
DAY = FetchWindow(since=NOW - timedelta(hours=24), until=NOW)
QUERY = SourceQuery(keywords="Backend Engineer", location=Location(city="Bengaluru", country="IN"))
SETTINGS = Settings(brightdata_api_key="bd-key", rapidapi_key="rapid-key")


def http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def no_sleep(_: float) -> None:
    return None


class TestLinkedIn:
    RECORD = {
        "job_posting_id": "4012345678",
        "job_title": "Senior Backend Engineer",
        "company_name": "Acme Corp",
        "job_location": "Bengaluru, Karnataka, India",
        "job_summary": "Build APIs in Python. Apply: careers@acme.com",
        "job_posted_date": "2026-10-04T10:00:00.000Z",
        "apply_link": "https://boards.greenhouse.io/acme/jobs/987",
        "job_work_type": "Hybrid",
    }

    async def test_trigger_poll_download_and_normalise(self):
        seen: list[httpx.Request] = []
        polls = iter([{"status": "running"}, {"status": "ready"}])

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            path = request.url.path
            if path.endswith("/trigger"):
                return httpx.Response(200, json={"snapshot_id": "s_1"})
            if "/progress/" in path:
                return httpx.Response(200, json=next(polls))
            unusable = {"job_posting_id": "x"}  # delivered, so paid for, but has no title
            return httpx.Response(
                200, json=[self.RECORD, unusable, {"error": "blocked", "input": {}}]
            )

        async with http(handler) as client:
            adapter = LinkedInBrightDataAdapter(client, SETTINGS, sleep=no_sleep)
            result = await adapter.fetch_window(QUERY, DAY)

        trigger = seen[0]
        assert trigger.headers["authorization"] == "Bearer bd-key"
        assert trigger.url.params["discover_by"] == "keyword"
        body = json.loads(trigger.read())[0]
        assert body["time_range"] == "Past 24 hours"
        assert body["location"] == "Bengaluru, India"
        assert result.credits_used == 2 and len(result.postings) == 1
        posting = result.postings[0]
        assert posting.source_job_id == "4012345678"
        assert posting.locations[0].city == "Bengaluru"
        assert posting.work_mode == WorkMode.HYBRID
        assert posting.contact_email == "careers@acme.com"

    def test_catch_up_uses_the_smallest_filter_that_reaches_back(self):
        assert time_range_for(DAY) == "Past 24 hours"
        assert time_range_for(FetchWindow(since=NOW - timedelta(days=3), until=NOW)) == "Past week"
        assert (
            time_range_for(FetchWindow(since=NOW - timedelta(days=14), until=NOW)) == "Past month"
        )

    async def test_missing_key_is_reported(self):
        async with http(lambda r: httpx.Response(200)) as client:
            with pytest.raises(SourceNotConfigured):
                await LinkedInBrightDataAdapter(client, Settings()).fetch_window(QUERY, DAY)

    @pytest.mark.parametrize(
        ("status", "body", "error"),
        [
            (402, "insufficient balance", SourceQuotaExhausted),
            (429, "slow down", SourceQuotaRejected),
            (401, "bad token", SourceUnavailable),
        ],
    )
    async def test_provider_errors_are_classified(self, status, body, error):
        async with http(lambda r: httpx.Response(status, text=body)) as client:
            with pytest.raises(error):
                await LinkedInBrightDataAdapter(client, SETTINGS, sleep=no_sleep).fetch_window(
                    QUERY, DAY
                )

    async def test_failed_snapshot(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/trigger"):
                return httpx.Response(200, json={"snapshot_id": "s"})
            return httpx.Response(200, json={"status": "failed"})

        async with http(handler) as client:
            with pytest.raises(SourceUnavailable):
                await LinkedInBrightDataAdapter(client, SETTINGS, sleep=no_sleep).fetch_window(
                    QUERY, DAY
                )


class TestJSearch:
    JOB = {
        "job_id": "abc==",
        "job_title": "Python Developer",
        "employer_name": "Globex",
        "job_description": "Remote-friendly team. Email jobs@globex.io",
        "job_apply_link": "https://jobs.lever.co/globex/123",
        "job_city": "Bangalore",
        "job_country": "IN",
        "job_is_remote": False,
        "job_posted_at_datetime_utc": "2026-10-04T09:00:00.000Z",
    }

    async def test_query_and_mapping(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(
                200,
                json={
                    "status": "OK",
                    "data": {"jobs": [self.JOB, {"job_id": None}], "cursor": None},
                },
            )

        async with http(handler) as client:
            result = await JSearchAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
        params = seen[0].url.params
        assert seen[0].url.path == "/search-v2"
        assert params["query"] == "Backend Engineer in Bengaluru, India"
        assert params["date_posted"] == "today" and params["country"] == "in"
        assert seen[0].headers["x-rapidapi-key"] == "rapid-key"
        assert result.credits_used == 1 and len(result.postings) == 1
        assert result.postings[0].locations[0].city == "Bengaluru"

    async def test_empty_v2_search_is_a_successful_fetch(self):
        async with http(
            lambda r: httpx.Response(
                200, json={"status": "OK", "data": {"jobs": [], "cursor": None}}
            )
        ) as client:
            result = await JSearchAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
        assert result.postings == []
        assert result.credits_used == 1

    def test_date_filter_widens_for_catch_up(self):
        assert date_posted_for(FetchWindow(since=NOW - timedelta(days=2), until=NOW)) == "3days"
        assert date_posted_for(FetchWindow(since=NOW - timedelta(days=14), until=NOW)) == "month"

    async def test_monthly_quota_message(self):
        body = "You have exceeded the MONTHLY quota for Requests on your current plan"
        async with http(lambda r: httpx.Response(429, text=body)) as client:
            with pytest.raises(SourceQuotaExhausted):
                await JSearchAdapter(client, SETTINGS).fetch_window(QUERY, DAY)


class TestGreenhouse:
    async def test_board_snapshot(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/jobs"):
                return httpx.Response(
                    200,
                    json={
                        "jobs": [
                            {
                                "id": 987,
                                "title": "Backend Engineer",
                                "location": {"name": "Bengaluru, India"},
                                "absolute_url": "https://boards.greenhouse.io/acme/jobs/987",
                                "content": "&lt;p&gt;Python and Postgres&lt;/p&gt;",
                                "updated_at": "2026-10-03T08:00:00-04:00",
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"name": "Acme Corp"})

        async with http(handler) as client:
            result = await GreenhouseAdapter(client, SETTINGS).fetch_board("acme")
        posting = result.postings[0]
        assert (posting.company, posting.description) == ("Acme Corp", "Python and Postgres")
        assert posting.locations[0].country == "IN"

    async def test_missing_board(self):
        async with http(lambda r: httpx.Response(404)) as client:
            with pytest.raises(BoardNotFound):
                await GreenhouseAdapter(client, SETTINGS).fetch_board("gone")


class TestLever:
    async def test_board_snapshot(self):
        job = {
            "id": "a-b-c",
            "text": "Platform Engineer",
            "categories": {"location": "Remote - India", "commitment": "Full-time"},
            "descriptionPlain": "Kubernetes and Go.",
            "lists": [{"text": "Requirements", "content": "<li>3 years</li>"}],
            "hostedUrl": "https://jobs.lever.co/acme-labs/a-b-c",
            "createdAt": 1791100800000,
            "workplaceType": "remote",
        }
        async with http(lambda r: httpx.Response(200, json=[job])) as client:
            result = await LeverAdapter(client, SETTINGS).fetch_board("acme-labs")
        posting = result.postings[0]
        assert posting.company == "Acme Labs"
        assert posting.work_mode == WorkMode.REMOTE
        assert "Requirements\n3 years" in posting.description
        assert posting.locations[0].country == "IN"

    def test_company_name_from_slug(self):
        assert company_from_slug("acme.io") == "Acme Io"


class TestRemotive:
    async def test_keeps_only_jobs_inside_the_window(self):
        jobs = [
            {
                "id": 1,
                "title": "Backend Engineer",
                "company_name": "Initech",
                "publication_date": "2026-10-04T12:00:00",
                "candidate_required_location": "India",
                "url": "https://remotive.com/remote-jobs/software-dev/backend-1",
                "description": "<p>Remote role</p>",
            },
            {
                "id": 2,
                "title": "Old job",
                "company_name": "Initech",
                "publication_date": "2026-09-01T12:00:00",
                "candidate_required_location": "Worldwide",
                "url": "https://remotive.com/x",
            },
        ]
        async with http(lambda r: httpx.Response(200, json={"jobs": jobs})) as client:
            result = await RemotiveAdapter(client, SETTINGS).fetch_window(None, DAY)
        assert [p.source_job_id for p in result.postings] == ["1"]
        assert result.postings[0].locations[0] == Location(country="IN", remote=True)


async def test_jsearch_counts_failed_requests_that_reached_rapidapi():
    async with http(lambda r: httpx.Response(500, text="oops")) as client:
        with pytest.raises(SourceUnavailable) as error:
            await JSearchAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
    assert error.value.credits_used == 1
    async with http(lambda r: httpx.Response(429, text="slow down")) as client:
        with pytest.raises(SourceRateLimited) as error:
            await JSearchAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
    assert error.value.credits_used == 0


def test_daily_windows_with_drift_keep_the_one_day_filters():
    """A daily window is 24 h plus the 2 h overlap plus drift; it must never be billed as
    "Past week" (Bright Data charges per record)."""
    from app.adapters.naukri_apify import freshness_for
    from app.adapters.serpapi import date_chip_for

    drifted = FetchWindow(since=NOW - timedelta(hours=26, minutes=40), until=NOW)
    assert time_range_for(drifted) == "Past 24 hours"
    assert date_posted_for(drifted) == "today"
    assert date_chip_for(drifted) == "date_posted:today"
    assert freshness_for(drifted) == "1"
    # A missed day still widens the filter.
    two_days = FetchWindow(since=NOW - timedelta(hours=50), until=NOW)
    assert time_range_for(two_days) == "Past week"


@pytest.mark.parametrize(
    "status,body,allowed",
    [
        (402, "no credits", True),
        (400, "insufficient credits", True),
        (400, "invalid input", False),
        (403, "insufficient credits", True),
        (429, "slow down", True),
        (401, "bad token", False),
        (503, "unavailable", False),
    ],
)
async def test_only_limit_rejection_before_snapshot_is_safe_to_switch_accounts(
    status, body, allowed
):
    from app.adapters.errors import SourceError, SourceQuotaRejected

    async with http(lambda r: httpx.Response(status, text=body)) as client:
        with pytest.raises(SourceError) as caught:
            await LinkedInBrightDataAdapter(client, SETTINGS, sleep=no_sleep).fetch_window(
                QUERY, DAY
            )
    assert isinstance(caught.value, SourceQuotaRejected) is allowed
    assert caught.value.credits_used == 0


@pytest.mark.parametrize("status", [400, 403])
@pytest.mark.parametrize("phase", ["trigger", "progress", "snapshot"])
async def test_brightdata_inactive_account_is_only_retryable_before_start(status, phase):
    from app.adapters.errors import SourceCredentialRejected, SourceError, quota_rejected

    def handler(request):
        current = request.url.path.split("/")[3]
        if current == phase:
            response = httpx.Response(status, text=" CUSTOMER IS NOT ACTIVE ")
            assert not quota_rejected(response)
            return response
        if current == "trigger":
            return httpx.Response(200, json={"snapshot_id": "s"})
        return httpx.Response(200, json={"status": "ready"})

    async with http(handler) as client:
        with pytest.raises(SourceError) as caught:
            await LinkedInBrightDataAdapter(client, SETTINGS, sleep=no_sleep).fetch_window(
                QUERY, DAY
            )
    assert isinstance(caught.value, SourceCredentialRejected) is (phase == "trigger")
    if phase == "trigger":
        assert str(caught.value) == "LinkedIn (Bright Data) account is not active"


DISCOVERY = Settings(
    brightdata_api_key="bd-key",
    brightdata_discovery_keywords='Software, Developer,Backend, "Full stack" ,software',
)


def test_discovery_keywords_search_once_per_country_with_or():
    """Cities, titles and work modes are left to the Feed: one OR search per country, one
    worldwide remote search, and one worldwide search for a Preference with no place."""
    preference_queries = [
        SourceQuery(keywords="Rails Developer", location=Location(city="Bengaluru", country="IN")),
        SourceQuery(keywords="Backend Engineer", location=Location(city="Pune", country="IN")),
        SourceQuery(keywords="Rails Developer", location=Location(country="IN", remote=True)),
        SourceQuery(keywords="Rails Developer", location=Location(remote=True)),
        SourceQuery(keywords="Rails Developer", location=None),
    ]
    adapter = LinkedInBrightDataAdapter(httpx.AsyncClient(), DISCOVERY)
    queries = adapter.search_queries(preference_queries)
    keyword = 'Software OR Developer OR Backend OR "Full stack"'
    assert {q.keywords for q in queries} == {keyword}
    places = {(q.location.country, q.location.remote) if q.location else None for q in queries}
    assert places == {("IN", False), (None, True), None}
    assert len(queries) == 3
    assert sum(q.location is None for q in queries) == 1
    assert not adapter.searches_titles()


def test_without_discovery_keywords_titles_are_searched_as_before():
    adapter = LinkedInBrightDataAdapter(httpx.AsyncClient(), SETTINGS)
    assert adapter.search_queries([QUERY]) == [QUERY]
    assert adapter.searches_titles()


async def test_discovery_search_is_country_wide_and_capped():
    seen: list[httpx.Request] = []
    records = [
        {"job_posting_id": str(i), "job_title": "Developer", "company_name": "Acme",
         "job_location": "Indore", "country_code": "IN"}
        for i in range(3)
    ]  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/trigger"):
            return httpx.Response(200, json={"snapshot_id": "s_1"})
        if "/progress/" in request.url.path:
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(200, json=records)

    settings = DISCOVERY.model_copy(update={"brightdata_limit_per_search": 3})
    adapter = LinkedInBrightDataAdapter(httpx.AsyncClient(), settings)
    [query] = adapter.search_queries([QUERY])
    async with http(handler) as client:
        result = await LinkedInBrightDataAdapter(client, settings, sleep=no_sleep).fetch_window(
            query, DAY
        )
    trigger = seen[0]
    assert trigger.url.params["limit_per_input"] == "3"
    body = json.loads(trigger.read())[0]
    assert (body["keyword"], body["location"], body["country"], body["remote"]) == (
        'Software OR Developer OR Backend OR "Full stack"',
        "India",
        "IN",
        "",
    )
    # Three records against a cap of three: the window may hold more.
    assert result.complete is False
    # A bare city takes the record's own country code.
    assert (result.postings[0].locations[0].city, result.postings[0].locations[0].country) == (
        "Indore",
        "IN",
    )


async def test_no_cap_sends_no_limit():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/trigger"):
            return httpx.Response(200, json={"snapshot_id": "s_1"})
        if "/progress/" in request.url.path:
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(200, json=[])

    settings = SETTINGS.model_copy(update={"brightdata_limit_per_search": 0})
    async with http(handler) as client:
        result = await LinkedInBrightDataAdapter(client, settings, sleep=no_sleep).fetch_window(
            QUERY, DAY
        )
    assert "limit_per_input" not in seen[0].url.params
    assert result.complete is True


def test_long_keyword_lists_keep_every_country_and_distinct_keys():
    """SourceQuery.key fits the 300-character columns without merging two searches."""
    terms = ",".join(f"Keyword number {i}" for i in range(30))
    settings = DISCOVERY.model_copy(update={"brightdata_discovery_keywords": terms})
    adapter = LinkedInBrightDataAdapter(httpx.AsyncClient(), settings)
    queries = adapter.search_queries(
        [
            SourceQuery(keywords="Rails", location=Location(city="Pune", country="IN")),
            SourceQuery(keywords="Rails", location=Location(city="Austin", country="US")),
        ]
    )
    assert sorted(q.location.country for q in queries) == ["IN", "US"]
    keys = [q.key for q in queries]
    assert len(set(keys)) == 2 and all(len(k) <= 300 for k in keys)
    assert keys[0].endswith("@|IN|False") or keys[1].endswith("@|IN|False")
    # Short keys keep their existing form, so current watermarks still match.
    assert QUERY.key == "backend engineer@Bengaluru|IN|False"


def test_new_discovery_searches_reach_back_one_day_not_the_full_backfill():
    assert LinkedInBrightDataAdapter(httpx.AsyncClient(), DISCOVERY).backfill_days(14) == 1
    assert LinkedInBrightDataAdapter(httpx.AsyncClient(), SETTINGS).backfill_days(14) == 14
