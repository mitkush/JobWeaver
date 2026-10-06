import pytest

from app.adapters.base import (
    FetchMode,
    FetchResult,
    FetchWindow,
    SnapshotSourceAdapter,
    SourceQuery,
    WindowedSourceAdapter,
)
from app.adapters.registry import (
    _REGISTRY,
    get_adapter_class,
    register_adapter,
    registered_adapters,
)


@pytest.fixture(autouse=True)
def isolated_registry():
    saved = dict(_REGISTRY)
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(saved)


class FakeBoard(SnapshotSourceAdapter):
    name = "fake-board"
    priority = 3

    async def fetch_board(self, board_slug: str) -> FetchResult:
        return FetchResult(postings=[])


class FakeSearch(WindowedSourceAdapter):
    name = "fake-search"
    priority = 1

    async def fetch_window(self, query: SourceQuery, window: FetchWindow) -> FetchResult:
        return FetchResult(postings=[], requests_used=1)


def test_adapters_register_by_name_and_sort_by_priority():
    register_adapter(FakeBoard)
    register_adapter(FakeSearch)
    assert get_adapter_class("fake-board") is FakeBoard
    assert [a.name for a in registered_adapters()] == ["fake-search", "fake-board"]
    assert FakeBoard.mode == FetchMode.SNAPSHOT and FakeSearch.mode == FetchMode.WINDOWED


def test_duplicate_names_are_rejected():
    register_adapter(FakeBoard)

    class Other(FakeBoard):
        pass

    with pytest.raises(ValueError):
        register_adapter(Other)


def test_unknown_adapter_is_a_clear_error():
    with pytest.raises(KeyError, match="no-such"):
        get_adapter_class("no-such")
