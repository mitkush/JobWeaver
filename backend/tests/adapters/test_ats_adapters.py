"""Ashby, SmartRecruiters, Workable, Recruitee and Workday against recorded-shape payloads
(success, malformed and provider-limit cases, FR-B1 AC2)."""

import json

import httpx
import pytest

from app.adapters.ashby import AshbyAdapter
from app.adapters.base import WorkMode
from app.adapters.errors import BoardNotFound, SourceBadResponse, SourceRateLimited
from app.adapters.recruitee import RecruiteeAdapter
from app.adapters.smartrecruiters import SmartRecruitersAdapter
from app.adapters.workable import WorkableAdapter
from app.adapters.workday import WorkdayAdapter
from app.core.config import Settings

SETTINGS = Settings()


def http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def always(status: int, body=None):
    return lambda request: httpx.Response(status, json=body if body is not None else {})


ASHBY = {
    "apiVersion": "1",
    "jobs": [
        {
            "id": "7f1c",
            "title": "Backend Engineer",
            "location": "Bengaluru, India",
            "isRemote": False,
            "workplaceType": "Hybrid",
            "isListed": True,
            "descriptionPlain": "Python and Postgres. Write to jobs@acme.dev",
            "publishedAt": "2026-10-01T09:00:00.000+00:00",
            "jobUrl": "https://jobs.ashbyhq.com/acme/7f1c",
            "address": {
                "postalAddress": {"addressLocality": "Bengaluru", "addressCountry": "India"}
            },
            "secondaryLocations": [{"location": "Remote - India"}],
        },
        {"id": "hidden", "title": "Unlisted", "isListed": False},
    ],
}


class TestAshby:
    async def test_board_is_normalised_and_unlisted_jobs_skipped(self):
        async with http(always(200, ASHBY)) as client:
            result = await AshbyAdapter(client, SETTINGS).fetch_board("acme")
        assert len(result.postings) == 1
        job = result.postings[0]
        assert (job.title, job.company, job.work_mode) == ("Backend Engineer", "Acme", "hybrid")
        assert job.locations[0].city == "Bengaluru" and job.locations[0].country == "IN"
        assert job.locations[1].remote and job.locations[1].country == "IN"
        assert job.contact_email == "jobs@acme.dev"
        assert job.posted_at.isoformat().startswith("2026-10-01")

    async def test_missing_board_and_malformed_payload(self):
        async with http(always(404)) as client:
            with pytest.raises(BoardNotFound):
                await AshbyAdapter(client, SETTINGS).fetch_board("gone")
        async with http(always(200, {"jobs": "nope"})) as client:
            with pytest.raises(SourceBadResponse):
                await AshbyAdapter(client, SETTINGS).fetch_board("acme")


class TestSmartRecruiters:
    SUMMARY = {
        "id": "744000012345",
        "name": "Data Engineer",
        "company": {"identifier": "acme", "name": "Acme Corp"},
        "releasedDate": "2026-10-02T08:00:00.000Z",
        "location": {"city": "Pune", "country": "in", "remote": False, "hybrid": True},
    }
    DETAIL = {
        "jobAd": {
            "sections": {
                "companyDescription": {"text": "<p>We sell rockets</p>"},
                "jobDescription": {"text": "<p>Build pipelines in Spark</p>"},
                "qualifications": {"text": "<ul><li>3 years</li></ul>"},
            }
        },
        "postingUrl": "https://jobs.smartrecruiters.com/acme/744000012345",
    }

    async def test_pages_then_fetches_details(self):
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if request.url.path.endswith("/postings"):
                return httpx.Response(200, json={"totalFound": 1, "content": [self.SUMMARY]})
            return httpx.Response(200, json=self.DETAIL)

        async with http(handler) as client:
            result = await SmartRecruitersAdapter(client, SETTINGS).fetch_board("acme")
        job = result.postings[0]
        assert job.title == "Data Engineer" and job.company == "Acme Corp"
        assert job.locations[0].city == "Pune" and job.locations[0].country == "IN"
        assert job.work_mode == WorkMode.HYBRID
        # The company blurb is not part of the advert's own requirements.
        assert "rockets" not in job.description and "Spark" in job.description
        assert job.apply_url.endswith("/744000012345")
        assert len(calls) == 2

    async def test_rate_limit_on_a_detail_call_stops_the_board(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/postings"):
                return httpx.Response(200, json={"totalFound": 1, "content": [self.SUMMARY]})
            return httpx.Response(429)

        async with http(handler) as client:
            with pytest.raises(SourceRateLimited):
                await SmartRecruitersAdapter(client, SETTINGS).fetch_board("acme")


class TestWorkable:
    BODY = {
        "name": "Acme Labs",
        "jobs": [
            {
                "title": "Frontend Engineer",
                "shortcode": "AB12CD",
                "telecommuting": True,
                "workplace_type": "remote",
                "url": "https://apply.workable.com/j/AB12CD",
                "published_on": "2026-09-30",
                "description": "<p>React</p>",
                "locations": [{"city": "London", "countryCode": "GB", "hidden": False}],
            },
            {"title": "No shortcode"},
        ],
    }

    async def test_widget_payload(self):
        async with http(always(200, self.BODY)) as client:
            result = await WorkableAdapter(client, SETTINGS).fetch_board("acme")
        assert len(result.postings) == 1
        job = result.postings[0]
        assert (job.source_job_id, job.company, job.work_mode) == ("AB12CD", "Acme Labs", "remote")
        assert job.locations[0].country == "GB" and job.locations[0].remote

    async def test_missing_account(self):
        async with http(always(404)) as client:
            with pytest.raises(BoardNotFound):
                await WorkableAdapter(client, SETTINGS).fetch_board("gone")


class TestRecruitee:
    BODY = {
        "offers": [
            {
                "id": 991,
                "title": "QA Engineer",
                "company_name": "Acme BV",
                "status": "published",
                "remote": False,
                "hybrid": True,
                "description": "<p>Testing</p>",
                "requirements": "<p>Playwright</p>",
                "careers_url": "https://acme.recruitee.com/o/qa",
                "published_at": "2026-08-14 08:23:10 UTC",
                "locations": [{"city": "Amsterdam", "country_code": "NL"}],
            }
        ]
    }

    async def test_offers_payload_and_its_non_iso_dates(self):
        async with http(always(200, self.BODY)) as client:
            result = await RecruiteeAdapter(client, SETTINGS).fetch_board("acme")
        job = result.postings[0]
        assert job.work_mode == WorkMode.HYBRID and job.locations[0].country == "NL"
        assert "Playwright" in job.description
        assert job.posted_at.isoformat() == "2026-08-14T08:23:10+00:00"

    async def test_malformed(self):
        async with http(always(200, ["not", "a", "dict"])) as client:
            with pytest.raises(SourceBadResponse):
                await RecruiteeAdapter(client, SETTINGS).fetch_board("acme")


class TestWorkday:
    def handler(self, total: int, listed: int):
        def handle(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                offset = json.loads(request.read())["offset"]
                count = max(min(20, listed - offset), 0)
                page = [
                    {"title": f"Engineer {offset + i}", "externalPath": f"/job/Pune/E_{offset + i}"}
                    for i in range(count)
                ]
                return httpx.Response(
                    200, json={"total": total if offset == 0 else 0, "jobPostings": page}
                )
            return httpx.Response(
                200,
                json={
                    "jobPostingInfo": {
                        "title": "Engineer",
                        "jobDescription": "<p>Go</p>",
                        "location": "Pune, India",
                        "startDate": "2026-10-01",
                        "jobReqId": request.url.path.rsplit("_", 1)[1],
                        "externalUrl": "https://acme.wd5.myworkdayjobs.com/Ext/job/x",
                    },
                    "hiringOrganization": {"name": "Acme Inc"},
                },
            )

        return handle

    async def test_pages_of_twenty_and_details(self):
        async with http(self.handler(total=25, listed=25)) as client:
            result = await WorkdayAdapter(client, SETTINGS).fetch_board("acme/wd5/Ext")
        assert len(result.postings) == 25 and result.complete
        assert result.postings[0].company == "Acme Inc"
        assert result.postings[0].locations[0].city == "Pune"

    async def test_listing_cap_marks_the_snapshot_partial(self, monkeypatch):
        monkeypatch.setattr("app.adapters.workday.MAX_LISTED", 40)
        async with http(self.handler(total=500, listed=500)) as client:
            result = await WorkdayAdapter(client, SETTINGS).fetch_board("acme/wd5/Ext")
        assert len(result.postings) == 40 and not result.complete

    async def test_off_by_default_and_bad_slug(self):
        assert WorkdayAdapter.default_enabled is False and WorkdayAdapter.disabled_reason
        async with http(always(200)) as client:
            with pytest.raises(BoardNotFound):
                await WorkdayAdapter(client, SETTINGS).fetch_board("no-slashes")
