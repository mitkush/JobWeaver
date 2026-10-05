import logging
import uuid
from typing import TypeVar

from pydantic import BaseModel

from app.core.errors import GatewayError
from app.gateway import prompts
from app.gateway.base import BaseAIGateway
from app.gateway.parsing import parse_output
from app.gateway.providers import ProviderClient
from app.gateway.quota import UsageLedger
from app.gateway.routing import DAILY_QUOTAS, ROUTING_TABLE
from app.gateway.schemas import GatewayResponse, ParseDocumentsRequest, ParseDocumentsResult

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LiveAIGateway(BaseAIGateway):
    """Tries each route of a task in order; skips routes without a key or over quota."""

    def __init__(self, clients: dict[str, ProviderClient], ledger: UsageLedger) -> None:
        self.clients = clients
        self.ledger = ledger

    async def parse_documents(
        self, request: ParseDocumentsRequest
    ) -> GatewayResponse[ParseDocumentsResult]:
        return await self._run(
            "parse_documents",
            request.user_id,
            prompts.PARSE_DOCUMENTS_SYSTEM,
            prompts.parse_documents_user(request),
            ParseDocumentsResult,
        )

    async def _run(
        self, task: str, user_id: uuid.UUID | None, system: str, user: str, result_type: type[T]
    ) -> GatewayResponse[T]:
        failures: list[str] = []
        for route in ROUTING_TABLE[task]:
            client = self.clients.get(route.provider)
            if client is None:
                failures.append(f"{route.provider}: not configured")
                continue
            quota = DAILY_QUOTAS.get((route.provider, route.model))
            used = await self.ledger.used_today(route.provider, route.model)
            if quota is not None and used >= quota:
                failures.append(f"{route.provider}/{route.model}: daily quota reached")
                continue
            try:
                completion = await client.complete_json(
                    route.model, system, user, route.max_output_tokens
                )
                result = parse_output(completion.text, result_type)
            except GatewayError as exc:
                logger.warning(
                    "AI route %s/%s failed for %s: %s", route.provider, route.model, task, exc
                )
                await self.ledger.record(
                    user_id=user_id,
                    task=task,
                    provider=route.provider,
                    model=route.model,
                    outcome="error",
                )
                failures.append(f"{route.provider}/{route.model}: {exc.message}")
                continue
            await self.ledger.record(
                user_id=user_id,
                task=task,
                provider=route.provider,
                model=route.model,
                outcome="ok",
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
            )
            return GatewayResponse[result_type](  # type: ignore[valid-type]
                result=result,
                provider=route.provider,
                model=route.model,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
            )
        raise GatewayError("All AI providers are unavailable right now: " + "; ".join(failures))
