"""Import every model so Alembic and create_all see the full metadata."""

from app.models.ai_usage import AIUsage
from app.models.base import Base
from app.models.document import Document, DocumentKind
from app.models.fact import Fact, FactKind, FactOrigin
from app.models.oauth_credential import OAuthCredential
from app.models.preference import Preference
from app.models.session import UserSession
from app.models.user import Role, User

__all__ = [
    "AIUsage",
    "Base",
    "Document",
    "DocumentKind",
    "Fact",
    "FactKind",
    "FactOrigin",
    "OAuthCredential",
    "Preference",
    "Role",
    "User",
    "UserSession",
]
