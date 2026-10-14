"""Provider-neutral balance orchestration; providers own their HTTP and parsing."""

from datetime import UTC, datetime

import httpx

from app.adapters.base import SourceAdapter
from app.core.config import Settings
from app.schemas.account_balances import AccountBalance, AccountCredit
from app.services.provider_credentials import active_primary_pause, credentials


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
    if any(balance is None for balance in balances):
        return None
    # Same ordering as fetching: an unverifiable primary does not silently spend elsewhere.
    index = 0
    paused_until = active_primary_pause(adapter, settings, now)
    if paused_until is not None and len(options) > 1:
        index = 1
    if adapter.account_balance_required:
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
                    paused_until=paused_until if option.primary else None,
                    allowance=balance.allowance,
                    spent=balance.spent,
                    remaining=balance.remaining,
                    renews_on=balance.renews_on,
                )
                for option, balance in zip(options, balances, strict=True)
            ],
        }
    )
