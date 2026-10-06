import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from rapidfuzz import fuzz

from app.models.job import Band

# Query parameters that identify one job on a careers page (Greenhouse embeds, Lever, ...).
_JOB_PARAMS = ("gh_jid", "jobid", "job_id", "jid", "lever-via", "id")
_TRACKING = re.compile(r"^(utm_|gh_src|source|ref|src|trk|lever-source)")
_PUNCT = re.compile(r"[^\w+#]+")
# Text shorter than this is too generic ("Apply on our site") to prove two adverts match.
MIN_TEXT_FOR_EXACT = 200


@dataclass(frozen=True)
class Thresholds:
    """Start strict so the Medium band stays small; tune on real data (FR-C1 AC3)."""

    high_title: float = 90
    high_description: float = 0.92
    medium_title: float = 75
    medium_description: float = 0.85


@dataclass(frozen=True)
class PostingView:
    id: object
    title: str
    description: str
    apply_url: str | None
    locations: Sequence[dict[str, object]]


def clean_title(title: str) -> str:
    return " ".join(_PUNCT.sub(" ", title.lower()).split())


def title_similarity(a: str, b: str) -> float:
    """0 to 100; word order does not matter ("Engineer, Backend" = "Backend Engineer")."""
    return float(fuzz.token_sort_ratio(clean_title(a), clean_title(b)))


def url_key(url: str | None) -> str | None:
    """A job-specific apply URL without tracking noise, or None for generic pages."""
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.rstrip("/").lower()
    params = {
        k.lower(): v[0] for k, v in parse_qs(parsed.query).items() if not _TRACKING.match(k.lower())
    }
    job_param = next((f"{k}={params[k]}" for k in _JOB_PARAMS if k in params), None)
    segments = [s for s in path.split("/") if s]
    if job_param is None and len(segments) < 2:
        return None  # "acme.com/careers" names no single job
    return f"{host}{path}" + (f"?{job_param}" if job_param else "")


def text_key(title: str, description: str) -> str | None:
    """Same title and same advert text, whatever the city (FR-C5 multi-location)."""
    body = " ".join(description.lower().split())
    if len(body) < MIN_TEXT_FOR_EXACT:
        return None
    return hashlib.sha1(f"{clean_title(title)}\n{body}".encode()).hexdigest()


def exact_reason(a: PostingView, b: PostingView) -> str | None:
    url_a = url_key(a.apply_url)
    if url_a is not None and url_a == url_key(b.apply_url):
        return "same_url"
    text_a = text_key(a.title, a.description)
    if text_a is not None and text_a == text_key(b.title, b.description):
        return "same_text"
    return None


def _place(location: dict[str, object]) -> tuple[str | None, str | None]:
    city = location.get("city")
    country = location.get("country")
    return (
        str(city).lower() if city else None,
        str(country).upper() if country else None,
    )


def locations_compatible(a: Sequence[dict[str, object]], b: Sequence[dict[str, object]]) -> bool:
    """False only when both sides name places and none of them can be the same place."""
    if not a or not b:
        return True
    for loc_a in a:
        city_a, country_a = _place(loc_a)
        for loc_b in b:
            city_b, country_b = _place(loc_b)
            if country_a and country_b and country_a != country_b:
                continue
            if city_a and city_b and city_a != city_b:
                continue
            return True
    return False


def band_for(
    title_score: float,
    description_score: float,
    same_place: bool,
    thresholds: Thresholds,
) -> Band | None:
    """Semantic band for a pair that has no Exact signal. None means Low (ignored)."""
    if title_score >= thresholds.high_title and description_score >= thresholds.high_description:
        # Same words in different cities might still be two openings: let a person decide.
        return Band.HIGH if same_place else Band.MEDIUM
    if (
        title_score >= thresholds.medium_title
        and description_score >= thresholds.medium_description
    ):
        return Band.MEDIUM
    return None


def embedding_text(title: str, description: str) -> str:
    """What gets embedded: the title plus the start of the advert, where the role is
    described (keeps each request inside free-tier token limits)."""
    return f"{title}\n\n{' '.join(description.split())[:3000]}"
