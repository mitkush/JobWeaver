"""Years of experience counted by code from the User's role dates (ADR-0005).

The AI never picks the number: code reads the date ranges in Experience Facts
("Senior Software Developer, March 2023 to Present", "2021 - Feb 2023"), merges
overlapping roles, and a claim of "N+ years" is allowed only up to that total.
"""

import re
from collections.abc import Iterable
from datetime import date

from app.tailoring.content import FactSnapshot

_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        1,
    )
    for name in names
}
_MONTH = r"(?:(?P<{0}m>[A-Za-z]{{3,9}})\.?\s+)?(?P<{0}y>(?:19|20)\d\d)"
_RANGE = re.compile(
    _MONTH.format("a")
    + r"\s*(?:-|\u2013|\u2014|to|until)\s*"
    + r"(?:(?P<now>present|current|now|today|date)|"
    + _MONTH.format("b")
    + ")",
    re.IGNORECASE,
)


def _month(name: str | None, *, end: bool) -> int:
    """A year without a month counts the shortest span it can mean: a role "from 2021"
    starts in December, one "to 2023" ends in January, so the total never overstates."""
    if name is None or name.casefold() not in _MONTHS:
        return 1 if end else 12
    return _MONTHS[name.casefold()]


def role_periods(facts: Iterable[FactSnapshot], today: date) -> list[tuple[int, int]]:
    """Each role's (first month, last month) as month numbers, from Experience Facts."""
    periods = []
    now = today.year * 12 + today.month - 1
    for fact in facts:
        if fact.kind != "experience":
            continue
        for match in _RANGE.finditer(fact.text):
            start = int(match["ay"]) * 12 + _month(match["am"], end=False) - 1
            if match["now"]:
                stop = now
            else:
                stop = int(match["by"]) * 12 + _month(match["bm"], end=True) - 1
            stop = min(stop, now)
            if start <= stop:
                periods.append((start, stop))
    return periods


def experience_years(facts: Iterable[FactSnapshot], today: date | None = None) -> float | None:
    """Total years across the User's roles, overlaps counted once, rounded down to the
    half year ("5.5" for 5 years 8 months). None when no Fact gives role dates."""
    periods = sorted(role_periods(facts, today or date.today()))
    if not periods:
        return None
    months, end = 0, -1
    for start, stop in periods:
        if stop <= end:
            continue
        months += stop - max(start, end + 1) + 1
        end = stop
    return int(months / 6) / 2


def years_text(years: float) -> str:
    """ "5.5+" or "5+": the form the resume and email use."""
    return f"{years:g}+"


def role_dates(text: str) -> tuple[str, str | None, int, int] | None:
    """The first date range in a line, as ("YYYY" or "YYYY-MM" start, end or None when
    current, match start, match end). Months are kept only when the line names them."""
    match = _RANGE.search(text)
    if match is None:
        return None

    def when(year: str, month: str | None) -> str:
        if month and month.casefold() in _MONTHS:
            return f"{year}-{_MONTHS[month.casefold()]:02d}"
        return year

    start = when(match["ay"], match["am"])
    end = None if match["now"] else when(match["by"], match["bm"])
    return start, end, match.start(), match.end()
