"""HTTP transport to the isolated official CLI; subscription tokens never enter the app."""

import httpx

from app.core.errors import GatewayError
from app.gateway.providers import Completion


class ClaudeCodeClient:
    name = "claude-code"

    def __init__(self, url: str, key: str, http: httpx.AsyncClient) -> None:
        self.url, self.key, self.http = url.rstrip("/"), key, http

    async def complete_json(self, model, system, user, max_output_tokens) -> Completion:
        try:
            response = await self.http.post(
                f"{self.url}/complete",
                headers={"Authorization": f"Bearer {self.key}"},
                json={"system": system, "user": user},
                timeout=59,
            )
            if response.status_code != 200:
                # Never expose CLI stderr, subscription diagnostics or service credentials.
                raise GatewayError(f"Claude Code worker unavailable (HTTP {response.status_code})")
            data = response.json()
            text, actual_model = data["text"], data["model"]
            if not isinstance(text, str) or not isinstance(actual_model, str):
                raise ValueError
            counts = [data["input_tokens"], data["output_tokens"]]
            if any(type(n) is not int or n < 0 for n in counts):
                raise ValueError
            return Completion(text, *counts, model=actual_model)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise GatewayError("Claude Code worker did not return a valid response") from exc
