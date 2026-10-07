"""Gmail draft creation only. There is deliberately no send operation."""

import base64
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx

from app.core.errors import ExternalServiceError, GoogleFlowError

DRAFTS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"


def compose_url(sender: str, recipient: str, subject: str, body: str) -> str:
    params = urlencode({"view": "cm", "fs": "1", "to": recipient, "su": subject, "body": body})
    return f"https://mail.google.com/mail/u/{sender}/?{params}"


def raw_message(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    pdf: bytes | None = None,
    filename: str | None = None,
) -> str:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if pdf is not None:  # follow-up emails carry no attachment
        message.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


class GmailClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def create_draft(self, access_token: str, raw: str) -> str:
        try:
            response = await self.http.post(
                DRAFTS_URL,
                json={"message": {"raw": raw}},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("Gmail could not be reached") from exc
        if response.status_code == 401:
            raise GoogleFlowError("gmail_expired", "Connect Gmail again to continue")
        if response.status_code >= 400:
            raise ExternalServiceError("Gmail draft creation failed")
        try:
            draft_id = response.json()["id"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ExternalServiceError("Gmail sent an unexpected response") from exc
        if not isinstance(draft_id, str) or not draft_id:
            raise ExternalServiceError("Gmail sent an unexpected response")
        return draft_id


_http = httpx.AsyncClient(timeout=httpx.Timeout(20.0))


def get_gmail_client() -> GmailClient:
    return GmailClient(_http)
