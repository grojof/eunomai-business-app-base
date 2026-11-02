"""Boards: cards in columns, moved on the server. See docs/specification.md#boards

A board is drawn on the server, and each card carries a form that moves it: a plain POST that works without JavaScript.
Dragging, where the browser can, sends that same form with the card's new neighbour. The server decides: it reads what
was sent against its lists, checks the person may move it and that nobody moved it first, and gives the card its place.

A card's place in its column is a whole number, `rank`. Cards are read in rank order, with the primary key after it. A
card that lands between two others takes the number half way between theirs; when there is no number left between
them, the column is numbered again with gaps, which touches the rank alone and so moves no version.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.forms import Refused

RANK_STEP = 1024
"""The gap between two cards numbered afresh: about ten cards can land between two neighbours before a renumbering."""


@dataclass(frozen=True)
class BoardCard:
    """One card: its row's number and version, the words that name it to a screen reader, and the row itself for the
    caller to draw."""

    id: int
    version: int
    label: str
    item: Any = None


@dataclass(frozen=True)
class BoardColumn:
    """One column as a page shows it. `total` counts the cards not shown, too, and `more` is where they all are."""

    key: str
    title: str
    cards: Sequence[BoardCard]
    total: int
    more: str = ""


@dataclass(frozen=True)
class Move:
    """What a person asked: this card, to this column, after that card or first."""

    card: int
    to: str
    after: int | None
    version: int | None


@dataclass
class Board:
    """What the `board` macro needs. `action` is where a card's form goes; without `can_move` there are no forms."""

    identifier: str
    label: str
    columns: list[BoardColumn]
    action: str
    can_move: bool = False
    back: str = ""
    focus: int | None = None
    hidden: dict[str, str] = field(default_factory=dict)


def _number(text: str, missing: str) -> int:
    if not (text.isascii() and text.isdigit() and len(text) < 10):
        raise Refused(missing)
    return int(text)


def read_move(card: str, to: str, after: str, version: str, columns: Collection[str]) -> Move:
    """Each value against what it may be: a number, a column of the board, a number or nothing. Refused otherwise."""
    if to not in columns:
        raise Refused("column")
    return Move(
        _number(card, "card"),
        to,
        _number(after, "after") if after else None,
        _number(version, "version") if version else None,
    )


def rank_between(previous: int | None, following: int | None) -> int | None:
    """The rank for a card between two neighbours, either of which may be missing. None: there is no room left."""
    if previous is None and following is None:
        return RANK_STEP
    if previous is None:
        assert following is not None  # noqa: S101  # both missing is answered above
        return following - RANK_STEP
    if following is None:
        return previous + RANK_STEP
    if following - previous < 2:
        return None
    return (previous + following) // 2


def renumbered(ids: Sequence[int]) -> list[dict[str, int]]:
    """Ranks with their gaps back, in the order given, for one `update()` with these rows."""
    return [{"id": identifier, "rank": (position + 1) * RANK_STEP} for position, identifier in enumerate(ids)]
