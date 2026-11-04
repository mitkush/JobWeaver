"""Preference keywords found in a Job (FR-D1): spellings count once, whole phrases only,
and a core keyword gates the keyword section."""

import pytest

from app.tailoring.keywords import keyword_matches, keyword_rule, mentioned, qualifies


def found(rule, requirements: str = "", description: str = ""):
    return keyword_matches(
        rule, mentioned(requirements, rule.terms), mentioned(description, rule.terms)
    )


def test_no_core_keyword_turns_the_keyword_section_off():
    assert keyword_rule(["Ruby", "PostgreSQL"], [], 2) is None


def test_core_must_name_one_of_the_keywords():
    assert keyword_rule(["PostgreSQL"], ["Kotlin"], 1) is None


def test_spellings_of_one_skill_count_once():
    rule = keyword_rule(["Rails", "Ruby on Rails", "RoR", "PostgreSQL"], ["Rails"], 2)
    assert [k.label for k in rule.keywords] == ["Rails", "PostgreSQL"]
    matches = found(rule, description="We use Ruby on Rails, RoR tooling and Rails engines.")
    assert [m.keyword for m in matches] == ["Rails"]
    assert not qualifies(rule, matches)


def test_core_flag_follows_any_spelling_of_the_skill():
    rule = keyword_rule(["Rails", "Ruby on Rails"], ["Ruby on Rails"], 1)
    assert [(k.label, k.core) for k in rule.keywords] == [("Rails", True)]


def test_only_whole_skill_phrases_count():
    rule = keyword_rule(["Rails", "Sidekiq"], ["Rails"], 1)
    assert found(rule, description="Strong guardrails for our AI models, and Sidekiqs.") == []


def test_users_own_terms_are_matched_too():
    rule = keyword_rule(["Sidekiq", "Payments"], ["Sidekiq"], 2)
    matches = found(rule, description="Background jobs in Sidekiq for payments at scale.")
    assert {m.keyword for m in matches} == {"Sidekiq", "Payments"}
    assert qualifies(rule, matches)


def test_common_skills_alone_never_qualify_without_a_core_one():
    rule = keyword_rule(["Ruby on Rails", "Git", "PostgreSQL"], ["Ruby on Rails"], 2)
    matches = found(rule, description="Java role. Git and PostgreSQL required.")
    assert {m.keyword for m in matches} == {"Git", "PostgreSQL"}
    assert not qualifies(rule, matches)


def test_marking_a_common_skill_core_is_the_users_choice():
    rule = keyword_rule(["Git", "PostgreSQL"], ["Git"], 2)
    assert qualifies(rule, found(rule, description="Java role. Git and PostgreSQL required."))


def test_minimum_counts_distinct_keywords():
    rule = keyword_rule(["Rails", "PostgreSQL", "Redis"], ["Rails"], 3)
    two = found(rule, description="Rails and PostgreSQL.")
    three = found(rule, description="Rails, PostgreSQL and Redis.")
    assert not qualifies(rule, two)
    assert qualifies(rule, three)


def test_each_match_says_where_it_was_found():
    rule = keyword_rule(["Rails", "PostgreSQL"], ["Rails"], 2)
    matches = found(rule, requirements="Ruby on Rails", description="Rails app on Postgres.")
    assert [(m.keyword, m.where, m.core) for m in matches] == [
        ("Rails", "requirements", True),
        ("PostgreSQL", "description", False),
    ]


def test_another_users_longer_phrase_never_hides_a_match():
    mine = keyword_rule(["Rails", "PostgreSQL"], ["Rails"], 2)
    theirs = keyword_rule(["Rails developer"], ["Rails developer"], 1)
    text = "Rails developer wanted. PostgreSQL required."
    # Every User's keywords are scanned together in the Feed sync.
    together = mine.terms | theirs.terms
    matches = keyword_matches(mine, set(), mentioned(text, together))
    assert {m.keyword for m in matches} == {"Rails", "PostgreSQL"}
    assert qualifies(mine, matches)
    assert qualifies(theirs, keyword_matches(theirs, set(), mentioned(text, together)))


def test_lowercase_skill_names_match():
    rule = keyword_rule(["Rails", "PostgreSQL"], ["Rails"], 2)
    for text in (
        "Rails development experience required. PostgreSQL required.",
        "rails development experience required. postgresql required.",
    ):
        assert qualifies(rule, found(rule, description=text)), text


def test_prose_words_need_a_capital_to_count():
    rule = keyword_rule(["Go", "Kafka"], ["Go"], 2)
    assert not qualifies(rule, found(rule, description="Ready to go the extra mile with kafka."))
    assert qualifies(rule, found(rule, description="Services in Go with Kafka."))


def test_only_the_job_description_confirms_a_keyword():
    from app.tailoring.keywords import has_description

    rule = keyword_rule(["Rails", "PostgreSQL"], ["Rails"], 2)
    description = mentioned("Our monolith runs on PostgreSQL.", rule.terms)
    # "Ruby on Rails Developer" in the title alone confirms nothing.
    assert [m.keyword for m in keyword_matches(rule, set(), description)] == ["PostgreSQL"]
    assert not has_description("Build billing services.")
    assert has_description("x" * 100)


def test_extracted_skills_never_confirm_a_keyword_alone():
    from app.tailoring.keywords import has_description

    rule = keyword_rule(["Rails", "PostgreSQL"], ["Rails"], 1)
    # Skill extraction reads the title too: "Rails" from a title is not JD evidence.
    extracted = {"ruby on rails", "postgresql"}
    assert keyword_matches(rule, extracted, set()) == []
    assert not has_description("")
    described = mentioned("Rails services on PostgreSQL.", rule.terms)
    assert [(m.keyword, m.where) for m in keyword_matches(rule, extracted, described)] == [
        ("Rails", "requirements"),
        ("PostgreSQL", "requirements"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "rails engineers",
        "rails api",
        "rails 7",
        "rails stack",
        "rails monolith",
        "ruby/rails",
        "rails-based",
        "using rails",
        "built with rails",
        "rails, postgres, sidekiq",
        "RoR",
        "RUBY ON RAILS",
    ],
)
def test_keyword_context_accepts_all_technical_spellings(text):
    from app.tailoring.keywords import confirmed_matches, keyword_matches, keyword_rule, mentioned

    rule = keyword_rule(["rails"], ["rails"], 1)
    found = keyword_matches(rule, set(), mentioned(text, ["rails"]))
    assert len(confirmed_matches(found, ["Ruby on Rails"])) == 1


def test_context_confirmation_is_generic_and_requires_literal_evidence():
    from app.tailoring.keywords import confirmed_matches, keyword_matches, keyword_rule, mentioned

    for term, text, skills in [
        ("rails", "data, trust and rails to transact", ["Python", "Django"]),
        ("Rust", "Remove rust from metal surfaces", ["manufacturing"]),
    ]:
        rule = keyword_rule([term], [term], 1)
        found = keyword_matches(rule, set(), mentioned(text, [term]))
        assert found
        assert confirmed_matches(found, skills) == []
        assert confirmed_matches([], [term]) == []


def test_keyword_excerpt_is_original_and_bounded():
    from app.tailoring.keywords import keyword_excerpt

    text = "Our mission. Build Ruby on Rails APIs. Team details."
    assert keyword_excerpt(text, "RoR") == "Build Ruby on Rails APIs."
    assert keyword_excerpt(text, "Python") is None
    assert len(keyword_excerpt("x " * 1000 + "Rails" + " y" * 1000, "rails")) < 320


def test_ruby_keyword_is_supported_by_explicit_ruby_on_rails_context():
    from app.tailoring.keywords import confirmed_matches

    rule = keyword_rule(["Ruby"], ["Ruby"], 1)
    candidates = found(rule, description="Build Ruby on Rails APIs")
    assert len(confirmed_matches(candidates, ["Ruby on Rails"])) == 1
