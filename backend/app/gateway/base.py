from abc import ABC, abstractmethod

from app.gateway.schemas import GatewayResponse, ParseDocumentsRequest, ParseDocumentsResult


class BaseAIGateway(ABC):
    """Typed task methods. Later phases add tasks here (extract_job, tailor_resume, ...)."""

    @abstractmethod
    async def parse_documents(
        self, request: ParseDocumentsRequest
    ) -> GatewayResponse[ParseDocumentsResult]: ...
