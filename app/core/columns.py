"""Column types that keep a value exact on both databases. See docs/specification.md#data"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Numeric, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

WHOLE_DIGITS = 18
DECIMAL_DIGITS = 20
COLLATION = "exact_decimal"
"""SQLite compares these columns with this collation, registered on each connection by app/core/database.py."""


def _plain(value: Decimal) -> str:
    """Fixed point and no trailing zeros. `Decimal.normalize` is not used: it rounds to the context's 28 digits."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def canonical(value: Decimal | int) -> str:
    """The one way a value is written: 1.5, 1.50 and 1.500 are the same text.

    Only a Decimal or an int gets through, and only if the column can hold it whole. PostgreSQL would round extra
    decimals without a word, and SQLite would keep them, so both refuse here.
    """
    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        raise TypeError(f"An exact column takes a Decimal or an int, not {type(value).__name__}")
    exact = Decimal(value)
    if not exact.is_finite() or (exact and exact.adjusted() >= WHOLE_DIGITS):
        raise ValueError(f"An exact column holds {WHOLE_DIGITS} digits before the point, not {value}")
    text = _plain(exact)
    if len(text.partition(".")[2]) > DECIMAL_DIGITS:
        raise ValueError(f"An exact column holds {DECIMAL_DIGITS} decimals, not {value}")
    return text


class ExactDecimal(TypeDecorator[Decimal]):
    """Money and quantities: `Numeric(38, 20)` on PostgreSQL, text on SQLite, a Decimal in Python. Never a float."""

    impl = Numeric
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(WHOLE_DIGITS + DECIMAL_DIGITS, DECIMAL_DIGITS)

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Text(collation=COLLATION))
        return dialect.type_descriptor(self.impl_instance)

    def process_bind_param(self, value: Decimal | int | None, dialect: Dialect) -> str | Decimal | None:
        if value is None:
            return None
        text = canonical(value)
        return text if dialect.name == "sqlite" else Decimal(text)

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if not isinstance(value, str | Decimal):  # a float here means the value has already lost digits
            raise TypeError(f"An exact column gave {type(value).__name__}")
        return Decimal(_plain(Decimal(value)))


class UtcDateTime(TypeDecorator[datetime]):
    """A moment, stored in UTC. It takes only an aware datetime and always gives one back in UTC.

    PostgreSQL has `timestamptz`. SQLite has no date type: SQLAlchemy keeps text of a fixed width, naive, so a moment
    is converted to UTC first. That text still orders and compares correctly.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise TypeError("A moment needs a datetime with its time zone")
        moment = value.astimezone(UTC)
        return moment.replace(tzinfo=None) if dialect.name == "sqlite" else moment

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
