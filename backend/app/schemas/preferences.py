from pydantic import BaseModel, Field, field_validator

from app.adapters.base import WorkMode


class PreferenceLocation(BaseModel):
    city: str | None = Field(default=None, max_length=120)
    country: str = Field(pattern=r"^[A-Za-z]{2}$")

    @field_validator("country")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("city")
    @classmethod
    def _blank_city(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


def _clean(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        cleaned = " ".join(value.split())
        if cleaned and cleaned.lower() not in seen:
            seen[cleaned.lower()] = cleaned
    return list(seen.values())


class PreferencesIn(BaseModel):
    titles: list[str] = Field(min_length=1, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    # No places means global coverage, independently of work mode.
    locations: list[PreferenceLocation] = Field(default_factory=list, max_length=30)
    work_modes: list[WorkMode] = Field(min_length=1)

    @field_validator("titles", "keywords")
    @classmethod
    def _dedupe(cls, values: list[str]) -> list[str]:
        if any(len(v) > 100 for v in values):
            raise ValueError("Each entry must be 100 characters or fewer")
        return _clean(values)

    @field_validator("titles")
    @classmethod
    def _non_empty(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("Add at least one job title")
        return values


class PreferencesOut(PreferencesIn):
    pass
