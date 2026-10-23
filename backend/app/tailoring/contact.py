"""The User's contact details, taken only from their reviewed Facts (ADR-0005).

Used by the resume header and the application email signature."""

import re

from app.tailoring.content import FactSnapshot

_PHONE = re.compile(r"(?<![\w+])\+?\d[\d ().-]{7,}\d(?!\w)")
# A profile, not a repository: "github.com/asha", never "github.com/asha/ledger".
_PROFILE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in|github\.com)/[\w.-]+/?(?![\w/])",
    re.IGNORECASE,
)
_CONTACT_LABEL = re.compile(
    r"^(?:phone|mobile|tel|linkedin|github|location|portfolio|website)\s*:\s*", re.IGNORECASE
)


def contact_facts(facts: list[FactSnapshot]) -> list[str]:
    """Contact details the User reviewed as Facts, copied as written: anything filed
    under the Contact group, and phone numbers and profile links in link Facts."""
    parts: list[str] = []
    for fact in facts:
        text = " ".join(fact.text.split())
        if fact.group.strip().casefold() == "contact":
            parts.append(_CONTACT_LABEL.sub("", text))
        elif fact.kind == "link":
            parts += [m.group(0) for m in _PHONE.finditer(text)]
            parts += [m.group(0).rstrip("/") for m in _PROFILE.finditer(text)]
    phones = [p for p in parts if _PHONE.fullmatch(p)]
    return list(dict.fromkeys(phones + [p for p in parts if p not in phones]))


def is_phone(text: str) -> bool:
    return bool(_PHONE.fullmatch(text))


def first_phone(text: str) -> str | None:
    match = _PHONE.search(text)
    return match.group(0) if match else None


def profile_links(text: str) -> list[str]:
    """LinkedIn and GitHub profile links in a line, without a trailing slash."""
    return [m.group(0).rstrip("/") for m in _PROFILE.finditer(text)]


# Web addresses and emails in a line, printed as clickable links.
LINK = re.compile(
    r"(https?://[^\s|,;()]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    # A bare .io/.dev/.app/.ai name needs a path: "Socket.io" is a library, not a link.
    r"|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\."
    r"(?:(?:com|org|net|in|me|co)(?:/[^\s|,;()]*)?|(?:io|dev|app|ai)/[^\s|,;()]*))",
    re.IGNORECASE,
)


def href(target: str) -> str:
    if "@" in target and "/" not in target:
        return "mailto:" + target
    return target if target.startswith("http") else "https://" + target
