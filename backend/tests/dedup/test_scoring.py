import pytest

from app.dedup.scoring import (
    PostingView,
    Thresholds,
    band_for,
    embedding_text,
    exact_reason,
    locations_compatible,
    text_key,
    title_similarity,
    url_key,
)
from app.gateway.recorded import recorded_vector
from app.models.job import Band

ADVERT = (
    "We are hiring a backend engineer to build payment APIs in Python and PostgreSQL. "
    "You will design services, own reliability, review code and mentor engineers. "
    "Experience with Kubernetes, Kafka and AWS is a plus. Hybrid in Bengaluru."
)


def view(title="Backend Engineer", description=ADVERT, url=None, locations=()):
    return PostingView(
        id=1, title=title, description=description, apply_url=url, locations=list(locations)
    )


@pytest.mark.parametrize(
    ("url", "key"),
    [
        (
            "https://boards.greenhouse.io/stripe/jobs/123?gh_src=linkedin&utm_source=x",
            "boards.greenhouse.io/stripe/jobs/123",
        ),
        ("https://www.acme.com/careers?gh_jid=42&utm_medium=x", "acme.com/careers?gh_jid=42"),
        ("https://jobs.lever.co/acme/abc-def/", "jobs.lever.co/acme/abc-def"),
        ("https://acme.com/careers", None),
        ("https://acme.com/", None),
        (None, None),
    ],
)
def test_url_key_keeps_only_what_identifies_the_job(url, key):
    assert url_key(url) == key


def test_same_apply_url_from_two_sources_is_exact():
    a = view(url="https://boards.greenhouse.io/stripe/jobs/123?gh_src=linkedin")
    b = view(title="Software Engineer, Backend", url="https://boards.greenhouse.io/stripe/jobs/123")
    assert exact_reason(a, b) == "same_url"


def test_same_text_in_two_cities_is_exact_multi_location():
    a = view(locations=[{"city": "Bengaluru", "country": "IN"}])
    b = view(locations=[{"city": "Pune", "country": "IN"}])
    assert exact_reason(a, b) == "same_text"


def test_short_generic_text_proves_nothing():
    assert text_key("Engineer", "Apply on our website.") is None
    assert exact_reason(view(description="Apply now"), view(description="Apply now")) is None


def test_backend_and_data_engineer_titles_are_far_apart():
    # FR-C1 AC2: two roles at one Company stay Low, whatever the boilerplate.
    assert title_similarity("Backend Engineer", "Data Engineer") < Thresholds().medium_title
    assert (
        band_for(title_similarity("Backend Engineer", "Data Engineer"), 0.99, True, Thresholds())
        is None
    )


def test_word_order_and_punctuation_do_not_matter():
    assert title_similarity("Engineer, Backend (Payments)", "Backend Engineer - Payments") == 100


@pytest.mark.parametrize(
    ("title", "description", "same_place", "band"),
    [
        (95, 0.95, True, Band.HIGH),
        (95, 0.95, False, Band.MEDIUM),
        (80, 0.88, True, Band.MEDIUM),
        (95, 0.80, True, None),
        (60, 0.99, True, None),
    ],
)
def test_bands(title, description, same_place, band):
    assert band_for(title, description, same_place, Thresholds()) == band


@pytest.mark.parametrize(
    ("a", "b", "ok"),
    [
        ([], [{"city": "Pune", "country": "IN"}], True),
        ([{"city": "Pune", "country": "IN"}], [{"city": "pune", "country": "in"}], True),
        ([{"city": None, "country": "IN"}], [{"city": "Pune", "country": "IN"}], True),
        ([{"city": "Pune", "country": "IN"}], [{"city": "Mumbai", "country": "IN"}], False),
        ([{"city": "London", "country": "GB"}], [{"city": "London", "country": "CA"}], False),
    ],
)
def test_locations_compatible(a, b, ok):
    assert locations_compatible(a, b) is ok


def cosine(a: str, b: str) -> float:
    va, vb = recorded_vector(a), recorded_vector(b)
    return sum(x * y for x, y in zip(va, vb, strict=True))


def test_labelled_pairs_with_recorded_vectors():
    """A small labelled set (FR-C1 AC1, AC2). Recorded vectors are word-based, so this
    checks the banding logic; thresholds must be re-checked on real Gemini vectors."""
    # Lightly reworded, as job boards do when re-posting an ATS advert.
    reworded = ADVERT.replace("a plus", "welcome")
    other_role = (
        "We are hiring a data engineer to build pipelines in Spark and Airflow. "
        "You will model warehouses, own data quality and partner with analysts. "
        "Experience with dbt, BigQuery and AWS is a plus. Hybrid in Bengaluru."
    )
    th = Thresholds()
    same = band_for(
        title_similarity("Backend Engineer", "Backend Engineer"),
        cosine(
            embedding_text("Backend Engineer", ADVERT), embedding_text("Backend Engineer", reworded)
        ),
        True,
        th,
    )
    different = band_for(
        title_similarity("Backend Engineer", "Data Engineer"),
        cosine(
            embedding_text("Backend Engineer", ADVERT), embedding_text("Data Engineer", other_role)
        ),
        True,
        th,
    )
    assert same in (Band.HIGH, Band.EXACT)
    assert different is None
