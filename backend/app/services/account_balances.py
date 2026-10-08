"""Provider-reported allowance, separate from JobWeaver's historical spend ledger.

Bright Data does not expose its free-credit pool through the Account Management API.
Its dollar balance must never be converted into scraper credits.
"""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal

import httpx
from pydantic import BaseModel

from app.adapters.base import SourceAdapter
from app.core.config import Settings
from app.services.provider_credentials import credentials


class AccountCredit(BaseModel):
    label: str
    status: Literal["live", "unavailable", "unsupported"]
    allowance: int | None = None
    spent: int | None = None
    remaining: int | None = None
    renews_on: datetime | None = None


class AccountBalance(BaseModel):
    account_label: str = "Primary account"
    accounts: list[AccountCredit] = []
    status: Literal["live", "unavailable", "unsupported"]
    allowance: int | None = None
    spent: int | None = None
    remaining: int | None = None
    unit: str = "US cents"
    checked_at: datetime | None = None
    period_start: datetime | None = None
    renews_on: datetime | None = None
    message: str


# Keyed by the credential fingerprint: replacing the account never reuses its balance.
# No credentials, account details or provider error bodies are returned to the browser.
_cache: dict[str, tuple[datetime, AccountBalance]] = {}
_lock = asyncio.Lock()


def _amount(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Invalid amount")
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid amount")
    return amount


def _date(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Invalid cycle date")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Missing timezone")
    return result


async def account_balance(
    adapter: type[SourceAdapter],
    http: httpx.AsyncClient,
    settings: Settings,
    now: datetime | None = None,
    *,
    force: bool = False,
) -> AccountBalance | None:
    now = now or datetime.now(UTC)
    if adapter.name == "linkedin":
        return AccountBalance(
            status="unsupported",
            unit="credits",
            message="Bright Data does not expose free-credit balances through its API. "
            "Check the Free credits card in Bright Data; JobWeaver's count excludes other usage.",
        )
    if adapter.budget_pool != "apify" or not settings.apify_token:
        return None
    fingerprint = hashlib.sha256(settings.apify_token.encode()).hexdigest()
    async with _lock:
        cached = _cache.get(fingerprint)
        if not force and cached and cached[0] > now:
            return cached[1]
        try:
            headers = {"Authorization": f"Bearer {settings.apify_token}"}
            account, limits = await asyncio.gather(
                http.get("https://api.apify.com/v2/users/me", headers=headers, timeout=10),
                http.get("https://api.apify.com/v2/users/me/limits", headers=headers, timeout=10),
            )
            account.raise_for_status()
            limits.raise_for_status()
            credits = _amount(account.json()["data"]["plan"]["monthlyUsageCreditsUsd"])
            data = limits.json()["data"]
            usage = _amount(data["current"]["monthlyUsageUsd"])
            hard_limit = _amount(data["limits"]["maxMonthlyUsageUsd"])
            cycle = data["monthlyUsageCycle"]
            start, end = _date(cycle["startAt"]), _date(cycle["endAt"])
            if not start <= now <= end:
                raise ValueError("Expired usage cycle")
            result = AccountBalance(
                status="live",
                allowance=int((credits * 100).to_integral_value(rounding=ROUND_FLOOR)),
                spent=int((usage * 100).to_integral_value(rounding=ROUND_CEILING)),
                remaining=int(
                    (max(min(credits, hard_limit) - usage, Decimal(0)) * 100).to_integral_value(
                        rounding=ROUND_FLOOR
                    )
                ),
                checked_at=now,
                period_start=start,
                renews_on=end + timedelta(milliseconds=1),
                message="Account-wide Apify usage, including activity outside JobWeaver. "
                "Runs stop at the remaining included credits or account spending limit.",
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ArithmeticError):
            result = AccountBalance(
                status="unavailable",
                message="Could not verify Apify's account credits. Check token permissions or "
                "try again later. Paid searches pause until the balance can be verified.",
            )
        # Bound the cache and retry failures soon. A failed refresh never displays an old
        # balance as current, and a new token cannot inherit another account's usage.
        for key, (expiry, _) in list(_cache.items()):
            if expiry <= now:
                del _cache[key]
        if len(_cache) >= 32:
            _cache.clear()
        expiry = now + timedelta(seconds=60 if result.status == "live" else 15)
        if result.renews_on:
            expiry = min(expiry, result.renews_on)
        _cache[fingerprint] = (expiry, result)
        return result


async def account_status(
    adapter: type[SourceAdapter],
    http: httpx.AsyncClient,
    settings: Settings,
    now: datetime,
) -> AccountBalance | None:
    options = credentials(adapter, settings)
    if not options:
        return await account_balance(adapter, http, settings, now)
    balances = [await account_balance(adapter, http, option.settings, now) for option in options]
    # Same ordering as fetching: an unverifiable primary does not silently spend elsewhere.
    index = 0
    if adapter.budget_pool == "apify":
        while (
            index < len(balances) - 1
            and balances[index].status == "live"
            and not balances[index].remaining
        ):
            index += 1
    selected = balances[index]
    return selected.model_copy(
        update={
            "account_label": options[index].label,
            "accounts": [
                AccountCredit(
                    label=option.label,
                    status=balance.status,
                    allowance=balance.allowance,
                    spent=balance.spent,
                    remaining=balance.remaining,
                    renews_on=balance.renews_on,
                )
                for option, balance in zip(options, balances, strict=True)
            ],
        }
    )
