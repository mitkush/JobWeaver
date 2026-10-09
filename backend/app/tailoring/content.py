import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Section = Literal[
    "Headline",
    "Contact",
    "Summary",
    "Skills",
    "Experience",
    "Projects",
    "Education",
    "Links",
    "Additional",
]


class DraftLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    text: str = Field(min_length=1, max_length=2000)
    fact_refs: list[str] = Field(min_length=1, max_length=20)
    section: Section = "Experience"
    # A role or project title line ("Senior Developer | Acme | 2021 to 2023"), not a bullet.
    heading: bool = False
    manual: bool = False


class DraftContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume: list[DraftLine] = Field(min_length=1, max_length=50)
    cover_letter: list[DraftLine] = Field(min_length=1, max_length=12)
    email_subject: str = Field(default="", max_length=200)
    email_body: list[DraftLine] = Field(default_factory=list, max_length=10)


class FactSnapshot(BaseModel):
    ref: str
    id: uuid.UUID
    kind: str
    group: str
    text: str
    in_base_resume: bool


def names_group(text: str, group: str) -> bool:
    """The line is the group's own title: the bare employer or project name, or the name
    followed by a role ("Acme Corp - Senior Developer"), as older Drafts wrote them."""
    folded, name = " ".join(text.split()).casefold(), " ".join(group.split()).casefold()
    if not name or not folded.startswith(name):
        return False
    rest = folded[len(name) :].strip()
    return not rest or rest[0] in "-|:–—"
