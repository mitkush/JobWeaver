"""Self-hosted JobSpy LinkedIn collection, opt-in and last in the fallback chain."""

import asyncio
import contextlib
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
from app.adapters.errors import SourceBadResponse
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
        "Experimental self-hosted LinkedIn scraper; requires the optional JobSpy package. "
        "No API key, but LinkedIn may block requests."
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
            limit=8 * 1024 * 1024,
        )
        result: dict[str, Any] = {"jobs": [], "error": False, "complete": False}
        try:
            async with asyncio.timeout(self.settings.jobspy_timeout_seconds):
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(json.dumps(payload).encode())
                await process.stdin.drain()
                process.stdin.close()
                while line := await process.stdout.readline():
                    frame = json.loads(line)
                    if not isinstance(frame, dict) or not isinstance(frame.get("jobs"), list):
                        raise ValueError("Invalid worker checkpoint")
                    result["jobs"].extend(frame["jobs"])
                    result["error"] = result["error"] or bool(frame.get("error"))
                    result["complete"] = bool(frame.get("complete"))
                await process.wait()
        except (TimeoutError, ValueError, UnicodeDecodeError, BrokenPipeError):
            # Even a hard timeout keeps every complete checkpoint already received.
            result["error"], result["complete"] = True, False
        finally:
            # Cancellation and timeouts stop the worker, including its blocking requests.
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
        if process.returncode:
            result["error"], result["complete"] = True, False
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
                "location": ", ".join(part for part in where if part) or "Worldwide",
                "hours_old": max(1, math.ceil(window.hours)),
                "proxies": self.settings.jobspy_proxies,
                "max_results": self.settings.jobspy_max_results,
                "time_budget": max(1, self.settings.jobspy_timeout_seconds - 5),
            }
        )
        rows = result.get("jobs")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise SourceBadResponse(f"{self.label} returned unexpected jobs")
        postings = []
        seen = set()
        complete = bool(result.get("complete")) and not result.get("error")
        for row in rows:
            posting = self.to_posting(row)
            if posting is None:
                # Keep the good rows, but leave the window open for the missed details.
                complete = False
                continue
            if posting.source_job_id not in seen:
                seen.add(posting.source_job_id)
                postings.append(posting)
        return FetchResult(postings=postings, complete=complete)

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
