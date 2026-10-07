"""Compare the Tailored Resume against its immutable Base Resume Fact snapshot."""

from typing import Literal

from pydantic import BaseModel, Field

from app.tailoring.content import DraftContent, FactSnapshot


class DiffLine(BaseModel):
    text: str
    kind: Literal["unchanged", "rewritten", "added_from_portfolio", "reordered", "removed"]
    fact_refs: list[str]
    before: list[str] = Field(default_factory=list)


def moved(order: list[int]) -> set[int]:
    """Indexes of items out of their original order: everything outside the longest run
    that is still in order. One line moved up marks that line, not every line after it."""
    if not order:
        return set()
    # Longest increasing subsequence with back-pointers (O(n log n)).
    tails: list[int] = []
    tail_index: list[int] = []
    parent = [-1] * len(order)
    for i, value in enumerate(order):
        low, high = 0, len(tails)
        while low < high:
            mid = (low + high) // 2
            if tails[mid] <= value:  # equal places (two lines, one Fact) are in order
                low = mid + 1
            else:
                high = mid
        if low == len(tails):
            tails.append(value)
            tail_index.append(i)
        else:
            tails[low] = value
            tail_index[low] = i
        parent[i] = tail_index[low - 1] if low else -1
    keep = set()
    i = tail_index[-1]
    while i != -1:
        keep.add(i)
        i = parent[i]
    return set(range(len(order))) - keep


def resume_diff(content: DraftContent, facts: list[FactSnapshot]) -> list[DiffLine]:
    by_ref = {fact.ref: fact for fact in facts}
    base_position = {fact.ref: i for i, fact in enumerate(facts) if fact.in_base_resume}
    used = {ref for line in content.resume for ref in line.fact_refs}
    # Each line's place in the Base Resume is its first base Fact.
    placed = [
        (i, min(base_position[ref] for ref in line.fact_refs if ref in base_position))
        for i, line in enumerate(content.resume)
        if any(ref in base_position for ref in line.fact_refs)
    ]
    out_of_order = {placed[j][0] for j in moved([position for _, position in placed])}
    result = []
    for index, line in enumerate(content.resume):
        sources = [by_ref[ref] for ref in line.fact_refs if ref in by_ref]
        before = [fact.text for fact in sources]
        if any(not fact.in_base_resume for fact in sources):
            kind = "added_from_portfolio"
        elif line.text not in before:
            kind = "rewritten"
        elif index in out_of_order:
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
