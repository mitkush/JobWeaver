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
# Free OpenRouter models come and go: gpt-oss-20b:free was withdrawn on 7 Oct 2026 (HTTP 404).
# Gemma answers without hidden reasoning, so its whole output budget goes to the JSON.
OPENROUTER_FREE = "google/gemma-4-31b-it:free"
# The only embedding model (ADR-0014). Changing it means re-embedding every Posting.
GEMINI_EMBEDDING = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

# Requests per day on the free tiers, kept slightly under the published limits.
DAILY_QUOTAS: dict[tuple[str, str], int] = {
    ("gemini", GEMINI_FLASH): 18,
    ("gemini", GEMINI_FLASH_LITE): 450,
    ("groq", GROQ_LARGE): 900,
    ("openrouter", OPENROUTER_FREE): 45,
    # Embedding limits are not published in a table; confirm in AI Studio (COSTS.md).
    ("gemini", GEMINI_EMBEDDING): 900,
}

ROUTING_TABLE: dict[str, list[Route]] = {
    "tailor_draft": [
        Route("gemini", GEMINI_FLASH),
        Route("groq", GROQ_LARGE),
        Route("openrouter", OPENROUTER_FREE),
    ],
    "revise_draft": [
        Route("gemini", GEMINI_FLASH),
        Route("groq", GROQ_LARGE),
        Route("openrouter", OPENROUTER_FREE),
    ],
    # Flash (about 20 calls a day) is reserved for Drafts and Draft Chat (FR-G4 AC1,
    # COSTS.md); parsing is extraction work, so Flash-Lite goes first.
    "parse_documents": [
        Route("gemini", GEMINI_FLASH_LITE),
        Route("groq", GROQ_LARGE),
        Route("openrouter", OPENROUTER_FREE),
    ],
    # High volume and simple: Flash-Lite first, Groq as the bulk fallback (COSTS.md).
    "extract_skills": [
        Route("gemini", GEMINI_FLASH_LITE, 4096),
        Route("groq", GROQ_LARGE, 4096),
        Route("openrouter", OPENROUTER_FREE, 4096),
    ],
    # Hacker News "Who is hiring" comments into Postings: same volume profile as skills.
    "extract_adverts": [
        Route("gemini", GEMINI_FLASH_LITE, 8192),
        Route("groq", GROQ_LARGE, 8192),
        Route("openrouter", OPENROUTER_FREE, 8192),
    ],
}
