"""Boards: cards in columns, moved on the server. See docs/base/specification.md#boards

A board is drawn on the server, and each card carries a form that moves it: a plain POST that works without JavaScript.
Dragging, where the browser can, sends that same form with the card's new neighbour. The server decides: it reads what
was sent against its lists, checks the person may move it and that nobody moved it first, and gives the card its place.

A card's place in its column is a whole number, `rank`. Cards are read in rank order, with the primary key after it. A
card that lands between two others takes the number half way between theirs; when there is no number left between
them, the column is numbered again with gaps, which touches the rank alone and so moves no version.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import Select, Table, and_, bindparam, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.forms import Refused
from app.core.i18n import _

RANK_STEP = 1024
"""The gap between two cards numbered afresh: about ten cards can land between two neighbours before a renumbering."""
RANK_LIMIT = 2**62
"""Ranks are big integers. One that would pass this asks for the column to be numbered again, so no move can reach
the end of the type, however many times a card goes to the top."""


@dataclass(frozen=True)
class BoardCard:
    """One card: its row's number and version, the words that name it to a screen reader, and the row itself for the
    caller to draw. With `href`, the macro draws it: `title` as a link to the row's page, a few short `lines`, and
    `actions`, each (label, address, the words that say which card), as small buttons a finger can hit."""

    id: int
    version: int
    label: str
    item: Any = None
    title: str = ""
    href: str = ""
    lines: Sequence[str] = ()
    actions: Sequence[tuple[str, str, str]] = ()


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
    """The rank for a card between two neighbours, either of which may be missing. None: there is no room left, or the
    rank would pass its bound."""
    if previous is None and following is None:
        rank = RANK_STEP
    elif previous is None:
        assert following is not None  # noqa: S101  # both missing is answered above
        rank = following - RANK_STEP
    elif following is None:
        rank = previous + RANK_STEP
    elif following - previous < 2:
        return None
    else:
        rank = (previous + following) // 2
    return rank if -RANK_LIMIT < rank < RANK_LIMIT else None


def renumbered(ids: Sequence[int]) -> list[dict[str, int]]:
    """Ranks with their gaps back, in the order given, for one `update()` with these rows."""
    return [{"id": identifier, "rank": (position + 1) * RANK_STEP} for position, identifier in enumerate(ids)]


def column_lock(model: Any, column: str, keys: Collection[str]) -> Select[Any]:
    """What holds the rows of the columns a move reads and writes, for the route to run first, where the database can:
    PostgreSQL locks them until the commit, in one order, so two moves cannot deadlock, and a move that waited reads the
    ranks another move left. SQLite has one writer at a time and takes no row locks: SQLAlchemy leaves FOR UPDATE out
    there."""
    return select(model.id).where(getattr(model, column).in_(sorted(set(keys)))).order_by(model.id).with_for_update()


def place_card(session: Session, model: Any, card: Any, move: Move, column: str, rank: str = "rank") -> None:
    """Puts `card` in the column `move.to`, after `move.after` or first, with the ranks of the whole column and not
    only of what a page showed: half way between its neighbours, or with the column numbered again when there is no
    room, through the table, so that no other card's version moves. Refused when the card to follow is not in that
    column. The caller has locked the columns, compared the version, and saves, in `saved`."""
    group, order = getattr(model, column), getattr(model, rank)
    others = and_(group == move.to, model.id != card.id)
    if move.after is None:
        previous, following = None, session.scalar(select(func.min(order)).where(others))
    else:
        after = session.get(model, move.after, populate_existing=True)
        if after is None or getattr(after, column) != move.to or after.id == card.id:
            raise Refused(_("That place on the board has changed. Here it is as it is now: try again."))
        later = or_(order > getattr(after, rank), and_(order == getattr(after, rank), model.id > after.id))
        previous = getattr(after, rank)
        following = session.scalar(select(func.min(order)).where(others, later))  # one it shares: no room
    setattr(card, column, move.to)
    place = rank_between(previous, following)
    if place is None:
        ids = list(session.scalars(select(model.id).where(others).order_by(order, model.id)))
        at = ids.index(move.after) + 1 if move.after in ids else 0
        rows = renumbered([*ids[:at], card.id, *ids[at:]])
        table = cast(Table, model.__table__)
        statement = update(table).where(table.c.id == bindparam("row_id")).values({rank: bindparam("row_rank")})
        session.execute(
            statement, [{"row_id": row["id"], "row_rank": row["rank"]} for row in rows if row["id"] != card.id]
        )
        place = rows[at]["rank"]
    setattr(card, rank, place)
