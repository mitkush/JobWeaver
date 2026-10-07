"""Preference keywords found in a Job (FR-D1): plain code, no AI call per User.

A differently titled Job reaches the Feed's keyword section only through the keywords the
User chose in Preferences; the Fact Bank plays no part. Spellings of one skill count once
("Rails" = "Ruby on Rails"), and only whole skill phrases count ("Rails" never matches
inside "guardrails")."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from app.tailoring.checks import technologies_in
from app.tailoring.skills import canonical_skill

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


def mentioned(text: str, terms: Iterable[str]) -> set[str]:
    """Canonical names of the skills named in the text, the User's own terms included."""
    return set(technologies_in(text, terms)) if text else set()


def keyword_matches(
    rule: KeywordRule, in_requirements: set[str], in_description: set[str]
) -> list[KeywordMatch]:
    """The rule's keywords found in the Job, requirements first, each skill once."""
    found: list[KeywordMatch] = []
    for keyword in rule.keywords:
        if keyword.canonical in in_requirements:
            found.append(KeywordMatch(keyword.label, "requirements", keyword.core))
        elif keyword.canonical in in_description:
            found.append(KeywordMatch(keyword.label, "description", keyword.core))
    return found


def qualifies(rule: KeywordRule, found: Sequence[KeywordMatch]) -> bool:
    """At least one core keyword, and at least min_matches distinct keywords in total."""
    return any(m.core for m in found) and len(found) >= rule.min_matches
