"""Small single-column PDFs with selectable, embedded Unicode text."""

import re
from pathlib import Path
from typing import Literal

from fontTools.ttLib import TTFont
from fpdf import FPDF

from app.core.errors import ValidationFailedError
from app.tailoring.content import DraftContent, DraftLine, FactSnapshot

# Sections whose lines sit under the employer, project or school they come from.
_GROUPED = {"Experience", "Projects", "Education"}


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
    text = "\n".join([name, email, *(line.text for line in getattr(content, kind))])
    with TTFont(font_path) as font:
        supported = font.getBestCmap()
        if any(ord(char) not in supported for char in text if not char.isspace()):
            raise ValidationFailedError("This PDF font cannot render a character. Edit it first.")
    pdf = FPDF()
    pdf.set_margins(18, 15, 18)
    pdf.set_auto_page_break(True, 15)
    pdf.add_font("Liberation", fname=str(font_path))
    pdf.add_font("Liberation", style="B", fname=str(FONTS / "LiberationSans-Bold.ttf"))
    pdf.add_page()
    pdf.set_font("Liberation", "B", 16)
    pdf.multi_cell(0, 8, name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Liberation", size=10)
    pdf.multi_cell(0, 5, email, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    size, height = (10, 5) if template == "compact" else (11, 5.5)
    if kind == "cover_letter":
        for line in content.cover_letter:
            pdf.set_font("Liberation", size=size)
            pdf.multi_cell(0, height, line.text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
    else:
        for section, groups in _layout(content.resume, facts or []):
            pdf.set_font("Liberation", "B", 11)
            pdf.multi_cell(0, 7, section, new_x="LMARGIN", new_y="NEXT")
            for heading, lines in groups:
                if heading:
                    pdf.set_font("Liberation", "B", size)
                    pdf.multi_cell(0, height, heading, new_x="LMARGIN", new_y="NEXT")
                for line in lines:
                    pdf.set_font("Liberation", size=size)
                    pdf.multi_cell(0, height, line.text, new_x="LMARGIN", new_y="NEXT")
                    pdf.ln(1)
            pdf.ln(1)
    if kind == "resume" and pdf.pages_count > 2:
        raise ValidationFailedError("The resume exceeds two pages. Shorten it or use Compact.")
    return bytes(pdf.output())
