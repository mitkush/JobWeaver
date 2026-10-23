"""Import every model so Alembic and create_all see the full metadata."""

from app.models.ai_usage import AIUsage
from app.models.application_profile import ApplicationProfile, SavedAnswer
from app.models.base import Base
from app.models.document import Document, DocumentKind
from app.models.draft import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    Draft,
    DraftVersion,
    GmailHandoff,
)
from app.models.extension import ExtensionCredential, ExtensionGrant
from app.models.fact import DismissedFact, Fact, FactKind, FactOrigin
from app.models.fetch import FetchRun, QueryWatermark, RunStatus
from app.models.job import Band, Job, MatchPair, PairStatus, RejectedPair, UserJob
from app.models.oauth_credential import OAuthCredential
from app.models.posting import AtsBoard, Company, Posting
from app.models.preference import Preference
from app.models.raw_advert import RawAdvert
from app.models.session import UserSession
from app.models.source import Source, SourceState
from app.models.user import Role, User

__all__ = [
    "ApplicationProfile",
    "SavedAnswer",
    "ExtensionCredential",
    "ExtensionGrant",
    "Application",
    "ApplicationEvent",
    "ApplicationStatus",
    "GmailHandoff",
    "Draft",
    "DraftVersion",
    "AIUsage",
    "AtsBoard",
    "Band",
    "Job",
    "MatchPair",
    "PairStatus",
    "RejectedPair",
    "UserJob",
    "Company",
    "FetchRun",
    "Posting",
    "QueryWatermark",
    "RawAdvert",
    "RunStatus",
    "Source",
    "SourceState",
    "Base",
    "DismissedFact",
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
