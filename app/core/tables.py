"""Lists on the server: what an address asks for, checked against allow-lists, as one parameterised query.

Paging, sorting, filtering and grouping happen in the database, so only one page of rows reaches the browser. The state
lives in the address, so a page can be bookmarked, reloaded, shared and reached with the back button.

Nothing from the address reaches SQL as text. A sort name selects a `Column` by its key, a filter value must be one of
that filter's options, a number must be a number, and the search term travels as a bound parameter. A value outside the
list is ignored rather than refused: an old bookmark should still open.
"""

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import ColumnElement, Select, func, or_
from sqlalchemy.orm import Session

from app.core.templating import layout_for, render

PAGE_SIZES = (10, 25, 50, 100)
DEFAULT_SIZE = 25
SEARCH_LENGTH = 80
READ_IN_BLOCKS = 1_000
"""An export reads this many rows at a time, so a long list never sits in memory whole."""
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
"""PostgreSQL refuses a NUL inside text, and none of these belongs in a search."""

Direction = Literal["asc", "desc"]
AnySelect = Select[*tuple[Any, ...]]


@dataclass(frozen=True)
class Column:
    """One column of a list. `sort` is what the database orders by; without it, the column does not sort."""

    key: str
    label: str
    sort: Any = None
    numeric: bool = False
    first: Direction = "asc"
    wide_only: bool = False
    nullable: bool = False

    @property
    def sortable(self) -> bool:
        return self.sort is not None


@dataclass(frozen=True)
class Filter:
    """One choice of a filter bar: a closed list of options, and what each one means in SQL.

    `every` names the option that filters nothing; empty means there is no such option. Without `condition` it changes
    how the list is shown, not which rows it holds, as grouping does.
    """

    key: str
    label: str
    options: Sequence[tuple[str, str]]
    condition: Callable[[str], ColumnElement[bool]] | None = None
    every: str = ""
    default: str = ""


def _whole_number(text: str | None, default: int) -> int:
    try:
        return int(text) if text is not None else default
    except ValueError:  # not a number, or more digits than Python agrees to read
        return default


@dataclass
class ListView:
    """What a list shows: the state its address asked for and, after `load`, one page of rows."""

    name: str
    path: str
    columns: tuple[Column, ...]
    tiebreak: Any
    default_sort: str
    filters: tuple[Filter, ...] = ()
    searched: tuple[Any, ...] = ()
    search_label: str = ""
    term: str = ""
    chosen: dict[str, str] = field(default_factory=dict)
    sort: str = ""
    direction: Direction = "asc"
    page: int = 1
    size: int = DEFAULT_SIZE
    rows: list[Any] = field(default_factory=list)
    total: int = 0
    sizes: tuple[int, ...] = PAGE_SIZES
    wide: bool = False
    dense: bool = False
    offered: tuple[str, ...] = ()
    """How the person likes their lists, and which of those choices they may change from the list's own toolbar."""

    @classmethod
    def read(
        cls,
        name: str,
        path: str,
        params: Mapping[str, str],
        columns: Sequence[Column],
        tiebreak: Any,
        default_sort: str,
        filters: Sequence[Filter] = (),
        searched: Sequence[Any] = (),
        search_label: str = "",
    ) -> "ListView":
        """Every value is checked here, and only here: what passes is one of the listed options or a whole number."""
        view = cls(name, path, tuple(columns), tiebreak, default_sort, tuple(filters), tuple(searched), search_label)
        view.term = _CONTROL_CHARACTERS.sub("", params.get("q", "")).strip()[:SEARCH_LENGTH]
        for choice in filters:
            allowed = {value for value, _label in choice.options} | ({""} if choice.every else set())
            value = params.get(choice.key)
            view.chosen[choice.key] = value if value in allowed else choice.default
        wanted = params.get("sort", default_sort)
        view.sort = wanted if wanted in view._sortable else default_sort
        direction = params.get("dir")
        view.direction = direction if direction in ("asc", "desc") else view._sorted_by.first  # type: ignore[assignment]
        size = _whole_number(params.get("size"), DEFAULT_SIZE)
        view.size = size if size in PAGE_SIZES else DEFAULT_SIZE
        view.page = max(_whole_number(params.get("page"), 1), 1)
        return view

    @property
    def _sortable(self) -> dict[str, Column]:
        return {column.key: column for column in self.columns if column.sortable}

    @property
    def _sorted_by(self) -> Column:
        return self._sortable[self.sort]

    @property
    def sorted_label(self) -> str:
        return self._sorted_by.label

    @property
    def conditions(self) -> list[ColumnElement[bool]]:
        found = [
            choice.condition(self.chosen[choice.key])
            for choice in self.filters
            if choice.condition and self.chosen[choice.key]
        ]
        if self.term and self.searched:
            # autoescape: a % or a _ typed by a person means that character, not a wildcard.
            found.append(or_(*(column.icontains(self.term, autoescape=True) for column in self.searched)))
        return found

    def order(self, *first: Any) -> list[Any]:
        """`first` comes before the chosen column, as a group does. The tiebreak keeps a page's rows in a fixed order:
        without it, rows with the same value can move between pages."""
        column = self._sorted_by
        descending = self.direction == "desc"
        main = column.sort.desc() if descending else column.sort.asc()
        if column.nullable:  # PostgreSQL and SQLite put NULL at opposite ends
            main = main.nulls_last()
        return [*first, main, self.tiebreak.desc() if descending else self.tiebreak.asc()]

    def load(self, session: Session, statement: AnySelect, *first: Any, options: Sequence[Any] = ()) -> None:
        """Counts what the filters leave, then reads one page. A page past the end shows the last one."""
        filtered = statement.where(*self.conditions)
        counted = filtered.with_only_columns(func.count(), maintain_column_froms=True).order_by(None)
        self.total = session.scalar(counted) or 0
        self.page = min(self.page, max(self.pages, 1))
        ordered = filtered.options(*options).order_by(*self.order(*first))
        self.rows = list(session.scalars(ordered.limit(self.size).offset((self.page - 1) * self.size)))

    def everything(
        self, session: Session, statement: AnySelect, *first: Any, options: Sequence[Any] = ()
    ) -> Iterator[Any]:
        """Every row the filters leave, in the same order as the screen, read in blocks: what an export needs."""
        ordered = statement.where(*self.conditions).options(*options).order_by(*self.order(*first))
        yield from session.execute(ordered.execution_options(yield_per=READ_IN_BLOCKS))

    @property
    def pages(self) -> int:
        return (self.total + self.size - 1) // self.size

    @property
    def first_row(self) -> int:
        return (self.page - 1) * self.size + 1 if self.total else 0

    @property
    def last_row(self) -> int:
        return min(self.page * self.size, self.total)

    def page_numbers(self) -> list[int | None]:
        """The pages to offer: the first, the last and those around this one. None marks a gap of two or more."""
        wanted = sorted({1, self.pages, *range(max(self.page - 1, 1), min(self.page + 1, self.pages) + 1)})
        numbers: list[int | None] = []
        previous = 0
        for number in wanted:
            if number - previous == 2:
                numbers.append(number - 1)
            elif number - previous > 2:
                numbers.append(None)
            numbers.append(number)
            previous = number
        return numbers

    def _state(self) -> dict[str, str]:
        return {
            "q": self.term,
            **self.chosen,
            "sort": self.sort,
            "dir": self.direction,
            "size": str(self.size),
            "page": str(self.page),
        }

    def _defaults(self, state: Mapping[str, str]) -> dict[str, str]:
        return {
            "q": "",
            **{choice.key: choice.default for choice in self.filters},
            "sort": self.default_sort,
            "dir": self._sortable[state["sort"]].first,
            "size": str(DEFAULT_SIZE),
            "page": "1",
        }

    def _address(self, path: str, state: Mapping[str, str]) -> str:
        defaults = self._defaults(state)
        query = urlencode({key: value for key, value in state.items() if value != defaults[key]})
        return f"{path}?{query}" if query else path

    @property
    def here(self) -> str:
        """This page's address, in one form however it was reached."""
        return self._address(self.path, self._state())

    def link(self, **changes: str | int) -> str:
        """Another state of this list. Anything but a change of page goes back to the first page."""
        state = self._state() | {"page": "1"} | {key: str(value) for key, value in changes.items()}
        return self._address(self.path, state)

    def sort_link(self, column: Column) -> str:
        direction = column.first
        if column.key == self.sort:
            direction = "desc" if self.direction == "asc" else "asc"
        return self.link(sort=column.key, dir=direction)

    def sort_state(self, column: Column) -> str:
        """The value of `aria-sort`: only the sorted column carries one."""
        if column.key != self.sort:
            return ""
        return "ascending" if self.direction == "asc" else "descending"

    def elsewhere(self, path: str) -> str:
        """The same list at another address, such as its export: every filter and the order, without the page."""
        return self._address(path, self._state() | {"page": "1"})

    @property
    def active(self) -> list[tuple[str, str, str]]:
        """What narrows the list now, each with the address that removes it: (name, value, link)."""
        found = []
        if self.term:
            found.append((self.search_label, self.term, self.link(q="")))
        for choice in self.filters:
            value = self.chosen[choice.key]
            if choice.condition and value != choice.default:
                labels = dict(choice.options) | {"": choice.every}
                found.append((choice.label, labels[value], self.link(**{choice.key: choice.default})))
        return found

    @property
    def clear_link(self) -> str:
        return self.link(q="", **{choice.key: choice.default for choice in self.filters if choice.condition})

    @property
    def hidden_fields(self) -> list[tuple[str, str]]:
        """What the filter form must carry so that a plain submit keeps the order."""
        state = self._state()
        defaults = self._defaults(state)
        return [(key, state[key]) for key in ("sort", "dir") if state[key] != defaults[key]]

    @property
    def form_id(self) -> str:
        return f"{self.name}-filters"


def list_query(address: str, path: str) -> dict[str, str]:
    """The state in an address a person came from, for the list at `path`, to pass to `ListView.read`.

    It is input like any other, so nothing but the query is kept, and what cannot be read counts as nothing: a bad value
    is ignored, never an error. Blank values stay, because they mean something: `status=` is every state, and with the
    value dropped the list would quietly go back to its default.
    """
    try:
        parts = urlsplit(address)
        return dict(parse_qsl(parts.query, keep_blank_values=True)) if parts.path == path else {}
    except ValueError:
        return {}


def fragment_requested(request: Request) -> bool:
    """htmx asks for the part that changes. Going back through history asks for the whole page."""
    headers = request.headers
    return headers.get("hx-request") == "true" and headers.get("hx-history-restore-request") != "true"


def whole_page(request: Request, address: str) -> Response:
    """Sends a person to a whole page, however they asked. htmx follows a plain redirect by itself and would put that
    page inside a fragment, so it is told in a header, and it navigates."""
    if fragment_requested(request):
        return Response(headers={"HX-Redirect": address})
    return RedirectResponse(address, status_code=303)


LIST_CHOICES = ("list_width", "list_density")


def arrange(request: Request, view: ListView) -> ListView:
    """Applies the person's way of seeing lists, kept with their other layout choices. `render_list` calls it; a route
    that draws a list another way, as a save that sends the list back, calls it too."""
    layout = layout_for(request)
    view.wide = layout["list_width"] == "wide"
    view.dense = layout["list_density"] == "dense"
    view.offered = tuple(name for name in LIST_CHOICES if name in request.app.state.settings.layout_choices)
    return view


def render_list(request: Request, view: ListView, page: str, results: str, **context: Any) -> HTMLResponse:
    """The whole page, or only its results for htmx, whichever was asked for at the same address.

    `Vary` keeps the browser from showing a stored fragment as if it were the page. The filter form is sent again
    unless it made the request: a link that sorts or clears a filter has to bring the form's controls in step, and a
    form that is being typed in must not be replaced.
    """
    context["view"] = arrange(request, view)
    if not fragment_requested(request):
        response = render(request, page, refill_filters=False, **context)
    else:
        refill = request.headers.get("hx-trigger") != view.form_id
        response = render(request, results, refill_filters=refill, **context)
        response.headers["HX-Push-Url"] = view.here
    response.headers["Vary"] = "HX-Request"
    return response
