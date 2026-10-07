from datetime import datetime

from pydantic import BaseModel


class ModelUsage(BaseModel):
    provider: str
    model: str
    calls_today: int
    errors_today: int
    # None for a model with no configured free quota.
    daily_quota: int | None


class TaskUsage(BaseModel):
    task: str
    calls: int
    errors: int
    input_tokens: int
    output_tokens: int


class AIUsageOut(BaseModel):
    day_started_at: datetime
    models: list[ModelUsage]
    tasks_last_7_days: list[TaskUsage]
