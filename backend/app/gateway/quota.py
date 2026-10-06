import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.ai_usage import AIUsage


class UsageLedger:
    """Counts calls per provider and model per UTC day, and records each call (FR-G4).

    Uses its own short sessions and commits each record at once, so usage is never lost
    when the caller's transaction rolls back (e.g. every provider failed).
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def used_today(self, provider: str, model: str) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        query = select(func.count()).where(
            AIUsage.provider == provider, AIUsage.model == model, AIUsage.created_at >= start
        )
        async with self.sessionmaker() as session:
            return int((await session.execute(query)).scalar_one())

    async def record(
        self,
        *,
        user_id: uuid.UUID | None,
        task: str,
        provider: str,
        model: str,
        outcome: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        async with self.sessionmaker() as session:
            session.add(
                AIUsage(
                    user_id=user_id,
                    task=task,
                    provider=provider,
                    model=model,
                    outcome=outcome,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            )
            await session.commit()
