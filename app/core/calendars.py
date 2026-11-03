"""Calendars: events on the server, drawn in the browser by FullCalendar. See docs/base/specification.md#calendars

The server owns the events and the words. It sends events as JSON with their moments in UTC, FullCalendar shows them in
the application's time zone, and a drop sends back the new moment with its offset, read here into UTC again. Every word
FullCalendar shows or announces comes from this application's catalogue, so Spanish and Catalan are ours to correct.
Without JavaScript the same events are an agenda drawn on the server, with its own links to move through the calendar.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.core.forms import Refused
from app.core.i18n import _, current_language

VIEWS = ("month", "week", "agenda")
_MOMENT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
PADDING = timedelta(days=15)
"""What a view shows past its period: a month view starts on the Monday before the 1st and runs six weeks."""


@dataclass(frozen=True)
class Limits:
    """The days a calendar accepts, and the longest range it gives events for at once. An application whose dates go
    further passes its own to `Period.read`, `read_range`, `read_moment` and `read_day`."""

    earliest: date = date(2000, 1, 1)
    latest: date = date(2099, 12, 31)
    longest: int = 62


LIMITS = Limits()


@dataclass(frozen=True)
class CalendarEvent:
    """One event. `start` and `end` are moments with their time zone, or days for an all-day event, whose `end` is the
    last day, included. `url` is where a keyboard goes to change it, through a form."""

    id: str
    title: str
    start: datetime | date
    end: datetime | date
    url: str
    kind: str = "primary"
    version: int = 1
    movable: bool = False

    @property
    def all_day(self) -> bool:
        return not isinstance(self.start, datetime)

    def as_json(self) -> dict[str, Any]:
        """FullCalendar's form. An all-day event's end there is the day after its last."""
        if isinstance(self.start, datetime) and isinstance(self.end, datetime):
            start, end = _utc(self.start), _utc(self.end)
        else:
            start, end = self.start.isoformat(), (self.end + timedelta(days=1)).isoformat()
        return {
            "id": self.id,
            "title": self.title,
            "start": start,
            "end": end,
            "allDay": self.all_day,
            "url": self.url,
            "editable": self.movable,
            "extendedProps": {"version": self.version, "kind": self.kind},
        }


def _utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Period:
    """What a calendar's address asks for: a view and a day in it, checked against their lists."""

    view: str
    day: date

    @classmethod
    def read(cls, params: Any, today: date, limits: Limits = LIMITS) -> "Period":
        view = params.get("view", "")
        text = params.get("date", "")
        day = date.fromisoformat(text) if _DAY.fullmatch(text) and _valid(text) else today
        return cls(view if view in VIEWS else "month", min(max(day, limits.earliest), limits.latest))

    @property
    def first(self) -> date:
        if self.view == "month":
            start = self.day.replace(day=1)
            return start - timedelta(days=start.weekday())
        return self.day - timedelta(days=self.day.weekday())

    @property
    def last(self) -> date:
        """The last day shown, included."""
        if self.view == "month":
            following = (self.day.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = following - timedelta(days=1)
            return end + timedelta(days=6 - end.weekday())
        return self.first + timedelta(days=6)

    def step(self, forward: bool) -> date:
        if self.view == "month":
            month = self.day.replace(day=15) + timedelta(days=31 if forward else -31)
            return month.replace(day=1)
        return self.day + timedelta(days=7 if forward else -7)

    def address(self, path: str, view: str | None = None, day: date | None = None, **more: str) -> str:
        query = {
            "view": view or self.view,
            "date": (day or self.day).isoformat(),
            **{k: v for k, v in more.items() if v},
        }
        return f"{path}?{urlencode(query)}"

    def bounds(self, zone: str) -> tuple[datetime, datetime]:
        """The moments the period covers in the application's time zone, in UTC, for a query."""
        local = ZoneInfo(zone)
        start = datetime.combine(self.first, time(), local).astimezone(UTC)
        end = datetime.combine(self.last + timedelta(days=1), time(), local).astimezone(UTC)
        return start, end


def _valid(text: str) -> bool:
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def read_range(start: str, end: str, limits: Limits = LIMITS) -> tuple[date, date]:
    """The days FullCalendar asks events for: its first, and the day after its last. Only the day part is read. A view
    at the edge of the limits asks for a little past them, and gets it."""
    days = [text[:10] for text in (start, end)]
    if not all(_DAY.fullmatch(day) and _valid(day) for day in days):
        raise Refused("range")
    first, after = (date.fromisoformat(day) for day in days)
    within = limits.earliest - PADDING <= first < after <= limits.latest + timedelta(days=1) + PADDING
    if not within or (after - first).days > limits.longest:
        raise Refused("range")
    return first, after


def read_moment(text: str, limits: Limits = LIMITS) -> datetime:
    """A moment as a drop sends it, with its offset, in UTC. Anything else is refused: a moment without a time zone
    means nothing."""
    if not _MOMENT.fullmatch(text):
        raise Refused(_("That time could not be read."))
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise Refused(_("That time could not be read.")) from None
    if not limits.earliest <= value.date() <= limits.latest:
        raise Refused(_("That time could not be read."))
    return value.astimezone(UTC)


def read_day(text: str, limits: Limits = LIMITS) -> date:
    """A day as a drop of an all-day event sends it."""
    if not (_DAY.fullmatch(text) and _valid(text)):
        raise Refused(_("That day could not be read."))
    day = date.fromisoformat(text)
    if not limits.earliest <= day <= limits.latest:
        raise Refused(_("That day could not be read."))
    return day


def calendar_words() -> dict[str, Any]:
    """Every word FullCalendar shows or announces, in the person's language. A hint holds its button's words, so what
    a screen reader says is what a person sees: WCAG 2.5.3."""
    previous, following, today = _("Previous"), _("Next"), _("Today")
    return {
        "code": current_language().replace("_", "-"),
        "prevText": previous,
        "nextText": following,
        "todayText": today,
        "prevYearText": _("Previous year"),
        "nextYearText": _("Next year"),
        "yearText": _("Year"),
        "monthText": _("Month"),
        "weekTextLong": _("Week"),
        "weekTextShort": _("Wk"),
        "dayText": _("Day"),
        "listText": _("Agenda"),
        "allDayText": _("All day"),
        "timedText": _("At a time"),
        "moreLinkText": _("more"),
        "noEventsText": _("Nothing in these days."),
        "closeHint": _("Close"),
        "eventsHint": _("Events"),
        "viewChangeHint": _("Change the view"),
        "prevHint": {"month": _("Previous month"), "week": _("Previous week"), "list": _("Previous week")},
        "nextHint": {"month": _("Next month"), "week": _("Next week"), "list": _("Next week")},
        "todayHint": {"month": today, "week": today, "list": today},
        "viewHint": {"month": _("Month view"), "week": _("Week view"), "list": _("Agenda view")},
        "moreLinkHint": _("Show %(count)s more events") % {"count": "{n}"},
        "moreLinkHintOne": _("Show 1 more event"),
        "navLinkHint": _("Go to %(day)s") % {"day": "{date}"},
        "moved": _("%(event)s is now on %(when)s."),
        "refused": _("That could not be moved. It is back where it was."),
    }


def calendar_config(
    events: str | list[dict[str, Any]],
    move: str,
    zone: str,
    period: Period,
    today: date,
    can_move: bool,
    extra: Sequence[tuple[str, str]] = (),
    hours: tuple[str, str] = ("06:00", "20:00"),
) -> dict[str, Any]:
    """What calendar.js needs, as JSON in the page: where the events are, or the events themselves for a calendar that
    never changes, where a drop goes, the hours a week shows, and every word."""
    return {
        "events": events,
        "move": move,
        "timeZone": zone,
        "view": period.view,
        "date": period.day.isoformat(),
        "today": today.isoformat(),
        "canMove": can_move,
        "hours": list(hours),
        "extra": dict(extra),
        "words": calendar_words(),
    }
