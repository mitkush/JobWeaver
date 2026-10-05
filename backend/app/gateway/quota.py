import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage import AIUsage


class UsageLedger:
    """Counts calls per provider and model per UTC day, and records each call (FR-G4)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def used_today(self, provider: str, model: str) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        query = select(func.count()).where(
            AIUsage.provider == provider, AIUsage.model == model, AIUsage.created_at >= start
        )
        return int((await self.session.execute(query)).scalar_one())

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
        self.session.add(
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
        await self.session.flush()
