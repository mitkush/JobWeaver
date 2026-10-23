import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ExtensionApproveIn(BaseModel):
    extension_id: str = Field(max_length=32)
    challenge: str = Field(max_length=64)


class ExtensionGrantOut(BaseModel):
    code: str
    expires_at: datetime


class ExtensionTokenIn(BaseModel):
    code: str = Field(max_length=128)
    verifier: str = Field(max_length=128)


class ExtensionUserOut(BaseModel):
    name: str
    email: str


class ExtensionTokenOut(BaseModel):
    token: str
    expires_at: datetime
    user: ExtensionUserOut


class ExtensionConnectionOut(BaseModel):
    id: uuid.UUID
    extension_id: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
