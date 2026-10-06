"""Gemini's terms require paid services for users in these regions (ADR-0012)."""

# fmt: off
EEA_CH_UK = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "IS", "LI", "NO", "CH", "GB",
})
# fmt: on


def ai_region_blocked(country: str | None, gemini_free_tier: bool) -> bool:
    return gemini_free_tier and country is not None and country.upper() in EEA_CH_UK
