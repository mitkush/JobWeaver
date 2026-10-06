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
