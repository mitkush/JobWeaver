import uuid

from app.tailoring.checks import check
from app.tailoring.completeness import include_supported_skills
from app.tailoring.content import DraftContent, DraftLine, FactSnapshot


def fact(ref: str, text: str, kind: str = "skill") -> FactSnapshot:
    return FactSnapshot(
        ref=ref, id=uuid.uuid4(), kind=kind, group="", text=text, in_base_resume=True
    )


def test_missing_supported_job_skills_are_added_once_with_trace():
    content = DraftContent(
        resume=[DraftLine(text="Backend: Ruby", fact_refs=["F1"], section="Skills")],
        cover_letter=[DraftLine(text="Ruby", fact_refs=["F1"])],
    )
    result = include_supported_skills(
        content,
        [fact("F1", "Ruby"), fact("F2", "Ruby on Rails"), fact("F3", "GoodJob", "project")],
        ["Ruby", "RoR", "Ruby on Rails", "GoodJob"],
    )
    assert len(result.resume) == 2
    assert result.resume[-1].text == "Skills: Ruby on Rails"
    assert result.resume[-1].fact_refs == ["F2"]
    assert len(content.resume) == 1
    checked = check(
        result, [fact("F1", "Ruby"), fact("F2", "Ruby on Rails")], job_skills=["Ruby", "RoR"]
    )
    assert checked.warnings == []
    assert checked.content.resume[-1].text == "Skills: Ruby on Rails"
