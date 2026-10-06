import uuid

import pytest

from app.tailoring.checks import check_content, line_problem
from app.tailoring.content import DraftContent, DraftLine, FactSnapshot
from app.tailoring.diff import resume_diff

FACTS = [
    FactSnapshot(
        ref="F1", id=uuid.uuid4(), kind="skill", group="", text="Python", in_base_resume=True
    ),
    FactSnapshot(
        ref="F2",
        id=uuid.uuid4(),
        kind="experience",
        group="Acme Corp",
        text="Built the billing API used by 40 merchant teams",
        in_base_resume=True,
    ),
    FactSnapshot(
        ref="F3",
        id=uuid.uuid4(),
        kind="project",
        group="Ledger Sync",
        text="Used PostgreSQL for the ledger pipeline",
        in_base_resume=False,
    ),
    FactSnapshot(
        ref="F4",
        id=uuid.uuid4(),
        kind="education",
        group="State University",
        text="B.Tech in Computer Science, 2020",
        in_base_resume=True,
    ),
]


@pytest.mark.parametrize(
    ("text", "refs", "truthful"),
    [
        ("Python", ["F1"], True),
        ("Built the billing API used by 40 merchant teams", ["F2"], True),
        ("Developed the billing API used by 40 merchant teams", ["F2"], True),
        ("Used Postgres for the ledger pipeline", ["F3"], True),
        ("B.Tech in Computer Science, 2020", ["F4"], True),
        ("Built the billing API used by 2 million users", ["F2"], False),
        ("Built the billing API used by 41 merchant teams", ["F2"], False),
        ("Kubernetes", ["F1"], False),
        ("Worked at Google", ["F2"], False),
        ("B.Tech in Computer Science, 2021", ["F4"], False),
        ("Expert Python engineer", ["F1"], False),
        ("I have years of Go experience", ["F1"], False),
        ("Led 40 merchant teams", ["F2"], False),
        ("Built Python applications", ["F1"], False),
        ("Python", ["other-user-fact"], False),
        ("Python", ["F1", "F1"], False),
    ],
)
def test_labelled_truthfulness_set(text, refs, truthful):
    line = DraftLine(text=text, fact_refs=refs)
    assert (line_problem(line, FACTS) is None) is truthful


def content():
    return DraftContent(
        resume=[
            DraftLine(id="r1", text="Python", fact_refs=["F1"], section="Skills"),
            DraftLine(
                id="r2",
                text="Used PostgreSQL for the ledger pipeline",
                fact_refs=["F3"],
                section="Projects",
            ),
        ],
        cover_letter=[DraftLine(id="c1", text="Python", fact_refs=["F1"])],
    )


def test_unknown_fact_and_duplicate_line_identifiers_are_removed():
    package = content()
    package.resume.append(DraftLine(id="r1", text="Kubernetes", fact_refs=["F1"]))
    checked, warnings = check_content(package, FACTS)
    assert len(checked.resume) == 2
    assert len(warnings) == 1
    assert len(package.resume) == 3


def test_diff_covers_portfolio_and_removed_base_facts():
    changes = resume_diff(content(), FACTS)
    assert changes[0].kind == "unchanged"
    assert changes[1].kind == "added_from_portfolio"
    assert {c.fact_refs[0] for c in changes if c.kind == "removed"} == {"F2", "F4"}
