"""LinkedIn via Bright Data "Discover jobs by keyword" (ADR-0009).

Field names follow Bright Data's LinkedIn job listings dataset and were checked against a
live response on 15 Oct 2026; the alternatives stay as a guard against renames.

With BRIGHTDATA_DISCOVERY_KEYWORDS set, the Source searches broad role keywords joined with
OR ("Software OR Developer OR Backend OR \"Full stack\"") once per Preference country,
instead of one search per title and city: LinkedIn honours OR in the keyword (verified on
15 Oct 2026), and the Feed's title, place and Core-keyword rules then pick each User's Jobs.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    Location,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import (
    SourceBadResponse,
    SourceCredentialRejected,
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


def _country(record: dict[str, Any]) -> str | None:
    code = _first(record, "country_code")
    return str(code).upper() if isinstance(code, str) and len(code) == 2 else None


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
    scheduled_window_hours = 24
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
    resumable_collections = True
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
            "JobWeaver's tracked count is an estimate only and excludes other usage. "
            "It does not pause searches or select credentials.",
        )

    def _discovery_terms(self) -> list[str]:
        """The configured keywords, cleaned, each once ignoring case (LinkedIn does)."""
        terms: dict[str, str] = {}
        for raw in self.settings.brightdata_discovery_keywords.split(","):
            term = raw.strip().strip('"').strip()
            if term:
                terms.setdefault(term.casefold(), term)
        return list(terms.values())

    def searches_titles(self) -> bool:
        return not self._discovery_terms()

    def continues_from(
        self, query: SourceQuery, preference_queries: list[SourceQuery]
    ) -> list[str]:
        """A discovery search replaces the per-title searches for its place: country-wide
        covers every title and city in that country, and worldwide remote covers remote
        searches with no country."""
        if not self._discovery_terms():
            return []
        place = query.location

        def covered(other: SourceQuery) -> bool:
            loc = other.location
            if place is not None and place.country:
                return loc is not None and loc.country == place.country
            if place is not None and place.remote:
                return loc is not None and loc.remote and not loc.country
            return False

        return [q.key for q in preference_queries if covered(q)]

    def search_queries(self, preference_queries: list[SourceQuery]) -> list[SourceQuery]:
        """One OR search per Preference country; cities, titles and work modes are left to
        the Feed. A remote search with no country becomes one worldwide remote search. A
        Preference with no place searches only remote work: on-site or hybrid jobs anywhere
        in the world are ones a User cannot attend, and would fill the cap with noise."""
        terms = self._discovery_terms()
        if not terms:
            return preference_queries
        keyword = " OR ".join(f'"{t}"' if " " in t else t for t in terms)
        queries: dict[SourceQuery, SourceQuery] = {}
        for query in preference_queries:
            loc = query.location
            if loc and loc.country:
                place = Location(country=loc.country)
            elif loc and loc.remote:
                place = Location(remote=True)
            else:
                continue
            search = SourceQuery(keywords=keyword, location=place)
            queries.setdefault(search, search)
        for country in self.settings.brightdata_discovery_countries.split(","):
            if country:
                search = SourceQuery(keywords=keyword, location=Location(country=country))
                queries.setdefault(search, search)
        return sorted(queries.values(), key=lambda q: q.key)

    def is_configured(self) -> bool:
        return bool(self.settings.brightdata_api_key or self.settings.brightdata_api_keys)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.brightdata_api_key}"}

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        snapshot_id = self.collection_id
        if snapshot_id is None:
            snapshot_id = await self._trigger(query, window)
            if self.checkpoint_collection is not None:
                await self.checkpoint_collection(snapshot_id)
        records = await self._wait_and_download(snapshot_id)
        postings = [p for r in records if (p := self._to_posting(r)) is not None]
        cap = self.settings.brightdata_limit_per_search
        # Bright Data charges one credit per record delivered, even ones JobWeaver cannot use.
        return FetchResult(
            postings=postings,
            credits_used=len(records),
            complete=not (cap > 0 and len(records) >= cap),
        )

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
        params: dict[str, str | int] = {
            "dataset_id": self.settings.brightdata_linkedin_dataset_id,
            "type": "discover_new",
            "discover_by": "keyword",
            "include_errors": "true",
        }
        if self.settings.brightdata_limit_per_search > 0:
            # Caps the records (and credits) one search can return.
            params["limit_per_input"] = self.settings.brightdata_limit_per_search
        for attempt in range(2):
            response = await self.http.post(
                f"{API}/trigger",
                params=params,
                headers=self._headers,
                json=payload,
            )
            # A temporary burst should not immediately consume every credential.
            if response.status_code == 429 and not quota_rejected(response) and attempt == 0:
                await self.sleep(3.0)
                continue
            break
        if response.status_code in (400, 403) and (
            response.text.strip().casefold() == "customer is not active"
        ):
            raise SourceCredentialRejected(f"{self.label} account is not active")
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
            if progress.status_code == 404:
                # The fetcher pins the original credential and forbids rotation once
                # a collection starts. Treat 404 as unavailable/expired only under that
                # invariant; a wrong-account 404 must never discard another account's id.
                if self.checkpoint_collection is not None:
                    await self.checkpoint_collection(None)
                raise SourceUnavailable(
                    "Bright Data collection expired; the next run starts a new search"
                )
            self.check_response(self.label, progress)
            status = str(progress.json().get("status", "")).lower()
            if status == "ready":
                break
            if status in ("failed", "canceled", "cancelled"):
                if self.checkpoint_collection is not None:
                    await self.checkpoint_collection(None)
                raise SourceUnavailable(
                    "Bright Data collection failed or was canceled; "
                    "the next run starts a new search"
                )
            await self.sleep(self.poll_interval_seconds)
            waited += self.poll_interval_seconds
        else:
            raise SourceUnavailable(
                "Bright Data is still collecting; the next run resumes the same collection"
            )

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
            # The record's own country code fills in a bare city such as "Indore".
            locations=[parse_location(location_text, default_country=_country(record))]
            if location_text
            else [],
            work_mode=work_mode_from(work_text),
            apply_url=_first(record, "apply_link", "job_apply_link", "url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(
                _first(record, "job_posted_date", "job_posted_time", "posted_date")
            ),
        )
