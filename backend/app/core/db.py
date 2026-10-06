from collections.abc import AsyncIterator, Iterable
from typing import Any

from sqlalchemy import ColumnElement, Uuid, any_, literal
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def among(
    column: ColumnElement[Any], ids: Iterable[Any], item_type: Any = None
) -> ColumnElement[bool]:
    """`column = ANY(:ids)`: one bound parameter however many ids. A plain IN list uses a
    parameter per id, and asyncpg allows at most 32,767 per statement."""
    return column == any_(literal(list(ids), ARRAY(item_type or Uuid())))
