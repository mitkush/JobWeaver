import io
import uuid

import pytest
from pypdf import PdfReader

from app.core.errors import ValidationFailedError
from app.documents.pdf import filename, render_pdf
from app.tailoring.content import DraftContent, DraftLine, FactSnapshot


def package(text):
    return DraftContent(
        resume=[DraftLine(text=text, fact_refs=["F1"])],
        cover_letter=[DraftLine(text=text, fact_refs=["F1"])],
    )


@pytest.mark.parametrize("template", ["standard", "compact"])
def test_pdf_round_trip_and_unicode(template):
    text = "Built Python APIs for café billing, improving reports by 40%."
    data = render_pdf(package(text), "Zoë Engineer", "zoe@example.com", template=template)
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) <= 2
    extracted = "\n".join(page.extract_text() for page in reader.pages)
    assert "Zoë Engineer" in extracted
    assert text in extracted


def test_filename_is_safe_and_predictable():
    assert (
        filename("Asha Rao", "Acme/Corp", "Backend Engineer")
        == "Asha_Rao_Acme_Corp_Backend_Engineer.pdf"
    )
    assert filename("Asha", "Acme", "Engineer", "cover_letter").endswith("_Cover_Letter.pdf")


def test_resume_overflow_is_rejected():
    content = package("Python")
    content.resume = [
        DraftLine(id=str(uuid.uuid4()), text="Built Python APIs. " * 75, fact_refs=["F1"])
        for _ in range(20)
    ]
    with pytest.raises(ValidationFailedError, match="two pages"):
        render_pdf(content, "Asha", "asha@example.com")


def test_unrenderable_characters_are_not_silently_lost():
    with pytest.raises(ValidationFailedError, match="character"):
        render_pdf(package("Python 🚀"), "Asha", "asha@example.com")


def test_resume_lines_sit_under_their_employer_headings():
    facts = [
        FactSnapshot(
            ref="F1",
            id=uuid.uuid4(),
            kind="experience",
            group="Acme Corp",
            text="a",
            in_base_resume=True,
        ),
        FactSnapshot(
            ref="F2",
            id=uuid.uuid4(),
            kind="experience",
            group="Globex",
            text="b",
            in_base_resume=True,
        ),
        FactSnapshot(
            ref="F3", id=uuid.uuid4(), kind="skill", group="", text="Python", in_base_resume=True
        ),
    ]
    content = DraftContent(
        resume=[
            DraftLine(text="Python", fact_refs=["F3"], section="Skills"),
            DraftLine(text="Built the billing API", fact_refs=["F1"]),
            DraftLine(text="Ran the data platform", fact_refs=["F2"]),
            DraftLine(text="Cut report time", fact_refs=["F1"]),
        ],
        cover_letter=[DraftLine(text="Hello", fact_refs=["F1"])],
    )
    data = render_pdf(content, "Asha", "asha@example.com", facts=facts)
    text = " ".join(PdfReader(io.BytesIO(data)).pages[0].extract_text().split())
    assert (
        text.index("Acme Corp")
        < text.index("Built the billing API")
        < text.index("Cut report time")
    )
    assert (
        text.index("Cut report time") < text.index("Globex") < text.index("Ran the data platform")
    )
    assert text.count("EXPERIENCE") == 1


def test_common_ai_characters_print_with_a_fallback():
    text = "Built full‑stack ✓ APIs ➔ saved ₹ 2 lakh⁠ for 3 teams"
    data = render_pdf(package(text), "Asha", "asha@example.com")
    extracted = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
    assert "full-stack" in extracted
    assert "Rs 2 lakh" in extracted


def test_an_unprintable_character_is_named_with_its_line():
    content = package("Python")
    content.resume.append(DraftLine(text="Shipped the launch 🚀 on time", fact_refs=["F1"]))
    with pytest.raises(ValidationFailedError) as caught:
        render_pdf(content, "Asha", "asha@example.com")
    assert '"🚀" (U+1F680)' in caught.value.message
    assert 'resume line "Shipped the launch 🚀 on time"' in caught.value.message


def _fact(ref, kind, group):
    return FactSnapshot(
        ref=ref, id=uuid.uuid4(), kind=kind, group=group, text="x", in_base_resume=True
    )


FACTS = [
    _fact("F1", "experience", "Acme Corp"),
    _fact("F2", "project", "Ledger"),
    _fact("F3", "skill", ""),
    _fact("F4", "link", "Contact"),
]


def resume(*lines):
    return DraftContent(resume=list(lines), cover_letter=[DraftLine(text="Hi", fact_refs=["F1"])])


def page_text(data):
    reader = PdfReader(io.BytesIO(data))
    return " ".join(" ".join(page.extract_text() for page in reader.pages).split())


def test_resume_reads_like_a_resume():
    """Header under the name, sections in reading order whatever order the lines came in,
    role headings in place of the bare employer name, and bulleted work lines."""
    content = resume(
        DraftLine(text="Backend: Python, PostgreSQL", fact_refs=["F3"], section="Skills"),
        DraftLine(text="Built the billing API", fact_refs=["F1"]),
        DraftLine(
            text="Senior Developer | Acme Corp | 2021 to 2024", fact_refs=["F1"], heading=True
        ),
        DraftLine(text="Ships billing systems.", fact_refs=["F1"], section="Summary"),
        DraftLine(text="Senior Developer | Python", fact_refs=["F1"], section="Headline"),
        DraftLine(text="+1 555 0100 | Pune, India", fact_refs=["F4"], section="Contact"),
    )
    text = page_text(render_pdf(content, "Asha Rao", "asha@example.com", facts=FACTS))
    assert text.index("Asha Rao") < text.index("Senior Developer | Python")
    assert "+1 555 0100 | asha@example.com | Pune, India" in text
    assert text.index("SUMMARY") < text.index("EXPERIENCE") < text.index("SKILLS")
    assert "Acme Corp | 2021 to 2024" in text
    assert text.count("Acme Corp") == 1  # the heading replaces the employer name
    assert "\u2022 Built the billing API" in text


def test_links_are_clickable():
    content = resume(
        DraftLine(text="+1 555 0100 | linkedin.com/in/asha", fact_refs=["F4"], section="Contact"),
        DraftLine(
            text="Ledger | Python | github.com/asha/ledger",
            fact_refs=["F2"],
            section="Projects",
            heading=True,
        ),
        DraftLine(text="Built with Socket.io", fact_refs=["F2"], section="Projects"),
    )
    reader = PdfReader(io.BytesIO(render_pdf(content, "Asha", "asha@example.com", facts=FACTS)))
    links = {
        annot.get_object()["/A"]["/URI"]
        for annot in reader.pages[0].get("/Annots", [])
        if "/A" in annot.get_object()
    }
    assert links == {
        "mailto:asha@example.com",
        "https://linkedin.com/in/asha",
        "https://github.com/asha/ledger",
    }


def test_page_count_tells_which_template_fits():
    from app.documents.pdf import page_count

    bullets = [
        DraftLine(text="Built Python APIs for the billing platform team. " * 3, fact_refs=["F1"])
        for _ in range(24)
    ]
    content = resume(*bullets)
    assert page_count(content, "Asha", "a@example.com", "standard", FACTS) >= page_count(
        content, "Asha", "a@example.com", "compact", FACTS
    )
    assert page_count(resume(bullets[0]), "Asha", "a@example.com", "standard", FACTS) == 1


def test_contact_line_comes_from_contact_facts_when_the_draft_has_none():
    facts = [
        *(fact for fact in FACTS if fact.group != "Contact"),
        FactSnapshot(
            ref="F5",
            id=uuid.uuid4(),
            kind="link",
            group="",
            text="LinkedIn: https://www.linkedin.com/in/asha-rao/ and github.com/asha/ledger",
            in_base_resume=True,
        ),
        FactSnapshot(
            ref="F6",
            id=uuid.uuid4(),
            kind="other",
            group="Contact",
            text="Location: Pune, India",
            in_base_resume=True,
        ),
        FactSnapshot(
            ref="F7",
            id=uuid.uuid4(),
            kind="link",
            group="",
            text="Phone +91 98765 43210",
            in_base_resume=True,
        ),
    ]
    content = resume(DraftLine(text="Built the billing API", fact_refs=["F1"]))
    text = page_text(render_pdf(content, "Asha", "asha@example.com", facts=facts))
    assert (
        "+91 98765 43210 | asha@example.com | https://www.linkedin.com/in/asha-rao | Pune, India"
        in text
    )
    assert "ledger" not in text  # a repository is not a profile


def test_a_line_naming_its_group_is_printed_once_as_the_title():
    content = resume(
        DraftLine(text="Acme Corp — Senior Developer", fact_refs=["F1"]),
        DraftLine(text="Built the billing API", fact_refs=["F1"]),
        DraftLine(text="Ledger", fact_refs=["F2"], section="Projects"),
        DraftLine(text="Ledger sync streams changes", fact_refs=["F2"], section="Projects"),
    )
    text = page_text(render_pdf(content, "Asha", "asha@example.com", facts=FACTS))
    assert text.count("Acme Corp") == 1
    assert "• Acme Corp" not in text
    assert text.count("Ledger") == 2  # the title, and the bullet that starts with it
    assert "• Ledger sync streams changes" in text
