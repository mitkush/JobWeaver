"""Provider-neutral balance orchestration; providers own their HTTP and parsing."""

from datetime import UTC, datetime

import httpx

from app.adapters.base import SourceAdapter
from app.core.config import Settings
from app.schemas.account_balances import AccountBalance, AccountCredit
from app.services.provider_credentials import active_primary_pause, credentials


def balance_is_usable(adapter: type[SourceAdapter], balance: AccountBalance | None) -> bool:
    """Whether this account would be selected for a new provider search."""
    minimum = max(1, getattr(adapter, "minimum_usable_balance", 1))
    return (
        balance is not None
        and balance.status == "live"
        and balance.remaining is not None
        and balance.remaining >= minimum
    )


async def account_balance(
    adapter: type[SourceAdapter],
    http: httpx.AsyncClient,
    settings: Settings,
    now: datetime | None = None,
    *,
    force: bool = False,
) -> AccountBalance | None:
    return await adapter(http, settings).account_balance(now or datetime.now(UTC), force=force)


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
    paused_until = active_primary_pause(adapter, settings, now)
    active = [
        index
        for index, option in enumerate(options)
        if not (option.primary and paused_until is not None)
    ]
    eligible = (
        [index for index in active if balance_is_usable(adapter, balances[index])]
        if adapter.account_balance_required
        else active
    )
    if not eligible:
        accounts = [
            AccountCredit(
                label=option.label,
                status=balance.status if balance else "unavailable",
                paused_until=paused_until if option.primary else None,
                allowance=balance.allowance if balance else None,
                spent=balance.spent if balance else None,
                remaining=balance.remaining if balance else None,
                renews_on=balance.renews_on if balance else None,
            )
            for option, balance in zip(options, balances, strict=True)
        ]
        return AccountBalance(
            account_label="No usable account",
            accounts=accounts,
            status="unavailable",
            message="No configured account has a verified balance sufficient for a new search",
        )
    # Preserve configured order, matching Fetcher._check_budget; unavailable or low-balance
    # accounts are skipped by both paths.
    index = eligible[0]
    selected = balances[index]
    assert selected is not None
    return selected.model_copy(
        update={
            "account_label": options[index].label,
            "accounts": [
                AccountCredit(
                    label=option.label,
                    status=balance.status if balance else "unavailable",
                    paused_until=paused_until if option.primary else None,
                    allowance=balance.allowance if balance else None,
                    spent=balance.spent if balance else None,
                    remaining=balance.remaining if balance else None,
                    renews_on=balance.renews_on if balance else None,
                )
                for option, balance in zip(options, balances, strict=True)
            ],
        }
    )
