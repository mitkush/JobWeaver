"""JSearch on RapidAPI: Google for Jobs, Indeed, Glassdoor and more (COSTS.md: 200/month)."""

from datetime import UTC, datetime
from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    Location,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import SourceBadResponse, SourceError
from app.adapters.normalize import (
    country_code,
    country_display,
    extract_contact_email,
    html_to_text,
    normalize_city,
    parse_datetime,
    work_mode_from,
)
from app.adapters.registry import register_adapter

HOST = "jsearch.p.rapidapi.com"


def date_posted_for(window: FetchWindow) -> str:
    for days, value in ((1, "today"), (3, "3days"), (7, "week"), (31, "month")):
        if window.within_days(days):
            return value
    return "all"


@register_adapter
class JSearchAdapter(WindowedSourceAdapter):
    name = "jsearch"
    default_enabled = False
    label = "JSearch"
    priority = 5
    monthly_allowance = 200
    allowance_unit = "requests"

    def is_configured(self) -> bool:
        return bool(self.settings.rapidapi_key)

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        loc = query.location
        where = ""
        if loc and (loc.city or loc.country):
            where = " in " + ", ".join(
                x for x in (loc.city, country_display(loc.country) if loc.country else None) if x
            )
        params = {
            "query": f"{query.keywords}{where}",
            "page": "1",
            "num_pages": "1",
            "date_posted": date_posted_for(window),
        }
        if loc and loc.country:
            params["country"] = loc.country.lower()
        if loc and loc.remote:
            params["work_from_home"] = "true"
        response = await self.http.get(
            f"https://{HOST}/search-v2",
            params=params,
            headers={"X-RapidAPI-Key": self.settings.rapidapi_key, "X-RapidAPI-Host": HOST},
        )
        try:
            self.check_response(self.label, response)
            body = response.json()
        except SourceError as exc:
            # A request that reached RapidAPI counts against the monthly quota; a 429
            # (rate limit or quota already used up) does not.
            exc.credits_used = 0 if response.status_code == 429 else 1
            raise
        except ValueError as exc:
            raise SourceBadResponse(
                "JSearch returned data JobWeaver could not read", credits_used=1
            ) from exc
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, dict):
            data = data.get("jobs")
        if not isinstance(data, list):
            raise SourceBadResponse("JSearch returned an unexpected response", credits_used=1)
        postings = [p for job in data if (p := self._to_posting(job)) is not None]
        return FetchResult(postings=postings, credits_used=1)

    def _to_posting(self, job: dict[str, Any]) -> NormalizedPosting | None:
        if not (job.get("job_id") and job.get("job_title") and job.get("employer_name")):
            return None
        remote = bool(job.get("job_is_remote"))
        location = Location(
            city=normalize_city(job.get("job_city")),
            country=country_code(job.get("job_country")),
            remote=remote,
        )
        description = html_to_text(job.get("job_description") or "")
        posted = parse_datetime(job.get("job_posted_at_datetime_utc"))
        if posted is None and job.get("job_posted_at_timestamp"):
            posted = datetime.fromtimestamp(int(job["job_posted_at_timestamp"]), UTC)
        return NormalizedPosting(
            source_job_id=str(job["job_id"]),
            title=job["job_title"],
            company=job["employer_name"],
            description=description,
            locations=[location] if (location.city or location.country or remote) else [],
            work_mode=work_mode_from(description[:500], remote_flag=remote),
            apply_url=job.get("job_apply_link") or job.get("job_google_link"),
            contact_email=extract_contact_email(description),
            posted_at=posted,
        )
