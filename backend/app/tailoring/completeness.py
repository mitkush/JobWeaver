"""Keep supported job skills visible in the tailored resume's Skills section."""

from collections.abc import Iterable

from app.tailoring.content import DraftContent, DraftLine, FactSnapshot
from app.tailoring.skills import canonical_skill, covers, user_skills


def include_supported_skills(
    content: DraftContent, facts: list[FactSnapshot], required: Iterable[str]
) -> DraftContent:
    """Add only explicitly reviewed skill Facts the AI overlooked, with their trace."""
    skill_facts = {
        canonical_skill(fact.text): fact
        for fact in facts
        if fact.kind == "skill" and fact.text.strip()
    }
    written = user_skills([], [line.text for line in content.resume if line.section == "Skills"])
    missing: list[tuple[str, FactSnapshot]] = []
    seen: set[str] = set()
    for name in required:
        canonical = canonical_skill(name)
        if canonical in seen or canonical not in skill_facts or covers(written, canonical):
            continue
        seen.add(canonical)
        missing.append((skill_facts[canonical].text, skill_facts[canonical]))
        if len(missing) == 8:
            break
    if not missing or len(content.resume) >= 50:
        return content
    result = content.model_copy(deep=True)
    result.resume.append(
        DraftLine(
            text="Skills: " + ", ".join(name for name, _ in missing),
            fact_refs=[fact.ref for _, fact in missing],
            section="Skills",
        )
    )
    return result


def resume_words(content: DraftContent) -> int:
    return sum(len(line.text.split()) for line in content.resume)


def needs_development(content: DraftContent, facts: list[FactSnapshot]) -> bool:
    """Only rich evidence banks justify a second call; sparse resumes stay honest.

    This is an internal generation heuristic, never a quality score or a hard minimum.
    A checked result has already lost any unsupported lines, so assess that result.
    """
    work = {(f.group, f.text) for f in facts if f.kind in {"experience", "project", "achievement"}}
    return (
        resume_words(content) < 380
        and len(work) >= 8
        and sum(len(text.split()) for _, text in work) >= 450
    )
