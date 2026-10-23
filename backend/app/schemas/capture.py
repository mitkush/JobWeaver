"""Only reviewed public advert text, never a whole application form."""

import ipaddress
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator

JOB_PARAMS = frozenset({"gh_jid", "jobid", "job_id", "reqid", "requisitionid", "jid", "id"})


def public_page_url(value: str) -> str:
    parts = urlsplit(value.strip())
    host = parts.hostname or ""
    if parts.scheme not in ("https", "http") or not host or parts.username or parts.password:
        raise ValueError("Use a public http(s) job page URL without login details")
    if "." not in host or host.lower().endswith((".localhost", ".local", ".internal")):
        raise ValueError("Use a public careers page")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Use a public careers page")
    # Never retain tracking, login tokens or fragments from the User's browser URL.
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() in JOB_PARAMS])
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, query, ""))


class CaptureIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    company: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=80, max_length=50000)
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("title", "company", "description", mode="before")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Advert fields must be text")
        value = value.strip()
        if not value:
            raise ValueError("Review and complete the advert fields before saving")
        return value

    @field_validator("url")
    @classmethod
    def page_url(cls, value: str) -> str:
        return public_page_url(value)


class CapturedJobOut(BaseModel):
    job_id: uuid.UUID
    title: str
    company: str
    matched_existing: bool


class CapturedDraftOut(BaseModel):
    draft_id: uuid.UUID
    state: str
