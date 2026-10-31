"""The equipment list: the server table, on the generated rows. See docs/specification.md#the-demo"""

from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import ColumnElement, case, select

from app.core.database import DatabaseSession, exact_sum
from app.core.excel import ExcelColumn, excel_response
from app.core.i18n import N_, _
from app.core.tables import Column, Filter, ListView, fragment_requested, list_query, render_list, whole_page
from app.core.templating import render
from app.demo.data import GENERATE, READY, rows_state
from app.demo.models import EQUIPMENT_STATUSES, LOCATIONS, Equipment, WorkOrder

STATUS_LABELS = {
    "in_service": (N_("In service"), "success"),
    "due_soon": (N_("Due soon"), "warning"),
    "stopped": (N_("Stopped"), "danger"),
}
ORDER_LABELS = {
    "reported": (N_("Reported"), "neutral"),
    "planned": (N_("Planned"), "info"),
    "in_progress": (N_("In progress"), "warning"),
    "checked": (N_("Checked"), "info"),
    "closed": (N_("Closed"), "success"),
}
LARGEST_ID = 2**31 - 1
"""The database's integer. A longer number in an address is a page that does not exist, not an error."""
STATUS_ORDER = ("stopped", "due_soon", "in_service")
"""What needs attention first: sorted by what it means, not by its letters."""


def ranked(column: Any, values: Iterable[str]) -> ColumnElement[int]:
    """An order chosen here, by position: the database cannot sort a label it does not hold."""
    return case({value: rank for rank, value in enumerate(values)}, value=column)


def labels_in_order(values: Iterable[str]) -> list[str]:
    """Stored values in the order of their labels in the person's language."""
    return sorted(values, key=lambda value: _(value).casefold())


def equipment_view(params: Mapping[str, str]) -> ListView:
    locations = labels_in_order(LOCATIONS)
    return ListView.read(
        "equipment",
        "/equipment",
        params,
        (
            Column("code", _("Code"), Equipment.code),
            Column("name", _("Name"), Equipment.name),
            Column("location", _("Location"), ranked(Equipment.location, locations), wide_only=True),
            Column("status", _("State"), ranked(Equipment.status, STATUS_ORDER)),
            Column("next_inspection", _("Next inspection"), Equipment.next_inspection, wide_only=True),
            Column("cost", _("Cost"), Equipment.cost, numeric=True, first="desc", wide_only=True),
        ),
        Equipment.id,
        "code",
        (
            Filter(
                "status",
                _("State"),
                [(value, _(STATUS_LABELS[value][0])) for value in EQUIPMENT_STATUSES],
                lambda value: Equipment.status == value,
                every=_("All states"),
            ),
            Filter(
                "location",
                _("Location"),
                [(value, _(value)) for value in locations],
                lambda value: Equipment.location == value,
                every=_("All locations"),
            ),
        ),
        (Equipment.code, Equipment.name),
        _("Code or name"),
    )


def equipment_list(request: Request, session: DatabaseSession) -> Response:
    state = rows_state(session)
    if state != READY:
        if fragment_requested(request):
            return whole_page(request, "/equipment")
        return render(request, "demo/equipment/list.html", state=state, command=GENERATE)
    view = equipment_view(request.query_params)
    view.load(session, select(Equipment))
    return render_list(
        request,
        view,
        "demo/equipment/list.html",
        "demo/equipment/results.html",
        state=state,
        command=GENERATE,
        statuses=STATUS_LABELS,
    )


def equipment_export(request: Request, session: DatabaseSession) -> Response:
    """Exactly what the list shows, in the same order, on every page of it. It blocks one worker while it writes."""
    if rows_state(session) != READY:
        return whole_page(request, "/equipment")
    view = equipment_view(request.query_params)
    columns = (
        ExcelColumn(_("Code"), width=14),
        ExcelColumn(_("Name"), width=30),
        ExcelColumn(_("Location"), width=18),
        ExcelColumn(_("State"), width=14),
        ExcelColumn(_("Next inspection"), "date", width=16),
        ExcelColumn(_("Cost"), "number", width=16),
        ExcelColumn(_("Updated"), "moment", width=20),
    )
    statement = select(
        Equipment.code,
        Equipment.name,
        Equipment.location,
        Equipment.status,
        Equipment.next_inspection,
        Equipment.cost,
        Equipment.updated_at,
    )
    rows = (
        (row.code, row.name, _(row.location), _(STATUS_LABELS[row.status][0]), *row[4:])
        for row in view.everything(session, statement)
    )
    return excel_response(_("Equipment"), columns, rows, request.app.state.settings.time_zone)


def _list_address(request: Request) -> str:
    """Back to the list a person came from, with its filters. A tab's own address says it, because after a click on a
    tab the Referer is this same page. Only the query is kept, and it is read like any other."""
    came_from = request.query_params.get("back") or request.headers.get("referer", "")
    return equipment_view(list_query(came_from, "/equipment")).here


def equipment_detail(request: Request, equipment_id: int, session: DatabaseSession) -> Response:
    state = rows_state(session)
    if state != READY:
        if fragment_requested(request):
            return whole_page(request, f"/equipment/{equipment_id}")
        return render(request, "demo/equipment/detail_missing.html", state=state, command=GENERATE)
    item = session.get(Equipment, equipment_id) if equipment_id <= LARGEST_ID else None
    if item is None:
        raise HTTPException(status_code=404)
    tab = request.query_params.get("tab")
    orders = session.scalars(
        select(WorkOrder)
        .where(WorkOrder.equipment_id == equipment_id)
        .order_by(WorkOrder.opened_at.desc(), WorkOrder.id.desc())
    ).all()
    back = _list_address(request)
    keep = {} if back == "/equipment" else {"back": back}
    page = f"/equipment/{equipment_id}"
    context: dict[str, Any] = {
        "item": item,
        "overview_address": f"{page}?{urlencode(keep)}" if keep else page,
        "orders_address": f"{page}?{urlencode({'tab': 'orders'} | keep)}",
        "tab": tab if tab == "orders" else "overview",
        "orders": orders,
        "hours": exact_sum(order.hours for order in orders),
        "cost": exact_sum(order.cost for order in orders),
        "statuses": STATUS_LABELS,
        "order_statuses": ORDER_LABELS,
    }
    if fragment_requested(request):
        response = render(request, "demo/equipment/tabs.html", **context)
    else:
        response = render(request, "demo/equipment/detail.html", back=back, **context)
    response.headers["Vary"] = "HX-Request"
    return response


def install(application: FastAPI) -> None:
    application.add_api_route("/equipment", equipment_list, include_in_schema=False)
    application.add_api_route("/equipment/export", equipment_export, include_in_schema=False)
    application.add_api_route("/equipment/{equipment_id:int}", equipment_detail, include_in_schema=False)
