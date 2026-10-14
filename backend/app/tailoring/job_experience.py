import re

_EXPERIENCE_REQUIREMENT = re.compile(
    r"\b(?P<minimum>\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:[-–]\s*(?P<maximum>\d+(?:\.\d+)?)\s*)?"
    r"years?\s*(?:of\s+)?(?:(?:relevant|professional|industry)\s+)?experience\b",
    re.IGNORECASE,
)


def experience_requirement(description: str) -> str | None:
    """Return an explicit years-of-experience requirement stated in a job description."""
    match = _EXPERIENCE_REQUIREMENT.search(description)
    if match is None:
        return None
    minimum = match.group("minimum")
    maximum = match.group("maximum")
    return f"{minimum}–{maximum} years" if maximum else f"{minimum}+ years"
