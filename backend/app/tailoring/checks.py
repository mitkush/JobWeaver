"""Truthfulness checks run by code, not by the AI, before a Draft version is saved
(ADR-0005).

They check what ADR-0005 forbids inventing, and nothing else, so ordinary rewording
("serving", "designed", "scalable") is allowed:
- a Tailoring Trace: every line cites real Facts, and a resume line does not mix two
  employers;
- skills and technologies named anywhere must be in the Fact Bank;
- numbers (metrics and dates) must appear in the cited Facts;
- names (an employer, product or school written with a capital letter) must appear in
  the Fact Bank; the Cover Letter and Email may also name the Job's company and title;
- claims of seniority, leadership or expertise must appear in the cited Facts, and an
  Experience or Projects line must cite work, not only skills.

AI lines that fail are removed. Lines the User edited are kept and flagged: they are
the User's own words (FR-E6).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from app.tailoring.content import DraftContent, DraftLine, FactSnapshot
from app.tailoring.skills import TECHNOLOGIES, all_spellings, canonical_skill, covers, user_skills
from app.tailoring.vocabulary import TECHNOLOGIES as COMMON_TECHNOLOGIES

Part = str  # "resume" | "cover_letter" | "email_body"
PARTS: tuple[Part, ...] = ("resume", "cover_letter", "email_body")
_LABELS = {"resume": "resume", "cover_letter": "cover letter", "email_body": "email"}

# Also ordinary English: counted as a technology only when capitalised after the start of
# the line ("built it in Go", not "go to market").
_AMBIGUOUS = {
    "go", "rest", "spring", "express", "swift", "rails", "chef", "puppet", "consul", "unity",
    "helm", "jest", "spark", "next.js", "remix", "phoenix", "dart", "pulsar", "nats", "envoy",
    "jax", "elastic", "flask", "sap", "looker", "vault", "node.js", "react", "rust", "oracle",
}  # fmt: skip
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w])")
_CAPITALISED = re.compile(r"(?<![\w'])[A-Z][\w&+.'-]*")
# Capitalised words of letters and greetings that are never a claim.
_LETTER_WORDS = {
    "i", "dear", "hello", "hi", "hiring", "manager", "managers", "team", "recruiter",
    "recruiting", "recruitment", "talent", "sincerely", "regards", "best", "kind", "warm",
    "thank", "thanks", "yours", "resume", "cv", "cover", "letter", "application",
}  # fmt: skip
# Claims that must be stated in the cited Facts, grouped by meaning.
_CLAIMS = [
    {"lead", "led", "leading", "leader", "leadership"},
    {"manage", "managed", "manager", "management", "managing"},
    {"mentor", "mentored", "mentoring"},
    {"architect", "architected"},
    {"expert", "expertise"},
    {"senior"},
    {"principal"},
    {"head"},
    {"director"},
    {"year", "years", "decade", "decades"},
    {"award", "awarded", "award-winning"},
    {"patent", "patented"},
    {"promoted", "promotion"},
    {"certified", "certification", "certificate"},
]
_WORD = re.compile(r"[a-z][a-z-]*")
_ADDRESSING = re.compile(r"\bhiring (?:manager|managers|team|lead|leads)\b")


@lru_cache(maxsize=1)
def _base_terms() -> frozenset[str]:
    return frozenset(COMMON_TECHNOLOGIES | TECHNOLOGIES | set(all_spellings()))


@lru_cache(maxsize=64)
def _pattern(extra: frozenset[str]) -> re.Pattern[str]:
    terms = sorted(_base_terms() | extra, key=len, reverse=True)
    alternation = "|".join(re.escape(term) for term in terms)
    return re.compile(rf"(?<![\w+#.])({alternation})(?![\w+#])", re.IGNORECASE)


def technologies_in(text: str, extra_terms: Iterable[str] = ()) -> dict[str, str]:
    """Technologies named in the text: canonical name -> the words as written."""
    extra = frozenset(term.casefold().strip() for term in extra_terms if term.strip())
    found: dict[str, str] = {}
    for match in _pattern(extra).finditer(text):
        written = match.group(1)
        canonical = canonical_skill(written)
        ambiguous = canonical in _AMBIGUOUS or written.casefold() in _AMBIGUOUS
        if ambiguous and (not written[0].isupper() or match.start() == 0):
            continue
        found.setdefault(canonical, written)
    return found


def _numbers_missing(text: str, evidence: str, terms: frozenset[str]) -> list[str]:
    """Numbers absent from the evidence, except versions after a technology ("Python 3")."""
    known = {n.replace(",", "") for n in _NUMBER.findall(evidence)}
    missing = []
    for match in _NUMBER.finditer(text):
        if match.group(0).replace(",", "") in known:
            continue
        before = text[: match.start()].rstrip().rsplit(" ", 1)[-1].casefold()
        if before not in terms:
            missing.append(match.group(0))
    return missing


def _says_more_than_skills(text: str, extra_terms: Iterable[str]) -> bool:
    rest = _pattern(frozenset(t.casefold() for t in extra_terms)).sub(" ", text)
    return bool(re.search(r"[A-Za-z]{2,}", re.sub(r"\b(and|or)\b", " ", rest)))


def _sentence_starts(text: str) -> set[int]:
    return {0} | {m.end() for m in re.finditer(r"[.!?:;]\s+|\n+|[-•]\s+", text)}


@dataclass
class Checker:
    facts: list[FactSnapshot]
    job_title: str = ""
    company: str = ""
    job_skills: tuple[str, ...] = ()
    _by_ref: dict[str, FactSnapshot] = field(init=False)

    def __post_init__(self) -> None:
        self._by_ref = {fact.ref: fact for fact in self.facts}
        self._skills = user_skills(
            (f.text for f in self.facts if f.kind == "skill"),
            (f"{f.group}\n{f.text}" for f in self.facts),
        )
        self._bank = "\n".join(f"{f.group}\n{f.text}" for f in self.facts).casefold()
        self._terms = _base_terms() | frozenset(s.casefold() for s in self.job_skills)
        self._role_words = {w.casefold() for w in re.findall(r"[\w+#.]+", self.job_title)}
        self._company = " ".join(self.company.split()).casefold()

    def _in_bank(self, word: str) -> bool:
        pattern = rf"(?<![\w]){re.escape(word.casefold())}(?![\w])"
        return re.search(pattern, self._bank) is not None

    def problems(self, line: DraftLine, part: Part) -> list[str]:
        if len(set(line.fact_refs)) != len(line.fact_refs):
            return ["It lists the same Fact twice"]
        if not line.fact_refs or any(ref not in self._by_ref for ref in line.fact_refs):
            return ["It is not based on Facts in your Fact Bank"]
        sources = [self._by_ref[ref] for ref in line.fact_refs]
        evidence = "\n".join(f"{f.group}\n{f.text}" for f in sources)
        reasons: list[str] = []
        employers = {f.group.strip().casefold() for f in sources if f.kind != "skill"}
        employers.discard("")
        if (
            part == "resume"
            and line.section in ("Experience", "Projects")
            and all(f.kind == "skill" for f in sources)
            and _says_more_than_skills(line.text, self.job_skills)
        ):
            # Knowing a skill is not the same as having done this work (ADR-0005).
            reasons.append("It describes work but cites only skills")
        if part == "resume" and len(employers) > 1:
            reasons.append("It mixes Facts from different employers or projects")
        text = line.text
        if part != "resume":
            # Naming the company and role you apply to is not a claim about yourself.
            for name in (self.company, self.job_title):
                if name.strip():
                    text = re.sub(re.escape(" ".join(name.split())), " ", text, flags=re.I)
        for canonical, written in technologies_in(text, self.job_skills).items():
            if not covers(self._skills, canonical):
                reasons.append(f"{written} is not in your Fact Bank")
        for number in _numbers_missing(text, evidence, self._terms):
            reasons.append(f"The number {number} is not in the Facts it cites")
        starts = _sentence_starts(text)
        for match in _CAPITALISED.finditer(text):
            word = match.group(0).rstrip(".'")
            folded = word.casefold()
            if match.start() in starts or len(word) < 2 or folded in _LETTER_WORDS:
                continue
            if folded in self._role_words or folded in self._terms or self._in_bank(word):
                continue
            if technologies_in(word, self.job_skills):
                continue  # already checked as a technology
            reasons.append(f"{word} is not in your Fact Bank")
        cited = set(_WORD.findall(evidence.casefold()))
        # "Dear Hiring Manager" addresses the reader; it claims nothing about the User.
        claim_text = _ADDRESSING.sub(" ", text.casefold())
        written = set(_WORD.findall(claim_text))
        for group in _CLAIMS:
            claimed = written & group
            if claimed and not cited & group:
                reasons.append(f'"{sorted(claimed)[0]}" is not stated in the Facts it cites')
        return list(dict.fromkeys(reasons))


@dataclass
class CheckResult:
    content: DraftContent
    # AI lines taken out (ADR-0005: never silently kept).
    removed: list[str] = field(default_factory=list)
    # The User's own lines that name something outside the Fact Bank.
    flagged: list[str] = field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        return self.removed + self.flagged


def check(
    content: DraftContent,
    facts: list[FactSnapshot],
    *,
    job_title: str = "",
    company: str = "",
    job_skills: Iterable[str] = (),
) -> CheckResult:
    checker = Checker(facts, job_title, company, tuple(job_skills))
    checked = content.model_copy(deep=True)
    result = CheckResult(checked)
    seen: set[str] = set()
    for part in PARTS:
        kept = []
        for line in getattr(checked, part):
            reasons = ["It repeats another line's id"] if line.id in seen else []
            seen.add(line.id)
            reasons = reasons or checker.problems(line, part)
            if not reasons:
                kept.append(line)
            elif line.manual:
                # Rejected AI text is never logged; the User's own line is kept and shown.
                result.flagged.append(f"Your edit in the {_LABELS[part]}: {'; '.join(reasons)}")
                kept.append(line)
            else:
                result.removed.append(f"Removed a {_LABELS[part]} line: {'; '.join(reasons)}")
        setattr(checked, part, kept)
    return result


def line_problem(line: DraftLine, facts: list[FactSnapshot]) -> str | None:
    """The first reason a resume line fails, or None."""
    reasons = Checker(facts).problems(line, "resume")
    return reasons[0] if reasons else None


def check_content(
    content: DraftContent, facts: list[FactSnapshot]
) -> tuple[DraftContent, list[str]]:
    """Kept for callers that only need the content and every warning."""
    result = check(content, facts)
    return result.content, result.warnings


def unknown_technologies(
    text: str, facts: list[FactSnapshot], job_skills: Iterable[str] = ()
) -> list[str]:
    skills = user_skills(
        (f.text for f in facts if f.kind == "skill"), (f"{f.group}\n{f.text}" for f in facts)
    )
    return [
        written
        for canonical, written in technologies_in(text, job_skills).items()
        if not covers(skills, canonical)
    ]
