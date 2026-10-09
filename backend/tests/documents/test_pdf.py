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


def test_resume_does_not_repeat_bare_project_heading_and_links_profiles():
    facts = [
        FactSnapshot(
            ref="F1",
            id=uuid.uuid4(),
            kind="project",
            group="JobWeaver",
            text="Built a job-search application.",
            in_base_resume=True,
        ),
        FactSnapshot(
            ref="F2",
            id=uuid.uuid4(),
            kind="link",
            group="",
            text="linkedin.com/in/example-person",
            in_base_resume=True,
        ),
        FactSnapshot(
            ref="F3",
            id=uuid.uuid4(),
            kind="link",
            group="",
            text="https://github.com/example-person",
            in_base_resume=True,
        ),
    ]
    content = DraftContent(
        resume=[
            DraftLine(text="JobWeaver", fact_refs=["F1"], section="Projects"),
            DraftLine(text="Built a job-search application.", fact_refs=["F1"], section="Projects"),
        ],
        cover_letter=[DraftLine(text="Hello", fact_refs=["F1"])],
    )
    reader = PdfReader(io.BytesIO(render_pdf(content, "Asha", "asha@example.com", facts=facts)))
    text = reader.pages[0].extract_text()
    assert text.count("JobWeaver") == 1
    urls = {
        annotation.get_object()["/A"].get("/URI")
        for annotation in reader.pages[0].get("/Annots", [])
        if annotation.get_object().get("/A")
    }
    assert "mailto:asha@example.com" in urls
    assert "https://linkedin.com/in/example-person" in urls
    assert "https://github.com/example-person" in urls


def test_contact_phone_is_used_only_when_it_is_a_link_fact():
    content = package("Python")
    phone = FactSnapshot(
        ref="F2",
        id=uuid.uuid4(),
        kind="link",
        group="",
        text="Phone: +91 7222986584",
        in_base_resume=True,
    )
    reader = PdfReader(io.BytesIO(render_pdf(content, "Asha", "asha@example.com", facts=[phone])))
    assert "+91 7222986584" in reader.pages[0].extract_text()
    urls = {
        annotation.get_object()["/A"].get("/URI")
        for annotation in reader.pages[0].get("/Annots", [])
        if annotation.get_object().get("/A")
    }
    assert "tel:+917222986584" in urls


def test_bare_project_url_in_resume_is_clickable():
    fact = FactSnapshot(
        ref="F1",
        id=uuid.uuid4(),
        kind="link",
        group="",
        text="github.com/example-person/sample-project",
        in_base_resume=True,
    )
    content = DraftContent(
        resume=[
            DraftLine(
                text="Code: github.com/example-person/sample-project",
                fact_refs=["F1"],
                section="Links",
            )
        ],
        cover_letter=[DraftLine(text="Hello", fact_refs=["F1"])],
    )
    reader = PdfReader(io.BytesIO(render_pdf(content, "Asha", "asha@example.com", facts=[fact])))
    urls = {
        annotation.get_object()["/A"].get("/URI")
        for annotation in reader.pages[0].get("/Annots", [])
        if annotation.get_object().get("/A")
    }
    assert "https://github.com/example-person/sample-project" in urls


def test_employer_prefix_is_removed_but_role_is_preserved():
    fact = FactSnapshot(
        ref="F1",
        id=uuid.uuid4(),
        kind="experience",
        group="Acme Corp",
        text="Senior Software Developer at Acme Corp",
        in_base_resume=True,
    )
    content = DraftContent(
        resume=[
            DraftLine(
                text="Acme Corp - Senior Software Developer",
                fact_refs=["F1"],
                section="Experience",
            )
        ],
        cover_letter=[DraftLine(text="Hello", fact_refs=["F1"])],
    )
    text = (
        PdfReader(io.BytesIO(render_pdf(content, "Asha", "asha@example.com", facts=[fact])))
        .pages[0]
        .extract_text()
    )
    assert text.count("Acme Corp") == 1
    assert "Senior Software Developer" in text


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
