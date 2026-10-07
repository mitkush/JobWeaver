"""Foundit (formerly Monster India) through the JSON search its own site calls.

Off by default (FR-B1): not a published API, could not be reached from the build
environment to verify, and may block cloud IPs. Field names follow other projects' code."""

from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import SourceBadResponse
from app.adapters.normalize import (
    extract_contact_email,
    first,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter

API = "https://www.foundit.in/middleware/jobsearch"
PAGE = 50


@register_adapter
class FounditAdapter(WindowedSourceAdapter):
    name = "foundit"
    label = "Foundit (site fetch)"
    priority = 10
    default_enabled = False
    disabled_reason = (
        "Reads the search JSON behind foundit.in, which is not a published API and could "
        "not be checked from the build environment. Turn it on and use Run now to see "
        "whether it works from your server."
    )

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        assert query is not None
        loc = query.location
        if loc and loc.country and loc.country != "IN":
            return FetchResult(postings=[])
        params: dict[str, Any] = {
            "query": query.keywords,
            "sort": 1,  # newest first
            "limit": PAGE,
            "start": 0,
            "jobFreshness": next(d for d in range(1, 10_000) if window.within_days(d)),
        }
        if loc and loc.city and not loc.remote:
            params["locations"] = loc.city
        if loc and loc.remote:
            params["query"] = f"{query.keywords} remote"
        response = await self.http.get(API, params=params, headers={"Accept": "application/json"})
        self.check_response(self.label, response)
        body = response.json()
        data = (body.get("jobSearchResponse") or {}).get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise SourceBadResponse("Foundit returned an unexpected response")
        postings = [p for job in data if (p := self._to_posting(job)) is not None]
        return FetchResult(postings=postings, credits_used=1)

    @staticmethod
    def _to_posting(job: dict[str, Any]) -> NormalizedPosting | None:
        job_id = first(job, "jobId", "id")
        title = first(job, "title", "jobTitle")
        company = first(job, "companyName", "company")
        if not (job_id and title and company):
            return None
        places = first(job, "locations", "location") or ""
        if isinstance(places, list):
            places = ",".join(str(p.get("city", p) if isinstance(p, dict) else p) for p in places)
        description = html_to_text(first(job, "description", "jobDescription") or "")
        url = first(job, "seoJdUrl", "jdUrl", "redirectUrl")
        if url and str(url).startswith("/"):
            url = f"https://www.foundit.in{url}"
        return NormalizedPosting(
            source_job_id=str(job_id),
            title=str(title),
            company=str(company),
            description=description,
            locations=[
                parse_location(p, default_country="IN") for p in str(places).split(",") if p.strip()
            ],
            work_mode=work_mode_from(f"{first(job, 'workMode') or ''} {places}"),
            apply_url=url,
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(first(job, "createdAt", "postedAt", "postedBy")),
        )
