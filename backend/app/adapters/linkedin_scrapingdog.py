"""Opt-in LinkedIn search and full job details through Scrapingdog's Jobs API."""

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
    SourceUnavailable,
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

API = "https://api.scrapingdog.com"
REQUEST_CREDITS = 5
PAGE_SIZE = 10  # Confirmed against a live search on 23 Oct 2026.
MAX_PAGES = 100  # LinkedIn's public search exposes about 1,000 results.


@register_adapter
class LinkedInScrapingdogAdapter(WindowedSourceAdapter):
    name = "linkedin-scrapingdog"
    label = "LinkedIn (Scrapingdog)"
    site = "LinkedIn"
    priority = 21
    standby_for = "linkedin-piloterr"
    retry_incomplete_window = True
    default_enabled = False
    disabled_reason = "Experimental LinkedIn provider; search and each job detail cost credits."
    monthly_allowance = 100
    allowance_unit = "credits"

    @classmethod
    def credit_allowance(cls, settings: Settings) -> int:
        return settings.scrapingdog_monthly_credits

    def is_configured(self) -> bool:
        return bool(self.settings.scrapingdog_api_key)

    async def _request(self, path: str, params: dict[str, Any], spent: int) -> Any:
        try:
            response = await self.http.get(
                f"{API}/{path}",
                params={**params, "api_key": self.settings.scrapingdog_api_key},
            )
        except httpx.HTTPError as exc:
            # Exception strings can contain the credential-bearing URL.
            raise SourceUnavailable(
                f"{self.label} could not be reached", credits_used=spent
            ) from exc
        try:
            self.check_response(self.label, response)
        except SourceError as exc:
            exc.credits_used = spent
            raise
        try:
            return response.json()
        except ValueError as exc:
            raise SourceBadResponse(
                f"{self.label} returned unreadable data",
                credits_used=spent + (REQUEST_CREDITS if path == "jobs" else 0),
            ) from exc

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        account = await self._request("account", {}, 0)
        try:
            # Check account-wide usage as well as the local safety ceiling. Bonus credits
            # are not assumed to renew when the local monthly ledger resets.
            limit, used = account["requestLimit"], account["requestUsed"]
            if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (limit, used)):
                raise ValueError
            available = max(limit - used, 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailable(f"{self.label} account credits could not be verified") from exc
        allowance = min(
            available,
            self.allowance_left
            if self.allowance_left is not None
            else self.credit_allowance(self.settings),
        )
        if allowance < REQUEST_CREDITS * 2:
            raise SourceQuotaExhausted(
                f"{self.label} needs credits for search and a full job detail"
            )

        params: dict[str, Any] = {"type": "listings", "field": query.keywords}
        for days, value in ((1, "day"), (7, "week"), (30, "month")):
            if window.within_days(days):
                params["sort_by"] = value
                break
        if query.location:
            loc = query.location
            where = [loc.city, country_display(loc.country) if loc.country else None]
            if any(where):
                params["location"] = ", ".join(part for part in where if part)
            if loc.remote:
                params["work_type"] = "remote"
        else:
            params["geoid"] = "92000000"

        postings: list[NormalizedPosting] = []
        seen: set[str] = set()
        spent = 0
        for page in range(1, MAX_PAGES + 1):
            if allowance - spent < REQUEST_CREDITS * 2:
                return FetchResult(postings=postings, credits_used=spent, complete=False)
            rows = await self._request("jobs", {**params, "page": page}, spent)
            spent += REQUEST_CREDITS
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise SourceBadResponse(
                    f"{self.label} returned unexpected listings", credits_used=spent
                )
            for row in rows:
                job_id = str(row.get("job_id") or "")
                if not job_id:
                    raise SourceBadResponse(
                        f"{self.label} listing is missing a job ID", credits_used=spent
                    )
                if job_id in seen:
                    continue
                seen.add(job_id)
                posted_at = parse_datetime(row.get("job_posting_date"), now=window.until)
                # Search dates are whole days; keep the boundary day for overlap safety.
                if posted_at and posted_at.date() < window.since.date():
                    continue
                if allowance - spent < REQUEST_CREDITS:
                    return FetchResult(postings=postings, credits_used=spent, complete=False)
                details = await self._request("jobs", {"job_id": job_id}, spent)
                spent += REQUEST_CREDITS
                if (
                    not isinstance(details, list)
                    or len(details) != 1
                    or not isinstance(details[0], dict)
                ):
                    raise SourceBadResponse(
                        f"{self.label} returned unexpected job details", credits_used=spent
                    )
                combined = {**row, **details[0]}
                if posting := self.to_posting(combined, window.until):
                    postings.append(posting)
                elif str(combined.get("jobs_status") or "").lower() not in {"closed", "expired"}:
                    raise SourceBadResponse(
                        f"{self.label} returned a job without full details", credits_used=spent
                    )
            if len(rows) < PAGE_SIZE:
                return FetchResult(postings=postings, credits_used=spent)
        return FetchResult(postings=postings, credits_used=spent, complete=False)

    @staticmethod
    def to_posting(row: dict[str, Any], now: datetime) -> NormalizedPosting | None:
        description = html_to_text(
            row.get("job_description") or row.get("job_description_html") or ""
        )
        if not all(
            (row.get("job_id"), row.get("job_position"), row.get("company_name"), description)
        ):
            return None
        if str(row.get("jobs_status") or "").lower() in {"closed", "expired"}:
            return None
        location = str(row.get("job_location") or "")
        return NormalizedPosting(
            source_job_id=str(row["job_id"]),
            title=str(row["job_position"]),
            company=str(row["company_name"]),
            description=description,
            locations=[parse_location(location)] if location else [],
            work_mode=work_mode_from(f"{location} {row['job_position']}"),
            apply_url=row.get("job_apply_link")
            or row.get("job_link")
            or f"https://www.linkedin.com/jobs/view/{row['job_id']}",
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(
                row.get("job_posting_date") or row.get("job_posting_time"), now=now
            ),
        )
