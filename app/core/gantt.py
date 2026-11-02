"""Timelines: tasks as bars on a calendar, drawn on the server as SVG beside the native table that holds the same rows.

The table is what a screen reader and a keyboard use, and it holds every action. The picture shows when: each task's
bar, the weekends, today, and an arrow from a task to the one that waits for it. Its geometry is worked out here and
written as SVG attributes; its colours are classes, read from the theme. Nothing runs in the browser. See
docs/specification.md#timelines
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.formatters import format_month, format_month_and_year

SCALES = ("day", "week", "month")
ASKED = ("fit", *SCALES)
"""`fit` takes the finest scale that shows every task without scrolling, and is the default."""
FIT_WIDTH = 800
"""The width `fit` aims at, in the picture's units: what a wide screen shows beside its table and a filter panel."""
MAX_WIDTH = 6000
"""The widest a picture grows. Past it the scale coarsens, and past a month's it shows a window from the first task,
and counts what falls outside: a page of tasks from 2000 to 2099 at a scale of days would be megabytes."""
DAY_WIDTH = {"day": 32, "week": 12, "month": 4}
"""How wide a day is at each scale, in the picture's units: a pixel at the browser's usual text size."""
ROW = 40
HEADER = 48
BAR = 20
SHORTEST_BAR = 6
"""A one-day task at the month scale is four units: it is drawn a little wider, so that it can be seen."""
KINDS = ("neutral", "info", "warning", "success", "error")
LABEL_ROOM = 112
"""What a month and its year need, in the picture's units."""


@dataclass(frozen=True)
class Task:
    """One row. `start` and `end` are the first and the last day, both included; without them the row has no bar.
    `after` names the tasks this one waits for, by `key`."""

    key: int
    label: str
    start: date | None
    end: date | None
    kind: str = "info"
    after: tuple[int, ...] = ()


@dataclass(frozen=True)
class Bar:
    key: int
    x: int
    y: int
    width: int
    kind: str
    label: str


@dataclass(frozen=True)
class Tick:
    x: int
    label: str
    first: bool
    """The first day of a month: its line is stronger, and it names the month."""


@dataclass(frozen=True)
class Timeline:
    """What the `timeline` macro draws. Rows are tasks or, for a group's heading, None."""

    scale: str
    asked: str
    outside: int
    width: int
    height: int
    bars: list[Bar]
    links: list[str]
    weekends: list[int]
    ticks: list[Tick]
    months: list[Tick]
    today: int | None
    first: date
    last: date

    @property
    def unit(self) -> int:
        return DAY_WIDTH[self.scale]

    @property
    def rows(self) -> int:
        return (self.height - HEADER) // ROW


def _ticks(first: date, last: date, scale: str, x_of: Callable[[date], int]) -> tuple[list[Tick], list[Tick]]:
    """The scale's labels, and the months above them."""
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    months = [Tick(x_of(day), format_month_and_year(day), True) for day in days if day.day == 1 or day == first]
    if scale == "day":
        ticks = [Tick(x_of(day), str(day.day), day.day == 1) for day in days]
    elif scale == "week":
        ticks = [Tick(x_of(day), str(day.day), day.day <= 7) for day in days if day.weekday() == 0]
    else:
        ticks = [Tick(x_of(day), format_month(day), True) for day in days if day.day == 1]
        months = [
            Tick(x_of(day), str(day.year), True) for day in days if day == first or (day.day, day.month) == (1, 1)
        ]
    return ticks, _with_room(months)


def _with_room(ticks: list[Tick]) -> list[Tick]:
    """A label that the next one would cover gives way: a calendar that starts a few days before a month."""
    return [
        tick
        for tick, following in zip(ticks, [*ticks[1:], None], strict=True)
        if not following or following.x - tick.x >= LABEL_ROOM
    ]


def _link(start: Bar, end: Bar) -> str:
    """An arrow from the end of one bar to the start of the next: out to the right, down or up, then in."""
    x1, y1 = start.x + start.width, start.y + BAR // 2
    x2, y2 = end.x, end.y + BAR // 2
    turn = x1 + 8
    if x2 - 8 >= turn:
        return f"M{x1} {y1}H{turn}V{y2}H{x2}"
    middle = end.y - (ROW - BAR) // 2 if y2 > y1 else end.y + BAR + (ROW - BAR) // 2
    return f"M{x1} {y1}H{turn}V{middle}H{x2 - 8}V{y2}H{x2}"


def _start(first: date, scale: str) -> date:
    if scale == "month":
        return first.replace(day=1)
    if scale == "week":
        return first - timedelta(days=first.weekday())
    return first


def _scale(asked: str, first: date, last: date) -> str:
    """The scale to draw: the one asked for while it stays within MAX_WIDTH, else the next coarser; for `fit`, the
    finest within FIT_WIDTH, else months."""
    days = (last - first).days + 1
    if asked == "fit":
        return next((scale for scale in SCALES if days * DAY_WIDTH[scale] <= FIT_WIDTH), "month")
    coarser = SCALES[SCALES.index(asked) :]
    return next((scale for scale in coarser if days * DAY_WIDTH[scale] <= MAX_WIDTH), "month")


def timeline(rows: Sequence[Task | None], scale: str, today: date, margin: int = 2) -> Timeline:
    """Lays out the rows, in their order, on a calendar from the first start to the last end, with `margin` days on
    either side, at the scale asked for or, if it would be too wide, a coarser one. A scale off its list is `fit`."""
    asked = scale if scale in ASKED else "fit"
    tasks = [row for row in rows if row is not None and row.start and row.end]
    starts = [task.start for task in tasks if task.start] or [today]
    ends = [task.end for task in tasks if task.end] or [today]
    first = min(starts) - timedelta(days=margin)
    last = max(ends) + timedelta(days=margin)
    scale = _scale(asked, first, last)
    first = _start(first, scale)
    unit = DAY_WIDTH[scale]
    last = min(last, first + timedelta(days=MAX_WIDTH // unit - 1))
    shown = [row for row in tasks if row.start and row.start <= last]
    outside = len(tasks) - len(shown)

    def x_of(day: date) -> int:
        return (day - first).days * unit

    bars: list[Bar] = []
    for position, row in enumerate(rows):
        if row is None or not (row.start and row.end) or row.start > last:
            continue
        width = max((min(row.end, last) - row.start).days + 1, 1) * unit
        y = HEADER + position * ROW + (ROW - BAR) // 2
        bars.append(
            Bar(
                row.key,
                x_of(row.start),
                y,
                max(width, SHORTEST_BAR),
                row.kind if row.kind in KINDS else "info",
                row.label,
            )
        )
    placed = {bar.key: bar for bar in bars}
    links = [
        _link(placed[before], placed[task.key])
        for task in tasks
        for before in task.after
        if before in placed and task.key in placed
    ]
    span = (last - first).days + 1
    weekends = [
        x_of(first + timedelta(days=offset))
        for offset in range(span)
        if (first + timedelta(days=offset)).weekday() >= 5
    ]
    ticks, months = _ticks(first, last, scale, x_of)
    return Timeline(
        scale,
        asked,
        outside,
        span * unit,
        HEADER + len(rows) * ROW,
        bars,
        links,
        weekends if scale != "month" else [],
        ticks,
        months,
        x_of(today) if first <= today <= last else None,
        first,
        last,
    )
