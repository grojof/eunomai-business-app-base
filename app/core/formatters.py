"""Numbers, dates and times as the person's language writes them. Values stay exact: only their look changes."""

from datetime import date, datetime
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from babel.dates import format_date as babel_date
from babel.dates import format_datetime as babel_datetime
from babel.numbers import format_decimal as babel_decimal
from babel.numbers import parse_decimal as babel_parse

from app.core.i18n import current_language

PRECISION = 76
"""Digits kept while formatting. Python's default of 28 cuts longer values without any error."""

MINIMUM_GROUPING_DIGITS = {"es": 2}
"""CLDR's minimumGroupingDigits, which Babel does not apply: in Spanish, 1250 but 12.500. Add yours from CLDR."""


def _groups(value: Decimal | int, language: str) -> bool:
    integer_digits = len(str(abs(int(value))))
    return integer_digits >= 3 + MINIMUM_GROUPING_DIGITS.get(language, 1)


def format_decimal(value: Decimal | int) -> str:
    language = current_language()
    with localcontext(prec=PRECISION):
        return babel_decimal(
            value, locale=language, decimal_quantization=False, group_separator=_groups(value, language)
        )


def parse_decimal(text: str) -> Decimal:
    """Reads a number as the person's language writes it. Raises ValueError if it is not one."""
    try:
        with localcontext(prec=PRECISION):
            return babel_parse(text.strip(), locale=current_language(), strict=True)
    except Exception as error:
        raise ValueError(text) from error


def format_date(value: date) -> str:
    return babel_date(value, format="medium", locale=current_language())


def format_datetime(value: datetime, time_zone: str) -> str:
    return babel_datetime(value, format="medium", tzinfo=ZoneInfo(time_zone), locale=current_language())
