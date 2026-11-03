"""The work order form: every kind of field on one screen, reached from Planning and from the equipment detail.

The equipment is asked for by its code. There are 50,000: a searchable select must hold its options in the page, because
without JavaScript it is a plain select, so that field is the list of faults. See docs/base/decisions.md.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import DatabaseSession, saved
from app.core.formatters import format_decimal, format_file_size
from app.core.forms import Refused, read_choice, read_date, read_decimal, read_fields, read_flag, read_text, read_whole
from app.core.i18n import N_, _
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


@dataclass(frozen=True)
class OrderField:
    """One field of the form. The page, the error summary and a conflict all read `FIELDS`, so they cannot disagree."""

    name: str
    label: str
    shown: Callable[[WorkOrder], str] | None = None
    compared: str = ""
    wide: bool = False

    @property
    def identifier(self) -> str:
        return "field-" + self.name.replace("_", "-")


FIELDS = (
    OrderField("title", N_("What has to be done"), lambda order: order.title, wide=True),
    OrderField("equipment", N_("Equipment code"), lambda order: order.equipment.code, "equipment_id"),
    OrderField("fault", N_("Fault"), lambda order: _(FAULTS[order.fault]) if order.fault else _("Not known")),
    OrderField("description", N_("Description"), lambda order: order.description, wide=True),
    OrderField("status", N_("State"), lambda order: _(ORDER_LABELS[order.status][0])),
    OrderField("planned_on", N_("Planned for"), planned_text),
    OrderField("hours", N_("Hours"), lambda order: format_decimal(order.hours, HOUR_DECIMALS)),
    OrderField("crew", N_("People needed"), lambda order: str(order.crew)),
    OrderField("cost", N_("Cost"), lambda order: format_decimal(order.cost)),
    OrderField("priority", N_("Priority"), lambda order: _(PRIORITY_LABELS[order.priority])),
    OrderField(
        "stop_needed",
        N_("The equipment must stop for this work"),
        lambda order: _("Yes") if order.stop_needed else _("No"),
        wide=True,
    ),
    OrderField("attachment", N_("Attachment")),
)
"""In the order of the page, by its cards: the work, the plan, and the file."""
WORK_FIELDS, PLAN_FIELDS, FILE_FIELD = FIELDS[:4], FIELDS[4:11], FIELDS[11]
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
    typed = {field.name: getattr(sent, field.name) for field in FIELDS if field is not FILE_FIELD}
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
        summary=[(field.identifier, errors[field.name]) for field in FIELDS if field.name in errors],
        work_fields=WORK_FIELDS,
        plan_fields=PLAN_FIELDS,
        file_item=FILE_FIELD,
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


def _attach(order: WorkOrder, sent: Sent, store: UploadStore, clean: dict[str, Any], kept: list[str]) -> None:
    """Stores a file that passed, and notes its name at once, so that whatever goes wrong next can take it away."""
    kind = clean["attachment"]
    if kind is None or sent.attachment is None or sent.attachment.filename is None:
        return
    stored = store.save(sent.attachment.file)
    kept.append(stored)
    size = store.path_of(stored).stat().st_size
    name = sent.attachment.filename
    order.files.append(
        WorkOrderFile(name=name, stored_name=stored, media_type=kind.media_type, size=size, added_at=LAST_MOMENT)
    )


def _saved_with_file(session: Session, store: UploadStore, order: WorkOrder, sent: Sent, clean: dict[str, Any]) -> bool:
    """Whether it saved. A file stored for a save that did not happen goes, on every way out: its row never was."""
    kept: list[str] = []

    def change() -> None:
        _apply(order, clean)
        session.add(order)
        _attach(order, sent, store, clean, kept)

    done = False
    number = order.id
    try:
        done = saved(session, change)
    except IntegrityError:
        session.rollback()  # a file alone changes no version: it is the foreign key that says the row went
        if number is None or session.get(WorkOrder, number) is not None:
            raise
    finally:
        if not done:
            for stored in kept:
                store.remove(stored)
    return done


def _shown_here() -> dict[str, tuple[str, Callable[[WorkOrder], str]]]:
    return {field.compared or field.name: (_(field.label), field.shown) for field in FIELDS if field.shown}


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
    _saved_with_file(session, store, order, sent, clean)
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
    if not _saved_with_file(session, store, order, sent, clean):
        order = _order_or_404(session, order_id)
        return conflict(order, _changes(order, clean))
    return whole_page(request, _ending(back, "saved", order.id))


def _what_goes(order: WorkOrder) -> list[str]:
    """In this row's own words: a confirmation that says only *Are you sure?* protects nothing."""
    hours = format_decimal(order.hours, HOUR_DECIMALS)
    return [
        _("%(work)s, on %(equipment)s") % {"work": order.title, "equipment": order.equipment.name},
        _("Hours recorded: %(hours)s") % {"hours": hours},
        *(_("Attached file: %(name)s") % {"name": file.name} for file in order.files),
    ]


def _files_named(order: WorkOrder) -> str:
    """What a confirmation goes on to promise. Adding a file moves no version, so the version alone cannot say."""
    return ",".join(str(file.id) for file in order.files)


def _asking(request: Request, order: WorkOrder, back: str, template: str, status: int = 200) -> Response:
    return render(
        request,
        template,
        status_code=status,
        order=order,
        lost=_what_goes(order),
        files_named=_files_named(order),
        back=back,
        changed=status == 409,
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
    files: Annotated[str, Form()] = "",
) -> Response:
    """A confirmation named what would go. If that changed, it asks again with what is there now.

    The files go first, by one statement that says which, because the foreign key's cascade would say nothing: a file
    added in the last instant would lose its row, stay on the disk, and never have been named. The lock is PostgreSQL's
    answer to that instant, and on SQLite the statement itself holds the only writer.
    """
    if rows_state(session) != READY:
        return whole_page(request, "/planning")
    order = _order_or_404(session, order_id, lock=True)
    template = "demo/work_orders/delete.html"
    if read_version(version) != order.version:
        return _asking(request, order, way_back(back), template, 409)
    taken = session.execute(
        sql_delete(WorkOrderFile)
        .where(WorkOrderFile.work_order_id == order_id)
        .returning(WorkOrderFile.id, WorkOrderFile.stored_name)
    ).all()
    if ",".join(str(row.id) for row in sorted(taken, key=lambda row: row.id)) != files:
        session.rollback()
        return _asking(request, _order_or_404(session, order_id), way_back(back), template, 409)
    session.delete(order)
    if not saved(session):
        return _asking(request, _order_or_404(session, order_id), way_back(back), template, 409)
    for row in taken:
        _store(request).remove(row.stored_name)
    return whole_page(request, _ending(way_back(back), "deleted", order_id))


def _file_or_404(session: Session, order_id: int, file_id: int) -> WorkOrderFile:
    """A file is reached through its own order, and only by numbers: nothing from the address names a path."""
    ready = rows_state(session) == READY and file_id <= LARGEST_ID
    file = session.get(WorkOrderFile, file_id) if ready else None
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
