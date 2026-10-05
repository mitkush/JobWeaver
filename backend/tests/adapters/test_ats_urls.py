import pytest

from app.adapters.ats_urls import parse_ats_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/stripe/jobs/123", ("greenhouse", "stripe")),
        ("https://job-boards.greenhouse.io/Figma/jobs/9?gh_src=x", ("greenhouse", "figma")),
        ("https://boards.greenhouse.io/embed/job_app?for=notion&token=1", ("greenhouse", "notion")),
        ("https://jobs.lever.co/netflix/abc-123/apply", ("lever", "netflix")),
        ("https://jobs.eu.lever.co/acme/1", ("lever", "acme")),
        ("https://jobs.ashbyhq.com/linear/42", ("ashby", "linear")),
        ("https://jobs.smartrecruiters.com/Visa/7438", ("smartrecruiters", "visa")),
        ("https://apply.workable.com/huggingface/j/ABC/", ("workable", "huggingface")),
        ("https://acme.recruitee.com/o/backend", ("recruitee", "acme")),
        ("boards.greenhouse.io/stripe", ("greenhouse", "stripe")),
        ("https://www.linkedin.com/jobs/view/123", None),
        ("https://careers.google.com/jobs/1", None),
        (None, None),
    ],
)
def test_parse_ats_url(url, expected):
    assert parse_ats_url(url) == expected
