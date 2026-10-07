"""SerpApi Google Jobs: standby for JSearch (ADR-0016, COSTS.md: 250/month).

Both read Google for Jobs, so SerpApi runs only while JSearch is Degraded or disabled and
continues from JSearch's query watermarks. Each results page is one paid search."""

from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import SourceBadResponse, SourceError, SourceQuotaExhausted
from app.adapters.normalize import (
    country_display,
    extract_contact_email,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter

API = "https://serpapi.com/search.json"
_NO_RESULTS = "hasn't returned any results"


def date_chip_for(window: FetchWindow) -> str:
    for days, value in ((1, "today"), (3, "3days"), (7, "week")):
        if window.within_days(days):
            return f"date_posted:{value}"
    return "date_posted:month"


@register_adapter
class SerpApiAdapter(WindowedSourceAdapter):
    name = "serpapi"
    label = "SerpApi Google Jobs"
    priority = 6
    standby_for = "jsearch"
    monthly_allowance = 250
    allowance_unit = "searches"

    def is_configured(self) -> bool:
        return bool(self.settings.serpapi_key)

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        loc = query.location
        params: dict[str, str] = {
            "engine": "google_jobs",
            "q": f"{query.keywords} remote" if loc and loc.remote else query.keywords,
            "chips": date_chip_for(window),
            "hl": "en",
            "api_key": self.settings.serpapi_key,
        }
        if loc and (loc.city or loc.country):
            params["location"] = ", ".join(
                x for x in (loc.city, country_display(loc.country) if loc.country else None) if x
            )
        if loc and loc.country:
            params["gl"] = loc.country.lower()
        postings: list[NormalizedPosting] = []
        spent = 0
        for _ in range(max(self.settings.serpapi_pages_per_query, 1)):
            if self.allowance_left is not None and spent >= self.allowance_left:
                break  # each page is a paid search; stop at the monthly allowance
            body = await self._search(params, spent)
            spent += 1
            jobs = body.get("jobs_results") or []
            if not isinstance(jobs, list):
                raise SourceBadResponse(
                    "SerpApi returned an unexpected response", credits_used=spent
                )
            postings += [p for job in jobs if (p := self._to_posting(job)) is not None]
            token = (body.get("serpapi_pagination") or {}).get("next_page_token")
            if not token or not jobs:
                break
            params["next_page_token"] = token
        return FetchResult(postings=postings, credits_used=spent)

    async def _search(self, params: dict[str, str], spent: int) -> dict[str, Any]:
        response = await self.http.get(API, params=params)
        try:
            body = response.json()
        except ValueError:
            body = None
        error = str(body.get("error") or "") if isinstance(body, dict) else ""
        if _NO_RESULTS in error:
            # Counted, to be safe: the budget must never read low (FR-B5).
            return {"jobs_results": []}
        if "run out of searches" in error.lower():
            raise SourceQuotaExhausted("SerpApi free searches are used up", credits_used=spent)
        try:
            self.check_response(self.label, response)
        except SourceError as exc:
            exc.credits_used = spent  # errors are not billed
            raise
        if not isinstance(body, dict) or error:
            raise SourceBadResponse(
                f"SerpApi returned an error: {error[:120]}" if error else
                "SerpApi returned data JobWeaver could not read",
                credits_used=spent,
            )  # fmt: skip
        return body

    @staticmethod
    def _to_posting(job: dict[str, Any]) -> NormalizedPosting | None:
        if not (job.get("job_id") and job.get("title") and job.get("company_name")):
            return None
        extensions = job.get("detected_extensions") or {}
        remote = bool(extensions.get("work_from_home"))
        location = parse_location(job.get("location"))
        if remote:
            location = location.model_copy(update={"remote": True})
        description = str(job.get("description") or "")
        options = [o for o in job.get("apply_options") or [] if isinstance(o, dict)]
        return NormalizedPosting(
            source_job_id=str(job["job_id"])[:255],
            title=job["title"],
            company=job["company_name"],
            description=description,
            locations=[location] if (location.city or location.country or remote) else [],
            work_mode=work_mode_from(description[:500], remote_flag=remote),
            apply_url=(options[0].get("link") if options else None) or job.get("share_link"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(extensions.get("posted_at")),
        )
