"""The demo: a fictional company that maintains its equipment. Deleting this folder leaves a working application."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.core.database import DatabaseSession
from app.core.formatters import rounded
from app.core.i18n import N_, _
from app.core.identity import Person, require_role
from app.core.templating import NavigationItem, add_templates, render
from app.demo import equipment, gallery, planning
from app.demo.charts import dashboard_figures
from app.demo.data import GENERATE, READY, rows_state

HERE = Path(__file__).resolve().parent
IN_SERVICE = (N_("In service"), "success")
DUE = (N_("Due soon"), "warning")
STOPPED = (N_("Stopped"), "danger")
EQUIPMENT = [
    (N_("Air compressor"), N_("Workshop"), date(2027, 3, 15), IN_SERVICE),
    (N_("Conveyor belt"), N_("Packing"), date(2026, 11, 20), DUE),
    (N_("Standby generator"), N_("Plant room"), date(2027, 1, 12), IN_SERVICE),
    (N_("Cooling tower"), N_("Roof"), date(2026, 11, 9), STOPPED),
    (N_("Forklift"), N_("Warehouse"), date(2027, 5, 3), IN_SERVICE),
]
PLAN = [
    (N_("Preventive plan"), 72, "primary"),
    (N_("Spare parts in stock"), 88, "success"),
    (N_("Safety checks"), 41, "warning"),
]
WORK_ORDER_STEPS = (N_("Reported"), N_("Planned"), N_("In progress"), N_("Checked"), N_("Closed"))


def dashboard(request: Request, session: DatabaseSession) -> Response:
    """Fixed values for a first run, and the generated rows once they are there. It never needs a database."""
    state = rows_state(session)
    figures: dict[str, Any] = {
        "open_orders": 3,
        "hours": Decimal("1250.75"),
        "cost": Decimal("12500.12345678901234567890"),
        "next_inspection": date(2027, 3, 15),
        "next_equipment": N_("Air compressor"),
        "equipment": EQUIPMENT,
        "orders_chart": None,
    }
    if state == READY:
        figures |= dashboard_figures(session, request.app.state.settings.time_zone)
    return render(
        request,
        "demo/dashboard.html",
        **figures,
        cost_rounded=rounded(figures["cost"]),
        updated=datetime(2026, 10, 30, 7, 30, tzinfo=UTC),
        plan=PLAN,
        steps=[_(step) for step in WORK_ORDER_STEPS],
        state=state,
        command=GENERATE,
    )


async def inspections(request: Request) -> Response:
    return render(request, "demo/inspections.html", due=1)


async def administration(request: Request, person: Annotated[Person, Depends(require_role("admin"))]) -> Response:
    return render(request, "demo/administration.html", roles=sorted(person.roles))


def install(application: FastAPI) -> None:
    add_templates(HERE / "templates")
    application.state.languages.add_folder(HERE / "locales")
    application.state.navigation += [
        NavigationItem(N_("Dashboard"), "/", "gauge"),
        NavigationItem(N_("Equipment"), "/equipment", "wrench"),
        NavigationItem(N_("Planning"), "/planning", "calendar-range"),
        NavigationItem(N_("Gallery"), "/gallery", "component", children=gallery.navigation_groups),
        NavigationItem(N_("Administration"), "/administration", "shield", role="admin"),
    ]
    if application.state.settings.layout_choices:
        application.state.navigation.insert(4, NavigationItem(N_("Settings"), "/settings", "sliders-horizontal"))
    application.mount("/static/demo", StaticFiles(directory=HERE / "static"), name="demo")
    application.add_api_route("/", dashboard, include_in_schema=False)
    application.add_api_route("/inspections", inspections, include_in_schema=False)
    application.add_api_route("/administration", administration, include_in_schema=False)
    equipment.install(application)
    planning.install(application)
    gallery.install(application)
