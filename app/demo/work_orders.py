"""The work order form: every kind of field on one screen, reached from Planning and from the equipment detail.

The equipment is asked for by its code. There are 50,000: a searchable select must hold its options in the page, because
without JavaScript it is a plain select, so that field is the list of faults. See docs/decisions.md.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import DatabaseSession, saved
from app.core.formatters import format_decimal, format_file_size
from app.core.forms import Refused, read_choice, read_date, read_decimal, read_fields, read_flag, read_text, read_whole
from app.core.i18n import N_, _, ngettext
from app.core.identity import Person, require_role
from app.core.tables import fragment_requested, list_query, whole_page
from app.core.templating import render
from app.core.uploads import ACCEPTED, KINDS, UploadStore, read_upload
from app.demo.data import READY, rows_state
from app.demo.equipment import LARGEST_ID, ORDER_LABELS, equipment_view, record_number
from app.demo.models import LAST_MOMENT, PRIORITIES, WORK_ORDER_STATUSES, Equipment, WorkOrder, WorkOrderFile
from app.demo.planning import (
    EARLIEST,
    HOUR_DECIMALS,
    LATEST,
    _order_or_404,
    _state_options,
    differences,
    planned_text,
    planning_view,
    read_hours,
    read_version,
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
    "attachment": "field-attachment",
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
    version: str
    attachment: UploadFile | None


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
    version: Annotated[str, Form()] = "",
    attachment: Annotated[UploadFile | None, File()] = None,
) -> Sent:
    return Sent(
        title,
        equipment,
        description,
        fault,
        status,
        priority,
        planned_on,
        hours,
        crew,
        cost,
        stop_needed,
        back,
        version,
        attachment,
    )


Posted = Annotated[Sent, Depends(sent_form)]


def _equipment_of(session: Session, code: str) -> Equipment:
    wanted = read_text(code, longest=LONGEST_CODE, missing=_("Enter the code of the equipment.")).upper()
    found = session.scalar(select(Equipment).where(Equipment.code == wanted))
    if found is None:
        raise Refused(_("No equipment has that code. Look it up in the list of equipment."))
    return found


def _store(request: Request) -> UploadStore:
    store: UploadStore = request.app.state.uploads
    return store


def checked(sent: Sent, session: Session, store: UploadStore) -> tuple[dict[str, Any], dict[str, str]]:
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
            "attachment": lambda: read_upload(sent.attachment, store.largest),
        }
    )


def _typed(sent: Sent) -> dict[str, Any]:
    typed = {name: getattr(sent, name) for name in FIELD_IDS if name != "attachment"}
    return typed | {"stop_needed": sent.stop_needed == "yes", "version": sent.version}


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
        "version": order.version,
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
        "version": "",
    }


def _form(
    request: Request,
    order: WorkOrder | None,
    back: str,
    values: dict[str, Any],
    errors: dict[str, str],
    status: int = 200,
    file_sent: bool = False,
    conflict: Sequence[tuple[str, str]] = (),
) -> Response:
    partial = fragment_requested(request) and request.method == "POST"
    store = _store(request)
    kinds = ", ".join(kind.label for kind in KINDS)
    limits = {"kinds": kinds, "most": format_file_size(store.largest)}
    hint = _("One file: %(kinds)s, of up to %(most)s.") % limits
    return render(
        request,
        "demo/work_orders/form.html" if partial else "demo/work_orders/page.html",
        status_code=200 if partial else status,
        conflict=conflict,
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
        accepted=ACCEPTED,
        file_hint=_("Choose the file again: a browser cannot keep it when a form comes back.") if file_sent else hint,
        files=order.files if order else [],
        removed="removed" in request.query_params,
    )


def _attach(order: WorkOrder, sent: Sent, store: UploadStore, clean: dict[str, Any]) -> str:
    """Stores a file that passed, and gives its stored name, or nothing. Called last: nothing else can refuse it."""
    kind = clean["attachment"]
    if kind is None or sent.attachment is None or sent.attachment.filename is None:
        return ""
    stored = store.save(sent.attachment.file)
    size = store.path_of(stored).stat().st_size
    name = sent.attachment.filename
    order.files.append(
        WorkOrderFile(name=name, stored_name=stored, media_type=kind.media_type, size=size, added_at=LAST_MOMENT)
    )
    return stored


def _committed(session: Session, store: UploadStore, stored: str) -> bool:
    """Whether it saved. A failed commit leaves no file behind: its row never was."""
    try:
        done = saved(session)
    except Exception:
        done = False
        raise
    finally:
        if stored and not done:
            store.remove(stored)
    return done


def _shown_here() -> dict[str, tuple[str, Callable[[WorkOrder], str]]]:
    """What a conflict can name, in the order of the page."""
    return {
        "title": (_("What has to be done"), lambda order: order.title),
        "equipment_id": (_("Equipment code"), lambda order: order.equipment.code),
        "description": (_("Description"), lambda order: order.description),
        "fault": (_("Fault"), lambda order: _(FAULTS[order.fault]) if order.fault else _("Not known")),
        "status": (_("State"), lambda order: _(ORDER_LABELS[order.status][0])),
        "planned_on": (_("Planned for"), planned_text),
        "hours": (_("Hours"), lambda order: format_decimal(order.hours, HOUR_DECIMALS)),
        "crew": (_("People needed"), lambda order: str(order.crew)),
        "cost": (_("Cost"), lambda order: format_decimal(order.cost)),
        "priority": (_("Priority"), lambda order: _(PRIORITY_LABELS[order.priority])),
        "stop_needed": (
            _("The equipment must stop for this work"),
            lambda order: _("Yes") if order.stop_needed else _("No"),
        ),
    }


def _changes(order: WorkOrder, clean: dict[str, Any]) -> list[tuple[str, str]]:
    return differences(order, clean | {"equipment_id": clean["equipment"].id}, _shown_here())


def _has_file(sent: Sent) -> bool:
    return bool(sent.attachment and sent.attachment.filename)


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
    wanted = record_number(request.query_params.get("equipment", ""))
    known = session.get(Equipment, wanted) if wanted is not None else None
    return _form(request, None, way_back(request.query_params.get("back", "")), _blank(known.code if known else ""), {})


def create(request: Request, session: DatabaseSession, _person: Admin, sent: Posted) -> Response:
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    back = way_back(sent.back)
    store = _store(request)
    clean, errors = checked(sent, session, store)
    if errors:
        return _form(request, None, back, _typed(sent), errors, 422, _has_file(sent))
    order = _new_order()
    _apply(order, clean)
    session.add(order)
    _committed(session, store, _attach(order, sent, store, clean))
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
    store = _store(request)
    clean, errors = checked(sent, session, store)
    if errors:
        return _form(request, order, back, _typed(sent), errors, 422, _has_file(sent))

    def conflict(row: WorkOrder, changes: list[tuple[str, str]]) -> Response:
        typed = _typed(sent) | {"version": row.version}  # a second Save replaces their work, knowingly
        return _form(request, row, back, typed, {}, 409, _has_file(sent), changes)

    late = read_version(sent.version) != order.version
    if late and (changes := _changes(order, clean)):
        return conflict(order, changes)
    _apply(order, clean)
    if not _committed(session, store, _attach(order, sent, store, clean)):
        order = _order_or_404(session, order_id)
        return conflict(order, _changes(order, clean))
    return whole_page(request, _ending(back, "saved", order.id))


def _what_goes(order: WorkOrder) -> list[str]:
    """In this row's own words: a confirmation that says only *Are you sure?* protects nothing."""
    hours = format_decimal(order.hours, HOUR_DECIMALS)
    return [
        _("%(work)s, on %(equipment)s") % {"work": order.title, "equipment": order.equipment.name},
        _("Hours recorded: %(hours)s") % {"hours": hours},
        *(
            [ngettext("%(count)s attached file", "%(count)s attached files", files) % {"count": files}]
            if (files := len(order.files))
            else []
        ),
    ]


def _asking(request: Request, order: WorkOrder, back: str, template: str, status: int = 200) -> Response:
    return render(
        request, template, status_code=status, order=order, lost=_what_goes(order), back=back, changed=status == 409
    )


def confirm_delete(request: Request, order_id: int, session: DatabaseSession, _person: Admin) -> Response:
    """The dialog's body for htmx, and a page of its own without JavaScript."""
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    template = "demo/work_orders/confirm.html" if fragment_requested(request) else "demo/work_orders/delete.html"
    back = way_back(request.query_params.get("back", ""))
    return _asking(request, _order_or_404(session, order_id), back, template)


def delete(
    request: Request,
    order_id: int,
    session: DatabaseSession,
    _person: Admin,
    back: Annotated[str, Form()] = "",
    version: Annotated[str, Form()] = "",
) -> Response:
    """A confirmation named what would go. If that changed, it asks again with what is there now."""
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    order = _order_or_404(session, order_id)
    if read_version(version) != order.version:
        return _asking(request, order, way_back(back), "demo/work_orders/delete.html", 409)
    stored = [file.stored_name for file in order.files]
    session.delete(order)
    if not saved(session):
        return _asking(request, _order_or_404(session, order_id), way_back(back), "demo/work_orders/delete.html", 409)
    for name in stored:
        _store(request).remove(name)
    return whole_page(request, _ending(way_back(back), "deleted", order_id))


def _file_or_404(session: Session, order_id: int, file_id: int) -> WorkOrderFile:
    """A file is reached through its own order, and only by numbers: nothing from the address names a path."""
    file = session.get(WorkOrderFile, file_id) if file_id <= LARGEST_ID else None
    if file is None or file.work_order_id != order_id:
        raise HTTPException(status_code=404)
    return file


def download(request: Request, order_id: int, file_id: int, session: DatabaseSession, _person: Admin) -> Response:
    file = _file_or_404(session, order_id, file_id)
    return _store(request).response(file.stored_name, file.name, file.media_type)


def confirm_remove(request: Request, order_id: int, file_id: int, session: DatabaseSession, _person: Admin) -> Response:
    file = _file_or_404(session, order_id, file_id)
    return render(
        request,
        "demo/work_orders/confirm_file.html" if fragment_requested(request) else "demo/work_orders/remove_file.html",
        file=file,
        order_id=order_id,
        back=way_back(request.query_params.get("back", "")),
    )


def remove_file(
    request: Request,
    order_id: int,
    file_id: int,
    session: DatabaseSession,
    _person: Admin,
    back: Annotated[str, Form()] = "",
) -> Response:
    file = _file_or_404(session, order_id, file_id)
    stored = file.stored_name
    session.delete(file)
    session.commit()
    _store(request).remove(stored)
    keep = urlencode({"back": way_back(back), "removed": 1})
    return whole_page(request, f"/work-orders/{order_id}/edit?{keep}")


def install(application: FastAPI) -> None:
    add = application.add_api_route
    add("/work-orders/new", new_form, include_in_schema=False)
    add("/work-orders", create, methods=["POST"], include_in_schema=False)
    add("/work-orders/{order_id:int}/edit", edit_form, include_in_schema=False)
    add("/work-orders/{order_id:int}", update, methods=["POST"], include_in_schema=False)
    add("/work-orders/{order_id:int}/delete", confirm_delete, include_in_schema=False)
    add("/work-orders/{order_id:int}/delete", delete, methods=["POST"], include_in_schema=False)
    add("/work-orders/{order_id:int}/files/{file_id:int}", download, include_in_schema=False)
    add("/work-orders/{order_id:int}/files/{file_id:int}/delete", confirm_remove, include_in_schema=False)
    add(
        "/work-orders/{order_id:int}/files/{file_id:int}/delete", remove_file, methods=["POST"], include_in_schema=False
    )
