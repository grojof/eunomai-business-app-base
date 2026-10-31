"""Reading a form at its edge, as SEC-03 asks: each value checked here, by field, in words that say how to fix it.

A reader takes what was sent, as text, and gives back the value to save, or raises `Refused` with what the person should
read. `read_fields` runs them all and keeps each problem with its field, so a person sees every problem at once.
"""

import re
from collections.abc import Callable, Collection, Mapping
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from app.core.formatters import format_date, format_decimal, parse_date, parse_decimal
from app.core.i18n import _, ngettext

LONGEST_NUMBER = 64
"""No number a form takes is longer, and reading a very long one takes time."""
_ONE_LINE = re.compile(r"[\x00-\x1f\x7f]")
_MANY_LINES = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
"""PostgreSQL refuses a NUL inside text, and none of the others belongs in what a person types."""


class Refused(ValueError):
    """A value that cannot be saved. Its text is for the person: what to do, in their language."""


def read_fields(fields: Mapping[str, Callable[[], Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    """What can be saved, and what cannot, by field, in the order given."""
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, read in fields.items():
        try:
            clean[name] = read()
        except Refused as problem:
            errors[name] = str(problem)
    return clean, errors


def read_text(text: str, *, longest: int, missing: str = "", lines: bool = False) -> str:
    """Text without its outer spaces, and with one form of line break. `missing` says it is needed, and what to do. The
    length is checked here because SQLite does not."""
    value = text.replace("\r\n", "\n").strip()
    if not value and missing:
        raise Refused(missing)
    if (_MANY_LINES if lines else _ONE_LINE).search(value):
        raise Refused(_("Remove the special characters, such as tabs, from this text."))
    if len(value) > longest:
        raise Refused(_("Use %(most)s characters at most.") % {"most": format_decimal(longest)})
    return value


def read_choice(text: str, options: Collection[str], message: str) -> str:
    if text not in options:
        raise Refused(message)
    return text


def read_flag(text: str) -> bool:
    """A checkbox sends its value when it is ticked, and nothing when it is not."""
    if text not in ("", "yes"):
        raise Refused(_("Tick the box or leave it empty."))
    return text == "yes"


def read_decimal(
    text: str,
    low: int | Decimal,
    high: int | Decimal,
    places: int,
    *,
    not_a_number: str = "",
    out_of_range: str = "",
    too_precise: str = "",
) -> Decimal:
    """A number as the person's language writes it, exact. Never a float."""
    example = {"example": format_decimal(Decimal("7.5"), 2)}
    try:
        if len(text) > LONGEST_NUMBER:
            raise ValueError(text)
        number = parse_decimal(text)
    except ValueError:
        raise Refused(not_a_number or _("Enter a number, such as %(example)s.") % example) from None
    if not low <= number <= high:
        limits = {"low": format_decimal(low), "high": format_decimal(high)}
        raise Refused(out_of_range or _("Enter a number between %(low)s and %(high)s.") % limits)
    with localcontext(prec=len(text) + places + 8):
        if number != number.quantize(Decimal(1).scaleb(-places)):
            words = ngettext("Use %(places)s decimal at most.", "Use %(places)s decimals at most.", places)
            raise Refused(too_precise or words % {"places": places})
    return number if number else abs(number)


def read_whole(text: str, low: int, high: int, message: str = "") -> int:
    """A whole number, from the same reader: a person's language can group its digits too."""
    words = message or _("Enter a whole number between %(low)s and %(high)s.") % {
        "low": format_decimal(low),
        "high": format_decimal(high),
    }
    return int(read_decimal(text, low, high, 0, not_a_number=words, out_of_range=words, too_precise=words))


def read_date(text: str, earliest: date, latest: date, message: str, *, needed: bool = False) -> date | None:
    """A date in its one form, within what makes sense here. A year typed as 0026 is a mistake, and a valid date."""
    if not text and not needed:
        return None
    try:
        value = parse_date(text)
    except ValueError:
        raise Refused(message) from None
    if not earliest <= value <= latest:
        limits = {"earliest": format_date(earliest), "latest": format_date(latest)}
        raise Refused(_("Enter a date between %(earliest)s and %(latest)s.") % limits)
    return value
