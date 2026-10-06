"""Import every model so Alembic and create_all see the full metadata."""

from app.models.ai_usage import AIUsage
from app.models.base import Base
from app.models.document import Document, DocumentKind
from app.models.fact import Fact, FactKind, FactOrigin
from app.models.fetch import FetchRun, QueryWatermark, RunStatus
from app.models.oauth_credential import OAuthCredential
from app.models.posting import AtsBoard, Company, Posting
from app.models.preference import Preference
from app.models.session import UserSession
from app.models.source import Source, SourceState
from app.models.user import Role, User

__all__ = [
    "AIUsage",
    "AtsBoard",
    "Company",
    "FetchRun",
    "Posting",
    "QueryWatermark",
    "RunStatus",
    "Source",
    "SourceState",
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
