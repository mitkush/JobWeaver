"""AI usage for the Admin (FR-G4): today's calls against each free quota, and the last
week by task. Counts only; prompts and outputs are never stored."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.routing import DAILY_QUOTAS
from app.models.ai_usage import AIUsage
from app.schemas.ai_usage import AIUsageOut, ModelUsage, TaskUsage


async def summary(session: AsyncSession, now: datetime | None = None) -> AIUsageOut:
    now = now or datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    errors = func.sum(case((AIUsage.outcome != "ok", 1), else_=0))
    used = dict(
        (
            (row.provider, row.model),
            (int(row.calls), int(row.errors)),
        )
        for row in await session.execute(
            select(
                AIUsage.provider, AIUsage.model, func.count().label("calls"), errors.label("errors")
            )
            .where(AIUsage.created_at >= today)
            .group_by(AIUsage.provider, AIUsage.model)
        )
    )
    models = [
        ModelUsage(
            provider=provider,
            model=model,
            calls_today=used.get((provider, model), (0, 0))[0],
            errors_today=used.get((provider, model), (0, 0))[1],
            daily_quota=DAILY_QUOTAS.get((provider, model)),
        )
        for provider, model in sorted({*DAILY_QUOTAS, *used})
    ]
    week = await session.execute(
        select(
            AIUsage.task,
            func.count().label("calls"),
            errors.label("errors"),
            func.coalesce(func.sum(AIUsage.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AIUsage.output_tokens), 0).label("output_tokens"),
        )
        .where(AIUsage.created_at >= now - timedelta(days=7))
        .group_by(AIUsage.task)
        .order_by(AIUsage.task)
    )
    return AIUsageOut(
        day_started_at=today,
        models=models,
        tasks_last_7_days=[
            TaskUsage(
                task=row.task,
                calls=int(row.calls),
                errors=int(row.errors),
                input_tokens=int(row.input_tokens),
                output_tokens=int(row.output_tokens),
            )
            for row in week
        ],
    )
