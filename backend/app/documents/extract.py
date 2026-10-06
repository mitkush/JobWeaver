import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import ValidationFailedError

PDF = "application/pdf"
TEXT_TYPES = {"text/plain", "text/markdown"}


def extract_text(data: bytes, content_type: str, filename: str) -> str:
    """Plain text from an uploaded PDF or text file. DOCX support is optional (FR-A2)."""
    lower = filename.lower()
    if content_type == PDF or lower.endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except (PdfReadError, ValueError) as exc:
            raise ValidationFailedError("This PDF could not be read") from exc
    elif content_type in TEXT_TYPES or lower.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise ValidationFailedError("Upload a PDF or a plain text file")
    text = text.strip()
    if len(text) < 20:
        raise ValidationFailedError(
            "No readable text found. If this is a scanned PDF, export it with selectable text."
        )
    return text
