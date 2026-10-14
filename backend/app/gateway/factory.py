from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.gateway.base import BaseAIGateway
from app.gateway.live import LiveAIGateway
from app.gateway.providers import GeminiClient, OpenAICompatibleClient, ProviderClient
from app.gateway.quota import UsageLedger
from app.gateway.recorded import RecordedAIGateway

_http = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0))


def build_gateway() -> BaseAIGateway:
    settings = get_settings()
    if settings.gateway_mode == "recorded":
        return RecordedAIGateway(Path(settings.gateway_recorded_dir))
    clients: dict[str, ProviderClient] = {}
    if settings.gemini_api_key:
        clients["gemini"] = GeminiClient(settings.gemini_api_key, _http)
    if settings.groq_api_key:
        clients["groq"] = OpenAICompatibleClient(
            "groq", "https://api.groq.com/openai/v1", settings.groq_api_key, _http
        )
    if settings.openrouter_api_key:
        clients["openrouter"] = OpenAICompatibleClient(
            "openrouter", "https://openrouter.ai/api/v1", settings.openrouter_api_key, _http
        )
    if settings.mistral_api_key:
        clients["mistral"] = OpenAICompatibleClient(
            "mistral", "https://api.mistral.ai/v1", settings.mistral_api_key, _http
        )
    return LiveAIGateway(clients, UsageLedger(get_sessionmaker()))
