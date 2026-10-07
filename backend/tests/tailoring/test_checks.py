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


@pytest.mark.parametrize(
    ("text", "refs"),
    [
        ("Built a billing API serving 40 merchant teams", ["F2"]),
        ("Designed and built a scalable billing API in Python for 40 merchant teams", ["F2", "F1"]),
    ],
)
def test_rewording_is_allowed(text, refs):
    # FR-E2: Facts may be reworded in the Job's language; only inventions are rejected.
    line = DraftLine(text=text, fact_refs=refs, section="Summary")
    assert line_problem(line, FACTS) is None


def test_cover_letter_may_name_the_company_and_role_but_not_new_skills():
    from app.tailoring.checks import check

    package = DraftContent(
        resume=[DraftLine(id="r", text="Python", fact_refs=["F1"], section="Skills")],
        cover_letter=[
            DraftLine(id="a", text="Dear Hiring Manager,", fact_refs=["F2"]),
            DraftLine(
                id="b",
                text="I am excited to apply for the Go Developer role at Initech.",
                fact_refs=["F2"],
            ),
            DraftLine(id="c", text="I have years of Go experience.", fact_refs=["F1"]),
        ],
    )
    result = check(package, FACTS, job_title="Go Developer", company="Initech")
    assert [line.id for line in result.content.cover_letter] == ["a", "b"]
    assert "Go is not in your Fact Bank" in result.removed[0]


def test_a_resume_line_cannot_mix_two_employers():
    line = DraftLine(text="Used PostgreSQL for the billing API", fact_refs=["F2", "F3"])
    assert line_problem(line, FACTS) == "It mixes Facts from different employers or projects"


def test_manual_lines_are_flagged_not_removed():
    from app.tailoring.checks import check

    package = content()
    package.resume.append(
        DraftLine(id="m", text="Ran Kubernetes clusters", fact_refs=["F1"], manual=True)
    )
    result = check(package, FACTS)
    assert [line.id for line in result.content.resume][-1] == "m"
    assert result.removed == []
    assert result.flagged[0].startswith("Your edit in the resume:")
    assert "Kubernetes is not in your Fact Bank" in result.flagged[0]


@pytest.mark.parametrize(
    ("text", "refs", "reason"),
    [
        # Ambiguous names count at the start of a line and in lowercase lists (Codex review).
        ("Go services for 40 merchant teams", ["F2"], "Go is not in your Fact Bank"),
        ("React dashboards for 40 merchant teams", ["F2"], "React is not in your Fact Bank"),
        ("Built the billing API with react and rust", ["F2"], "react is not in your Fact Bank"),
        # A version after a technology is only accepted when the Fact Bank states it.
        ("Built Python 999 services", ["F1"], "The number 999 is not in the Facts it cites"),
        # Names at the start of a sentence are checked too.
        ("Google employed me", ["F2"], "Google is not in your Fact Bank"),
    ],
)
def test_review_bypasses_are_closed(text, refs, reason):
    line = DraftLine(text=text, fact_refs=refs, section="Summary")
    assert line_problem(line, FACTS) == reason


@pytest.mark.parametrize(
    "text",
    [
        "Helped the team go to market faster with the billing API",
        "Backend engineer who built billing APIs for 40 merchant teams",
        "Designed and built a scalable billing API for 40 merchant teams",
    ],
)
def test_ordinary_english_is_not_mistaken_for_claims(text):
    line = DraftLine(text=text, fact_refs=["F2"], section="Summary")
    assert line_problem(line, FACTS) is None


def test_a_version_stated_in_the_fact_bank_is_accepted():
    facts = [*FACTS[1:], FACTS[0].model_copy(update={"text": "Python 3.12"})]
    line = DraftLine(text="Python 3.12 developer", fact_refs=["F1"], section="Summary")
    assert line_problem(line, facts) is None


def _line(text, *refs, section="Experience"):
    return DraftLine(text=text, fact_refs=list(refs or ["F2"]), section=section)


def test_labels_verbs_and_ordinary_words_are_not_names():
    from app.tailoring.checks import check

    package = DraftContent(
        resume=[
            _line("Languages: Python", "F1", section="Skills"),
            _line("Built and Designed the billing API used by 40 merchant teams"),
            _line("Built the billing API and Conducted reviews used by 40 merchant teams"),
            _line("Built the billing API with Partner teams; 40 merchant teams used it"),
        ],
        cover_letter=[_line("Built the billing API used by 40 merchant teams")],
    )
    result = check(package, FACTS, job_text="You will work with partner teams.")
    assert result.warnings == []


def test_invented_names_numbers_and_leadership_are_still_removed():
    from app.tailoring.checks import check

    package = DraftContent(
        resume=[
            _line("Built the billing API at Google used by 40 merchant teams"),
            _line("Built the billing API used by 400 merchant teams"),
            _line("Led the billing API used by 40 merchant teams"),
            _line("Built the billing API in Django for 40 merchant teams"),
        ],
        cover_letter=[_line("Built the billing API used by 40 merchant teams")],
    )
    result = check(package, FACTS, job_text="Designed for google-scale.")
    assert result.content.resume == []
    joined = " ".join(result.warnings)
    for reason in ("Google is not", "The number 400", '"led" is not', "Django is not"):
        assert reason in joined


def test_ai_written_as_a_name_in_the_fact_bank_covers_ai():
    from app.tailoring.checks import check

    facts = [
        *FACTS,
        FactSnapshot(
            ref="F5",
            id=uuid.uuid4(),
            kind="experience",
            group="Acme Corp",
            text="Built AI evaluation pipelines",
            in_base_resume=True,
        ),
    ]
    package = DraftContent(
        resume=[_line("Built AI evaluation pipelines", "F5")],
        cover_letter=[_line("Built AI evaluation pipelines", "F5")],
    )
    assert check(package, facts).warnings == []


def test_name_placeholders_are_filled_and_unknown_ones_removed():
    from app.tailoring.checks import check
    from app.tailoring.placeholders import fill_placeholders

    package = DraftContent(
        resume=[_line("Built the billing API used by 40 merchant teams")],
        cover_letter=[_line("Built the billing API used by 40 merchant teams")],
        email_body=[
            _line("I am applying to [Company Name] as [Job Title]."),
            _line("Best regards, Your Name"),
            _line("Call me on [Phone Number]."),
        ],
    )
    filled = fill_placeholders(
        package, name="Asha Rao", email="asha@example.com", company="Initech", title="SRE"
    )
    assert [line.text for line in filled.email_body[:2]] == [
        "I am applying to Initech as SRE.",
        "Best regards, Asha Rao",
    ]
    result = check(filled, FACTS, job_title="SRE", company="Initech", user_name="Asha Rao")
    assert [line.text for line in result.content.email_body] == [
        "I am applying to Initech as SRE.",
        "Best regards, Asha Rao",
    ]
    assert result.warnings == ["Removed a email line: It contains the placeholder [Phone Number]"]
