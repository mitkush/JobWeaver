import pytest

from app.adapters.linkedin_brightdata import LinkedInBrightDataAdapter
from app.core.config import Settings
from app.services.provider_credentials import credentials


@pytest.mark.parametrize(
    "primary,backups,expected",
    [
        ("one,two,three", "", ["one", "two", "three"]),
        (" one, ,two,one ", "two, three, ", ["one", "two", "three"]),
        ("", "one,two,three", ["one", "two", "three"]),
        ("one", "two,three", ["one", "two", "three"]),
        (" , ", ",", []),
    ],
)
def test_brightdata_accepts_ordered_key_lists(primary, backups, expected):
    settings = Settings(brightdata_api_key=primary, brightdata_api_keys=backups)
    options = credentials(LinkedInBrightDataAdapter, settings)
    assert [option.settings.brightdata_api_key for option in options] == expected
    assert len({option.fingerprint for option in options}) == len(expected)
    assert settings.brightdata_api_key == primary
