"""The board: work orders by state, moved on the server. See docs/base/specification.md#boards

A card moves by its own form, by keyboard and without JavaScript, or by dragging, which sends that same form. The
server checks the person may move it, that the column and the card it follows are what the page said, and that nobody
moved it first, with the version column. Then it gives the card its place in the column.
"""

from collections.abc import Mapping
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, contains_eager

from app.core import boards
from app.core.boards import Board, BoardCard, BoardColumn, place_card, read_move
from app.core.database import DatabaseSession, saved
from app.core.forms import Refused
from app.core.i18n import _
from app.core.identity import Person, require_role
from app.core.tables import fragment_requested, whole_page
from app.core.templating import render
from app.demo.data import GENERATE, READY, rows_state
from app.demo.equipment import LARGEST_ID, ORDER_LABELS, can_edit, labels_in_order, record_number
from app.demo.models import LOCATIONS, WORK_ORDER_STATUSES, Equipment, WorkOrder
from app.demo.planning import set_status

CARDS_SHOWN = 8
"""A column shows this many cards; the rest are a link away, in Planning."""
PATH = "/board"


def _location(params: Mapping[str, str]) -> str:
    value = params.get("location", "")
    return value if value in LOCATIONS else ""


def _address(location: str, **more: str) -> str:
    query = urlencode({key: value for key, value in ({"location": location} | more).items() if value})
    return f"{PATH}?{query}" if query else PATH


def _card(order: WorkOrder) -> BoardCard:
    label = _("Work order %(number)s: %(work)s") % {"number": order.id, "work": order.title}
    return BoardCard(order.id, order.version, label, order)


def load_board(request: Request, session: Session, location: str, focus: int | None = None) -> Board:
    """Each state's first cards in their order, and how many there are in all."""
    where = [Equipment.location == location] if location else []
    counted = dict(
        session.execute(
            select(WorkOrder.status, func.count()).join(WorkOrder.equipment).where(*where).group_by(WorkOrder.status)
        ).all()
    )
    columns = []
    for status in WORK_ORDER_STATUSES:
        orders = session.scalars(
            select(WorkOrder)
            .join(WorkOrder.equipment)
            .options(contains_eager(WorkOrder.equipment))
            .where(WorkOrder.status == status, *where)
            .order_by(WorkOrder.rank, WorkOrder.id)
            .limit(CARDS_SHOWN)
        ).all()
        more = "/planning?" + urlencode({"status": status, **({"location": location} if location else {})})
        cards = [_card(order) for order in orders]
        columns.append(BoardColumn(status, _(ORDER_LABELS[status][0]), cards, counted.get(status, 0), more))
    return Board(
        "board",
        _("Work orders by state"),
        columns,
        "/board/move",
        can_move=can_edit(request),
        focus=focus,
        hidden={"location": location} if location else {},
    )


def _page(request: Request, session: Session, location: str, status: int = 200, **context: Any) -> Response:
    board = load_board(request, session, location, context.pop("focus", None))
    template = "demo/board/board.html" if fragment_requested(request) else "demo/board/page.html"
    options = [(value, _(value)) for value in labels_in_order(LOCATIONS)]
    defaults = {"moved": "", "conflict": [], "refused": "", "announce": False, "state": READY}
    response = render(
        request, template, status_code=status, board=board, location=location, locations=options, **defaults | context
    )
    response.headers["Vary"] = "HX-Request"
    return response


def board_page(request: Request, session: DatabaseSession) -> Response:
    state = rows_state(session)
    if state != READY:
        if fragment_requested(request):
            return whole_page(request, PATH)
        return render(request, "demo/board/page.html", state=state, command=GENERATE)
    location = _location(request.query_params)
    number = record_number(request.query_params.get("moved", ""))
    moved = ""
    if number is not None and (order := session.get(WorkOrder, number)) is not None:
        moved = _moved_message(order)
    response = _page(request, session, location, moved=moved)
    if fragment_requested(request):
        response.headers["HX-Push-Url"] = _address(location)
    return response


def _moved_message(order: WorkOrder) -> str:
    return _("Work order %(number)s is now in %(state)s.") % {
        "number": order.id,
        "state": _(ORDER_LABELS[order.status][0]),
    }


def column_lock(statuses: tuple[str, ...]) -> Select[Any]:
    """The columns a move reads and writes, held until it commits: see app/core/boards.py."""
    return boards.column_lock(WorkOrder, "status", statuses)


def _conflict(order: WorkOrder) -> list[tuple[str, str]]:
    return [(_("State"), _(ORDER_LABELS[order.status][0]))]


def move_card(
    request: Request,
    session: DatabaseSession,
    _person: Annotated[Person, Depends(require_role("admin"))],
    card: Annotated[str, Form()] = "",
    to: Annotated[str, Form()] = "",
    after: Annotated[str, Form()] = "",
    version: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
) -> Response:
    """Moves one card. Cross-site posts never reach this: `_context` refuses them, as SEC-07 says."""
    if rows_state(session) != READY:
        return whole_page(request, PATH)
    place = location if location in LOCATIONS else ""
    try:
        move = read_move(card, to, after, version, WORK_ORDER_STATUSES)
    except Refused:
        raise HTTPException(status_code=400) from None
    order = session.get(WorkOrder, move.card) if move.card <= LARGEST_ID else None
    if order is None:
        raise HTTPException(status_code=404)
    partial = fragment_requested(request)
    session.execute(column_lock((order.status, move.to)))
    session.refresh(order)  # what another move, which this one waited for, left
    if move.version != order.version:
        return _page(request, session, place, 200 if partial else 409, conflict=_conflict(order), focus=order.id)
    status = order.status

    def change() -> None:
        place_card(session, WorkOrder, order, move, "status")
        order.status = status  # set_status records when it closed, from the state it leaves
        set_status(order, move.to)

    try:
        moved = saved(session, change)
    except Refused as problem:
        session.rollback()
        return _page(request, session, place, 200 if partial else 409, refused=str(problem), focus=order.id)
    if not moved:
        now = session.get(WorkOrder, move.card)
        if now is None:
            raise HTTPException(status_code=404)
        return _page(request, session, place, 200 if partial else 409, conflict=_conflict(now), focus=now.id)
    if not partial:
        return RedirectResponse(_address(place, moved=str(order.id)), status_code=303)
    return _page(request, session, place, moved=_moved_message(order), focus=order.id, announce=True)


def install(application: FastAPI) -> None:
    application.add_api_route(PATH, board_page, include_in_schema=False)
    application.add_api_route("/board/move", move_card, methods=["POST"], include_in_schema=False)
