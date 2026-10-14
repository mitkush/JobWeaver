"""Small single-column PDFs with selectable, embedded Unicode text."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fontTools.ttLib import TTFont
from fpdf import FPDF

from app.core.errors import ValidationFailedError
from app.tailoring.contact import LINK, contact_facts, href
from app.tailoring.content import DraftContent, DraftLine, FactSnapshot, names_group

# Sections whose lines sit under the employer, project or school they come from.
_GROUPED = {"Experience", "Projects", "Education"}
# The order a resume reads in, whatever order the lines were written in.
_ORDER = ["Summary", "Experience", "Projects", "Education", "Skills", "Links", "Additional"]
# Printed under the name rather than as sections of their own.
_HEADER = {"Headline", "Contact"}

Layout = list[tuple[str, list[tuple[str, list[DraftLine]]]]]


def _layout(lines: list[DraftLine], facts: list[FactSnapshot]) -> Layout:
    """Sections in reading order; inside each, lines grouped by the employer, project or
    school of their cited Facts (a Fact group, so never invented), in order of first use."""
    group_of = {fact.ref: fact.group.strip() for fact in facts if fact.kind != "skill"}
    sections: dict[str, dict[str, list[DraftLine]]] = {}
    for line in lines:
        if line.section in _HEADER:
            continue
        heading = ""
        if line.section in _GROUPED:
            heading = next((group_of[r] for r in line.fact_refs if group_of.get(r)), "")
        sections.setdefault(line.section, {}).setdefault(heading, []).append(line)
    return [(name, list(sections[name].items())) for name in _ORDER if name in sections]


FONTS = Path(__file__).with_name("fonts")

# Characters AI models often write that the embedded font lacks, mapped to ones it has.
# Only the PDF changes; the saved Draft keeps the original text.
_FALLBACK = str.maketrans(
    {
        "\u2011": "-",  # non-breaking hyphen ("full\u2011stack")
        "\u2012": "-",  # figure dash
        "\u2043": "-",  # hyphen bullet
        "\u2023": "\u2022",  # triangular bullet
        "\u2794": "\u2192",  # heavy arrows
        "\u27a4": "\u2192",
        "\u2713": "",  # check marks used as bullets
        "\u2714": "",
        "\u2605": "*",  # star
        "\u20b9": "Rs ",  # rupee sign
        "\u2060": "",  # word joiner
        "\ufeff": "",  # byte order mark
    }
)


def pdf_text(text: str) -> str:
    """The text as the PDF prints it, with unsupported look-alikes replaced."""
    # A removed check mark or "Rs " before a space would otherwise leave a double space.
    return re.sub(r"(?<=\S) {2,}", " ", text.translate(_FALLBACK))


@lru_cache(maxsize=1)
def _supported() -> frozenset[int]:
    with TTFont(FONTS / "LiberationSans-Regular.ttf") as font:
        return frozenset(font.getBestCmap())


def _unsupported(text: str) -> str | None:
    supported = _supported()
    return next((c for c in text if not c.isspace() and ord(c) not in supported), None)


def _check_printable(labelled: list[tuple[str, str]]) -> None:
    """Names the first character the font cannot draw and the line it is in."""
    for label, text in labelled:
        char = _unsupported(pdf_text(text))
        if char is not None:
            snippet = " ".join(text.split())
            snippet = snippet if len(snippet) <= 60 else snippet[:57] + "..."
            raise ValidationFailedError(
                f'The PDF cannot show "{char}" (U+{ord(char):04X}) in {label} "{snippet}". '
                "Remove or replace that character."
            )


def filename(name: str, company: str, title: str, kind: str = "resume") -> str:
    parts = [
        re.sub(r"[^\w-]+", "_", value).strip("_")[:60] or "Draft"
        for value in (name, company, title)
    ]
    suffix = "_Cover_Letter" if kind == "cover_letter" else ""
    return "_".join(parts) + suffix + ".pdf"


# Web addresses and emails in a line, printed as clickable links.
_LABEL = re.compile(r"^([^:]{1,40}):\s")
LINK_COLOUR = (26, 61, 140)
RULE_COLOUR = (150, 150, 150)


@dataclass(frozen=True)
class _Style:
    size: float
    height: float
    margin: float
    gap: float


_STYLES = {
    "standard": _Style(size=10, height=4.7, margin=15, gap=2.2),
    "compact": _Style(size=9.5, height=4.3, margin=12, gap=1.6),
}


class _Resume(FPDF):
    def __init__(self, style: _Style) -> None:
        super().__init__(format="A4")
        self.style = style
        self.set_margins(style.margin, style.margin * 0.8, style.margin)
        self.set_auto_page_break(True, style.margin * 0.8)
        self.add_font("Liberation", fname=str(FONTS / "LiberationSans-Regular.ttf"))
        self.add_font("Liberation", style="B", fname=str(FONTS / "LiberationSans-Bold.ttf"))
        self.add_page()

    def font(self, bold: bool = False, size: float | None = None, underline: bool = False) -> None:
        style = ("B" if bold else "") + ("U" if underline else "")
        self.set_font("Liberation", style, size or self.style.size)

    def rich(self, text: str, bold: bool = False, size: float | None = None) -> None:
        """Writes wrapped text from the current position; links are clickable and a
        leading "Label:" is bold. Ends at the start of the next line."""
        height = self.style.height * (size or self.style.size) / self.style.size
        text = pdf_text(text)
        label = _LABEL.match(text) if not bold else None
        if label:
            self.font(True, size)
            self.write(height, label.group(0))
            text = text[label.end() :]
        position = 0
        for match in LINK.finditer(text):
            if match.start() > position:
                self.font(bold, size)
                self.write(height, text[position : match.start()])
            self.font(bold, size, underline=True)
            self.set_text_color(*LINK_COLOUR)
            self.write(height, match.group(0), link=href(match.group(0)))
            self.set_text_color(0, 0, 0)
            position = match.end()
        if position < len(text):
            self.font(bold, size)
            self.write(height, text[position:])
        self.ln(height)

    def bullet(self, text: str) -> None:
        left = self.l_margin
        self.font()
        self.set_x(left + 1.5)
        self.cell(3.5, self.style.height, "\u2022")
        self.set_left_margin(left + 5)
        self.set_x(left + 5)
        self.rich(text)
        self.set_left_margin(left)
        self.ln(0.6)

    def section(self, title: str) -> None:
        self.ln(self.style.gap)
        self.font(True, self.style.size + 1)
        self.cell(0, self.style.height + 0.6, title.upper(), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE_COLOUR)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1.4)


def _contact(lines: list[DraftLine], email: str, facts: list[FactSnapshot]) -> str:
    """One contact line: the Draft's Contact lines, or else the User's contact Facts, with
    their sign-in email added after the phone number."""
    parts = [p.strip() for line in lines for p in line.text.split("|") if p.strip()]
    parts = parts or contact_facts(facts)
    if email and not any(email.casefold() in p.casefold() for p in parts):
        phones = [i for i, p in enumerate(parts) if re.fullmatch(r"[+\d\s().-]{7,}", p)]
        parts.insert(phones[0] + 1 if phones else 0, email)
    return " | ".join(parts)


def _build(
    content: DraftContent,
    name: str,
    email: str,
    kind: Literal["resume", "cover_letter"],
    template: Literal["standard", "compact"],
    facts: list[FactSnapshot],
) -> FPDF:
    part = "cover letter line" if kind == "cover_letter" else "resume line"
    labelled = [("your name", name), ("your email", email)]
    labelled += [(f"the {part}", line.text) for line in getattr(content, kind)]
    labelled += [
        ("the heading", heading)
        for _, groups in _layout(content.resume, facts)
        for heading, _ in groups
        if kind == "resume" and heading
    ]
    _check_printable(labelled)
    pdf = _Resume(_STYLES[template])
    size = pdf.style.size
    pdf.font(True, size + 8)
    pdf.multi_cell(0, 8, pdf_text(name), new_x="LMARGIN", new_y="NEXT")
    if kind == "resume":
        for line in content.resume:
            if line.section == "Headline":
                pdf.rich(line.text, bold=True, size=size + 1)
    contact = [line for line in content.resume if line.section == "Contact"]
    pdf.rich(_contact(contact, email, facts), size=size - 0.5)
    if kind == "cover_letter":
        pdf.ln(4)
        for line in content.cover_letter:
            pdf.font()
            pdf.multi_cell(0, pdf.style.height + 0.6, pdf_text(line.text), align="L")
            pdf.ln(3)
        return pdf
    for section, groups in _layout(content.resume, facts):
        pdf.section(section)
        for group, lines in groups:
            listed = section in _GROUPED
            # A line naming its own group is its title, so the name is not printed twice.
            titles = {
                line.id
                for line in lines
                if line.heading or (listed and names_group(line.text, group))
            }
            if listed and group and not titles:
                pdf.rich(group, bold=True)
            for line in lines:
                if line.id in titles:
                    pdf.ln(0.6)
                    pdf.rich(line.text, bold=True)
                elif listed:
                    pdf.bullet(line.text)
                else:
                    pdf.rich(line.text)
                    pdf.ln(0.6)
            if listed:
                pdf.ln(0.8)
    return pdf


def page_count(
    content: DraftContent,
    name: str,
    email: str,
    template: Literal["standard", "compact"] = "standard",
    facts: list[FactSnapshot] | None = None,
) -> int:
    return _build(content, name, email, "resume", template, facts or []).pages_count


def render_pdf(
    content: DraftContent,
    name: str,
    email: str,
    kind: Literal["resume", "cover_letter"] = "resume",
    template: Literal["standard", "compact"] = "standard",
    facts: list[FactSnapshot] | None = None,
) -> bytes:
    pdf = _build(content, name, email, kind, template, facts or [])
    if kind == "resume" and pdf.pages_count > 2:
        raise ValidationFailedError("The resume exceeds two pages. Shorten it or use Compact.")
    return bytes(pdf.output())
