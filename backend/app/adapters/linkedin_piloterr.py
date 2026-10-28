"""LinkedIn job search through Piloterr's independent third-party API."""

from datetime import datetime
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
    SourceError,
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
INFO_API = "https://api.piloterr.com/v2/linkedin/job/info"
PAGE_SIZE = 25


@register_adapter
class LinkedInPiloterrAdapter(WindowedSourceAdapter):
    """Opt-in Piloterr source, kept separate from LinkedIn's existing providers.

    Search cards omit descriptions. Each search page and each missing job detail costs
    one credit; known usable jobs skip the detail purchase. Incomplete windows retry.
    """

    credential_settings = None
    name = "linkedin-piloterr"
    label = "LinkedIn (Piloterr)"
    site = "LinkedIn"
    priority = 20
    standby_for = "linkedin-apify"
    default_enabled = False
    retry_incomplete_window = True
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
        seen: set[str] = set()
        spent = 0
        allowance = (
            self.allowance_left if self.allowance_left is not None else self.monthly_allowance
        )
        page_limit = max(1, self.settings.piloterr_linkedin_pages_per_query)
        if allowance <= 0:
            raise SourceQuotaExhausted(f"{self.label} local credit allowance is exhausted")
        complete = True
        try:
            for page in range(1, page_limit + 1):
                if spent >= allowance:
                    return FetchResult(postings=postings, credits_used=spent, complete=False)
                body = await self._request(API, {**params, "page": page}, spent)
                spent += 1
                records = (
                    body
                    if isinstance(body, list)
                    else body.get("results")
                    if isinstance(body, dict)
                    else None
                )
                if not isinstance(records, list) or any(
                    not isinstance(row, dict) for row in records
                ):
                    raise SourceBadResponse(
                        f"{self.label} returned unexpected listings", credits_used=spent
                    )
                ids = {
                    str(row.get("id") or row.get("job_id"))
                    for row in records
                    if row.get("id") or row.get("job_id")
                }
                try:
                    known = await self.known_postings(ids) if self.known_postings else set()
                except Exception as exc:
                    raise SourceUnavailable(
                        f"{self.label} could not check existing jobs", credits_used=spent
                    ) from exc
                for record in records:
                    job_id = str(record.get("id") or record.get("job_id") or "")
                    if not job_id:
                        raise SourceBadResponse(
                            f"{self.label} listing is missing a job ID", credits_used=spent
                        )
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    posted = parse_datetime(
                        record.get("list_date") or record.get("posted_at"), now=window.until
                    )
                    if posted and posted.date() < window.since.date():
                        continue
                    description = record.get("description") or record.get("job_description")
                    if not isinstance(description, str) or not html_to_text(description):
                        if job_id in known:
                            continue
                        if spent >= allowance:
                            return FetchResult(
                                postings=postings, credits_used=spent, complete=False
                            )
                        detail = await self._request(INFO_API, {"query": job_id}, spent)
                        spent += 1
                        if (
                            not isinstance(detail, dict)
                            or str(detail.get("id") or detail.get("job_id") or job_id) != job_id
                        ):
                            raise SourceBadResponse(
                                f"{self.label} returned unexpected job details", credits_used=spent
                            )
                        record = {**record, **detail}
                    posting = self.to_posting(record, window.until)
                    if posting is None:
                        complete = False
                        continue
                    postings.append(posting)
                if len(records) < PAGE_SIZE:
                    return FetchResult(postings=postings, credits_used=spent, complete=complete)
            # A full final page may have more results: keep the watermark for retry.
            return FetchResult(postings=postings, credits_used=spent, complete=False)
        except SourceError as exc:
            if not postings:
                raise
            return FetchResult(postings=postings, credits_used=exc.credits_used, complete=False)

    async def _request(self, url: str, params: dict[str, Any], spent: int) -> Any:
        try:
            response = await self.http.get(
                url, params=params, headers={"x-api-key": self.settings.piloterr_api_key}
            )
        except httpx.TimeoutException as exc:
            raise SourceUnavailable(f"{self.label} timed out", credits_used=spent) from exc
        except httpx.HTTPError as exc:
            raise SourceUnavailable(
                f"{self.label} could not be reached", credits_used=spent
            ) from exc
        if response.status_code == 402:
            raise SourceQuotaExhausted(f"{self.label} credits are exhausted", credits_used=spent)
        if response.status_code == 429:
            raise SourceRateLimited(f"{self.label} rate limit reached", credits_used=spent)
        try:
            self.check_response(self.label, response)
        except SourceError as exc:
            exc.credits_used = spent
            raise
        try:
            return response.json()
        except ValueError as exc:
            raise SourceBadResponse(
                f"{self.label} returned unreadable data", credits_used=spent + 1
            ) from exc

    @staticmethod
    def to_posting(record: dict[str, Any], now: datetime | None = None) -> NormalizedPosting | None:
        job_id = record.get("id") or record.get("job_id")
        title = record.get("title")
        company = record.get("company_name") or record.get("company")
        if not (job_id and title and company):
            return None
        raw_description = record.get("description") or record.get("job_description") or ""
        if not isinstance(raw_description, str):
            return None
        description = html_to_text(raw_description)
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
            posted_at=parse_datetime(record.get("list_date") or record.get("posted_at"), now=now),
        )
