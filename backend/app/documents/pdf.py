"""Small single-column PDFs with selectable, embedded Unicode text."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fontTools.ttLib import TTFont
from fpdf import FPDF

from app.core.errors import ValidationFailedError
from app.tailoring.content import DraftContent, DraftLine, FactSnapshot

# Sections whose lines sit under the employer, project or school they come from.
_GROUPED = {"Experience", "Projects", "Education"}
_URL = re.compile(
    r"(?<![@\w])(?:https?://)?(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}/[^\s<>)]+",
    re.IGNORECASE,
)
_PROFILE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in|github\.com)/[A-Za-z0-9_.-]+/?",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?<!\w)\+\d[\d ().-]{8,}\d(?!\w)")


def _profile_links(facts: list[FactSnapshot]) -> list[tuple[str, str]]:
    """Include personal profiles only when the User reviewed them as link Facts."""
    links: dict[str, str] = {}
    for fact in facts:
        if fact.kind != "link":
            continue
        for match in _PROFILE.finditer(fact.text):
            url = match.group().rstrip(".,;")
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            host_path = url.split("://", 1)[1].casefold().removeprefix("www.")
            if host_path.startswith("linkedin.com/in/"):
                links.setdefault("LinkedIn", url)
            elif re.fullmatch(r"github\.com/[^/?#]+/?", host_path):
                links.setdefault("GitHub", url)
    return list(links.items())


def _phone(facts: list[FactSnapshot]) -> str | None:
    for fact in facts:
        if fact.kind == "link":
            match = _PHONE.search(fact.text)
            if match:
                return match.group().strip()
    return None


def _display_line(text: str, heading: str) -> str:
    """The renderer already prints a cited group as a heading."""
    if not heading:
        return text
    rest = (
        text.strip()[len(heading) :]
        if text.strip().casefold().startswith(heading.casefold())
        else ""
    )
    if not rest:
        return "" if text.strip().casefold() == heading.casefold() else text
    if rest[0] in " -–—|:,":
        return rest.lstrip(" -–—|:,").strip()
    return text


def _layout(
    lines: list[DraftLine], facts: list[FactSnapshot]
) -> list[tuple[str, list[tuple[str, list[DraftLine]]]]]:
    """Sections in order of first use; inside each, lines grouped by the employer,
    project or school of their cited Facts (a Fact group, so never invented)."""
    group_of = {fact.ref: fact.group.strip() for fact in facts if fact.kind != "skill"}
    sections: dict[str, dict[str, list[DraftLine]]] = {}
    for line in lines:
        heading = ""
        if line.section in _GROUPED:
            heading = next((group_of[r] for r in line.fact_refs if group_of.get(r)), "")
        sections.setdefault(line.section, {}).setdefault(heading, []).append(line)
    return [(section, list(groups.items())) for section, groups in sections.items()]


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


def render_pdf(
    content: DraftContent,
    name: str,
    email: str,
    kind: Literal["resume", "cover_letter"] = "resume",
    template: Literal["standard", "compact"] = "standard",
    facts: list[FactSnapshot] | None = None,
) -> bytes:
    font_path = FONTS / "LiberationSans-Regular.ttf"
    part = "cover letter line" if kind == "cover_letter" else "resume line"
    labelled = [("your name", name), ("your email", email)]
    labelled += [(f"the {part}", line.text) for line in getattr(content, kind)]
    labelled += [
        ("the heading", heading)
        for _, groups in _layout(content.resume, facts or [])
        for heading, _ in groups
        if kind == "resume" and heading
    ]
    _check_printable(labelled)
    pdf = FPDF()
    pdf.set_margins(16, 13, 16)
    pdf.set_auto_page_break(True, 13)
    pdf.add_font("Liberation", fname=str(font_path))
    pdf.add_font("Liberation", style="B", fname=str(FONTS / "LiberationSans-Bold.ttf"))
    pdf.add_page()
    pdf.set_font("Liberation", "B", 16)
    pdf.multi_cell(0, 7, pdf_text(name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Liberation", size=9)
    phone = _phone(facts or []) if kind == "resume" else None
    if phone:
        pdf.cell(
            w=pdf.get_string_width(phone) + 4,
            h=5,
            text=phone + " | ",
            link="tel:" + re.sub(r"[^+\d]", "", phone),
        )
    pdf.cell(w=pdf.get_string_width(email) + 2, h=5, text=pdf_text(email), link=f"mailto:{email}")
    if kind == "resume":
        for label, url in _profile_links(facts or []):
            pdf.set_text_color(25, 60, 110)
            pdf.cell(w=pdf.get_string_width(label) + 5, h=5, text=" | " + label, link=url)
            pdf.set_text_color(0, 0, 0)
    pdf.ln(6)
    size, height = (9.5, 4.6) if template == "compact" else (10.5, 5.1)
    if kind == "cover_letter":
        for line in content.cover_letter:
            pdf.set_font("Liberation", size=size)
            pdf.multi_cell(0, height, pdf_text(line.text), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
    else:
        for section, groups in _layout(content.resume, facts or []):
            pdf.ln(2)
            pdf.set_font("Liberation", "B", 9.5)
            pdf.multi_cell(0, 5, section.upper(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(150, 160, 175)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(1.5)
            for heading, lines in groups:
                if heading:
                    pdf.set_font("Liberation", "B", size)
                    pdf.multi_cell(0, height, pdf_text(heading), new_x="LMARGIN", new_y="NEXT")
                for line in lines:
                    displayed = _display_line(line.text, heading)
                    if not displayed:
                        continue
                    pdf.set_font("Liberation", size=size)
                    pdf.set_x(pdf.l_margin + (2 if heading else 0))
                    url = _URL.search(displayed)
                    link = url.group().rstrip(".,;") if url else ""
                    if link and not link.startswith(("http://", "https://")):
                        link = "https://" + link
                    pdf.multi_cell(
                        pdf.w - pdf.r_margin - pdf.get_x(),
                        height,
                        pdf_text(displayed),
                        new_x="LMARGIN",
                        new_y="NEXT",
                        link=link,
                    )
    if kind == "resume" and pdf.pages_count > 2:
        raise ValidationFailedError("The resume exceeds two pages. Shorten it or use Compact.")
    return bytes(pdf.output())
