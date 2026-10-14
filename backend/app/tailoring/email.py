"""The Application Email as the employer reads it: subject, greeting, body and signature.

The AI writes only the body lines (checked like every Draft line, ADR-0005). Code adds
everything that is a fact about the User or the job rather than a claim: the subject
with the job title and the User's name, a greeting naming a person only when the job
advert names them, the resume attachment note, and a signature built from the User's
own contact Facts."""

import html
import re
from dataclasses import dataclass

from app.tailoring.contact import LINK, contact_facts, href, is_phone
from app.tailoring.content import DraftContent, FactSnapshot
from app.tailoring.placeholders import PLACEHOLDER

FIT_HEADING = "Why I fit this role:"
ATTACHMENT_NOTE = "Please find my resume attached."
# "PostgreSQL performance: made queries 60 times faster": a short label naming one of the
# job's requirements, then the proof.
_FIT_LINE = re.compile(r"^([^:.!?]{2,60}):\s+(\S.*)$", re.DOTALL)
_PERSON = re.compile(r"[A-Z][\w.'-]*(?: [A-Z][\w.'-]*){0,3}")


def _plain(text: str) -> str:
    return " ".join(text.split())


def subject(content: DraftContent, title: str, name: str) -> str:
    """The advert's own subject format when the AI found one and it names the job and
    the User; otherwise "Job title - Name"."""
    written = _plain(content.email_subject)
    title, name = _plain(title), _plain(name)
    folded = written.casefold()
    if (
        written
        and not PLACEHOLDER.search(written)
        and title.casefold() in folded
        and (not name or name.casefold() in folded)
    ):
        return written
    return f"{title} - {name}" if name else f"Application for {title}"


def greeting_name(candidate: str, job_text: str) -> str:
    """A person's name only when the job advert writes it exactly; else nothing."""
    name = _plain(candidate)
    if not name or not _PERSON.fullmatch(name):
        return ""
    return name if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", job_text) else ""


def fit_parts(text: str) -> tuple[str, str] | None:
    match = _FIT_LINE.match(_plain(text))
    return (match.group(1), match.group(2)) if match else None


@dataclass(frozen=True)
class Signature:
    name: str
    headline: str
    contact: list[str]


def signature(content: DraftContent, name: str, email: str, facts: list[FactSnapshot]) -> Signature:
    """Name, the resume's Headline, and phone | email | profile links from contact Facts."""
    headline = next(
        (_plain(line.text) for line in content.resume if line.section == "Headline"), ""
    )
    parts = contact_facts(facts)
    phones = [p for p in parts if is_phone(p)]
    others = [p for p in parts if p not in phones and LINK.search(p)]
    return Signature(
        _plain(name), headline, [*phones, email, *others] if email else [*phones, *others]
    )


def _blocks(content: DraftContent) -> list[str | list[tuple[str, str]]]:
    """Body paragraphs in order, with consecutive "Label: proof" lines as one list."""
    blocks: list[str | list[tuple[str, str]]] = []
    for line in content.email_body:
        parts = fit_parts(line.text)
        if parts is None:
            blocks.append(_plain(line.text))
        elif blocks and isinstance(blocks[-1], list):
            blocks[-1].append(parts)
        else:
            blocks.append([parts])
    return blocks


def body_text(content: DraftContent, greeting: str, sign: Signature) -> str:
    """The plain-text email, also used when Gmail is unavailable."""
    out = [f"Dear {greeting or 'Hiring Team'},"]
    listed = False
    for block in _blocks(content):
        if isinstance(block, str):
            out.append(block)
            continue
        items = "\n".join(f"- {label}: {proof}" for label, proof in block)
        out.append(items if listed else f"{FIT_HEADING}\n{items}")
        listed = True
    out.append(ATTACHMENT_NOTE)
    closing = ["Kind regards,", sign.name]
    if sign.headline:
        closing.append(sign.headline)
    if sign.contact:
        closing.append(" | ".join(sign.contact))
    out.append("\n".join(closing))
    return "\n\n".join(out)


def _linked(text: str) -> str:
    out, position = [], 0
    for match in LINK.finditer(text):
        out.append(html.escape(text[position : match.start()]))
        target = match.group(0)
        out.append(f'<a href="{html.escape(href(target))}">{html.escape(target)}</a>')
        position = match.end()
    out.append(html.escape(text[position:]))
    return "".join(out)


def body_html(content: DraftContent, greeting: str, sign: Signature) -> str:
    """The same email as HTML: bold labels, clickable links and a Gmail-style signature."""
    out = [f"<p>Dear {html.escape(greeting or 'Hiring Team')},</p>"]
    listed = False
    for block in _blocks(content):
        if isinstance(block, str):
            out.append(f"<p>{_linked(block)}</p>")
            continue
        if not listed:
            out.append(f"<p><b>{html.escape(FIT_HEADING)}</b></p>")
            listed = True
        items = "".join(
            f"<li><b>{html.escape(label)}:</b> {_linked(proof)}</li>" for label, proof in block
        )
        out.append(f"<ul>{items}</ul>")
    out.append(f"<p>{html.escape(ATTACHMENT_NOTE)}</p>")
    lines = [f'<b style="font-size:16px">{html.escape(sign.name)}</b>']
    if sign.headline:
        lines.append(html.escape(sign.headline))
    if sign.contact:
        lines.append(" | ".join(_linked(part) for part in sign.contact))
    out.append(f'<p>Kind regards,</p><div class="gmail_signature">{"<br>".join(lines)}</div>')
    return "\n".join(out)
