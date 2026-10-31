"""Planning: work orders grouped on the server, and one row edited at a time in a dialog.

It is what a spreadsheet-like grid would be asked for, without one: a native table a screen reader already knows, and a
form it already knows, with nothing to learn in between. See docs/decisions.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import ColumnElement, String, func, literal_column, select
from sqlalchemy.orm import Session, contains_eager

from app.core.database import DatabaseSession, totals_by
from app.core.formatters import format_decimal, format_month_and_year, parse_decimal
from app.core.i18n import N_, _, ngettext
from app.core.identity import Person, require_role
from app.core.tables import Column, Filter, ListView, fragment_requested, list_query, render_list
from app.core.templating import render
from app.demo.data import GENERATE, READY, rows_state
from app.demo.equipment import LARGEST_ID, ORDER_LABELS, labels_in_order, ranked
from app.demo.models import LOCATIONS, WORK_ORDER_STATUSES, Equipment, WorkOrder, overdue

OPEN = "open"
FIELD_IDS = {"status": "field-status", "planned_on": "field-planned", "hours": "field-hours"}
LONGEST_JOB = Decimal(9999)
HOUR_DECIMALS = 2
GROUPS = {"location": N_("Location"), "status": N_("State"), "month": N_("Month planned")}
_STATEMENT = select(WorkOrder).join(WorkOrder.equipment)
_LOADED = (contains_eager(WorkOrder.equipment),)


def _state_condition(value: str) -> ColumnElement[bool]:
    return WorkOrder.status != "closed" if value == OPEN else WorkOrder.status == value


def month_of(dialect: str) -> ColumnElement[str]:
    """The year and month of a planned date. A date is text on SQLite, and a date on PostgreSQL.

    The format is written into the SQL, not bound: PostgreSQL would take two parameters in SELECT and GROUP BY for two
    different expressions, and refuse the query.
    """
    if dialect == "sqlite":
        return func.substr(WorkOrder.planned_on, literal_column("1"), literal_column("7"), type_=String)
    return func.to_char(WorkOrder.planned_on, literal_column("'YYYY-MM'"), type_=String)


def planning_view(params: Mapping[str, str]) -> ListView:
    locations = labels_in_order(LOCATIONS)
    return ListView.read(
        "planning",
        "/planning",
        params,
        (
            Column("equipment", _("Equipment"), Equipment.name),
            Column("number", _("Number"), WorkOrder.id, numeric=True, wide_only=True),
            Column("title", _("Work"), WorkOrder.title, wide_only=True),
            Column("status", _("State"), ranked(WorkOrder.status, WORK_ORDER_STATUSES)),
            Column("planned", _("Planned for"), WorkOrder.planned_on, nullable=True, wide_only=True),
            Column("hours", _("Hours"), WorkOrder.hours, numeric=True, first="desc", wide_only=True),
        ),
        WorkOrder.id,
        "planned",
        (
            Filter(
                "status",
                _("State"),
                [(OPEN, _("Not closed")), *((value, _(ORDER_LABELS[value][0])) for value in WORK_ORDER_STATUSES)],
                _state_condition,
                every=_("All states"),
                default=OPEN,
            ),
            Filter(
                "location",
                _("Location"),
                [(value, _(value)) for value in locations],
                lambda value: Equipment.location == value,
                every=_("All locations"),
            ),
            Filter(
                "due",
                _("Planned for"),
                [("overdue", _("Overdue"))],
                lambda _value: overdue(),
                every=_("Any date"),
            ),
            Filter("group", _("Group by"), [(key, _(label)) for key, label in GROUPS.items()], default="location"),
        ),
        (Equipment.code, Equipment.name, WorkOrder.title),
        _("Equipment or work"),
    )


@dataclass(frozen=True)
class Section:
    """One group as a page shows it. Its totals are the whole group's, not just of the rows on this page."""

    title: str
    note: str
    rows: list[WorkOrder]


def _group_label(grouping: str, key: str | None) -> str:
    if grouping == "status":
        return _(ORDER_LABELS[str(key)][0])
    if grouping == "location":
        return _(str(key))
    if key is None:
        return _("Not planned yet")
    return format_month_and_year(date.fromisoformat(f"{key}-01"))


def _grouping(view: ListView, session: Session) -> tuple[Any, Any, list[str | None]]:
    """What the database groups by, what it orders by, and the groups in that order."""
    grouping = view.chosen["group"]
    if grouping == "status":
        return WorkOrder.status, ranked(WorkOrder.status, WORK_ORDER_STATUSES), list(WORK_ORDER_STATUSES)
    if grouping == "location":
        locations = labels_in_order(LOCATIONS)
        return Equipment.location, ranked(Equipment.location, locations), list(locations)
    month = month_of(session.get_bind().dialect.name)
    return month, month.asc().nulls_last(), []


def _key_of(order: WorkOrder, grouping: str) -> str | None:
    if grouping == "status":
        return order.status
    if grouping == "location":
        return order.equipment.location
    return order.planned_on.isoformat()[:7] if order.planned_on else None


def load_sections(view: ListView, session: Session) -> list[Section]:
    """Reads one page in the order of its groups, and each group's totals in the database or, where it cannot add exact
    numbers, in `totals_by`. A group cut by a page says so."""
    grouping = view.chosen["group"]
    key, order, known = _grouping(view, session)
    view.load(session, _STATEMENT, order, options=_LOADED)
    totals = totals_by(session, _STATEMENT.where(*view.conditions), key, WorkOrder.hours)
    ordered = known or sorted(totals, key=lambda value: (value is None, value or ""))
    starts: dict[str | None, int] = {}
    position = 0
    for group in ordered:
        starts[group] = position
        position += totals.get(group, (0, Decimal(0)))[0]
    sections: list[Section] = []
    current: list[WorkOrder] = []
    for number, row in enumerate(view.rows):
        group = _key_of(row, grouping)
        following = view.rows[number + 1] if number + 1 < len(view.rows) else None
        current.append(row)
        if following is None or _key_of(following, grouping) != group:
            count, hours = totals[group]
            title = _group_label(grouping, group)
            first_on_page = (view.page - 1) * view.size + number + 1 - len(current)
            sections.append(
                Section(
                    title if first_on_page == starts[group] else _("%(group)s, continued") % {"group": title},
                    ngettext("%(count)s order, %(hours)s hours", "%(count)s orders, %(hours)s hours", count)
                    % {"count": format_decimal(count), "hours": format_decimal(hours, HOUR_DECIMALS)},
                    current,
                )
            )
            current = []
    return sections


def _list_context(request: Request, person: Person | None) -> dict[str, Any]:
    return {
        "order_statuses": ORDER_LABELS,
        "can_edit": bool(person and "admin" in person.roles),
        "saved": "",
        "state": READY,
        "command": GENERATE,
    }


def planning(request: Request, session: DatabaseSession) -> Response:
    state = rows_state(session)
    if state != READY:
        return render(request, "demo/planning/list.html", state=state, command=GENERATE)
    view = planning_view(request.query_params)
    sections = load_sections(view, session)
    context = _list_context(request, request.state.person)
    return render_list(
        request, view, "demo/planning/list.html", "demo/planning/results.html", sections=sections, **context
    )


def _view_of(back: str) -> ListView:
    """The list a person came from."""
    return planning_view(list_query(back, "/planning"))


def _order_or_404(session: Session, order_id: int) -> WorkOrder:
    order = session.get(WorkOrder, order_id) if order_id <= LARGEST_ID else None
    if order is None:
        raise HTTPException(status_code=404)
    return order


def _state_options() -> list[tuple[str, str]]:
    return [(value, _(ORDER_LABELS[value][0])) for value in WORK_ORDER_STATUSES]


def _hours_text(hours: Decimal) -> str:
    return format_decimal(hours, HOUR_DECIMALS)


def _form(
    request: Request,
    template: str,
    order: WorkOrder,
    back: str,
    values: dict[str, str],
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    return render(
        request,
        template,
        status_code=status,
        order=order,
        back=back,
        values=values,
        errors=errors,
        summary=[(FIELD_IDS[name], error) for name, error in errors.items()],
        options=_state_options(),
    )


def planning_edit(
    request: Request,
    order_id: int,
    session: DatabaseSession,
    _person: Annotated[Person, Depends(require_role("admin"))],
) -> Response:
    """The editor of one row: in the dialog for htmx, as its own page without JavaScript."""
    if rows_state(session) != READY:
        return RedirectResponse("/planning", status_code=303)
    order = _order_or_404(session, order_id)
    back = _view_of(request.query_params.get("back", "")).here
    values = {
        "status": order.status,
        "planned_on": order.planned_on.isoformat() if order.planned_on else "",
        "hours": _hours_text(order.hours),
    }
    template = "demo/planning/editor.html" if fragment_requested(request) else "demo/planning/edit.html"
    return _form(request, template, order, back, values, {})


def checked(status: str, planned_on: str, hours: str) -> tuple[dict[str, Any], dict[str, str]]:
    """What can be saved, and what cannot, by field, in words that say how to fix it. Each value is checked here."""
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    if status in WORK_ORDER_STATUSES:
        clean["status"] = status
    else:
        errors["status"] = _("Choose a state from the list.")
    try:
        clean["planned_on"] = date.fromisoformat(planned_on) if planned_on else None
    except ValueError:
        errors["planned_on"] = _("Enter a date, or leave it empty if it is not planned yet.")
    try:
        number = parse_decimal(hours)
    except ValueError:
        errors["hours"] = _("Enter the hours as a number, such as %(example)s.") % {
            "example": _hours_text(Decimal("7.5"))
        }
    else:
        if not 0 <= number <= LONGEST_JOB:
            errors["hours"] = _("Enter between 0 and %(most)s hours.") % {"most": format_decimal(LONGEST_JOB)}
        elif -number.as_tuple().exponent > HOUR_DECIMALS:  # type: ignore[operator]
            errors["hours"] = _("Enter the hours with two decimals at most.")
        else:
            clean["hours"] = number
    return clean, errors


def planning_save(
    request: Request,
    order_id: int,
    session: DatabaseSession,
    _person: Annotated[Person, Depends(require_role("admin"))],
    status: Annotated[str, Form()] = "",
    planned_on: Annotated[str, Form()] = "",
    hours: Annotated[str, Form()] = "",
    back: Annotated[str, Form()] = "",
) -> Response:
    """Saves one row. Cross-site posts never reach this: `_context` refuses them, as SEC-07 says."""
    if rows_state(session) != READY:
        return RedirectResponse("/planning", status_code=303)
    order = _order_or_404(session, order_id)
    view = _view_of(back)
    partial = fragment_requested(request)
    clean, errors = checked(status, planned_on, hours)
    if errors:
        values = {"status": status, "planned_on": planned_on, "hours": hours}  # as typed: USE-03
        template = "demo/planning/editor.html" if partial else "demo/planning/edit.html"
        return _form(request, template, order, view.here, values, errors, 200 if partial else 422)

    if clean["status"] != order.status:
        order.closed_at = datetime.now(UTC) if clean["status"] == "closed" else None
    order.status = clean["status"]
    order.planned_on = clean["planned_on"]
    order.hours = clean["hours"]
    session.commit()

    if not partial:
        return RedirectResponse(view.here, status_code=303)
    sections = load_sections(view, session)
    context = _list_context(request, request.state.person)
    context["saved"] = _("Work order %(number)s saved.") % {"number": order_id}
    return render(
        request,
        "demo/planning/saved.html",
        view=view,
        sections=sections,
        order=order,
        refill_filters=False,
        **context,
    )


def install(application: FastAPI) -> None:
    application.add_api_route("/planning", planning, include_in_schema=False)
    application.add_api_route("/planning/{order_id:int}/edit", planning_edit, include_in_schema=False)
    application.add_api_route("/planning/{order_id:int}", planning_save, methods=["POST"], include_in_schema=False)
