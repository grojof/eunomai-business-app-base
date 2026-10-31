"""The work order form: every kind of field on one screen, reached from Planning and from the equipment detail.

The equipment is asked for by its code. There are 50,000: a searchable select must hold its options in the page, because
without JavaScript it is a plain select, so that field is the list of faults. See docs/decisions.md.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import DatabaseSession
from app.core.formatters import format_decimal
from app.core.forms import Refused, read_choice, read_date, read_decimal, read_fields, read_flag, read_text, read_whole
from app.core.i18n import N_, _
from app.core.identity import Person, require_role
from app.core.tables import fragment_requested, list_query, whole_page
from app.core.templating import render
from app.demo.data import READY, rows_state
from app.demo.equipment import LARGEST_ID, equipment_view
from app.demo.models import LAST_MOMENT, PRIORITIES, WORK_ORDER_STATUSES, Equipment, WorkOrder
from app.demo.planning import (
    EARLIEST,
    HOUR_DECIMALS,
    LATEST,
    _order_or_404,
    _state_options,
    planning_view,
    read_hours,
    set_status,
)

Admin = Annotated[Person, Depends(require_role("admin"))]
FIELD_IDS = {
    "title": "field-title",
    "equipment": "field-equipment",
    "description": "field-description",
    "fault": "field-fault",
    "status": "field-status",
    "priority": "field-priority",
    "planned_on": "field-planned-on",
    "hours": "field-hours",
    "crew": "field-crew",
    "cost": "field-cost",
    "stop_needed": "field-stop-needed",
}
"""In the order of the page, which is the order of the error summary."""
LONGEST_TITLE = 80
LONGEST_DESCRIPTION = 2000
LONGEST_CODE = 16
LARGEST_CREW = 50
LARGEST_COST = Decimal("999999999.99")
COST_DECIMALS = 20
"""The column's own: generated costs have twenty, and a form that showed fewer would round them on each save."""
PRIORITY_LABELS = {"low": N_("Low"), "normal": N_("Normal"), "high": N_("High")}
FAULTS = {
    "bearing_wear": N_("Bearing wear"),
    "belt_slip": N_("Belt slipping"),
    "blown_fuse": N_("Blown fuse"),
    "blocked_filter": N_("Blocked filter"),
    "corrosion": N_("Corrosion"),
    "cracked_housing": N_("Cracked housing"),
    "dirty_oil": N_("Dirty oil"),
    "dirty_sensor": N_("Dirty sensor"),
    "fluid_leak": N_("Fluid leak"),
    "loose_connection": N_("Loose connection"),
    "low_pressure": N_("Low pressure"),
    "misalignment": N_("Misalignment"),
    "motor_overload": N_("Motor overload"),
    "noise": N_("Noise or vibration"),
    "overheating": N_("Overheating"),
    "power_loss": N_("Power loss"),
    "seal_failure": N_("Seal failure"),
    "software_fault": N_("Software fault"),
    "stuck_valve": N_("Stuck valve"),
    "tripped_breaker": N_("Tripped breaker"),
    "worn_gasket": N_("Worn gasket"),
}
_EQUIPMENT_PAGE = re.compile(r"/equipment/([0-9]{1,10})")


def way_back(address: str) -> str:
    """Where a person came from: Planning or an equipment page, with their state, and nowhere else. It is input like any
    other, so it is rebuilt from what can be read in it."""
    try:
        parts = urlsplit(address)
    except ValueError:
        parts = None
    found = _EQUIPMENT_PAGE.fullmatch(parts.path) if parts else None
    if found and int(found[1]) <= LARGEST_ID:
        inner = dict(parse_qsl(parts.query if parts else "")).get("back", "")
        back = equipment_view(list_query(inner, "/equipment")).here
        keep = {"tab": "orders"} | ({} if back == "/equipment" else {"back": back})
        return f"/equipment/{found[1]}?{urlencode(keep)}"
    return planning_view(list_query(address, "/planning")).here


def _ending(address: str, outcome: str, number: int) -> str:
    return f"{address}{'&' if '?' in address else '?'}{outcome}={number}"


@dataclass(frozen=True)
class Sent:
    """What a form sent, as text."""

    title: str
    equipment: str
    description: str
    fault: str
    status: str
    priority: str
    planned_on: str
    hours: str
    crew: str
    cost: str
    stop_needed: str
    back: str


def sent_form(
    title: Annotated[str, Form()] = "",
    equipment: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    fault: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "",
    priority: Annotated[str, Form()] = "",
    planned_on: Annotated[str, Form()] = "",
    hours: Annotated[str, Form()] = "",
    crew: Annotated[str, Form()] = "",
    cost: Annotated[str, Form()] = "",
    stop_needed: Annotated[str, Form()] = "",
    back: Annotated[str, Form()] = "",
) -> Sent:
    return Sent(
        title, equipment, description, fault, status, priority, planned_on, hours, crew, cost, stop_needed, back
    )


Posted = Annotated[Sent, Depends(sent_form)]


def _equipment_of(session: Session, code: str) -> Equipment:
    wanted = read_text(code, longest=LONGEST_CODE, missing=_("Enter the code of the equipment.")).upper()
    found = session.scalar(select(Equipment).where(Equipment.code == wanted))
    if found is None:
        raise Refused(_("No equipment has that code. Look it up in the list of equipment."))
    return found


def checked(sent: Sent, session: Session) -> tuple[dict[str, Any], dict[str, str]]:
    """Every field, at the edge. The browser's `required` and `maxlength` help a person, and decide nothing."""
    return read_fields(
        {
            "title": lambda: read_text(sent.title, longest=LONGEST_TITLE, missing=_("Enter what has to be done.")),
            "equipment": lambda: _equipment_of(session, sent.equipment),
            "description": lambda: read_text(sent.description, longest=LONGEST_DESCRIPTION, lines=True),
            "fault": lambda: read_choice(sent.fault, ("", *FAULTS), _("Choose a fault from the list.")) or None,
            "status": lambda: read_choice(sent.status, WORK_ORDER_STATUSES, _("Choose a state from the list.")),
            "priority": lambda: read_choice(sent.priority, PRIORITIES, _("Choose a priority.")),
            "planned_on": lambda: read_date(
                sent.planned_on, EARLIEST, LATEST, _("Enter a date, or leave it empty if it is not planned yet.")
            ),
            "hours": lambda: read_hours(sent.hours),
            "crew": lambda: read_whole(sent.crew, 1, LARGEST_CREW),
            "cost": lambda: read_decimal(
                sent.cost, 0, LARGEST_COST, COST_DECIMALS, not_a_number=_("Enter the cost as a number, such as 120.50.")
            ),
            "stop_needed": lambda: read_flag(sent.stop_needed),
        }
    )


def _typed(sent: Sent) -> dict[str, Any]:
    return {name: getattr(sent, name) for name in FIELD_IDS} | {"stop_needed": sent.stop_needed == "yes"}


def _stored(order: WorkOrder) -> dict[str, Any]:
    return {
        "title": order.title,
        "equipment": order.equipment.code,
        "description": order.description,
        "fault": order.fault or "",
        "status": order.status,
        "priority": order.priority,
        "planned_on": order.planned_on.isoformat() if order.planned_on else "",
        "hours": format_decimal(order.hours, HOUR_DECIMALS),
        "crew": str(order.crew),
        "cost": format_decimal(order.cost),
        "stop_needed": order.stop_needed,
    }


def _blank(equipment: str) -> dict[str, Any]:
    return {
        "title": "",
        "equipment": equipment,
        "description": "",
        "fault": "",
        "status": "reported",
        "priority": "normal",
        "planned_on": "",
        "hours": format_decimal(Decimal(0), HOUR_DECIMALS),
        "crew": "1",
        "cost": format_decimal(Decimal(0), HOUR_DECIMALS),
        "stop_needed": False,
    }


def _form(
    request: Request,
    order: WorkOrder | None,
    back: str,
    values: dict[str, Any],
    errors: dict[str, str],
    status: int = 200,
) -> Response:
    partial = fragment_requested(request) and request.method == "POST"
    return render(
        request,
        "demo/work_orders/form.html" if partial else "demo/work_orders/page.html",
        status_code=200 if partial else status,
        order=order,
        action=f"/work-orders/{order.id}" if order else "/work-orders",
        back=back,
        values=values,
        errors=errors,
        summary=[(FIELD_IDS[name], errors[name]) for name in FIELD_IDS if name in errors],
        state_options=_state_options(),
        priority_options=[(value, _(label)) for value, label in PRIORITY_LABELS.items()],
        fault_options=sorted(((value, _(label)) for value, label in FAULTS.items()), key=lambda o: o[1].casefold()),
        earliest=EARLIEST.isoformat(),
        latest=LATEST.isoformat(),
        came_from_planning=back.startswith("/planning"),
    )


def _apply(order: WorkOrder, clean: dict[str, Any]) -> None:
    set_status(order, clean["status"])
    order.equipment_id = clean["equipment"].id
    for name in ("title", "description", "fault", "priority", "planned_on", "hours", "crew", "cost", "stop_needed"):
        setattr(order, name, clean[name])


def _new_order() -> WorkOrder:
    """It opens on the demo's today, which is fixed, as every date here is."""
    return WorkOrder(opened_at=LAST_MOMENT, status="reported", hours=Decimal(0), cost=Decimal(0))


def new_form(request: Request, session: DatabaseSession, _person: Admin) -> Response:
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    wanted = request.query_params.get("equipment", "")
    known = session.get(Equipment, int(wanted)) if wanted.isascii() and wanted.isdigit() and len(wanted) < 11 else None
    return _form(request, None, way_back(request.query_params.get("back", "")), _blank(known.code if known else ""), {})


def create(request: Request, session: DatabaseSession, _person: Admin, sent: Posted) -> Response:
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    back = way_back(sent.back)
    clean, errors = checked(sent, session)
    if errors:
        return _form(request, None, back, _typed(sent), errors, 422)
    order = _new_order()
    _apply(order, clean)
    session.add(order)
    session.commit()
    return whole_page(request, _ending(back, "saved", order.id))


def edit_form(request: Request, order_id: int, session: DatabaseSession, _person: Admin) -> Response:
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    order = _order_or_404(session, order_id)
    return _form(request, order, way_back(request.query_params.get("back", "")), _stored(order), {})


def update(request: Request, order_id: int, session: DatabaseSession, _person: Admin, sent: Posted) -> Response:
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    order = _order_or_404(session, order_id)
    back = way_back(sent.back)
    clean, errors = checked(sent, session)
    if errors:
        return _form(request, order, back, _typed(sent), errors, 422)
    _apply(order, clean)
    session.commit()
    return whole_page(request, _ending(back, "saved", order.id))


def _what_goes(order: WorkOrder) -> list[str]:
    """In this row's own words: a confirmation that says only *Are you sure?* protects nothing."""
    hours = format_decimal(order.hours, HOUR_DECIMALS)
    return [
        _("%(work)s, on %(equipment)s") % {"work": order.title, "equipment": order.equipment.name},
        _("Hours recorded: %(hours)s") % {"hours": hours},
    ]


def confirm_delete(request: Request, order_id: int, session: DatabaseSession, _person: Admin) -> Response:
    """The dialog's body for htmx, and a page of its own without JavaScript."""
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    order = _order_or_404(session, order_id)
    return render(
        request,
        "demo/work_orders/confirm.html" if fragment_requested(request) else "demo/work_orders/delete.html",
        order=order,
        lost=_what_goes(order),
        back=way_back(request.query_params.get("back", "")),
    )


def delete(
    request: Request,
    order_id: int,
    session: DatabaseSession,
    _person: Admin,
    back: Annotated[str, Form()] = "",
) -> Response:
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    order = _order_or_404(session, order_id)
    session.delete(order)
    session.commit()
    return whole_page(request, _ending(way_back(back), "deleted", order_id))


def install(application: FastAPI) -> None:
    add = application.add_api_route
    add("/work-orders/new", new_form, include_in_schema=False)
    add("/work-orders", create, methods=["POST"], include_in_schema=False)
    add("/work-orders/{order_id:int}/edit", edit_form, include_in_schema=False)
    add("/work-orders/{order_id:int}", update, methods=["POST"], include_in_schema=False)
    add("/work-orders/{order_id:int}/delete", confirm_delete, include_in_schema=False)
    add("/work-orders/{order_id:int}/delete", delete, methods=["POST"], include_in_schema=False)
