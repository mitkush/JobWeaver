"""Conservative code checks on every generated line (ADR-0005).

Trace is checked before vocabulary, names and numbers. Novel content words are rejected
rather than relying on the model to report its own hallucinations.
"""

import re
from collections.abc import Iterable

from app.tailoring.content import DraftContent, DraftLine, FactSnapshot
from app.tailoring.skills import canonical_skill

_TOKEN = re.compile(r"[\w+#]+(?:[.'/-][\w+#]+)*", re.UNICODE)
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)*(?:%|[kKmM])?\b")
# Writing glue may change; named technologies, employers, numbers and claims may not.
_GLUE = set(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "i",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "them",
        "these",
        "they",
        "this",
        "those",
        "to",
        "was",
        "we",
        "were",
        "will",
        "with",
        "would",
        "your",
        "you",
        "am",
        "thank",
        "thanks",
        "dear",
        "sincerely",
        "regards",
        "attached",
        "attachment",
        "resume",
        "application",
        "apply",
        "applying",
        "role",
        "position",
        "opportunity",
        "interest",
        "interested",
        "pleased",
        "writing",
        "consideration",
        "hiring",
        "team",
        "look",
        "forward",
        "discuss",
        "experience",
        "skills",
        "summary",
        "projects",
        "education",
        "additional",
        "best",
        "address",
        "contact",
        "email",
        "phone",
        "profile",
        "portfolio",
        "engineer",
        "developer",
        "engineering",
        "software",
    ]
)
_EQUIVALENT = {
    "built": "build",
    "building": "build",
    "developed": "build",
    "developing": "build",
    "development": "build",
    "created": "build",
    "create": "build",
    "implemented": "build",
    "implement": "build",
    "implementation": "build",
    "used": "use",
    "using": "use",
    "reduced": "cut",
    "cut": "cut",
    "improved": "improve",
    "improvement": "improve",
}


def tokens(text: str) -> set[str]:
    return {
        _EQUIVALENT.get(canonical_skill(word), canonical_skill(word))
        for word in _TOKEN.findall(text.lower())
    }


def line_problem(line: DraftLine, facts: Iterable[FactSnapshot]) -> str | None:
    by_ref = {fact.ref: fact for fact in facts}
    if len(set(line.fact_refs)) != len(line.fact_refs):
        return "Duplicate Fact references"
    if not line.fact_refs or any(ref not in by_ref for ref in line.fact_refs):
        return "Missing or unknown Tailoring Trace"
    sources = [by_ref[ref] for ref in line.fact_refs]
    evidence = "\n".join(f"{fact.group}\n{fact.text}" for fact in sources)
    if not set(_NUMBER.findall(line.text)) <= set(_NUMBER.findall(evidence)):
        return "A date or metric is absent from the referenced Facts"
    unknown = tokens(line.text) - tokens(evidence) - _GLUE
    if unknown:
        return "Content absent from the referenced Facts: " + ", ".join(sorted(unknown))
    # Stop unsupported numeric claims written in words as well as digits.
    return None


def check_content(
    content: DraftContent, facts: list[FactSnapshot]
) -> tuple[DraftContent, list[str]]:
    checked = content.model_copy(deep=True)
    warnings: list[str] = []
    seen: set[str] = set()
    for part in ("resume", "cover_letter", "email_body"):
        kept = []
        for line in getattr(checked, part):
            problem = line_problem(line, facts)
            if line.id in seen:
                problem = "Duplicate line identifier"
            seen.add(line.id)
            if problem:
                # Never put rejected model text in logs or an outward artifact.
                warnings.append(f"Removed {part} line: {problem}")
            else:
                kept.append(line)
        setattr(checked, part, kept)
    return checked, warnings
