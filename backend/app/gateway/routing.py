"""Per-task model routing and free daily quotas. Model names live here and nowhere else.

Quotas mirror jobweaver-docs/COSTS.md (checked 5 Oct 2026). Confirm the live numbers in
each provider's dashboard and update both places together.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    max_output_tokens: int = 8192


GEMINI_FLASH = "gemini-flash-latest"
GEMINI_FLASH_LITE = "gemini-flash-lite-latest"
GROQ_LARGE = "openai/gpt-oss-120b"
OPENROUTER_FREE = "openai/gpt-oss-20b:free"

# Requests per day on the free tiers, kept slightly under the published limits.
DAILY_QUOTAS: dict[tuple[str, str], int] = {
    ("gemini", GEMINI_FLASH): 18,
    ("gemini", GEMINI_FLASH_LITE): 450,
    ("groq", GROQ_LARGE): 900,
    ("openrouter", OPENROUTER_FREE): 45,
}

ROUTING_TABLE: dict[str, list[Route]] = {
    # Once per upload and quality matters, so the strongest model goes first.
    "parse_documents": [
        Route("gemini", GEMINI_FLASH),
        Route("gemini", GEMINI_FLASH_LITE),
        Route("groq", GROQ_LARGE),
        Route("openrouter", OPENROUTER_FREE),
    ],
}
