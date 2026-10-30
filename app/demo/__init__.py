"""The demo: a fictional company that maintains its equipment. Deleting this folder leaves a working application."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response

from app.core.i18n import N_
from app.core.identity import Person, require_role
from app.core.templating import NavigationItem, add_templates, render

HERE = Path(__file__).resolve().parent


async def dashboard(request: Request) -> Response:
    return render(
        request,
        "demo/dashboard.html",
        open_orders=3,
        hours=Decimal("1250.75"),
        cost=Decimal("12500.12345678901234567890"),
        next_inspection=date(2027, 3, 15),
        updated=datetime(2026, 10, 30, 7, 30, tzinfo=UTC),
    )


async def inspections(request: Request) -> Response:
    return render(request, "demo/inspections.html", due=1)


async def catalogue(request: Request) -> Response:
    return render(request, "demo/catalogue.html")


async def administration(request: Request, person: Annotated[Person, Depends(require_role("admin"))]) -> Response:
    return render(request, "demo/administration.html", roles=sorted(person.roles))


def install(application: FastAPI) -> None:
    add_templates(HERE / "templates")
    application.state.languages.add_folder(HERE / "locales")
    application.state.navigation += [
        NavigationItem(N_("Dashboard"), "/"),
        NavigationItem(N_("Component catalogue"), "/catalogue"),
        NavigationItem(N_("Administration"), "/administration", role="admin"),
    ]
    application.add_api_route("/", dashboard, include_in_schema=False)
    application.add_api_route("/inspections", inspections, include_in_schema=False)
    application.add_api_route("/catalogue", catalogue, include_in_schema=False)
    application.add_api_route("/administration", administration, include_in_schema=False)
