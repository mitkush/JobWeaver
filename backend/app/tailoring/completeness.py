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
