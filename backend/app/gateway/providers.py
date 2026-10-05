"""HTTP clients for each provider. Plain REST via httpx: no provider SDKs needed."""

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.errors import GatewayError


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class ProviderClient(Protocol):
    name: str

    async def complete_json(
        self, model: str, system: str, user: str, max_output_tokens: int
    ) -> Completion: ...


class GeminiClient:
    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.http = http

    async def complete_json(
        self, model: str, system: str, user: str, max_output_tokens: int
    ) -> Completion:
        response = await self.http.post(
            f"{self.base_url}/models/{model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": max_output_tokens,
                    "temperature": 0.2,
                },
            },
        )
        _raise_for_status(self.name, response)
        body = response.json()
        try:
            text = "".join(p.get("text", "") for p in body["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as exc:
            raise GatewayError(f"gemini returned no content: {body.get('promptFeedback')}") from exc
        usage = body.get("usageMetadata", {})
        return Completion(
            text, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
        )


class OpenAICompatibleClient:
    """Groq and OpenRouter both speak the OpenAI chat completions format."""

    def __init__(self, name: str, base_url: str, api_key: str, http: httpx.AsyncClient) -> None:
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.http = http

    async def complete_json(
        self, model: str, system: str, user: str, max_output_tokens: int
    ) -> Completion:
        response = await self.http.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": max_output_tokens,
                "temperature": 0.2,
            },
        )
        _raise_for_status(self.name, response)
        body = response.json()
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise GatewayError(f"{self.name} returned no content") from exc
        usage = body.get("usage") or {}
        return Completion(text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def _raise_for_status(provider: str, response: httpx.Response) -> None:
    if response.status_code == 429:
        raise GatewayError(f"{provider} rate limit or quota exceeded")
    if response.status_code >= 400:
        raise GatewayError(f"{provider} returned HTTP {response.status_code}")
