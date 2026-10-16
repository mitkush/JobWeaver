"""Workday career sites through their public "cxs" JSON endpoints, snapshot mode.

Off by default (FR-B1): this is the endpoint Workday's own career pages call, not a
published API, so it can change without notice. A board's slug is "tenant/wdN/site"."""

import asyncio
from typing import Any

from app.adapters.base import (
    FetchResult,
    NormalizedPosting,
    SnapshotSourceAdapter,
    bounded_gather,
)
from app.adapters.errors import BoardNotFound, SourceBadResponse
from app.adapters.normalize import (
    company_from_slug,
    extract_contact_email,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter

# Workday silently returns nothing for larger pages, and stops listing after about 2,000.
PAGE = 20
MAX_LISTED = 2000
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BACKOFF_SECONDS = 1.0
RATE_LIMIT_MAX_WAIT_SECONDS = 30.0


def split_slug(slug: str) -> tuple[str, str, str]:
    tenant, pod, site = slug.split("/", 2)
    return tenant, pod, site


@register_adapter
class WorkdayAdapter(SnapshotSourceAdapter):
    name = "workday"
    label = "Workday"
    priority = 9
    ats = "workday"
    default_enabled = False
    disabled_reason = (
        "Reads the JSON behind Workday career pages, which is not a published API and "
        "lists at most about 2,000 jobs per company. Turn it on if the boards you need "
        "fetch cleanly."
    )
    detail_concurrency = 4

    def __init__(self, http, settings, sleep=asyncio.sleep) -> None:
        super().__init__(http, settings)
        self.sleep = sleep

    async def fetch_board(self, slug: str) -> FetchResult:
        try:
            tenant, pod, site = split_slug(slug)
        except ValueError as exc:
            raise BoardNotFound(f"{slug!r} is not a Workday board reference") from exc
        base = f"https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
        listed: list[dict[str, Any]] = []
        total = None
        while len(listed) < MAX_LISTED:
            response = await self._request(
                "POST",
                f"{base}/jobs",
                json={"appliedFacets": {}, "limit": PAGE, "offset": len(listed), "searchText": ""},
                headers={"Accept": "application/json"},
            )
            if response.status_code in (404, 422):
                raise BoardNotFound(f"Workday has no career site at {slug!r}")
            self.check_response(self.label, response)
            body = response.json()
            page = body.get("jobPostings") if isinstance(body, dict) else None
            if not isinstance(page, list):
                raise SourceBadResponse("Workday returned an unexpected response")
            # Only the first page reports the total.
            total = total if total is not None else int(body.get("total") or 0)
            listed.extend(p for p in page if isinstance(p, dict) and p.get("externalPath"))
            if len(page) < PAGE:
                break
        details = await bounded_gather(
            (self._detail(base, p["externalPath"]) for p in listed), self.detail_concurrency
        )
        company = company_from_slug(tenant)
        postings = [
            self._to_posting(p, d, tenant, pod, site, company)
            for p, d in zip(listed, details, strict=True)
        ]
        # Past Workday's listing cap the snapshot is partial: nothing is closed from it.
        return FetchResult(postings=postings, complete=(total or 0) <= len(listed))

    async def _detail(self, base: str, path: str) -> dict[str, Any]:
        response = await self._request(
            "GET", f"{base}{path}", headers={"Accept": "application/json"}
        )
        if response.status_code == 404:
            return {}
        self.check_response(self.label, response)
        body = response.json()
        return body if isinstance(body, dict) else {}

    async def _request(self, method: str, url: str, **kwargs):
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            response = await self.http.request(method, url, **kwargs)
            if response.status_code != 429 or attempt == RATE_LIMIT_RETRIES:
                return response
            try:
                delay = float(response.headers.get("Retry-After", ""))
            except ValueError:
                delay = RATE_LIMIT_BACKOFF_SECONDS * (2**attempt)
            delay = min(max(delay, RATE_LIMIT_BACKOFF_SECONDS), RATE_LIMIT_MAX_WAIT_SECONDS)
            await self.sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def _to_posting(
        listed: dict[str, Any],
        detail: dict[str, Any],
        tenant: str,
        pod: str,
        site: str,
        company: str,
    ) -> NormalizedPosting:
        info = detail.get("jobPostingInfo") or {}
        org = (detail.get("hiringOrganization") or {}).get("name")
        places = [info.get("location") or listed.get("locationsText") or ""]
        places += [p for p in info.get("additionalLocations") or [] if isinstance(p, str)]
        description = html_to_text(info.get("jobDescription"))
        path = listed["externalPath"]
        return NormalizedPosting(
            source_job_id=str(info.get("jobReqId") or path),
            title=info.get("title") or listed.get("title") or "Untitled",
            company=org or company,
            description=description,
            locations=[parse_location(p) for p in places if p],
            work_mode=work_mode_from(str(info.get("remoteType") or "") or places[0]),
            apply_url=info.get("externalUrl")
            or f"https://{tenant}.{pod}.myworkdayjobs.com/{site}{path}",
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(info.get("startDate") or listed.get("postedOn")),
        )
