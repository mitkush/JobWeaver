import pytest

from app.services.skills import canonical_skill, skill_gaps, user_skills


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Postgres", "PostgreSQL"),
        ("JS", "JavaScript"),
        ("k8s", "Kubernetes"),
        ("Golang", "Go"),
        ("Node.js", "nodejs"),
        ("ReactJS", "React"),
    ],
)
def test_aliases_share_one_canonical_name(a, b):
    # FR-D3 AC2
    assert canonical_skill(a) == canonical_skill(b)


def test_gaps_are_required_skills_missing_from_the_fact_bank():
    skills = user_skills(["Python", "Postgres"], ["Python", "Postgres", "Built a Rails app"])
    assert skill_gaps(["PostgreSQL", "Python", "Kubernetes", "Go"], skills) == [
        "Kubernetes",
        "Go",
    ]


def test_a_skill_named_inside_an_experience_fact_counts():
    skills = user_skills([], ["Migrated 40 services to Kubernetes on AWS"])
    assert skill_gaps(["Kubernetes", "k8s", "AWS", "Terraform"], skills) == ["Terraform"]


def test_common_words_in_prose_do_not_count_as_skills():
    skills = user_skills([], ["Helped the team go to market faster", "Data at rest encrypted"])
    assert skill_gaps(["Go", "REST"], skills) == ["Go", "REST"]


def test_a_combined_skill_fact_is_split():
    skills = user_skills(["React, TypeScript / Node.js"], [])
    assert skill_gaps(["React", "TS", "Node", "Vue"], skills) == ["Vue"]


def test_no_gaps():
    skills = user_skills(["Python"], ["Python"])
    assert skill_gaps(["python"], skills) == []


@pytest.mark.parametrize("spelling", [".NET", "dotnet", "ASP.NET", "ASP.NET Core", ".net."])
def test_dotnet_keeps_its_leading_dot(spelling):
    assert canonical_skill(spelling) == ".net"


def test_dotnet_is_found_in_skills_and_in_experience_text():
    assert skill_gaps([".NET"], user_skills(["ASP.NET Core"], [])) == []
    assert skill_gaps([".NET"], user_skills([], ["Built billing APIs on ASP.NET"])) == []
    assert skill_gaps([".NET"], user_skills(["Python"], ["Python"])) == [".NET"]
