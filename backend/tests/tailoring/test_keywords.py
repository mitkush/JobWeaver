"""Preference keywords found in a Job (FR-D1): spellings count once, whole phrases only,
and a core keyword gates the keyword section."""

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


def test_trade_rails_do_not_satisfy_ruby_preferences():
    rule = keyword_rule(["Ruby", "Ruby on rails", "ROR", "rails"], ["Ruby", "rails"], 1)
    description = (
        "Whoever builds the infrastructure those agents run on, with the data, trust "
        "and rails to transact across borders, will define how the industry works. "
        "Strong Python and Django experience required."
    )
    assert found(rule, description=description) == []
    assert not qualifies(rule, found(rule, description=description))


def test_unambiguous_rails_spellings_and_named_framework_still_match():
    rule = keyword_rule(["rails"], ["rails"], 1)
    for description in (
        "Experience with Rails, PostgreSQL and Sidekiq.",
        "experience with ruby on rails.",
        "experience with ruby-on-rails.",
        "experience with ror.",
        "rails development experience required.",
        "experience with rails.",
    ):
        assert qualifies(rule, found(rule, description=description))
