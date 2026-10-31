"""The database: its connection, a session per request, and what keeps SQLite honest. See docs/specification.md#data"""

import sqlite3
from collections.abc import Iterable, Iterator
from datetime import datetime
from decimal import MAX_PREC, Decimal, localcontext
from pathlib import Path
from typing import Annotated, Any, ClassVar

from alembic import command
from alembic.config import Config
from fastapi import Depends, Request
from sqlalchemy import (
    BinaryExpression,
    Case,
    Cast,
    ColumnElement,
    Engine,
    FunctionElement,
    MetaData,
    Select,
    TypeCoerce,
    UnaryExpression,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Session
from sqlalchemy.sql import operators, visitors

from app.core.columns import COLLATION, ExactDecimal, UtcDateTime

ROOT = Path(__file__).resolve().parent.parent.parent
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Constraints with names, the same on both databases: a batch migration on SQLite can only change a named one."""
SAFE_ON_TEXT = {"count", "max", "min"}
"""Functions that give the right answer on SQLite: `count` reads no value, `max` and `min` follow the collation."""
ARITHMETIC = {
    operators.add,
    operators.sub,
    operators.mul,
    operators.truediv,
    operators.floordiv,
    operators.mod,
    operators.neg,
    operators.collate,
}
"""On text, SQLite converts to a float first. A new collation would go back to comparing letters."""


class Base(DeclarativeBase):
    """The base of every model. `Mapped[Decimal]` and `Mapped[datetime]` get the exact types without asking."""

    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map: ClassVar[dict[Any, Any]] = {Decimal: ExactDecimal, datetime: UtcDateTime}


class InexactQuery(Exception):
    """SQLite would answer this query with a float or a text comparison, without saying so."""


def _holds_exact_column(element: Any) -> bool:
    return any(isinstance(getattr(part, "type", None), ExactDecimal) for part in visitors.iterate(element))


def _is_inexact(element: Any) -> bool:
    if isinstance(element, FunctionElement):
        return getattr(element, "name", "") not in SAFE_ON_TEXT and _holds_exact_column(element)
    if isinstance(element, Case | Cast | TypeCoerce):
        return _holds_exact_column(element)
    if isinstance(element, BinaryExpression | UnaryExpression):
        return element.operator in ARITHMETIC and _holds_exact_column(element)
    return False


def _refuse_inexact(_connection: Any, statement: Any, *_rest: Any) -> None:
    """Runs before each statement on SQLite. Text written by hand, with `text()`, is not read: see the specification."""
    for element in visitors.iterate(statement):
        if _is_inexact(element):
            raise InexactQuery(
                f"SQLite keeps decimals as text, so this would not be exact: {element}. "
                "Use total() or exact_sum(), or do it in Python. See docs/specification.md#data"
            )


def _compare_decimals(first: str, second: str) -> int:
    a, b = Decimal(first), Decimal(second)
    return (a > b) - (a < b)


def _prepare_sqlite(connection: sqlite3.Connection, _record: Any) -> None:
    connection.create_collation(COLLATION, _compare_decimals)
    connection.execute("PRAGMA foreign_keys=ON")  # off by default, on each connection


def create_database_engine(url: str) -> Engine:
    """Nothing connects yet: the first query does, so an application that uses no database needs none."""
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        database = engine.url.database

        def make_folder(*_arguments: Any) -> None:
            if database and database != ":memory:":
                Path(database).resolve().parent.mkdir(parents=True, exist_ok=True)

        event.listen(engine, "do_connect", make_folder)
        event.listen(engine, "connect", _prepare_sqlite)
        event.listen(engine, "before_execute", _refuse_inexact)
    return engine


def get_session(request: Request) -> Iterator[Session]:
    """A session for one request. Nothing is saved unless the route calls `session.commit()`.

    A route that uses it is declared with `def`, not `async def`: FastAPI then runs it in a worker thread, and a slow
    query does not stop the server. The commit stays in the route so a failure can still reach the person.
    """
    with request.app.state.sessions() as session:
        yield session


DatabaseSession = Annotated[Session, Depends(get_session)]


def exact_sum(values: Iterable[Decimal | None]) -> Decimal:
    """Adds without losing a digit: Python's `sum` rounds to the context's 28, without an error."""
    with localcontext(prec=MAX_PREC):
        return sum((value for value in values if value is not None), Decimal(0))


def total(session: Session, column: InstrumentedAttribute[Any], *conditions: ColumnElement[bool]) -> Decimal:
    """The sum of an exact column, the same answer on both databases: in SQL on PostgreSQL, in Python on SQLite."""
    if session.get_bind().dialect.name == "sqlite":
        return exact_sum(session.scalars(select(column).where(*conditions)))
    return session.scalar(select(func.sum(column)).where(*conditions)) or Decimal(0)


def totals_by(
    session: Session, statement: Select[*tuple[Any, ...]], key: Any, column: Any
) -> dict[Any, tuple[int, Decimal]]:
    """Rows and the sum of an exact column for each group, the same answer on both databases, as `total()` gives."""
    if session.get_bind().dialect.name != "sqlite":
        grouped = statement.with_only_columns(key, func.count(), func.sum(column), maintain_column_froms=True)
        return {group: (count, amount or Decimal(0)) for group, count, amount in session.execute(grouped.group_by(key))}
    values: dict[Any, list[Decimal]] = {}
    for group, value in session.execute(statement.with_only_columns(key, column, maintain_column_froms=True)):
        values.setdefault(group, []).append(value)
    return {group: (len(found), exact_sum(found)) for group, found in values.items()}


def migrate(url: str) -> None:
    """The same as `alembic upgrade head`, for code that needs it."""
    config = Config(toml_file=str(ROOT / "pyproject.toml"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
