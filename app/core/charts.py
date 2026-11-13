"""Charts: what a figure shows, made on the server. See docs/base/data/charts.md#charts

A chart is a picture of numbers worked out here. They travel to the browser as text, so no Decimal becomes a float on
this side, and its table is written here too, with the locale's formatter, so it holds what a person reads.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from app.core.addresses import is_local
from app.core.formatters import format_decimal

CHART_TYPES = {"bar", "stacked", "line", "area", "pie", "doughnut", "radar", "polar", "scatter", "bubble", "mixed"}
ROUND_TYPES = {"pie", "doughnut", "polar"}
"""Chart.js draws a negative value in these as if it were positive: the picture would lie."""
SERIES_COLOURS = ("primary", "accent", "secondary", "info")
"""The fixed order for series, from the theme. `neutral` is left out: on the dark theme it cannot be told from the page.
A fifth series is a sign that the chart should be two charts."""
STATE_COLOURS = ("success", "warning", "error")
"""Reserved for states, which is where they mean something."""
SLICE_COLOURS = (*SERIES_COLOURS, "warning", "success", "error")
"""A pie can have more parts than a chart has series, and the theme has no more colours."""
Number = Decimal | int


@dataclass(frozen=True)
class Series:
    """One line of numbers. `colour` is a theme colour; empty takes the next in the fixed order."""

    label: str
    values: Sequence[Number | None]
    colour: str = ""
    kind: str = ""  # "line" on a mixed chart


@dataclass(frozen=True)
class Point:
    """One mark of a scatter or bubble chart. `size` is drawn as a radius in pixels on a bubble chart."""

    label: str
    x: Number
    y: Number
    size: Number | None = None


def _text(value: Number | None) -> str | None:
    if value is None:
        return None
    exact = Decimal(value)
    if not exact.is_finite():
        raise ValueError("A chart draws finite numbers: an empty value is None")
    return format(exact, "f")


def _cell(value: Number | None, places: int | None) -> str:
    return "" if value is None else format_decimal(value, places)


def _known(colour: str) -> str:
    """A colour the browser cannot find leaves a chart with nothing to draw: better an error here, while writing it."""
    if colour not in SLICE_COLOURS:
        raise ValueError(f"Not a colour a chart can use: {colour}. It takes {', '.join(SLICE_COLOURS)}")
    return colour


def _colour_of(series: Series, position: int) -> str:
    if series.colour:
        return _known(series.colour)
    if position >= len(SERIES_COLOURS):
        raise ValueError("A chart holds four series: make it two charts, or join the small ones")
    return SERIES_COLOURS[position]


@dataclass(frozen=True)
class ChartData:
    """What the `chart` macro needs: the JSON that goes to the browser, and the same numbers as a table."""

    config: dict[str, Any]
    headers: list[str]
    rows: list[list[str]]
    links: list[str] = field(default_factory=list)
    """Where each label leads, if anywhere: a click on its part of the picture, or its link in the table."""

    @property
    def link_values(self) -> list[str]:
        """What each link chooses, as the JSON htmx sends with a list's form on the same page, in place of the form's
        own values: every value of the address that changes from link to link, such as `location`. A single link
        chooses all of its values."""
        params = [dict(parse_qsl(urlsplit(link).query, keep_blank_values=True)) for link in self.links]
        names = sorted({name for one in params for name in one})
        varying = [name for name in names if len({one.get(name) for one in params}) > 1] or names
        return [json.dumps({name: one.get(name, "") for name in varying}) for one in params]

    def config_for(self, chart_type: str) -> dict[str, Any]:
        if chart_type not in CHART_TYPES:
            raise ValueError(f"Not a chart type: {chart_type}")
        if chart_type in ROUND_TYPES and any(
            value is not None and value.startswith("-") for line in self.config["series"] for value in line["values"]
        ):
            raise ValueError(f"A {chart_type} chart cannot show a negative value: use bars")
        return {**self.config, "type": chart_type}


def chart_data(
    labels: Sequence[str],
    series: Sequence[Series],
    row_header: str,
    places: int | None = None,
    unit: str = "",
    x_axis: str = "",
    y_axis: str = "",
    colours: Sequence[str] = SLICE_COLOURS,
    links: Sequence[str] = (),
) -> ChartData:
    """Rows of labels with one or more series. `colours` are a pie's, one per label. `links`, one per label, make the
    chart a way to choose: each is an address of this application, such as a list with that label as its filter."""
    if any(len(line.values) != len(labels) for line in series):
        raise ValueError("Each series needs one value per label")
    if links and len(links) != len(labels):
        raise ValueError("One link per label, or none")
    if not all(is_local(link) for link in links):
        raise ValueError("A chart's links stay in the application: each starts with a single /")
    if len(labels) > len(colours) and len(series) == 1 and colours is not SLICE_COLOURS:
        raise ValueError("One colour per slice")
    for colour in colours:
        _known(colour)
    config = {
        "labels": list(labels),
        "series": [
            {
                "label": line.label,
                "values": [_text(value) for value in line.values],
                "colour": _colour_of(line, position),
                "kind": line.kind,
            }
            for position, line in enumerate(series)
        ],
        "colours": list(colours[: len(labels)]),
        "axes": {"x": x_axis, "y": y_axis},
        "unit": unit,
        "places": 2 if places is None else places,
        "links": bool(links),
    }
    rows = [
        [label, *(_cell(line.values[position], places) for line in series)] for position, label in enumerate(labels)
    ]
    return ChartData(config, [row_header, *(line.label for line in series)], rows, list(links))


def point_data(
    series: Sequence[tuple[str, Sequence[Point]]],
    row_header: str,
    x_axis: str,
    y_axis: str,
    size_axis: str = "",
    unit: str = "",
    places: int | None = None,
) -> ChartData:
    """Marks on two axes, by group. A bubble's third number needs `size_axis`, which names it in tooltip and table."""
    config = {
        "labels": [],
        "series": [
            {
                "label": label,
                "values": [
                    {"x": _text(point.x), "y": _text(point.y), "r": _text(point.size), "label": point.label}
                    for point in points
                ],
                "colour": SERIES_COLOURS[position],
                "kind": "",
            }
            for position, (label, points) in enumerate(series)
        ],
        "colours": [],
        "axes": {"x": x_axis, "y": y_axis, "size": size_axis},
        "unit": unit,
        "places": 2 if places is None else places,
    }
    rows = [
        [
            point.label,
            _cell(point.x, places),
            _cell(point.y, places),
            *([_cell(point.size, places)] if size_axis else []),
        ]
        for _label, points in series
        for point in points
    ]
    return ChartData(config, [row_header, x_axis, y_axis, *([size_axis] if size_axis else [])], rows)
