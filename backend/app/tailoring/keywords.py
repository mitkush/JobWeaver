"""Preference keywords found in a Job (FR-D1): plain code, no AI call per User.

A differently titled Job reaches the Feed's keyword section only through the keywords the
User chose in Preferences; the Fact Bank plays no part. Spellings of one skill count once
("Rails" = "Ruby on Rails"), and only whole skill phrases count ("Rails" never matches
inside "guardrails"). Case does not matter, except for the few skill names that are also
common English words ("Go", "REST"), whose context may need review.

Each keyword is matched on its own: a longer phrase another User chose ("Rails developer")
never hides a shorter one ("Rails"), so one User's keywords cannot change another's Feed."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.tailoring.skills import PROSE_WORDS, canonical_skill, spellings

Where = Literal["requirements", "description"]


@dataclass(frozen=True)
class Keyword:
    label: str  # as the User wrote it
    canonical: str
    core: bool


@dataclass(frozen=True)
class KeywordRule:
    keywords: tuple[Keyword, ...]
    min_matches: int

    @property
    def terms(self) -> frozenset[str]:
        return frozenset(k.label for k in self.keywords)


@dataclass(frozen=True)
class KeywordMatch:
    keyword: str
    where: Where
    core: bool

    def as_dict(self) -> dict[str, object]:
        return {"keyword": self.keyword, "where": self.where, "core": self.core}


def keyword_rule(
    keywords: Sequence[str], core: Sequence[str], min_matches: int
) -> KeywordRule | None:
    """One entry per skill, core if any of its spellings is core. None while no keyword
    is core: the keyword section is off rather than open to any two common skills."""
    core_keys = {canonical_skill(c) for c in core}
    if not core_keys:
        return None
    merged: dict[str, Keyword] = {}
    for label in keywords:
        canonical = canonical_skill(label)
        if not canonical:
            continue
        is_core = canonical in core_keys
        if canonical in merged:
            if is_core and not merged[canonical].core:
                merged[canonical] = Keyword(merged[canonical].label, canonical, True)
            continue
        merged[canonical] = Keyword(label.strip(), canonical, is_core)
    if not any(k.core for k in merged.values()):
        return None
    return KeywordRule(tuple(merged.values()), max(1, min_matches))


def keyword_spellings(canonical: str) -> tuple[str, ...]:
    """Search expansion belongs to Preferences, not Fact Bank skill equivalence.

    A Rails-focused search includes Ruby roles, without claiming a Ruby Fact proves Rails.
    """
    variants = tuple(spellings(canonical))
    return variants + ("ruby",) if canonical == "ruby on rails" else variants


@lru_cache(maxsize=1024)
def _pattern(canonical: str) -> re.Pattern[str]:
    terms = sorted(set(keyword_spellings(canonical)), key=len, reverse=True)
    alternation = "|".join(re.escape(term) for term in terms)
    return re.compile(rf"(?<![\w+#.])(?:{alternation})(?![\w+#])", re.IGNORECASE)


def _found(canonical: str, text: str) -> bool:
    for match in _pattern(canonical).finditer(text):
        written = match.group(0)
        if written.casefold() not in PROSE_WORDS or written[0].isupper():
            return True
    return False


def mentioned(text: str, terms: Iterable[str]) -> set[str]:
    """Canonical names of the given keywords named in the text, each checked on its own."""
    if not text:
        return set()
    wanted = {canonical_skill(term) for term in terms} - {""}
    return {canonical for canonical in wanted if _found(canonical, text)}


def keyword_matches(
    rule: KeywordRule, in_requirements: set[str], in_description: set[str]
) -> list[KeywordMatch]:
    """The rule's keywords the job description's own text names, each skill once. The
    title never counts: a title can help find an advert, but only the description shows
    the skill is wanted. Extracted skills never count alone; they mark a described
    skill as a stated requirement. The caller confirms their skill/domain context."""
    found: list[KeywordMatch] = []
    for keyword in rule.keywords:
        if keyword.canonical not in in_description:
            continue
        where: Where = "requirements" if keyword.canonical in in_requirements else "description"
        found.append(KeywordMatch(keyword.label, where, keyword.core))
    return found


# Shorter than this, a description cannot confirm a skill. Extracted skills do not help:
# they may come from the title alone.
MIN_DESCRIPTION_CHARS = 100


def has_description(description: str) -> bool:
    return len(description.strip()) >= MIN_DESCRIPTION_CHARS


def has_core(found: Sequence[KeywordMatch]) -> bool:
    """Core keywords are must-haves: every Job in the Feed names at least one."""
    return any(m.core for m in found)


def qualifies(rule: KeywordRule, found: Sequence[KeywordMatch]) -> bool:
    """At least one core keyword, and at least min_matches distinct keywords in total."""
    return has_core(found) and len(found) >= rule.min_matches


# Ambiguous skill names already recognised by the vocabulary, plus Rails' prose sense.
# No preceding/following word lists decide whether a description is technical.
CONTEXT_SENSITIVE = {canonical_skill(word) for word in PROSE_WORDS | {"rails"}}


def literal_matches(found: Sequence[KeywordMatch], in_description: set[str]) -> list[KeywordMatch]:
    """Clear literal evidence never waits for AI or a limited extracted skill list.

    Ruby also confirms a Rails-focused Preference search, including a full Ruby on Rails
    mention, regardless of case. Bare Rails remains ambiguous even when capitalised.
    """
    return [
        match
        for match in found
        if canonical_skill(match.keyword) not in CONTEXT_SENSITIVE
        or (canonical_skill(match.keyword) == "ruby on rails" and "ruby" in in_description)
    ]


def confirmed_matches(
    found: Sequence[KeywordMatch],
    context: Iterable[str],
) -> list[KeywordMatch]:
    """Preferences name the keywords; the Job's cached skill extraction confirms context.

    Literal description evidence is still mandatory (the caller's candidate matches).
    A model-generated skill alone, or a title mention, never adds a Feed keyword.
    """
    names = list(context)
    supported = mentioned(", ".join(names), [match.keyword for match in found])
    supported.update(canonical_skill(skill) for skill in names)
    return [match for match in found if canonical_skill(match.keyword) in supported]


def keyword_excerpt(text: str, keyword: str) -> str | None:
    """Short original-source context for the Job page, never read for Feed cards."""
    match = _pattern(canonical_skill(keyword)).search(text)
    if match is None:
        return None
    sentence = text.rfind(". ", 0, match.start())
    start = max(text.rfind("\n", 0, match.start()) + 1, sentence + 2 if sentence >= 0 else 0)
    end = len(text)
    for marker in ("\n", ". "):
        stop = text.find(marker, match.end())
        if stop >= 0:
            end = min(end, stop + (1 if marker == ". " else 0))
    clipped_start = start < match.start() - 120
    start = max(start, match.start() - 120)
    end = min(end, match.end() + 180)
    return (
        ("…" if clipped_start else "")
        + text[start:end].strip()
        + ("…" if end < len(text) and text[end - 1] != "." else "")
    )
