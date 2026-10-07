"""Template placeholders an AI model sometimes leaves in a Draft ("[Your Name]",
"Your Name", "[Company Name]"), filled from what JobWeaver already knows.

A placeholder that cannot be filled ("[Phone Number]") is left for the checker, which
removes the AI line rather than send a template gap to an employer (ADR-0005)."""

import re

from app.tailoring.content import DraftContent

# Bracketed, braced or angled text that reads like a template slot.
PLACEHOLDER = re.compile(r"[\[{<]\s*([A-Za-z][A-Za-z .'/-]{0,40}?)\s*[\]}>]")
# The same slot written without brackets, as models also do.
_BARE = re.compile(r"\b(?:Your (?:Full )?Name|Your Email(?: Address)?)\b")

_SLOTS: dict[str, str] = {
    "name": "name",
    "your name": "name",
    "full name": "name",
    "your full name": "name",
    "applicant name": "name",
    "candidate name": "name",
    "email": "email",
    "your email": "email",
    "email address": "email",
    "your email address": "email",
    "company": "company",
    "company name": "company",
    "hiring company": "company",
    "organization": "company",
    "organisation": "company",
    "job title": "title",
    "position": "title",
    "position title": "title",
    "role": "title",
    "role title": "title",
}


def fill_placeholders(
    content: DraftContent, *, name: str, email: str, company: str, title: str
) -> DraftContent:
    values = {"name": name, "email": email, "company": company, "title": title}

    def slot(key: str) -> str | None:
        value = values.get(_SLOTS.get(" ".join(key.casefold().split()), ""), "")
        return value.strip() or None

    def bracketed(match: re.Match[str]) -> str:
        return slot(match.group(1)) or match.group(0)

    def bare(match: re.Match[str]) -> str:
        return slot(match.group(0)) or match.group(0)

    filled = content.model_copy(deep=True)
    for part in ("resume", "cover_letter", "email_body"):
        for line in getattr(filled, part):
            line.text = _BARE.sub(bare, PLACEHOLDER.sub(bracketed, line.text))
    filled.email_subject = PLACEHOLDER.sub(bracketed, filled.email_subject)
    return filled
