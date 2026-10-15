"""LinkedIn job search through Piloterr's independent third-party API."""

from typing import Any

import httpx

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import (
    SourceBadResponse,
    SourceQuotaExhausted,
    SourceRateLimited,
    SourceUnavailable,
)
from app.adapters.normalize import (
    extract_contact_email,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter

API = "https://api.piloterr.com/v2/linkedin/job/search"


@register_adapter
class LinkedInPiloterrAdapter(WindowedSourceAdapter):
    """Opt-in Piloterr source, kept separate from LinkedIn's existing providers.

    Piloterr documents one credit per successful page, up to 25 jobs per page. Search
    cards may not include descriptions or direct apply links, so these stay optional.
    """

    credential_settings = None
    name = "linkedin-piloterr"
    label = "LinkedIn (Piloterr)"
    site = "LinkedIn"
    priority = 20
    standby_for = "linkedin-apify"
    default_enabled = False
    disabled_reason = "Unofficial third-party LinkedIn data provider; enable only after testing."
    monthly_allowance = 500
    allowance_unit = "credits"

    def is_configured(self) -> bool:
        return bool(self.settings.piloterr_api_key)

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        location = query.location
        params: dict[str, Any] = {"keyword": query.keywords, "page": 1}
        if window.within_days(1):
            params["when"] = "day"
        elif window.within_days(7):
            params["when"] = "week"
        elif window.within_days(30):
            params["when"] = "month"
        if location:
            geo_ids = self.settings.piloterr_linkedin_geo_ids
            geo_id = geo_ids.get(location.city or "") or geo_ids.get(location.country or "")
            if geo_id:
                params["geo_id"] = geo_id
            if location.remote:
                params["flexibility"] = "remote"

        postings: list[NormalizedPosting] = []
        spent = 0
        configured_pages = max(1, self.settings.piloterr_linkedin_pages_per_query)
        page_limit = (
            min(configured_pages, self.allowance_left)
            if self.allowance_left is not None
            else configured_pages
        )
        if page_limit <= 0:
            raise SourceQuotaExhausted(f"{self.label} local credit allowance is exhausted")
        for page in range(1, page_limit + 1):
            params["page"] = page
            try:
                response = await self.http.get(
                    API,
                    params=params,
                    headers={"x-api-key": self.settings.piloterr_api_key},
                )
            except httpx.TimeoutException as exc:
                raise SourceUnavailable(
                    f"{self.label} request timed out", credits_used=spent
                ) from exc
            except httpx.HTTPError as exc:
                raise SourceUnavailable(
                    f"{self.label} could not be reached", credits_used=spent
                ) from exc

            if response.status_code == 402:
                raise SourceQuotaExhausted(
                    f"{self.label} credits are exhausted", credits_used=spent
                )
            if response.status_code == 429:
                raise SourceRateLimited(f"{self.label} rate limit reached", credits_used=spent)
            try:
                self.check_response(self.label, response)
                body = response.json()
            except ValueError as exc:
                raise SourceBadResponse(
                    f"{self.label} returned unreadable data", credits_used=spent + 1
                ) from exc
            spent += 1  # Piloterr bills successful HTTP 200 responses by page.
            records = (
                body
                if isinstance(body, list)
                else (body.get("results") if isinstance(body, dict) else None)
            )
            if not isinstance(records, list):
                raise SourceBadResponse(
                    f"{self.label} returned an unexpected response", credits_used=spent
                )
            postings.extend(
                p
                for record in records
                if isinstance(record, dict)
                if (p := self.to_posting(record))
            )
            if len(records) < 25:
                break
        return FetchResult(postings=postings, credits_used=spent)

    @staticmethod
    def to_posting(record: dict[str, Any]) -> NormalizedPosting | None:
        job_id = record.get("id") or record.get("job_id")
        title = record.get("title")
        company = record.get("company_name") or record.get("company")
        if not (job_id and title and company):
            return None
        description = html_to_text(record.get("description") or record.get("job_description") or "")
        if not description:
            return None
        location = record.get("location")
        return NormalizedPosting(
            source_job_id=str(job_id),
            title=str(title),
            company=str(company),
            description=description,
            locations=[parse_location(location)] if location else [],
            work_mode=work_mode_from(
                record.get("flexibility") or record.get("workplace_type") or ""
            ),
            apply_url=record.get("url") or record.get("job_url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(record.get("list_date") or record.get("posted_at")),
        )
