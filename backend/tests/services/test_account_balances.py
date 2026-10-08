from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.base import SourceAdapter
from app.core.config import Settings
from app.services import account_balances

NOW = datetime(2026, 10, 8, tzinfo=UTC)


class Apify(SourceAdapter):
    name = "test-apify"
    budget_pool = "apify"


class BrightData(SourceAdapter):
    name = "linkedin"


@pytest.fixture(autouse=True)
def clear_cache():
    account_balances._cache.clear()


def limits(usage=4.95, hard_limit=100):
    return {
        "data": {
            "current": {"monthlyUsageUsd": usage},
            "limits": {"maxMonthlyUsageUsd": hard_limit},
            "monthlyUsageCycle": {
                "startAt": "2026-10-02T00:00:00Z",
                "endAt": "2026-11-01T23:59:59.999Z",
            },
        }
    }


def response(request, usage=4.95, hard_limit=100, credits=5):
    if request.url.path.endswith("/limits"):
        return httpx.Response(200, json=limits(usage, hard_limit))
    return httpx.Response(200, json={"data": {"plan": {"monthlyUsageCreditsUsd": credits}}})


async def test_apify_uses_account_not_local_ledger_and_its_own_cycle():
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        result = await account_balances.account_balance(
            Apify, http, Settings(apify_token="test"), NOW
        )
    assert result.status == "live"
    assert (result.allowance, result.spent, result.remaining) == (500, 495, 5)
    assert result.period_start.day == 2
    assert result.checked_at == NOW


@pytest.mark.parametrize(
    "usage,hard,credits,remaining",
    [
        (5.2, 100, 5, 0),
        (1.111, 100, 5, 388),
        (1, 1.5, 5, 50),
        (1, 100, 49, 4800),
    ],
)
async def test_remaining_is_conservative_and_respects_spending_limit(
    usage, hard, credits, remaining
):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: response(r, usage, hard, credits))
    ) as http:
        result = await account_balances.account_balance(
            Apify, http, Settings(apify_token="test"), NOW
        )
    assert result.remaining == remaining


async def test_cache_shared_but_key_change_and_forced_check_refresh():
    calls = []

    def handler(request):
        calls.append(request)
        usage = 5 if request.headers["Authorization"] == "Bearer old" else 0
        return response(request, usage=usage)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        for _ in range(2):
            result = await account_balances.account_balance(
                Apify, http, Settings(apify_token="old"), NOW
            )
            assert result.remaining == 0
        assert len(calls) == 2
        result = await account_balances.account_balance(
            Apify, http, Settings(apify_token="new"), NOW
        )
        assert result.remaining == 500 and len(calls) == 4
        await account_balances.account_balance(
            Apify, http, Settings(apify_token="new"), NOW, force=True
        )
        assert len(calls) == 6


@pytest.mark.parametrize("failure", ["403", "timeout", "malformed", "expired", "nan"])
async def test_failures_never_return_cached_balance_or_provider_secrets(failure):
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        await account_balances.account_balance(Apify, http, Settings(apify_token="secret"), NOW)

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("secret", request=request)
        if failure == "403":
            return httpx.Response(403, text="secret")
        if failure == "malformed":
            return httpx.Response(200, json={"secret": "secret"})
        if failure == "nan":
            return response(request, usage="NaN")
        data = limits()
        data["data"]["monthlyUsageCycle"]["endAt"] = "2026-09-01T00:00:00Z"
        return (
            httpx.Response(200, json=data)
            if request.url.path.endswith("/limits")
            else response(request)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await account_balances.account_balance(
            Apify, http, Settings(apify_token="secret"), NOW, force=True
        )
    assert result.status == "unavailable"
    assert result.remaining is None and result.checked_at is None
    assert "secret" not in result.model_dump_json()


async def test_brightdata_free_credits_are_unknown_not_dollars():
    def no_call(request):
        raise AssertionError("Monetary balance is not free credits")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_call)) as http:
        result = await account_balances.account_balance(BrightData, http, Settings(), NOW)
    assert result.status == "unsupported" and result.remaining is None
