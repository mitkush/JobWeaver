"""Truthfulness checks run by code, not by the AI, before a Draft version is saved
(ADR-0005).

They check what ADR-0005 forbids inventing, and nothing else, so ordinary rewording
("serving", "designed", "scalable") is allowed:
- a Tailoring Trace: every line cites real Facts, and a resume line does not mix two
  employers;
- skills and technologies named anywhere must be in the Fact Bank;
- numbers (metrics and dates) must appear in the cited Facts;
- names (an employer, product or school written with a capital letter) must appear in
  the Fact Bank; the Cover Letter and Email may also name the Job's company and title,
  and any part may name the User. A capitalised word is not a name when it is a label
  ("Languages:"), a past-tense verb ("Designed"), or a word the Fact Bank or the job
  advert also writes in lower case ("conducted");
- claims of seniority, leadership or expertise must appear in the cited Facts, and an
  Experience or Projects line must cite work, not only skills;
- a Headline or Experience heading copies the role title from its cited Facts: the
  resume never takes the job's own title ("Engineer" for a "Developer").

AI lines that fail are removed. Lines the User edited are kept and flagged: they are
the User's own words (FR-E6).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from app.tailoring.content import DraftContent, DraftLine, FactSnapshot, names_group
from app.tailoring.placeholders import PLACEHOLDER
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
# Job title words a Headline or Experience heading may only copy from the cited Facts.
_ROLE_NOUNS = {
    "engineer", "developer", "programmer", "consultant", "architect", "analyst", "manager",
    "designer", "scientist", "administrator", "specialist", "intern", "officer", "tester",
    "staff",
}  # fmt: skip
_WORD = re.compile(r"[a-z][a-z-]*")


def _phrase(text: str) -> str:
    """Lower-case words separated by single spaces, so punctuation and spacing differences
    ("Developer," or a line break) do not matter when comparing phrases."""
    return " " + " ".join(re.findall(r"[\w+#]+", text.casefold())) + " "


def _role_titles(text: str) -> list[str]:
    """The " | "-separated parts of a title line that name a role ("Senior Developer")."""
    parts = [part.strip() for part in re.split(r"\s\|\s|\s[-\u2013\u2014]\s", text)]
    return [p for p in parts if set(_WORD.findall(p.casefold())) & _ROLE_NOUNS]


_ADDRESSING = re.compile(r"\bhiring (?:manager|managers|team|lead|leads)\b")


@lru_cache(maxsize=1)
def _base_terms() -> frozenset[str]:
    return frozenset(COMMON_TECHNOLOGIES | TECHNOLOGIES | set(all_spellings()))


@lru_cache(maxsize=64)
def _pattern(extra: frozenset[str]) -> re.Pattern[str]:
    terms = sorted(_base_terms() | extra, key=len, reverse=True)
    alternation = "|".join(re.escape(term) for term in terms)
    return re.compile(rf"(?<![\w+#.])({alternation})(?![\w+#])", re.IGNORECASE)


# Words around a lowercase ambiguous name that show it is a technology ("with go",
# "react and rust"), as opposed to English ("go to market", "at rest").
_TECH_BEFORE = {"in", "with", "using", "via", "on", "and", "or", "plus", ","}
_TECH_AFTER = {"and", "or", ","}


def _neighbours(text: str, start: int, end: int) -> tuple[str, str]:
    before = re.findall(r"[\w+#.]+|,", text[:start])
    after = re.findall(r"[\w+#.]+|,", text[end:])
    return (before[-1].casefold() if before else ""), (after[0].casefold() if after else "")


def technologies_in(text: str, extra_terms: Iterable[str] = ()) -> dict[str, str]:
    """Technologies named in the text: canonical name -> the words as written.

    A name that is also an English word (Go, Rust, React, Spring...) counts when written
    with a capital letter anywhere, or in lower case next to a list or tool word.
    Unclear cases count: an AI line is removed and reported rather than kept unchecked."""
    extra = frozenset(term.casefold().strip() for term in extra_terms if term.strip())
    found: dict[str, str] = {}
    for match in _pattern(extra).finditer(text):
        written = match.group(1)
        canonical = canonical_skill(written)
        ambiguous = canonical in _AMBIGUOUS or written.casefold() in _AMBIGUOUS
        if ambiguous and not written[0].isupper():
            before, after = _neighbours(text, match.start(), match.end())
            if before not in _TECH_BEFORE and after not in _TECH_AFTER:
                continue
        found.setdefault(canonical, written)
    return found


def _numbers_missing(text: str, evidence: str, bank: str) -> list[str]:
    """Numbers absent from the cited Facts. A version ("Python 3") is accepted only when
    the Fact Bank states that same version; otherwise it is a number like any other."""
    known = {n.replace(",", "") for n in _NUMBER.findall(evidence)}
    missing = []
    for match in _NUMBER.finditer(text):
        if match.group(0).replace(",", "") in known:
            continue
        before = text[: match.start()].rstrip().rsplit(" ", 1)[-1]
        stated = f"{before} {match.group(0)}".casefold()
        if before and re.search(rf"(?<![\w]){re.escape(stated)}(?![\w])", bank):
            continue
        missing.append(match.group(0))
    return missing


def _says_more_than_skills(text: str, extra_terms: Iterable[str]) -> bool:
    rest = _pattern(frozenset(t.casefold() for t in extra_terms)).sub(" ", text)
    return bool(re.search(r"[A-Za-z]{2,}", re.sub(r"\b(and|or)\b", " ", rest)))


# Words that open a resume bullet or a letter sentence. A capitalised word at the start of
# a sentence is checked as a possible name unless it is one of these or looks like a verb
# or adverb (-ed, -ing, -ly), so "Google employed me" is caught but "Built..." is not.
_OPENINGS = {
    "a", "an", "the", "i", "my", "we", "our", "you", "your", "it", "its", "this", "that",
    "these", "those", "there", "here", "at", "in", "on", "as", "with", "for", "from", "to",
    "by", "of", "over", "after", "before", "during", "while", "when", "since", "through",
    "outside", "beyond", "across", "within", "today", "currently", "previously", "recently",
    "most", "some", "each", "every", "both", "all", "please", "having", "also", "and", "but",
    "so", "if", "built", "led", "ran", "wrote", "cut", "set", "grew", "drove", "made", "won",
    "took", "sold", "kept", "met", "hired", "own", "owned", "build", "design", "develop",
    "create", "lead", "manage", "run", "write", "ship", "deliver", "improve", "reduce",
    "increase", "migrate", "launch", "automate", "maintain", "support", "drive", "scale",
    "experienced", "skilled", "passionate", "results", "hands-on", "backend", "frontend",
    "full-stack", "fullstack", "software", "data", "platform", "product", "engineer",
    "developer", "team", "teams", "worked", "work", "contributed", "responsible", "key",
    "strong", "proven", "focused", "detail-oriented", "self-motivated", "eager", "excited",
    "keen", "glad", "happy", "thank", "thanks", "looking", "best", "kind", "warm",
}  # fmt: skip


def _ordinary_opening(word: str) -> bool:
    return word in _OPENINGS or word.endswith(("ed", "ing", "ly"))


def _sentence_starts(text: str) -> set[int]:
    return {0} | {m.end() for m in re.finditer(r"[.!?:;]\s+|\n+|[-•]\s+", text)}


_LOWER_WORD = re.compile(r"(?<![\w'-])[a-z][a-z-]+(?![\w'])")


def _looks_like_verb(word: str) -> bool:
    """A past-tense verb ("Designed", "Conducted"), not a name, wherever it appears."""
    return len(word) >= 5 and word.endswith("ed")


@dataclass
class Checker:
    facts: list[FactSnapshot]
    job_title: str = ""
    company: str = ""
    job_skills: tuple[str, ...] = ()
    # The job advert and the User's own name: ordinary words and a name the User owns.
    job_text: str = ""
    user_name: str = ""
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
        written = "\n".join([*(f"{f.group}\n{f.text}" for f in self.facts), self.job_text])
        # Words written in lower case somewhere are ordinary English, not names.
        self._ordinary = set(_LOWER_WORD.findall(written))
        self._own_name = {w.casefold() for w in re.findall(r"[\w'-]+", self.user_name)}

    def _in_bank(self, word: str) -> bool:
        """The word or its singular ("APIs" for "API") appears in the Fact Bank."""
        folded = word.casefold()
        forms = {folded, folded.removesuffix("s"), folded.removesuffix("es")} - {""}
        return any(re.search(rf"(?<![\w]){re.escape(form)}(?![\w])", self._bank) for form in forms)

    def problems(self, line: DraftLine, part: Part) -> list[str]:
        if len(set(line.fact_refs)) != len(line.fact_refs):
            return ["It lists the same Fact twice"]
        if not line.fact_refs or any(ref not in self._by_ref for ref in line.fact_refs):
            return ["It is not based on Facts in your Fact Bank"]
        gap = PLACEHOLDER.search(line.text)
        if gap:
            # A template slot JobWeaver cannot fill ("[Phone Number]") is never sent.
            return [f"It contains the placeholder {gap.group(0)}"]
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
        for number in _numbers_missing(text, evidence, self._bank):
            reasons.append(f"The number {number} is not in the Facts it cites")
        starts = _sentence_starts(text)
        for match in _CAPITALISED.finditer(text):
            word = match.group(0).rstrip(".'")
            folded = word.casefold()
            if len(word) < 2 or folded in _LETTER_WORDS:
                continue
            if match.start() in starts and _ordinary_opening(folded):
                continue
            if text[match.end() : match.end() + 1] == ":" and match.start() in starts:
                continue  # a label such as "Languages:" or "Tools:"
            if _looks_like_verb(folded) or folded in self._ordinary or folded in self._own_name:
                continue
            # The job's own title may be named when applying, never claimed in the resume.
            if part != "resume" and folded in self._role_words:
                continue
            if folded in self._terms or self._in_bank(word):
                continue
            if technologies_in(word, self.job_skills):
                continue  # already checked as a technology
            reasons.append(f"{word} is not in your Fact Bank")
        cited = set(_WORD.findall(evidence.casefold()))
        titled = line.heading or any(names_group(line.text, f.group) for f in sources)
        if part == "resume" and (
            line.section == "Headline" or (titled and line.section == "Experience")
        ):
            # A role title is copied as a whole, not upgraded to the job's ("Developer"
            # stays), nor assembled from words found elsewhere in a Fact.
            for title in _role_titles(text):
                if _phrase(title) not in _phrase(evidence):
                    reasons.append(f'The role title "{title}" is not in the Facts it cites')
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
    job_text: str = "",
    user_name: str = "",
) -> CheckResult:
    checker = Checker(facts, job_title, company, tuple(job_skills), job_text, user_name)
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
