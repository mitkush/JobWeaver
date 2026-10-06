"""SerpApi, Adzuna and the remote boards against recorded-shape payloads (FR-B1 AC2)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.adapters.adzuna import AdzunaAdapter
from app.adapters.base import FetchWindow, Location, SourceQuery, WorkMode
from app.adapters.errors import (
    SourceBadResponse,
    SourceQuotaExhausted,
    SourceRateLimited,
)
from app.adapters.himalayas import HimalayasAdapter
from app.adapters.jobicy import JobicyAdapter
from app.adapters.normalize import remote_locations
from app.adapters.remoteok import RemoteOkAdapter
from app.adapters.serpapi import SerpApiAdapter, date_chip_for
from app.adapters.weworkremotely import WeWorkRemotelyAdapter
from app.adapters.workingnomads import WorkingNomadsAdapter
from app.core.config import Settings

NOW = datetime.now(UTC)
DAY = FetchWindow(since=NOW - timedelta(hours=26), until=NOW)
QUERY = SourceQuery(keywords="Backend Engineer", location=Location(city="Bengaluru", country="IN"))
SETTINGS = Settings(
    serpapi_key="serp", adzuna_app_id="az-id", adzuna_app_key="az-key", serpapi_pages_per_query=2
)
RECENT = (NOW - timedelta(hours=3)).isoformat()
OLD = (NOW - timedelta(days=10)).isoformat()


def http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def always(status: int, body=None, **kwargs):
    return lambda request: httpx.Response(status, json=body, **kwargs)


SERP_JOB = {
    "job_id": "eyJqb2JfdGl0bGUiOiJCYWNrZW5k",
    "title": "Backend Engineer",
    "company_name": "Acme",
    "location": "Bengaluru, Karnataka, India",
    "description": "Go and Kafka.",
    "detected_extensions": {"posted_at": "2 days ago", "work_from_home": True},
    "apply_options": [{"title": "Acme Careers", "link": "https://acme.dev/jobs/1"}],
}


class TestSerpApi:
    async def test_pages_count_one_search_each(self):
        seen: list[httpx.Request] = []

        def handler(request):
            seen.append(request)
            more = {"serpapi_pagination": {"next_page_token": "t2"}} if len(seen) == 1 else {}
            return httpx.Response(200, json={"jobs_results": [SERP_JOB], **more})

        async with http(handler) as client:
            result = await SerpApiAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
        assert result.credits_used == 2 and len(seen) == 2
        assert seen[0].url.params["location"] == "Bengaluru, India"
        assert seen[0].url.params["gl"] == "in"
        assert seen[1].url.params["next_page_token"] == "t2"
        job = result.postings[0]
        assert job.work_mode == WorkMode.REMOTE and job.locations[0].remote
        assert job.apply_url == "https://acme.dev/jobs/1"

    async def test_no_results_is_empty_and_exhaustion_is_a_quota_error(self):
        empty = {"error": "Google hasn't returned any results for this query."}
        async with http(always(200, empty)) as client:
            result = await SerpApiAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
        assert result.postings == [] and result.credits_used == 1
        used_up = {"error": "Your account has run out of searches."}
        async with http(always(429, used_up)) as client:
            with pytest.raises(SourceQuotaExhausted) as caught:
                await SerpApiAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
        assert caught.value.credits_used == 0

    async def test_malformed(self):
        async with http(always(200, {"jobs_results": "x"})) as client:
            with pytest.raises(SourceBadResponse):
                await SerpApiAdapter(client, SETTINGS).fetch_window(QUERY, DAY)

    def test_is_a_jsearch_standby_and_maps_windows(self):
        assert SerpApiAdapter.standby_for == "jsearch"
        assert date_chip_for(DAY) == "date_posted:today"
        assert date_chip_for(FetchWindow(since=NOW - timedelta(days=5), until=NOW)).endswith("week")


ADZUNA_RESULT = {
    "id": "4870112233",
    "title": "<strong>Backend</strong> Engineer",
    "company": {"display_name": "Acme India"},
    "location": {
        "display_name": "Bengaluru, Karnataka",
        "area": ["India", "Karnataka", "Bangalore"],
    },
    "description": "Python services, hybrid. Snippet only...",
    "created": "2026-10-04T08:00:00Z",
    "redirect_url": "https://www.adzuna.in/land/ad/4870112233",
}


class TestAdzuna:
    async def test_search_and_normalise(self):
        seen: list[httpx.Request] = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"count": 1, "results": [ADZUNA_RESULT]})

        async with http(handler) as client:
            result = await AdzunaAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
        assert seen[0].url.path == "/v1/api/jobs/in/search/1"
        assert seen[0].url.params["where"] == "Bengaluru"
        assert seen[0].url.params["max_days_old"] == "2"
        # Fewer than a full page: no second request.
        assert result.credits_used == 1 and len(seen) == 1
        job = result.postings[0]
        assert job.title == "Backend Engineer" and job.locations[0].city == "Bengaluru"
        assert job.locations[0].country == "IN" and job.work_mode == WorkMode.HYBRID

    async def test_unsupported_countries_and_global_searches_cost_nothing(self):
        async with http(always(500)) as client:
            adapter = AdzunaAdapter(client, SETTINGS)
            for location in (None, Location(country="AE")):
                query = SourceQuery(keywords="SRE", location=location)
                assert (await adapter.fetch_window(query, DAY)).credits_used == 0

    async def test_rate_limit_is_free_and_malformed_costs_one(self):
        async with http(always(429, {})) as client:
            with pytest.raises(SourceRateLimited) as caught:
                await AdzunaAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
        assert caught.value.credits_used == 0
        async with http(always(200, {"results": None})) as client:
            with pytest.raises(SourceBadResponse) as caught:
                await AdzunaAdapter(client, SETTINGS).fetch_window(QUERY, DAY)
        assert caught.value.credits_used == 1


class TestRemoteBoards:
    async def test_remote_ok_skips_its_legal_notice_and_old_jobs(self):
        body = [
            {"legal": "API Terms of Service"},
            {"id": "1", "position": "SRE", "company": "Acme", "date": RECENT,
             "location": "USA, Canada", "url": "https://remoteok.com/remote-jobs/1"},
            {"id": "2", "position": "Old", "company": "Acme", "date": OLD},
        ]  # fmt: skip
        async with http(always(200, body)) as client:
            result = await RemoteOkAdapter(client, Settings()).fetch_window(None, DAY)
        assert [p.title for p in result.postings] == ["SRE"]
        assert [loc.country for loc in result.postings[0].locations] == ["US", "CA"]
        assert result.postings[0].apply_url == "https://remoteok.com/remote-jobs/1"

    async def test_we_work_remotely_rss(self):
        rss = f"""<?xml version="1.0"?><rss><channel>
          <item><title>Acme: Staff Engineer: Platform</title><guid>wwr-1</guid>
            <link>https://weworkremotely.com/remote-jobs/acme-staff</link>
            <country>India</country><region>Anywhere in the World</region>
            <pubDate>{NOW.strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>
            <description>&lt;p&gt;Rust&lt;/p&gt;</description></item>
          <item><title>No company separator</title><guid>wwr-2</guid></item>
        </channel></rss>"""
        async with http(lambda r: httpx.Response(200, text=rss)) as client:
            result = await WeWorkRemotelyAdapter(client, Settings()).fetch_window(None, DAY)
        assert len(result.postings) == 1
        job = result.postings[0]
        assert (job.company, job.title) == ("Acme", "Staff Engineer: Platform")
        assert job.locations[0].country == "IN" and job.description == "Rust"
        async with http(lambda r: httpx.Response(200, text="<rss><broken")) as client:
            with pytest.raises(SourceBadResponse):
                await WeWorkRemotelyAdapter(client, Settings()).fetch_window(None, DAY)

    async def test_himalayas_pages_until_the_window_start(self):
        pages = {
            None: {"jobs": [{"guid": "h1", "title": "SRE", "companyName": "Acme",
                             "pubDate": RECENT, "locationRestrictions": ["India"]}],
                   "nextCursor": "c2"},
            "c2": {"jobs": [{"guid": "h2", "title": "Old", "companyName": "Acme",
                             "pubDate": OLD}], "nextCursor": "c3"},
        }  # fmt: skip
        seen = []

        def handler(request):
            seen.append(request.url.params.get("cursor"))
            return httpx.Response(200, json=pages[request.url.params.get("cursor")])

        async with http(handler) as client:
            result = await HimalayasAdapter(client, Settings()).fetch_window(None, DAY)
        assert seen == [None, "c2"]
        assert [p.source_job_id for p in result.postings] == ["h1"]
        assert result.postings[0].locations[0].country == "IN"

    async def test_jobicy_and_working_nomads(self):
        jobicy = {"jobs": [{"id": 77, "jobTitle": "Data Engineer", "companyName": "Acme",
                            "jobGeo": "Anywhere", "pubDate": RECENT,
                            "url": "https://jobicy.com/jobs/77"}]}  # fmt: skip
        async with http(always(200, jobicy)) as client:
            result = await JobicyAdapter(client, Settings()).fetch_window(None, DAY)
        assert result.postings[0].locations == [Location(remote=True)]
        nomads = [{"url": "https://www.workingnomads.com/jobs/x", "title": "QA",
                   "company_name": "Acme", "location": "Europe", "pub_date": RECENT}]  # fmt: skip
        async with http(always(200, nomads)) as client:
            result = await WorkingNomadsAdapter(client, Settings()).fetch_window(None, DAY)
        assert result.postings[0].source_job_id == "https://www.workingnomads.com/jobs/x"
        async with http(always(200, {"jobs": "x"})) as client:
            with pytest.raises(SourceBadResponse):
                await JobicyAdapter(client, Settings()).fetch_window(None, DAY)


def test_remote_locations():
    assert remote_locations("Anywhere") == [Location(remote=True)]
    assert [loc.country for loc in remote_locations(["India", "UK", "India"])] == ["IN", "GB"]
    assert remote_locations("USA only")[0].remote


class TestHackerNews:
    async def test_collects_new_top_level_comments_of_hiring_threads(self):
        from app.adapters.hackernews import HackerNewsAdapter

        recent = int((NOW - timedelta(hours=2)).timestamp())
        old = int((NOW - timedelta(days=3)).timestamp())
        hits = {"hits": [
            {"objectID": "500", "title": "Ask HN: Who wants to be hired? (October 2026)"},
            {"objectID": "501", "title": "Ask HN: Who is hiring? (October 2026)"},
        ]}  # fmt: skip
        thread = {"id": 501, "children": [
            {"id": 9001, "created_at_i": recent, "children": [{"id": 9101, "text": "reply"}],
             "text": 'Acme | SRE | <a href="https://acme.dev/careers/sre-2026">'
                     "https://acme.dev/careers/sre-...</a>"},
            {"id": 9002, "created_at_i": recent, "text": None},
            {"id": 9003, "created_at_i": old, "text": "Old advert"},
        ]}  # fmt: skip
        seen = []

        def handler(request):
            seen.append(request.url.path)
            return httpx.Response(200, json=hits if "search" in request.url.path else thread)

        async with http(handler) as client:
            result = await HackerNewsAdapter(client, Settings()).fetch_window(None, DAY)
        assert seen == ["/api/v1/search_by_date", "/api/v1/items/501"]
        assert result.postings == [] and [a.ref for a in result.pending] == ["9001"]
        # HN shortens long link text; the full link comes from the href.
        assert "https://acme.dev/careers/sre-2026" in result.pending[0].text
        assert result.pending[0].url == "https://news.ycombinator.com/item?id=9001"

    async def test_malformed_thread(self):
        from app.adapters.hackernews import HackerNewsAdapter

        def handler(request):
            if "search" in request.url.path:
                return httpx.Response(200, json={"hits": [{"objectID": "1",
                                      "title": "Ask HN: Who is hiring? (May)"}]})  # fmt: skip
            return httpx.Response(200, json={"children": "x"})

        async with http(handler) as client:
            with pytest.raises(SourceBadResponse):
                await HackerNewsAdapter(client, Settings()).fetch_window(None, DAY)


class TestSiteFetch:
    async def test_foundit_and_instahyre_are_off_by_default_and_parse(self):
        from app.adapters.foundit import FounditAdapter
        from app.adapters.instahyre import InstahyreAdapter

        assert not FounditAdapter.default_enabled and FounditAdapter.disabled_reason
        assert not InstahyreAdapter.default_enabled and InstahyreAdapter.disabled_reason
        foundit = {"jobSearchResponse": {"data": [{
            "jobId": 41, "title": "Java Developer", "companyName": "Acme",
            "locations": "Bengaluru, Pune", "seoJdUrl": "/job/java-developer-41",
            "createdAt": 1759622400000}]}}  # fmt: skip
        async with http(always(200, foundit)) as client:
            result = await FounditAdapter(client, Settings()).fetch_window(QUERY, DAY)
        job = result.postings[0]
        assert job.apply_url == "https://www.foundit.in/job/java-developer-41"
        assert [loc.city for loc in job.locations] == ["Bengaluru", "Pune"]
        instahyre = {"objects": [{"id": 7, "candidate_title": "SDE 2",
                     "employer": {"company_name": "Acme"}, "locations": "Bangalore",
                     "keywords": ["Go", "AWS"],
                     "public_url": "https://www.instahyre.com/job-7"}]}  # fmt: skip
        async with http(always(200, instahyre)) as client:
            result = await InstahyreAdapter(client, Settings()).fetch_window(QUERY, DAY)
        assert result.postings[0].description == "Go, AWS"
        assert result.postings[0].locations[0].city == "Bengaluru"
        async with http(always(200, {"objects": None})) as client:
            with pytest.raises(SourceBadResponse):
                await InstahyreAdapter(client, Settings()).fetch_window(QUERY, DAY)
