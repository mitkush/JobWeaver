import uuid
from datetime import date

import pytest

from app.tailoring.content import FactSnapshot
from app.tailoring.experience import experience_years, years_text

TODAY = date(2026, 10, 9)


def role(text, kind="experience"):
    return FactSnapshot(
        ref="F1", id=uuid.uuid4(), kind=kind, group="Shriffle", text=text, in_base_resume=True
    )


@pytest.mark.parametrize(
    ("texts", "years"),
    [
        (["Senior Software Developer, March 2023 to Present"], 3.5),
        (
            [
                "Senior Software Developer, March 2023 to Present",
                "Software Developer, January 2021 to February 2023",
            ],
            5.5,
        ),
        # A year without a month counts the shortest span it can mean.
        (
            [
                "Senior Software Developer, March 2023 to Present",
                "Software Developer, 2021 to February 2023",
            ],
            4.5,
        ),
        # Overlapping roles count once.
        (["Acme, Jan 2020 - Dec 2020", "Globex, Jun 2020 – Mar 2021"], 1.0),
        (["Built the billing API"], None),
    ],
)
def test_years_come_from_role_dates(texts, years):
    assert experience_years([role(t) for t in texts], TODAY) == years


def test_only_experience_facts_count():
    assert experience_years([role("B.Tech, 2016 to 2020", kind="education")], TODAY) is None


def test_years_text():
    assert (years_text(5.5), years_text(5.0)) == ("5.5+", "5+")
