"""Preference keywords found in a Job (FR-D1): plain code, no AI call per User.

A differently titled Job reaches the Feed's keyword section only through the keywords the
User chose in Preferences; the Fact Bank plays no part. Spellings of one skill count once
("Rails" = "Ruby on Rails"), and only whole skill phrases count ("Rails" never matches
inside "guardrails"). Case does not matter, except for the few skill names that are also
common English words ("Go", "REST"), which count only when written with a capital.

Each keyword is matched on its own: a longer phrase another User chose ("Rails developer")
never hides a shorter one ("Rails"), so one User's keywords cannot change another's Feed."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.tailoring.skills import PROSE_WORDS, canonical_skill, spellings

Where = Literal["requirements", "title", "description"]


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


@lru_cache(maxsize=1024)
def _pattern(canonical: str) -> re.Pattern[str]:
    terms = sorted(set(spellings(canonical)), key=len, reverse=True)
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
    rule: KeywordRule,
    in_requirements: set[str],
    in_description: set[str],
    in_title: set[str] | None = None,
) -> list[KeywordMatch]:
    """The rule's keywords found in the Job's title or job description, each skill once:
    the skills extracted from the description first, then the title, then its text."""
    found: list[KeywordMatch] = []
    for keyword in rule.keywords:
        where: Where | None = None
        if keyword.canonical in in_requirements:
            where = "requirements"
        elif in_title and keyword.canonical in in_title:
            where = "title"
        elif keyword.canonical in in_description:
            where = "description"
        if where:
            found.append(KeywordMatch(keyword.label, where, keyword.core))
    return found


def has_core(found: Sequence[KeywordMatch]) -> bool:
    """Core keywords are must-haves: every Job in the Feed names at least one."""
    return any(m.core for m in found)


def qualifies(rule: KeywordRule, found: Sequence[KeywordMatch]) -> bool:
    """At least one core keyword, and at least min_matches distinct keywords in total."""
    return has_core(found) and len(found) >= rule.min_matches
