import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.errors import GatewayError

T = TypeVar("T", bound=BaseModel)


def parse_output(raw: str, result_type: type[T]) -> T:
    """Validate model output against the task schema; anything else is a GatewayError."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GatewayError("AI output was not valid JSON") from exc
    if isinstance(data, dict) and "refusal" in data:
        raise GatewayError(f"AI declined the task: {data['refusal']}")
    try:
        return result_type.model_validate(data)
    except ValidationError as exc:
        raise GatewayError("AI output did not match the expected shape") from exc
