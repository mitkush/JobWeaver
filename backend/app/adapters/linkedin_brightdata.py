"""LinkedIn via Bright Data "Discover jobs by keyword" (ADR-0009).

Field names follow Bright Data's LinkedIn job listings dataset; alternatives are accepted
because the exact names could not be checked against a live response when this was written.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
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
    SourceQuotaRejected,
    SourceUnavailable,
    quota_rejected,
)
from app.adapters.normalize import (
    country_display,
    extract_contact_email,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter
from app.core.config import Settings
from app.schemas.account_balances import AccountBalance

API = "https://api.brightdata.com/datasets/v3"


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return None


def time_range_for(window: FetchWindow) -> str:
    """Smallest LinkedIn filter that reaches back to the window start (FR-B3 AC1)."""
    if window.within_days(1):
        return "Past 24 hours"
    if window.within_days(7):
        return "Past week"
    if window.within_days(31):
        return "Past month"
    return "Any time"


@register_adapter
class LinkedInBrightDataAdapter(WindowedSourceAdapter):
    credential_settings = ("brightdata_api_key", "brightdata_api_keys")
    credential_limits_from_errors = True
    primary_credential_pause_setting = "brightdata_primary_paused_until"
    name = "linkedin"
    label = "LinkedIn (Bright Data)"
    site = "LinkedIn"
    priority = 1
    monthly_allowance = 5000
    allowance_unit = "credits"
    renewal_day = 1
    poll_interval_seconds = 10.0
    poll_timeout = timedelta(minutes=15)

    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        super().__init__(http, settings)
        self.sleep = sleep

    async def account_balance(self, now: datetime, *, force: bool = False) -> AccountBalance:
        return AccountBalance(
            status="unsupported",
            unit="credits",
            message="Bright Data does not expose free-credit balances through its API. "
            "Account allowance and remaining credits are unknown. Check its Free credits card; "
            "JobWeaver's tracked count excludes other usage.",
        )

    def is_configured(self) -> bool:
        return bool(self.settings.brightdata_api_key or self.settings.brightdata_api_keys)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.brightdata_api_key}"}

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        snapshot_id = await self._trigger(query, window)
        records = await self._wait_and_download(snapshot_id)
        postings = [p for r in records if (p := self._to_posting(r)) is not None]
        # Bright Data charges one credit per record delivered, even ones JobWeaver cannot use.
        return FetchResult(postings=postings, credits_used=len(records))

    async def _trigger(self, query: SourceQuery, window: FetchWindow) -> str:
        loc = query.location
        location = ""
        if loc and (loc.city or loc.country):
            country = country_display(loc.country) if loc.country else ""
            location = ", ".join(x for x in (loc.city, country) if x)
        payload = [
            {
                "keyword": query.keywords,
                "location": location or "Worldwide",
                "country": (loc.country or "") if loc else "",
                "time_range": time_range_for(window),
                "job_type": "",
                "experience_level": "",
                "remote": "Remote" if loc and loc.remote else "",
                "company": "",
            }
        ]
        response = await self.http.post(
            f"{API}/trigger",
            params={
                "dataset_id": self.settings.brightdata_linkedin_dataset_id,
                "type": "discover_new",
                "discover_by": "keyword",
                "include_errors": "true",
            },
            headers=self._headers,
            json=payload,
        )
        if quota_rejected(response) or response.status_code == 429:
            reason = "rate limit reached" if response.status_code == 429 else "credits exhausted"
            raise SourceQuotaRejected(f"{self.label} account {reason} before search started")
        self.check_response(self.label, response)
        snapshot_id = response.json().get("snapshot_id")
        if not snapshot_id:
            raise SourceBadResponse("Bright Data did not return a snapshot id")
        return str(snapshot_id)

    async def _wait_and_download(self, snapshot_id: str) -> list[dict[str, Any]]:
        waited = 0.0
        while waited <= self.poll_timeout.total_seconds():
            progress = await self.http.get(f"{API}/progress/{snapshot_id}", headers=self._headers)
            self.check_response(self.label, progress)
            status = str(progress.json().get("status", "")).lower()
            if status == "ready":
                break
            if status == "failed":
                raise SourceUnavailable("Bright Data could not finish the LinkedIn search")
            await self.sleep(self.poll_interval_seconds)
            waited += self.poll_interval_seconds
        else:
            raise SourceUnavailable("Bright Data took too long; the search is retried next run")

        response = await self.http.get(
            f"{API}/snapshot/{snapshot_id}", params={"format": "json"}, headers=self._headers
        )
        self.check_response(self.label, response)
        try:
            data = response.json()
        except ValueError as exc:
            raise SourceBadResponse(
                "Bright Data returned a snapshot JobWeaver could not read"
            ) from exc
        if not isinstance(data, list):
            raise SourceBadResponse("Bright Data returned an unexpected snapshot format")
        return [r for r in data if isinstance(r, dict) and not r.get("error")]

    def _to_posting(self, record: dict[str, Any]) -> NormalizedPosting | None:
        job_id = _first(record, "job_posting_id", "job_id", "id")
        title = _first(record, "job_title", "title")
        company = _first(record, "company_name", "company")
        if not (job_id and title and company):
            return None
        description = html_to_text(
            _first(record, "job_description_formatted", "job_summary", "description") or ""
        )
        location_text = _first(record, "job_location", "location")
        work_text = " ".join(
            str(v)
            for v in (_first(record, "job_work_type", "workplace_type", "remote"), location_text)
            if v
        )
        return NormalizedPosting(
            source_job_id=str(job_id),
            title=str(title),
            company=str(company),
            description=description,
            locations=[parse_location(location_text)] if location_text else [],
            work_mode=work_mode_from(work_text),
            apply_url=_first(record, "apply_link", "job_apply_link", "url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(
                _first(record, "job_posted_date", "job_posted_time", "posted_date")
            ),
        )
