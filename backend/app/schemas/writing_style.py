from pydantic import BaseModel, Field


class WritingStyleOut(BaseModel):
    traits: list[str]
    excerpts: list[str]
    built_at: str | None = None


class WritingStyleIn(BaseModel):
    traits: list[str] = Field(default_factory=list, max_length=8)
    excerpts: list[str] = Field(default_factory=list, max_length=3)
