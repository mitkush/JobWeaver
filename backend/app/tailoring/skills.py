"""Skill Gaps (FR-D3, ADR-0010): plain code, no AI call per User.

Required skills come from the Job (extracted once by AI); a skill counts as covered when
the User has it as a skill Fact or names it anywhere in their Fact Bank."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

# canonical name -> other spellings. Keys and values are lower case.
_ALIASES: dict[str, tuple[str, ...]] = {
    "postgresql": ("postgres", "psql", "postgre sql", "postgre"),
    "javascript": ("js", "ecmascript", "es6"),
    "typescript": ("ts",),
    "kubernetes": ("k8s",),
    "go": ("golang",),
    "node.js": ("node", "nodejs", "node js"),
    "react": ("react.js", "reactjs", "react js"),
    "vue": ("vue.js", "vuejs"),
    "next.js": ("nextjs", "next"),
    "angular": ("angularjs", "angular.js"),
    "aws": ("amazon web services",),
    "gcp": ("google cloud", "google cloud platform"),
    "azure": ("microsoft azure",),
    "c#": ("csharp", "c sharp"),
    "c++": ("cpp",),
    ".net": ("dotnet", ".net core", "asp.net", "asp.net core"),
    "python": ("python3", "python 3"),
    "machine learning": ("ml",),
    "artificial intelligence": ("ai",),
    "ci/cd": ("cicd", "ci cd", "continuous integration"),
    "rest": ("rest api", "restful", "rest apis", "restful apis", "restful api"),
    "graphql": ("graph ql",),
    "mongodb": ("mongo",),
    "elasticsearch": ("elastic search", "elastic"),
    "kafka": ("apache kafka",),
    "spark": ("apache spark",),
    "tailwind css": ("tailwind", "tailwindcss"),
    "html": ("html5",),
    "css": ("css3",),
    "scikit-learn": ("sklearn", "scikit learn"),
    "large language models": ("llm", "llms"),
    "natural language processing": ("nlp",),
    "google bigquery": ("bigquery", "big query"),
    "github actions": ("gh actions",),
}
_CANONICAL = {alias: name for name, aliases in _ALIASES.items() for alias in aliases}
# Words too common in prose to count as a mention ("at rest", "go to market").
_PROSE_WORDS = {"go", "ai", "ml", "ts", "js", "rest", "next", "node", "elastic", "spark", "r", "c"}
TECHNOLOGIES = set(_ALIASES) | {
    name.strip()
    for name in [
        "ruby",
        " ruby on rails",
        " rails",
        " fastapi",
        " django",
        " flask",
        " python",
        " java",
        " spring boot",
        " kotlin",
        " scala",
        " rust",
        " go",
        " swift",
        " php",
        " laravel",
        " c++",
        " c#",
        " docker",
        " kubernetes",
        " helm",
        " terraform",
        " ansible",
        " redis",
        " sqlite",
        " mysql",
        " postgresql",
        " react",
        " next.js",
        " vue",
        " svelte",
        " angular",
        " javascript",
        " typescript",
        " aws",
        " azure",
        " gcp",
        " kafka",
        " rabbitmq",
        " celery",
        " pandas",
        " numpy",
        " pytorch",
        " tensorflow",
        " jax",
        " mongodb",
        " dynamodb",
        " snowflake",
        " spark",
        " airflow",
        " dbt",
        " databricks",
        " elasticsearch",
        " prometheus",
        " grafana",
        " linux",
        " git",
        " graphql",
    ]
}
_SPLIT = re.compile(r"[,;|/]\s*|\s+and\s+")


def canonical_skill(name: str) -> str:
    # Only trailing dots go: the leading one is part of ".NET".
    key = " ".join(name.lower().split()).strip(" ,;:").rstrip(".")
    return _CANONICAL.get(key, key)


def _spellings(canonical: str) -> list[str]:
    return [canonical, *_ALIASES.get(canonical, ())]


@dataclass
class UserSkills:
    canonical: set[str]
    text: str  # every Fact, lower case, for mentions inside experience or project lines


def user_skills(skill_facts: Iterable[str], all_facts: Iterable[str]) -> UserSkills:
    canonical: set[str] = set()
    for fact in skill_facts:
        canonical.add(canonical_skill(fact))
        canonical.update(canonical_skill(part) for part in _SPLIT.split(fact) if part.strip())
    return UserSkills(canonical, "\n".join(all_facts).lower())


def _mentioned(canonical: str, text: str) -> bool:
    for spelling in _spellings(canonical):
        if len(spelling) < 3 or spelling in _PROSE_WORDS:
            continue
        if re.search(rf"(?<![\w+#.]){re.escape(spelling)}(?![\w+#])", text):
            return True
    return False


def skill_gaps(required: Iterable[str], skills: UserSkills) -> list[str]:
    """Required skills the User does not show, in the Job's order, each named once."""
    gaps: list[str] = []
    seen: set[str] = set()
    for name in required:
        canonical = canonical_skill(name)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        if canonical in skills.canonical or _mentioned(canonical, skills.text):
            continue
        gaps.append(name.strip())
    return gaps


def requested_missing_skills(message: str, skills: UserSkills) -> list[str]:
    """Only explicit additions trigger a refusal; removing a missing skill is allowed."""
    if not re.search(r"\b(add|include|claim|mention|say|write)\b", message, re.I):
        return []
    if re.search(r"\b(remove|omit|drop|without|don't|do not)\b", message, re.I):
        return []
    mentioned = [
        name
        for name in sorted(TECHNOLOGIES)
        if re.search(rf"(?<![\w+#.]){re.escape(name)}(?![\w+#])", message, re.I)
    ]
    return skill_gaps(mentioned, skills)
