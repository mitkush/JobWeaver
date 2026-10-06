"""pgvector column type without the numpy-based client package (512 MB host, ADR-0008).

Values cross the wire as text ("[0.1,0.2,...]") and are cast in SQL, so asyncpg needs no
custom codec. Similarity is computed in SQL with pgvector's operators.
"""

from typing import Any

from sqlalchemy import String, Text, cast, type_coerce
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import TypeDecorator, UserDefinedType


class _VectorText(TypeDecorator[list[float]]):
    """Sends a vector as its text form; the SQL cast turns it into a real vector."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: list[float] | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return "[" + ",".join(f"{float(v):.7g}" for v in value) + "]"

    def process_result_value(self, value: str | None, dialect: Any) -> list[float] | None:
        if value is None:
            return None
        return [float(v) for v in value.strip("[]").split(",") if v]


class Vector(UserDefinedType[list[float]]):
    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dim})"

    def bind_expression(self, bindvalue: Any) -> ColumnElement[Any]:
        return cast(type_coerce(bindvalue, _VectorText()), self)

    def column_expression(self, colexpr: Any) -> ColumnElement[Any]:
        return type_coerce(cast(colexpr, Text), _VectorText())
