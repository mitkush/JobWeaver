"""Prompt text per task. Kept apart from transport so prompts are easy to review."""

from app.gateway.schemas import ParseDocumentsRequest

PARSE_DOCUMENTS_SYSTEM = """You extract a person's career facts from their own documents.
Return only JSON: {"facts": [{"kind", "group", "text", "source_kind", "in_base_resume"}]}.
- kind: one of skill, experience, project, achievement, education, link, other.
- group: the employer, project or school a fact belongs to; "" for skills.
- text: one fact, copied or minimally condensed from the documents. Never add anything
  that is not written in the documents.
- One skill per skill fact. One bullet or claim per experience/project/achievement fact.
- source_kind: the document the fact came from (resume, portfolio or summary).
- in_base_resume: true if the fact (or the same claim) appears in the resume document.
"""


def parse_documents_user(request: ParseDocumentsRequest) -> str:
    parts = [f'<document kind="{d.kind.value}">\n{d.text}\n</document>' for d in request.documents]
    return "\n\n".join(parts)
