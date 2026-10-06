import pytest

from app.models import Preference
from app.services.feed import job_matches, location_matches, title_matches


@pytest.mark.parametrize(
    ("job", "wanted", "ok"),
    [
        ("Senior Backend Engineer", ["Backend Engineer"], True),
        ("Back-End Developer", ["Backend Engineer"], True),
        ("SDE II", ["Software Engineer"], True),
        ("Engineer, Backend (Payments)", ["backend engineer"], True),
        ("Data Engineer", ["Backend Engineer"], False),
        ("Backend Engineer", ["Senior Backend Engineer"], False),
        ("Product Manager", ["Backend Engineer", "Product Manager"], True),
        ("Dev-Ops Engineer", ["DevOps Engineer"], True),
        ("DevOps Engineer", ["Dev Ops Engineer"], True),
        ("Python Dev", ["Python Developer"], True),
        ("ML Engineer", ["Machine Learning Engineer"], True),
        ("Full-Stack Developer", ["Fullstack Engineer"], True),
        ("DevOps Engineer", ["Backend Engineer"], False),
    ],
)
def test_title_matches(job, wanted, ok):
    assert title_matches(job, wanted) is ok


BLR = {"city": "Bengaluru", "country": "IN"}


@pytest.mark.parametrize(
    ("locations", "work_mode", "wanted", "modes", "ok"),
    [
        ([BLR], "hybrid", [BLR], ["hybrid"], True),
        ([{"city": "Pune", "country": "IN"}, BLR], None, [BLR], ["onsite"], True),
        ([{"city": "Pune", "country": "IN"}], None, [BLR], ["onsite"], False),
        ([{"city": "Pune", "country": "IN"}], None, [{"city": None, "country": "IN"}], [], True),
        ([{"city": None, "country": None, "remote": True}], "remote", [BLR], ["remote"], True),
        ([{"city": None, "country": "US", "remote": True}], "remote", [BLR], ["remote"], False),
        ([], None, [BLR], ["onsite"], True),
        ([{"city": "Berlin", "country": "DE"}], "onsite", [], ["onsite"], True),
        ([BLR], "onsite", [], ["onsite"], True),
        # Remote (WFH): only the country has to match, not the office city.
        ([{"city": "Pune", "country": "IN", "remote": True}], "remote", [BLR], ["remote"], True),
        ([{"city": "Pune", "country": "IN"}], "remote", [BLR], ["remote"], True),
        ([{"city": "Berlin", "country": "DE"}], "remote", [BLR], ["remote"], False),
        # Onsite and hybrid: the office city matters.
        ([{"city": "Pune", "country": "IN"}], "onsite", [BLR], ["onsite"], False),
        ([{"city": "Pune", "country": "IN"}], "hybrid", [BLR], ["hybrid"], False),
        (
            [{"city": "Pune", "country": "IN", "remote": True}],
            "remote",
            [{"country": "IN", "city": None}],
            ["remote"],
            True,
        ),
    ],
)
def test_location_matches(locations, work_mode, wanted, modes, ok):
    assert location_matches(locations, work_mode, wanted, modes) is ok


def test_work_mode_must_be_wanted_when_known():
    pref = Preference(titles=["Backend Engineer"], locations=[BLR], work_modes=["remote"])
    assert not job_matches("Backend Engineer", [BLR], "onsite", pref)
    onsite = Preference(titles=["Backend Engineer"], locations=[BLR], work_modes=["onsite"])
    remote_in = [{"city": None, "country": "IN", "remote": True}]
    assert not job_matches("Backend Engineer", remote_in, "remote", onsite)
    assert job_matches(
        "Backend Engineer",
        [BLR],
        None,
        Preference(titles=["Backend Engineer"], locations=[BLR], work_modes=["onsite"]),
    )


def test_global_location_does_not_override_work_mode():
    pref = Preference(titles=["Backend Engineer"], locations=[], work_modes=["remote"])
    place = [{"city": "Berlin", "country": "DE"}]
    assert job_matches("Backend Engineer", place, "remote", pref)
    assert not job_matches("Backend Engineer", place, "onsite", pref)


@pytest.mark.parametrize(
    ("wanted", "modes", "job_places", "job_mode", "shown"),
    [
        (
            [{"country": "IN", "city": None}],
            ["remote"],
            [{"city": None, "country": "IN", "remote": True}],
            "remote",
            True,
        ),
        (
            [{"country": "IN", "city": None}],
            ["remote"],
            [{"city": "Pune", "country": "IN"}],
            "remote",
            True,
        ),
        (
            [{"country": "IN", "city": None}],
            ["remote"],
            [{"city": "Berlin", "country": "DE"}],
            "remote",
            False,
        ),
        (
            [{"country": "IN", "city": None}],
            ["remote"],
            [{"city": "Pune", "country": "IN"}],
            "onsite",
            False,
        ),
        ([BLR], ["onsite"], [{"city": "Pune", "country": "IN"}], "onsite", False),
        ([], ["remote"], [{"city": "Austin", "country": "US"}], "remote", True),
    ],
)
def test_agreed_location_and_work_mode_rules(wanted, modes, job_places, job_mode, shown):
    """The table agreed for PR 4: location AND work mode, city ignored for WFH jobs."""
    pref = Preference(titles=["Backend Engineer"], locations=wanted, work_modes=modes)
    assert job_matches("Backend Engineer", job_places, job_mode, pref) is shown
