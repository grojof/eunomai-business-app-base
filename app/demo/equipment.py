"""The equipment list: the server table, on the generated rows. See docs/specification.md#the-demo"""

from collections.abc import Iterable, Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response
from sqlalchemy import ColumnElement, case, select

from app.core.database import DatabaseSession
from app.core.i18n import N_, _
from app.core.tables import Column, Filter, ListView, render_list
from app.core.templating import render
from app.demo.data import GENERATE, READY, rows_state
from app.demo.generate import LOCATIONS
from app.demo.models import EQUIPMENT_STATUSES, Equipment

STATUS_LABELS = {
    "in_service": (N_("In service"), "success"),
    "due_soon": (N_("Due soon"), "warning"),
    "stopped": (N_("Stopped"), "danger"),
}
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


def install(application: FastAPI) -> None:
    application.add_api_route("/equipment", equipment_list, include_in_schema=False)
