"""Encryption at rest for credentials, and token helpers."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AuthError, JobWeaverError


def _fernet() -> Fernet:
    key = get_settings().credentials_encryption_key
    if not key:
        raise JobWeaverError("CREDENTIALS_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise JobWeaverError("Stored credential could not be decrypted") from exc


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign_payload(payload: dict[str, object], max_age_seconds: int) -> str:
    """Tamper-proof, expiring token for OAuth state values."""
    body = dict(payload, exp=int(time.time()) + max_age_seconds)
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
    return f"{raw}.{_sign(raw)}"


def verify_payload(token: str) -> dict[str, object]:
    raw, _, signature = token.partition(".")
    if not raw or not hmac.compare_digest(signature, _sign(raw)):
        raise AuthError("Invalid sign-in state")
    try:
        body = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Invalid sign-in state") from exc
    if int(body.get("exp", 0)) < time.time():
        raise AuthError("The sign-in attempt expired. Please try again.")
    return body


def _sign(raw: str) -> str:
    secret = get_settings().session_secret.encode()
    return hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()
