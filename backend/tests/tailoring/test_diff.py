"""Base Resume diff: "Reordered" only for lines that actually moved (FR-E5)."""

import uuid

from app.tailoring.content import DraftContent, DraftLine, FactSnapshot
from app.tailoring.diff import moved, resume_diff

FACTS = [
    FactSnapshot(ref=f"F{i}", id=uuid.uuid4(), kind="experience", group="Acme",
                 text=f"Fact {i}", in_base_resume=True)
    for i in range(1, 5)
]  # fmt: skip


def content(*lines: tuple[str, list[str]]) -> DraftContent:
    return DraftContent(
        resume=[DraftLine(text=text, fact_refs=refs) for text, refs in lines],
        cover_letter=[DraftLine(text="Cover", fact_refs=["F1"])],
    )


def kinds(diff) -> list[str]:
    return [d.kind for d in diff if d.kind != "removed"]


def test_moved_marks_only_the_lines_that_left_their_place():
    assert moved([0, 1, 2, 3]) == set()
    assert moved([0, 3, 1, 2]) == {1}
    assert moved([0, 1, 1, 2]) == set()  # two lines from one Fact are still in order


def test_lines_sharing_a_fact_are_not_reordered():
    diff = resume_diff(content(("Fact 1", ["F1"]), ("Fact 1", ["F1"]), ("Fact 2", ["F2"])), FACTS)
    assert kinds(diff) == ["unchanged", "unchanged", "unchanged"]


def test_one_moved_line_marks_only_that_line():
    diff = resume_diff(
        content(("Fact 1", ["F1"]), ("Fact 4", ["F4"]), ("Fact 2", ["F2"]), ("Fact 3", ["F3"])),
        FACTS,
    )
    assert kinds(diff) == ["unchanged", "reordered", "unchanged", "unchanged"]
