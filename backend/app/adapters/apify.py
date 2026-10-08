"""Shared plumbing for Sources fetched through Apify actors (COSTS.md 1b and 2).

Start a run, wait for it, read its dataset. Spend is the run's reported cost in US cents,
counted against one Apify allowance shared by every Apify Source (budget_pool)."""

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.adapters.apify_balances import apify_account_balance
from app.adapters.base import FetchResult, FetchWindow, SourceQuery, WindowedSourceAdapter
from app.adapters.errors import (
    SourceBadResponse,
    SourceError,
    SourceQuotaRejected,
    SourceUnavailable,
    quota_rejected,
)
from app.core.config import Settings
from app.schemas.account_balances import AccountBalance

logger = logging.getLogger(__name__)

API = "https://api.apify.com/v2"
DATASET_PAGE = 1000
_FAILED = {"FAILED", "ABORTED", "TIMED-OUT"}
_DONE = {"SUCCEEDED", *_FAILED}


def cents(run: dict[str, Any]) -> int:
    # Unverified against a live run: usageTotalUsd is assumed to include result charges.
    usd = run.get("usageTotalUsd") or 0
    try:
        return math.ceil(float(usd) * 100)
    except (TypeError, ValueError):
        return 0


class ApifyAdapter(WindowedSourceAdapter):
    credential_settings = ("apify_token", "apify_tokens")
    account_balance_required = True
    budget_pool = "apify"
    monthly_allowance = 500  # $5.00 of platform usage
    allowance_unit = "US cents"
    poll_seconds = 60  # Apify holds each poll open up to this long
    retry_seconds = 5.0
    settle_seconds = 10.0
    run_timeout = timedelta(minutes=20)

    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        super().__init__(http, settings)
        self.sleep = sleep
        self._last_run: dict[str, Any] | None = None
        # Settled cost per run id: the fetcher reuses one adapter for every query.
        self._settled: dict[str, int] = {}
        self.monotonic: Callable[[], float] = time.monotonic

    async def account_balance(self, now: datetime, *, force: bool = False) -> AccountBalance | None:
        if not self.settings.apify_token:
            return None
        return await apify_account_balance(self.http, self.settings, now, force=force)

    def actor(self) -> str:
        raise NotImplementedError

    def actor_input(self, query: SourceQuery, window: FetchWindow) -> dict[str, Any] | None:
        """None skips the query (e.g. a country this Source does not cover)."""
        raise NotImplementedError

    def to_posting(self, record: dict[str, Any]):  # -> NormalizedPosting | None
        raise NotImplementedError

    def is_configured(self) -> bool:
        return bool(self.settings.apify_token or self.settings.apify_tokens)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.apify_token}"}

    async def fetch_window(self, query: SourceQuery | None, window: FetchWindow) -> FetchResult:
        self.ensure_configured()
        assert query is not None
        payload = self.actor_input(query, window)
        if payload is None:
            return FetchResult(postings=[])
        self._last_run = None  # never charge one search for another's run
        run = await self._wait(await self._start(payload))
        try:
            records = await self._items(str(run.get("defaultDatasetId") or ""))
            postings = [p for r in records if (p := self.to_posting(r)) is not None]
        except Exception as exc:
            # The run finished and is billed whatever happens to its results (FR-B5).
            raise self._billed(exc, await self._final_cost(run)) from exc
        return FetchResult(postings=postings, credits_used=await self._final_cost(run))

    def _billed(self, exc: Exception, spent: int) -> SourceError:
        """Any failure after a run started, as a SourceError that still carries its cost:
        the fetcher's generic handler would otherwise record the run as free."""
        if isinstance(exc, SourceError):
            error = exc
        elif isinstance(exc, httpx.TimeoutException):
            error = SourceUnavailable(f"{self.label} timed out")
        elif isinstance(exc, httpx.HTTPError):
            error = SourceUnavailable(f"{self.label} could not be reached ({type(exc).__name__})")
        elif isinstance(exc, ValueError | KeyError | TypeError):
            error = SourceBadResponse(f"{self.label} returned data JobWeaver could not read")
        else:
            logger.exception("Unexpected error after an Apify run of %s", self.label)
            error = SourceBadResponse(f"{self.label} failed unexpectedly; see the server logs")
        error.credits_used = max(error.credits_used, spent)
        return error

    async def _final_cost(self, run: dict[str, Any]) -> int:
        """Apify may report a just-finished run's cost as preliminary and asks callers to
        read it again about 10 seconds later. The larger of the two is kept, so the shared
        allowance never reads low. Read once per run id."""
        run_id = str(run["id"])
        if run_id in self._settled:
            return self._settled[run_id]
        preliminary = cents(run)
        final = preliminary
        await self.sleep(self.settle_seconds)
        try:
            response = await self.http.get(f"{API}/actor-runs/{run['id']}", headers=self._headers)
            self.check_response(self.label, response)
            final = cents(response.json().get("data") or {})
        except Exception:  # noqa: BLE001 - the preliminary cost still stands
            logger.warning("Could not read the final cost of %s run %s", self.label, run["id"])
        self._settled[run_id] = max(preliminary, final)
        return self._settled[run_id]

    async def _start(self, payload: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {"timeout": int(self.run_timeout.total_seconds())}
        if self.allowance_left is not None:
            # Apify stops the run at this charge, so one search cannot overrun the budget.
            params["maxTotalChargeUsd"] = f"{max(self.allowance_left, 1) / 100:.2f}"
        response = await self.http.post(
            f"{API}/acts/{self.actor()}/runs", params=params, headers=self._headers, json=payload
        )
        if quota_rejected(response):
            raise SourceQuotaRejected(
                f"{self.label} account credits exhausted before search started"
            )
        self.check_response(self.label, response)
        run = response.json().get("data")
        if not isinstance(run, dict) or not run.get("id"):
            raise SourceBadResponse(f"{self.label}: Apify did not return a run id")
        return run

    async def _wait(self, run: dict[str, Any]) -> dict[str, Any]:
        """Polls until the run ends. A failure still reports what the run cost."""
        try:
            return await self._poll(run)
        except Exception as exc:
            raise self._billed(exc, await self._final_cost(self._last_run or run)) from exc

    async def _poll(self, run: dict[str, Any]) -> dict[str, Any]:
        self._last_run = run
        deadline = self.monotonic() + self.run_timeout.total_seconds()
        while str(run.get("status")) not in _DONE:
            if self.monotonic() >= deadline:
                # Stop the run so it does not keep spending the shared allowance.
                await self.http.post(f"{API}/actor-runs/{run['id']}/abort", headers=self._headers)
                raise SourceUnavailable(f"{self.label} took too long; retried next run")
            response = await self.http.get(
                f"{API}/actor-runs/{run['id']}",
                params={"waitForFinish": self.poll_seconds},
                headers=self._headers,
            )
            self.check_response(self.label, response)
            run = response.json().get("data") or run
            self._last_run = run
            if str(run.get("status")) not in _DONE:
                await self.sleep(self.retry_seconds)
        if run.get("status") in _FAILED:
            message = run.get("statusMessage") or str(run["status"]).lower()
            raise SourceUnavailable(f"{self.label}: the Apify run failed ({message})")
        return run

    async def _items(self, dataset_id: str) -> list[dict[str, Any]]:
        if not dataset_id:
            raise SourceBadResponse(f"{self.label}: Apify run has no dataset")
        items: list[dict[str, Any]] = []
        while True:
            response = await self.http.get(
                f"{API}/datasets/{dataset_id}/items",
                params={
                    "format": "json",
                    "clean": "true",
                    "offset": len(items),
                    "limit": DATASET_PAGE,
                },  # fmt: skip
                headers=self._headers,
            )
            self.check_response(self.label, response)
            page = response.json()
            if not isinstance(page, list):
                raise SourceBadResponse(f"{self.label} returned an unexpected dataset")
            items.extend(r for r in page if isinstance(r, dict))
            if len(page) < DATASET_PAGE:
                return items
