"""Compare the Tailored Resume against its immutable Base Resume Fact snapshot."""

from typing import Literal

from pydantic import BaseModel, Field

from app.tailoring.content import DraftContent, FactSnapshot


class DiffLine(BaseModel):
    text: str
    kind: Literal["unchanged", "rewritten", "added_from_portfolio", "reordered", "removed"]
    fact_refs: list[str]
    before: list[str] = Field(default_factory=list)


def resume_diff(content: DraftContent, facts: list[FactSnapshot]) -> list[DiffLine]:
    by_ref = {fact.ref: fact for fact in facts}
    base = [fact.ref for fact in facts if fact.in_base_resume]
    used = {ref for line in content.resume for ref in line.fact_refs}
    current = [ref for line in content.resume for ref in line.fact_refs if ref in base]
    ordered = [ref for ref in base if ref in used]
    result = []
    for line in content.resume:
        sources = [by_ref[ref] for ref in line.fact_refs if ref in by_ref]
        before = [fact.text for fact in sources]
        if any(not fact.in_base_resume for fact in sources):
            kind = "added_from_portfolio"
        elif line.text not in before:
            kind = "rewritten"
        elif current != ordered:
            kind = "reordered"
        else:
            kind = "unchanged"
        result.append(DiffLine(text=line.text, kind=kind, fact_refs=line.fact_refs, before=before))
    result.extend(
        DiffLine(text=fact.text, kind="removed", fact_refs=[fact.ref], before=[fact.text])
        for fact in facts
        if fact.in_base_resume and fact.ref not in used
    )
    return result
