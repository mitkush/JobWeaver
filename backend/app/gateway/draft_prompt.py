"""Select whole, traceable Facts for a route without changing the saved Fact Bank."""

import re

from app.gateway import prompts
from app.gateway.schemas import DraftDevelopmentRequest, ReviseDraftRequest, TailorDraftRequest
from app.tailoring.content import FactSnapshot

MAX_DRAFT_PROMPT_CHARS = 24_000
# Reserve a useful full-package reply before allocating a token-limited route's input.
DRAFT_OUTPUT_RESERVE = 3072
_STOP = set(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "you",
        "your",
    ]
)


def _words(text: str) -> set[str]:
    return {word.strip(".") for word in re.findall(r"[\w+#.]+", text.casefold())} - _STOP


def draft_prompt(request: TailorDraftRequest, max_chars: int) -> str | None:
    """Keep employment/contact context and cited groups, then fit relevant whole groups.

    A group is indivisible: a project bullet must not lose its employer/title/date Facts.
    Skills are independent even when filed under one broad category. Protected context
    that cannot fit makes this route unavailable, rather than silently losing evidence.
    """
    groups: dict[str, list[FactSnapshot]] = {}
    for fact in request.facts:
        key = fact.group.strip().casefold()
        key = f"group:{key}" if key and fact.kind != "skill" else f"fact:{fact.ref}"
        groups.setdefault(key, []).append(fact)

    cited: set[str] = set()
    if isinstance(request, (ReviseDraftRequest, DraftDevelopmentRequest)):
        previous = (
            request.content if isinstance(request, ReviseDraftRequest) else request.previous_content
        )
        for part in ("resume", "cover_letter", "email_body"):
            for line in getattr(previous, part):
                cited.update(line.fact_refs)

    protected = {
        key
        for key, facts in groups.items()
        if any(
            f.kind in {"experience", "education", "link"}
            or f.group.strip().casefold() == "contact"
            or f.ref in cited
            for f in facts
        )
    }

    def render(keys: set[str]) -> str:
        refs = {f.ref for key in keys for f in groups[key]}
        # Preserve original order, IDs and refs, including gaps in the F-number sequence.
        selected = [f for f in request.facts if f.ref in refs]
        return prompts.draft_user(request.model_copy(update={"facts": selected}))

    if len(render(protected)) > max_chars:
        return None
    title = _words(request.job_title)
    job = _words(request.description)
    if isinstance(request, ReviseDraftRequest):
        job |= _words(request.message)

    def rank(key: str) -> tuple[int, int]:
        facts = groups[key]
        words = _words(" ".join(f"{f.group} {f.text}" for f in facts))
        score = 4 * len(words & title) + len(words & job)
        return score, int(any(f.in_base_resume for f in facts))

    selected = set(protected)
    for key in sorted((k for k in groups if k not in protected), key=rank, reverse=True):
        candidate = selected | {key}
        if len(render(candidate)) <= max_chars:
            selected = candidate
    if not selected:
        return None
    return render(selected)
