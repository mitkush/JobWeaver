"""Self-hosted JobSpy LinkedIn collection, opt-in and last in the fallback chain."""

import asyncio
import importlib.util
import json
import math
import sys
from typing import Any

from app.adapters.base import (
    FetchResult,
    FetchWindow,
    NormalizedPosting,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.errors import SourceBadResponse, SourceUnavailable
from app.adapters.normalize import (
    country_display,
    extract_contact_email,
    html_to_text,
    parse_datetime,
    parse_location,
    work_mode_from,
)
from app.adapters.registry import register_adapter


@register_adapter
class LinkedInJobSpyAdapter(WindowedSourceAdapter):
    name = "linkedin-jobspy"
    label = "LinkedIn (JobSpy)"
    site = "LinkedIn"
    priority = 22
    standby_for = "linkedin-scrapingdog"
    retry_incomplete_window = True
    default_enabled = False
    disabled_reason = (
        "Experimental self-hosted LinkedIn scraper; no API key, but LinkedIn may block requests."
    )

    def is_configured(self) -> bool:
        return importlib.util.find_spec("jobspy") is not None

    async def _collect(self, payload: dict[str, Any]) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.adapters.jobspy_worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(self.settings.jobspy_timeout_seconds):
                stdout, _ = await process.communicate(json.dumps(payload).encode())
        except TimeoutError as exc:
            raise SourceUnavailable(f"{self.label} timed out; search was stopped") from exc
        finally:
            # Cancellation and timeouts stop the worker, including its blocking requests.
            if process.returncode is None:
                process.kill()
                await process.wait()
        if process.returncode:
            raise SourceUnavailable(f"{self.label} worker exited before completing the search")
        try:
            result = json.loads(stdout)
        except (ValueError, UnicodeDecodeError) as exc:
            raise SourceBadResponse(f"{self.label} returned unreadable data") from exc
        if not isinstance(result, dict):
            raise SourceBadResponse(f"{self.label} returned unexpected data")
        return result

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        loc = query.location
        where = [loc.city, country_display(loc.country) if loc.country else None] if loc else []
        # JobSpy's LinkedIn implementation does not support is_remote. Preserve the
        # requested intent as a keyword; actual returned work modes are checked by Feed.
        keywords = query.keywords + (" remote" if loc and loc.remote else "")
        result = await self._collect(
            {
                "keywords": keywords,
                "location": ", ".join(part for part in where if part),
                "hours_old": max(1, math.ceil(window.hours)),
                "proxies": self.settings.jobspy_proxies,
            }
        )
        if result.get("error"):
            raise SourceUnavailable(f"{self.label} search was blocked or incomplete; retry later")
        rows = result.get("jobs")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise SourceBadResponse(f"{self.label} returned unexpected jobs")
        postings = []
        seen = set()
        for row in rows:
            posting = self.to_posting(row)
            if posting is None:
                # Missing details are often a block on the detail request. Do not turn
                # that into a successful search that loses the window across fallbacks.
                raise SourceUnavailable(f"{self.label} returned jobs without full details")
            if posting.source_job_id not in seen:
                seen.add(posting.source_job_id)
                postings.append(posting)
        return FetchResult(postings=postings, complete=len(rows) < 1000)

    @staticmethod
    def to_posting(row: dict[str, Any]) -> NormalizedPosting | None:
        job_id = str(row.get("id") or "").removeprefix("li-")
        description = html_to_text(row.get("description") or "")
        if not all((job_id, row.get("title"), row.get("company"), description)):
            return None
        location = row.get("location")
        mode = work_mode_from(str(location or ""))
        if row.get("is_remote") is True:
            mode = work_mode_from("remote")
        return NormalizedPosting(
            source_job_id=job_id,
            title=str(row["title"]),
            company=str(row["company"]),
            description=description,
            locations=[parse_location(location)] if location else [],
            work_mode=mode,
            apply_url=row.get("job_url_direct") or row.get("job_url"),
            contact_email=extract_contact_email(description),
            posted_at=parse_datetime(row.get("date_posted")),
        )
