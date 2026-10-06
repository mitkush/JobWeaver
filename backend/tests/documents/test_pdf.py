import io
import uuid

import pytest
from pypdf import PdfReader

from app.core.errors import ValidationFailedError
from app.documents.pdf import filename, render_pdf
from app.tailoring.content import DraftContent, DraftLine


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
