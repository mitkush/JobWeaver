import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.fetch import RunStatus
from app.models.source import SourceState
from app.schemas.account_balances import AccountBalance


class QuerySpend(BaseModel):
    query_key: str
    spent: int


class BudgetOut(BaseModel):
    """Local tracking guard and spend; verified provider values live under account."""

    account: AccountBalance | None = None
    tracked_account: str | None = None
    allowance: int
    unit: str
    spent: int
    projected: int
    period_start: datetime
    renews_on: datetime
    runs_out_on: datetime | None
    top_queries: list[QuerySpend]


class SourceStatusOut(BaseModel):
    name: str
    label: str
    site: str | None = None
    priority: int
    mode: str
    enabled: bool
    configured: bool
    state: SourceState
    last_success_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    degraded_since: datetime | None
    next_run_at: datetime | None
    open_postings: int
    boards: int | None
    budget: BudgetOut | None
    manual_runs_left: int
    # Label of the Source this one backs up; it runs only while that one is Degraded.
    standby_for: str | None
    # Labels of the other Sources drawing on the same allowance.
    shares_budget_with: list[str]
    # Why a Source is off by default (e.g. no stable API).
    disabled_reason: str | None


class SourceUpdate(BaseModel):
    enabled: bool


class RunOutcomeOut(BaseModel):
    source: str
    status: str
    message: str
    postings_new: int
    credits_used: int


class FetchRunOut(BaseModel):
    id: uuid.UUID
    source: str
    status: RunStatus
    trigger: str
    query_key: str | None
    board: str | None
    created_at: datetime
    finished_at: datetime | None
    postings_found: int
    postings_new: int
    postings_closed: int
    credits_used: int
    error: str | None


class AtsBoardIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class AtsBoardOut(BaseModel):
    id: uuid.UUID
    ats: str
    slug: str
    company: str | None
    discovered_from: str
    enabled: bool
    fetched: bool
    last_fetched_at: datetime | None
    open_postings: int
