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
    timeout_seconds: float = 90


GEMINI_FLASH = "gemini-flash-latest"
GEMINI_FLASH_LITE = "gemini-flash-lite-latest"
GROQ_LARGE = "openai/gpt-oss-120b"
# Free OpenRouter models come and go: gpt-oss-20b:free was withdrawn on 7 Oct 2026 (HTTP 404).
# Gemma answers without hidden reasoning, so its whole output budget goes to the JSON.
OPENROUTER_FREE = "google/gemma-4-31b-it:free"
MISTRAL_SMALL = "mistral-small-latest"
# The only embedding model (ADR-0014). Changing it means re-embedding every Posting.
GEMINI_EMBEDDING = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

# Requests per day on the free tiers, kept slightly under the published limits.
DAILY_QUOTAS: dict[tuple[str, str], int] = {
    ("gemini", GEMINI_FLASH): 18,
    ("gemini", GEMINI_FLASH_LITE): 450,
    ("groq", GROQ_LARGE): 900,
    ("openrouter", OPENROUTER_FREE): 45,
    # Application-side safety cap for the Mistral fallback; provider limits are
    # account-specific and must be checked in Mistral Studio.
    ("mistral", MISTRAL_SMALL): 50,
    # Embedding limits are not published in a table; confirm in AI Studio (COSTS.md).
    ("gemini", GEMINI_EMBEDDING): 900,
}

# Tokens per minute on the free tiers. Groq counts the prompt plus the requested output
# ceiling (max_tokens) against this before running a request, and rejects it with HTTP 413
# if the sum is over: on 21 Oct 2026, 15 of 21 Groq draft attempts failed that way
# ("Limit 8000, Requested 10861") because 8,192 output tokens alone exceed the limit.
TOKENS_PER_MINUTE: dict[tuple[str, str], int] = {
    ("groq", GROQ_LARGE): 8000,
}

ROUTING_TABLE: dict[str, list[Route]] = {
    "tailor_draft": [
        Route("gemini", GEMINI_FLASH, timeout_seconds=20),
        Route("groq", GROQ_LARGE, timeout_seconds=20),
        Route("openrouter", OPENROUTER_FREE, timeout_seconds=20),
        Route("mistral", MISTRAL_SMALL, timeout_seconds=20),
    ],
    "revise_draft": [
        Route("gemini", GEMINI_FLASH, timeout_seconds=20),
        Route("groq", GROQ_LARGE, timeout_seconds=20),
        Route("openrouter", OPENROUTER_FREE, timeout_seconds=20),
        Route("mistral", MISTRAL_SMALL, timeout_seconds=20),
    ],
    # Flash (about 20 calls a day) is reserved for Drafts and Draft Chat (FR-G4 AC1,
    # COSTS.md); parsing is extraction work, so Flash-Lite goes first.
    "parse_documents": [
        Route("gemini", GEMINI_FLASH_LITE),
        Route("groq", GROQ_LARGE),
        Route("openrouter", OPENROUTER_FREE),
        Route("mistral", MISTRAL_SMALL),
    ],
    # High volume and simple: Flash-Lite first, Groq as the bulk fallback (COSTS.md).
    "extract_skills": [
        Route("gemini", GEMINI_FLASH_LITE, 4096),
        Route("groq", GROQ_LARGE, 4096),
        Route("openrouter", OPENROUTER_FREE, 4096),
        Route("mistral", MISTRAL_SMALL, 4096),
    ],
    # Hacker News "Who is hiring" comments into Postings: same volume profile as skills.
    "extract_adverts": [
        Route("gemini", GEMINI_FLASH_LITE, 8192),
        Route("groq", GROQ_LARGE, 8192),
        Route("openrouter", OPENROUTER_FREE, 8192),
        Route("mistral", MISTRAL_SMALL, 8192),
    ],
}
