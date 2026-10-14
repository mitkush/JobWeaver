from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AccountCredit(BaseModel):
    label: str
    status: Literal["live", "unavailable", "unsupported"]
    paused_until: datetime | None = None
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
