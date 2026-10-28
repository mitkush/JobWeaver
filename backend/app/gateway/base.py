from abc import ABC, abstractmethod

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


class BaseAIGateway(ABC):
    """Typed task methods. Later phases add tasks here (tailor_resume, draft_chat, ...)."""

    # Stored with every vector; vectors from different models are never compared.
    embedding_model: str

    @abstractmethod
    async def tailor_draft(self, request: TailorDraftRequest) -> GatewayResponse[DraftResult]: ...

    @abstractmethod
    async def revise_draft(self, request: ReviseDraftRequest) -> GatewayResponse[DraftResult]: ...

    async def propose_draft(self, request: ReviseDraftRequest) -> GatewayResponse[DraftResult]:
        """Background-only candidate route; recorded gateways reuse revision fixtures."""
        return await self.revise_draft(request)

    @abstractmethod
    async def parse_documents(
        self, request: ParseDocumentsRequest
    ) -> GatewayResponse[ParseDocumentsResult]: ...

    @abstractmethod
    async def extract_skills(
        self, request: ExtractSkillsRequest
    ) -> GatewayResponse[ExtractSkillsResult]: ...

    @abstractmethod
    async def extract_adverts(
        self, request: ExtractAdvertsRequest
    ) -> GatewayResponse[ExtractAdvertsResult]: ...

    @abstractmethod
    async def embed_texts(self, request: EmbedRequest) -> GatewayResponse[EmbedResult]:
        """Gemini only, no fallback: vectors from different models are not comparable
        (ADR-0014). Raises GatewayError when Gemini is unavailable; callers queue."""
