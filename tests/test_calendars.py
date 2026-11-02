"""Calendars on their own: what stays in an application after the demo is deleted."""

from datetime import date

import pytest

from app.core.calendars import Limits, Period, read_day, read_range
from app.core.forms import Refused


def test_a_month_at_the_edge_of_the_limits_can_ask_for_its_padding():
    """January 2000's month view starts on 27 December 1999, and that is still its own period."""
    assert read_range("1999-12-27", "2000-02-07") == (date(1999, 12, 27), date(2000, 2, 7))
    assert read_range("2099-11-30", "2100-01-11") == (date(2099, 11, 30), date(2100, 1, 11))


@pytest.mark.parametrize(("start", "end"), [("1999-10-01", "1999-10-08"), ("2026-01-01", "2026-12-31"), ("x", "y")])
def test_a_range_past_the_padding_or_too_long_is_refused(start, end):
    with pytest.raises(Refused):
        read_range(start, end)


def test_an_application_sets_its_own_limits():
    limits = Limits(date(1950, 1, 1), date(2200, 12, 31), longest=400)
    assert read_range("1950-01-01", "1951-01-01", limits) == (date(1950, 1, 1), date(1951, 1, 1))
    assert read_day("2150-06-01", limits) == date(2150, 6, 1)
    assert Period.read({"date": "1960-05-05"}, date(2026, 1, 1), limits).day == date(1960, 5, 5)
    with pytest.raises(Refused):
        read_day("2150-06-01")
