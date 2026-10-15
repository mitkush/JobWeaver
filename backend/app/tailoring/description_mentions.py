"""Versioned, deterministic description mentions, separate from AI requirements."""

import hashlib
import json
from dataclasses import dataclass

from app.tailoring.keywords import MIN_DESCRIPTION_CHARS, has_description, mentioned
from app.tailoring.skills import PROSE_WORDS, TECHNOLOGIES, canonical_skill, spellings

VOCABULARY = frozenset(canonical_skill(term) for term in TECHNOLOGIES)
# Bump when keywords._pattern/_found/has_description semantics change. Vocabulary,
# aliases, prose words and the minimum description length invalidate automatically.
MATCHER_REVISION = 1
CACHE_VERSION = hashlib.sha256(
    json.dumps(
        [
            MATCHER_REVISION,
            MIN_DESCRIPTION_CHARS,
            sorted(PROSE_WORDS),
            [(term, spellings(term)) for term in sorted(VOCABULARY)],
        ]
    ).encode()
).hexdigest()


@dataclass(frozen=True)
class DescriptionMentions:
    skills: list[str]
    usable: bool
    version: str = CACHE_VERSION


def describe(text: str) -> DescriptionMentions:
    return DescriptionMentions(sorted(mentioned(text, VOCABULARY)), has_description(text))
