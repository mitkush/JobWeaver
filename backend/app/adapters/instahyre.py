"""Instahyre through the JSON search its own site calls.

Off by default (FR-B1): not a published API, could not be reached from the build
environment to verify, and its list has no posting dates or full descriptions, so
everything it returns is treated as new and the window cannot narrow it."""

from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import SourceBadResponse
from app.adapters.normalize import first, parse_location, work_mode_from
from app.adapters.registry import register_adapter

API = "https://www.instahyre.com/api/v1/job_search"


@register_adapter
class InstahyreAdapter(WindowedSourceAdapter):
    name = "instahyre"
    label = "Instahyre (site fetch)"
    priority = 10
    default_enabled = False
    disabled_reason = (
        "Reads the search JSON behind instahyre.com, which is not a published API and "
        "could not be checked from the build environment. Its results have no posting "
        "dates or full descriptions. Turn it on and use Run now to see whether it works."
    )

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        assert query is not None
        loc = query.location
        if loc and loc.country and loc.country != "IN":
            return FetchResult(postings=[])
        params: dict[str, Any] = {"search": "true", "job_type": 0, "skills": query.keywords}
        if loc and loc.city and not loc.remote:
            params["location"] = loc.city
        if loc and loc.remote:
            params["location"] = "Work From Home"
        response = await self.http.get(API, params=params, headers={"Accept": "application/json"})
        self.check_response(self.label, response)
        body = response.json()
        objects = body.get("objects") if isinstance(body, dict) else None
        if not isinstance(objects, list):
            raise SourceBadResponse("Instahyre returned an unexpected response")
        postings = [p for job in objects if (p := self._to_posting(job)) is not None]
        return FetchResult(postings=postings, credits_used=1)

    @staticmethod
    def _to_posting(job: dict[str, Any]) -> NormalizedPosting | None:
        employer = job.get("employer") if isinstance(job.get("employer"), dict) else {}
        title = first(job, "candidate_title", "title")
        company = first(employer, "company_name", "name")
        if not (job.get("id") and title and company):
            return None
        places = str(first(job, "locations", "location") or "")
        keywords = job.get("keywords") if isinstance(job.get("keywords"), list) else []
        return NormalizedPosting(
            source_job_id=str(job["id"]),
            title=str(title),
            company=str(company),
            # Only the role's listed keywords; the full advert is on Instahyre.
            description=", ".join(str(k) for k in keywords),
            locations=[
                parse_location(p, default_country="IN") for p in places.split(",") if p.strip()
            ],
            work_mode=work_mode_from(places),
            apply_url=first(job, "public_url", "url"),
        )
