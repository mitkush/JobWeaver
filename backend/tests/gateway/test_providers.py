import json

import httpx
import pytest

from app.core.errors import GatewayError
from app.gateway.providers import GeminiClient, OpenAICompatibleClient


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_gemini_sends_json_mode_and_reads_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": '{"facts": []}'}]}}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 3},
            },
        )

    async with client_for(handler) as http:
        result = await GeminiClient("k", http).complete_json("gemini-x", "sys", "user", 100)
    assert result.text == '{"facts": []}' and result.input_tokens == 12
    assert seen["url"].endswith("/models/gemini-x:generateContent")
    assert seen["key"] == "k"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


async def test_openai_compatible_client_reads_choices():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            },
        )

    async with client_for(handler) as http:
        client = OpenAICompatibleClient("groq", "https://api.example/v1", "k", http)
        result = await client.complete_json("m", "s", "u", 50)
    assert (result.text, result.output_tokens) == ("{}", 2)


@pytest.mark.parametrize("status", [429, 500])
async def test_http_errors_become_gateway_errors(status):
    async with client_for(lambda r: httpx.Response(status, json={})) as http:
        with pytest.raises(GatewayError):
            await GeminiClient("k", http).complete_json("m", "s", "u", 10)


async def test_blocked_gemini_response_is_a_gateway_error():
    body = {"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}
    async with client_for(lambda r: httpx.Response(200, json=body)) as http:
        with pytest.raises(GatewayError, match="no content"):
            await GeminiClient("k", http).complete_json("m", "s", "u", 10)
