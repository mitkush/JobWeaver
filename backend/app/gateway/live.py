import asyncio
import logging
import math
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel

from app.core.errors import GatewayError, ProviderBusy
from app.gateway import personal, progress, prompts
from app.gateway.base import BaseAIGateway
from app.gateway.draft_prompt import (
    DRAFT_OUTPUT_RESERVE,
    MAX_DRAFT_PROMPT_CHARS,
    draft_prompt,
)
from app.gateway.parsing import parse_output
from app.gateway.providers import GeminiClient, ProviderClient
from app.gateway.quota import UsageLedger
from app.gateway.routing import (
    DAILY_QUOTAS,
    EMBEDDING_DIMENSIONS,
    GEMINI_EMBEDDING,
    ROUTING_TABLE,
    TOKENS_PER_MINUTE,
    Route,
)
from app.gateway.schemas import (
    DraftResult,
    EmbedRequest,
    EmbedResult,
    ExtractAdvertsRequest,
    ExtractAdvertsResult,
    ExtractSkillsRequest,
    ExtractSkillsResult,
    GatewayResponse,
    ParseDocumentsRequest,
    ParseDocumentsResult,
    ReviseDraftRequest,
    TailorDraftRequest,
)

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


# Seconds within which a 503 must arrive for the provider to be retried.
BUSY_RETRY_WITHIN = 5.0


# Characters per token used to estimate a prompt's size. English and JSON average about
# four; three over-estimates, so the output budget errs small rather than over the limit.
CHARS_PER_TOKEN = 3
# Headroom for the chat template and message framing the provider adds.
TOKEN_MARGIN = 256
# Below this, a reply cannot hold a Draft or a parse result: skip the route instead.
MIN_OUTPUT_TOKENS = 1024
TOO_LARGE = "request exceeded this provider's token limit"


def route_of(route: Route) -> tuple[str, str]:
    return route.provider, route.model


def output_budget(route: Route, system: str, user: str) -> int | None:
    """The output ceiling to request: the route's own, lowered so prompt plus ceiling fit
    the provider's tokens-per-minute limit. None when even a minimal reply cannot fit."""
    limit = TOKENS_PER_MINUTE.get(route_of(route))
    if limit is None:
        return route.max_output_tokens
    prompt = math.ceil((len(system) + len(user)) / CHARS_PER_TOKEN)
    budget = min(route.max_output_tokens, limit - prompt - TOKEN_MARGIN)
    return budget if budget >= MIN_OUTPUT_TOKENS else None


def _failure_summary(exc: GatewayError) -> str:
    """Provider diagnostics stay in the logs; users see a compact, safe summary. Raw
    provider text can include account details such as an organisation id."""
    message = exc.message.lower()
    if isinstance(exc, ProviderBusy):
        return "temporarily overloaded"
    if "http 413" in message or "request too large" in message:
        return TOO_LARGE
    if "rate limit or quota exceeded" in message:
        return "rate-limited or quota exhausted"
    if "unavailable for free" in message:
        return "model is unavailable on this provider tier"
    if "daily quota reached" in message:
        return "daily quota reached"
    if "not configured" in message:
        return "not configured"
    if "timed out" in message:
        return "timed out"
    return "request failed (details recorded in server logs)"


class LiveAIGateway(BaseAIGateway):
    """Tries each route of a task in order; skips routes without a key or over quota."""

    embedding_model = GEMINI_EMBEDDING

    def __init__(
        self,
        clients: dict[str, ProviderClient],
        ledger: UsageLedger,
        busy_retry_delay: float = 2.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.clients = clients
        self.ledger = ledger
        # A 503 "high demand" from a free model usually clears within seconds.
        self.busy_retry_delay = busy_retry_delay
        self.sleep = sleep
        self.clock = clock

    async def tailor_draft(self, request: TailorDraftRequest) -> GatewayResponse[DraftResult]:
        return await self._run(
            "tailor_draft",
            request.user_id,
            prompts.TAILOR_DRAFT_SYSTEM,
            prompts.draft_user(request),
            DraftResult,
            prepare=lambda route: self._draft_prompt(request, route, prompts.TAILOR_DRAFT_SYSTEM),
            personal_route=True,
        )

    async def revise_draft(self, request: ReviseDraftRequest) -> GatewayResponse[DraftResult]:
        return await self._run(
            "revise_draft",
            request.user_id,
            prompts.REVISE_DRAFT_SYSTEM,
            prompts.draft_user(request),
            DraftResult,
            prepare=lambda route: self._draft_prompt(request, route, prompts.REVISE_DRAFT_SYSTEM),
        )

    @staticmethod
    def _draft_prompt(request: TailorDraftRequest, route: Route, system: str) -> str | None:
        limit = TOKENS_PER_MINUTE.get(route_of(route))
        chars = MAX_DRAFT_PROMPT_CHARS
        if limit is not None:
            reserve = min(route.max_output_tokens, DRAFT_OUTPUT_RESERVE)
            chars = min(chars, (limit - reserve - TOKEN_MARGIN) * CHARS_PER_TOKEN - len(system))
        selected = draft_prompt(request, chars)
        # The soft target must not exclude existing large-context providers when the
        # employment history alone exceeds it. Token-limited routes still skip safely.
        if selected is None and limit is None:
            return prompts.draft_user(request)
        return selected

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

    async def extract_skills(
        self, request: ExtractSkillsRequest
    ) -> GatewayResponse[ExtractSkillsResult]:
        return await self._run(
            "extract_skills",
            request.user_id,
            prompts.EXTRACT_SKILLS_SYSTEM,
            prompts.extract_skills_user(request),
            ExtractSkillsResult,
        )

    async def extract_adverts(
        self, request: ExtractAdvertsRequest
    ) -> GatewayResponse[ExtractAdvertsResult]:
        return await self._run(
            "extract_adverts",
            None,
            prompts.EXTRACT_ADVERTS_SYSTEM,
            prompts.extract_adverts_user(request),
            ExtractAdvertsResult,
        )

    async def embed_texts(self, request: EmbedRequest) -> GatewayResponse[EmbedResult]:
        client = self.clients.get("gemini")
        if not isinstance(client, GeminiClient):
            raise GatewayError("Embeddings need a Gemini key; postings stay queued")
        quota = DAILY_QUOTAS[("gemini", GEMINI_EMBEDDING)]
        if await self.ledger.used_today("gemini", GEMINI_EMBEDDING) >= quota:
            raise GatewayError("Gemini embedding quota reached for today; postings stay queued")
        try:
            vectors = await client.embed(GEMINI_EMBEDDING, request.texts, EMBEDDING_DIMENSIONS)
        except GatewayError:
            await self.ledger.record(
                user_id=None,
                task="embed_texts",
                provider="gemini",
                model=GEMINI_EMBEDDING,
                outcome="error",
            )
            raise
        await self.ledger.record(
            user_id=None,
            task="embed_texts",
            provider="gemini",
            model=GEMINI_EMBEDDING,
            outcome="ok",
        )
        return GatewayResponse[EmbedResult](
            result=EmbedResult(vectors=[unit(v) for v in vectors]),
            provider="gemini",
            model=GEMINI_EMBEDDING,
        )

    async def _run(
        self,
        task: str,
        user_id: uuid.UUID | None,
        system: str,
        user: str,
        result_type: type[T],
        prepare: Callable[[Route], str | None] | None = None,
        personal_route: bool = False,
    ) -> GatewayResponse[T]:
        failures: list[str] = []
        routes = list(ROUTING_TABLE[task])
        if personal_route and personal.allowed(user_id):
            routes.insert(0, personal.CLAUDE_ROUTE)
        for route in routes:
            client = self.clients.get(route.provider)
            if client is None:
                failures.append(f"{route.provider}: not configured")
                continue
            quota = DAILY_QUOTAS.get((route.provider, route.model))
            used = await self.ledger.used_today(route.provider, route.model)
            if quota is not None and used >= quota:
                failures.append(f"{route.provider}/{route.model}: daily quota reached")
                continue
            route_user = prepare(route) if prepare else user
            budget = output_budget(route, system, route_user) if route_user is not None else None
            if budget is None:
                # Sending it would only earn an HTTP 413; try the next provider at once.
                logger.warning(
                    "AI route %s/%s skipped for %s: prompt too large", *route_of(route), task
                )
                failures.append(f"{route.provider}/{route.model}: {TOO_LARGE}")
                continue
            await progress.trying(route.provider)
            try:
                try:
                    async with asyncio.timeout(route.timeout_seconds):
                        started = self.clock()
                        try:
                            completion = await client.complete_json(
                                route.model, system, route_user, budget
                            )
                        except ProviderBusy as exc:
                            # Retry only a quick refusal, and keep the retry inside this
                            # route's time budget so fallbacks still have time to run.
                            if self.clock() - started > BUSY_RETRY_WITHIN:
                                raise
                            logger.info(
                                "AI route %s/%s busy, retrying once: %s", *route_of(route), exc
                            )
                            await self.sleep(self.busy_retry_delay)
                            completion = await client.complete_json(
                                route.model, system, route_user, budget
                            )
                except TimeoutError as exc:
                    raise GatewayError(
                        f"{route.provider} timed out after {route.timeout_seconds:g}s"
                    ) from exc
                result = parse_output(completion.text, result_type)
            except GatewayError as exc:
                logger.warning(
                    "AI route %s/%s failed for %s: %s",
                    route.provider,
                    route.model,
                    task,
                    exc.message,
                )
                await self.ledger.record(
                    user_id=user_id,
                    task=task,
                    provider=route.provider,
                    model=route.model,
                    outcome="error",
                )
                failures.append(f"{route.provider}/{route.model}: {_failure_summary(exc)}")
                continue
            await self.ledger.record(
                user_id=user_id,
                task=task,
                provider=route.provider,
                model=completion.model or route.model,
                outcome="ok",
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
            )
            return GatewayResponse[result_type](  # type: ignore[valid-type]
                result=result,
                provider=route.provider,
                model=completion.model or route.model,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
            )
        raise GatewayError("All AI providers are unavailable right now: " + "; ".join(failures))


def unit(vector: list[float]) -> list[float]:
    """Reduced-size Gemini embeddings are not normalised; cosine needs comparable lengths."""
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
