import pytest

from app.core.errors import GatewayError
from app.gateway.parsing import parse_output
from app.gateway.schemas import ParseDocumentsResult


def test_accepts_fenced_json():
    raw = '```json\n{"facts": []}\n```'
    assert parse_output(raw, ParseDocumentsResult).facts == []


@pytest.mark.parametrize(
    "raw",
    ["no json here", '{"facts": [{"kind": "spaceship"}]}', '{"refusal": "cannot help"}'],
)
def test_rejects_anything_that_is_not_the_task_schema(raw):
    with pytest.raises(GatewayError):
        parse_output(raw, ParseDocumentsResult)
