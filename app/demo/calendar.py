"""The calendar: the inspection team's visits at their times, and work orders over their days. See
docs/specification.md#calendars

A visit moves by dragging, or through its own form; a work order by dragging, or through Planning's editor. Either way
the server checks the role, reads the new moment with its time zone, and compares the version, so a move that comes
after someone else's is refused and the event goes back.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from app.core.calendars import CalendarEvent, Period, calendar_config, read_day, read_moment, read_range
from app.core.database import DatabaseSession, saved
from app.core.formatters import format_date, format_datetime, format_time
from app.core.forms import Refused, read_date, read_fields, read_time
from app.core.i18n import _
from app.core.identity import Person, require_role
from app.core.tables import fragment_requested, whole_page
from app.core.templating import render
from app.demo.data import GENERATE, READY, rows_state
from app.demo.equipment import LARGEST_ID, can_edit, labels_in_order
from app.demo.models import LAST_DAY, LOCATIONS, Equipment, Inspection, WorkOrder, working_days
from app.demo.planning import LONGEST_JOB

PATH = "/calendar"
Admin = Annotated[Person, Depends(require_role("admin"))]


def _location(value: str) -> str:
    return value if value in LOCATIONS else ""


def _back(address: str) -> str:
    """Back to the calendar a person came from: only its path and what it says, read again."""
    try:
        parts = urlsplit(address)
    except ValueError:
        return PATH
    if parts.path != PATH:
        return PATH
    params = dict(parse_qsl(parts.query))
    period = Period.read(params, LAST_DAY)
    return period.address(PATH, location=_location(params.get("location", "")))


def _visit_event(visit: Inspection, back: str, movable: bool) -> CalendarEvent:
    title = _("Inspection: %(equipment)s") % {"equipment": visit.equipment.name}
    url = f"/inspections/{visit.id}/edit?{urlencode({'back': back})}"
    return CalendarEvent(
        f"visit-{visit.id}", title, visit.starts_at, visit.ends_at, url, "primary", visit.version, movable
    )


def _order_event(order: WorkOrder, back: str, movable: bool) -> CalendarEvent:
    assert order.planned_on is not None  # noqa: S101  # only planned orders are read
    title = _("Work order %(number)s: %(work)s") % {"number": order.id, "work": order.title}
    last = order.planned_on + timedelta(days=working_days(order.hours, order.crew) - 1)
    url = f"/planning/{order.id}/edit"
    return CalendarEvent(f"order-{order.id}", title, order.planned_on, last, url, "primary", order.version, movable)


def events_between(
    session: Session, first: date, after: date, zone: str, location: str, back: str, movable: bool
) -> list[CalendarEvent]:
    """Every visit and every planned work order that touches these days, in the application's time zone."""
    local = ZoneInfo(zone)
    start = datetime.combine(first, time(), local).astimezone(UTC)
    end = datetime.combine(after, time(), local).astimezone(UTC)
    where = [Equipment.location == location] if location else []
    visits = session.scalars(
        select(Inspection)
        .join(Inspection.equipment)
        .options(contains_eager(Inspection.equipment))
        .where(Inspection.starts_at < end, Inspection.ends_at > start, *where)
        .order_by(Inspection.starts_at, Inspection.id)
    ).all()
    longest = timedelta(days=working_days(LONGEST_JOB, 1))  # the longest a work order can last
    orders = session.scalars(
        select(WorkOrder)
        .join(WorkOrder.equipment)
        .where(
            WorkOrder.status == "planned",
            WorkOrder.planned_on < after,
            WorkOrder.planned_on >= first - longest,
            *where,
        )
        .order_by(WorkOrder.planned_on, WorkOrder.id)
    ).all()
    found = [_visit_event(visit, back, movable) for visit in visits]
    for order in orders:
        event = _order_event(order, back, movable)
        if isinstance(event.end, date) and not isinstance(event.end, datetime) and event.end >= first:
            found.append(event)
    return found


def _agenda(
    events: list[CalendarEvent], period: Period, zone: str
) -> list[tuple[date, list[tuple[str, CalendarEvent]]]]:
    """The same events by day, for a page without JavaScript: each under the first of its days that is shown, and one
    of several days says until when."""
    days: dict[date, list[tuple[str, CalendarEvent]]] = defaultdict(list)
    for event in events:
        if isinstance(event.start, datetime):
            day = event.start.astimezone(ZoneInfo(zone)).date()
            if period.first <= day <= period.last:
                days[day].append((format_time(event.start, zone), event))
        else:
            assert isinstance(event.end, date)  # noqa: S101  # all-day
            first = max(event.start, period.first)
            if first <= period.last:
                when = (
                    _("All day") if event.end == event.start else _("Until %(day)s") % {"day": format_date(event.end)}
                )
                days[first].append((when, event))
    return sorted(days.items())


def calendar_page(request: Request, session: DatabaseSession) -> Response:
    state = rows_state(session)
    if state != READY:
        if fragment_requested(request):
            return whole_page(request, PATH)
        return render(request, "demo/calendar/page.html", state=state, command=GENERATE)
    zone = request.app.state.settings.time_zone
    period = Period.read(request.query_params, LAST_DAY)
    location = _location(request.query_params.get("location", ""))
    here = period.address(PATH, location=location)
    movable = can_edit(request)
    events = events_between(session, period.first, period.last + timedelta(days=1), zone, location, here, movable)
    names = {"month": _("Month"), "week": _("Week"), "agenda": _("Agenda")}
    steps = [
        (_("Previous"), period.address(PATH, day=period.step(False), location=location), False),
        (_("Today"), period.address(PATH, day=LAST_DAY, location=location), False),
        (_("Next"), period.address(PATH, day=period.step(True), location=location), False),
        *((names[view], period.address(PATH, view=view, location=location), view == period.view) for view in names),
    ]
    extra = [("location", location)] if location else []
    moved = ""
    number = _number(request.query_params.get("moved", ""), "")
    if number is not None and number <= LARGEST_ID and (visit := session.get(Inspection, number)) is not None:
        title = _("Inspection: %(equipment)s") % {"equipment": visit.equipment.name}
        moved = _moved(title, format_datetime(visit.starts_at, zone))
    config = calendar_config(f"{PATH}/events", f"{PATH}/move", zone, period, LAST_DAY, movable, extra)
    return render(
        request,
        "demo/calendar/page.html",
        state=state,
        config=config,
        agenda=_agenda(events, period, zone),
        steps=steps,
        location=location,
        locations=[(value, _(value)) for value in labels_in_order(LOCATIONS)],
        moved=moved,
    )


def calendar_events(request: Request, session: DatabaseSession) -> Response:
    """What FullCalendar asks for: the events of some days, as JSON, with their moments in UTC."""
    if rows_state(session) != READY:
        return JSONResponse([])
    try:
        first, after = read_range(request.query_params.get("start", ""), request.query_params.get("end", ""))
    except Refused:
        raise HTTPException(status_code=400) from None
    zone = request.app.state.settings.time_zone
    location = _location(request.query_params.get("location", ""))
    back = Period("month", first + (after - first) / 2).address(PATH, location=location)
    events = events_between(session, first, after, zone, location, back, can_edit(request))
    return JSONResponse([event.as_json() for event in events])


def _refused(message: str, status: int = 409) -> JSONResponse:
    return JSONResponse({"message": message}, status_code=status)


def _number(text: str, prefix: str) -> int | None:
    rest = text.removeprefix(prefix)
    return int(rest) if text.startswith(prefix) and rest.isascii() and rest.isdigit() and len(rest) < 10 else None


def move_event(
    request: Request,
    session: DatabaseSession,
    _person: Admin,
    event: Annotated[str, Form()] = "",
    start: Annotated[str, Form()] = "",
    end: Annotated[str, Form()] = "",
    version: Annotated[str, Form()] = "",
) -> Response:
    """A drop. The new place is read with its time zone, the version compared, and the answer is JSON for calendar.js:
    what to say, and the version the event has now."""
    if rows_state(session) != READY:
        return _refused(_("That could not be moved. It is back where it was."), 503)
    zone = request.app.state.settings.time_zone
    sent = int(version) if version.isascii() and version.isdigit() and len(version) < 10 else None
    late = _("Someone else changed this first. It is back where it was: reload the page to see where it is now.")
    try:
        if (number := _number(event, "visit-")) is not None:
            visit = session.get(Inspection, number) if number <= LARGEST_ID else None
            if visit is None:
                return _refused(_("This is no longer here: someone may have removed it."), 404)
            starts = read_moment(start)  # a drop moves a visit and keeps its length: whatever end it sends is ignored
            if sent != visit.version:
                return _refused(late)
            length = visit.ends_at - visit.starts_at
            if length <= timedelta(0):
                return _refused(_("That could not be moved. It is back where it was."), 409)
            visit.starts_at, visit.ends_at = starts, starts + length
            if not saved(session):
                return _refused(late)
            when = format_datetime(visit.starts_at, zone)
            title = _("Inspection: %(equipment)s") % {"equipment": visit.equipment.name}
            return JSONResponse({"version": visit.version, "message": _moved(title, when)})
        if (number := _number(event, "order-")) is not None:
            order = session.get(WorkOrder, number) if number <= LARGEST_ID else None
            if order is None:
                return _refused(_("This is no longer here: someone may have removed it."), 404)
            day = read_day(start)
            if sent != order.version:
                return _refused(late)
            if order.status != "planned":
                return _refused(_("Only planned work orders move on the calendar. Change its state in Planning."))
            order.planned_on = day
            if not saved(session):
                return _refused(late)
            title = _("Work order %(number)s: %(work)s") % {"number": order.id, "work": order.title}
            return JSONResponse({"version": order.version, "message": _moved(title, format_date(day))})
    except Refused as problem:
        return _refused(str(problem), 422)
    return _refused(_("That could not be moved. It is back where it was."), 400)


def _moved(title: str, when: str) -> str:
    return _("%(event)s is now on %(when)s.") % {"event": title, "when": when}


def _visit_or_404(session: Session, visit_id: int) -> Inspection:
    visit = session.get(Inspection, visit_id) if visit_id <= LARGEST_ID else None
    if visit is None:
        raise HTTPException(status_code=404)
    return visit


def _local(moment: datetime, zone: str) -> datetime:
    return moment.astimezone(ZoneInfo(zone))


def _visit_form(
    request: Request,
    visit: Inspection,
    back: str,
    values: dict[str, Any],
    errors: dict[str, str],
    status: int = 200,
    conflict: list[tuple[str, str]] | None = None,
) -> Response:
    ids = {"day": "field-day", "starts": "field-starts", "ends": "field-ends"}
    return render(
        request,
        "demo/calendar/inspection.html",
        status_code=status,
        visit=visit,
        back=back,
        values=values,
        errors=errors,
        conflict=conflict or [],
        summary=[(ids[name], error) for name, error in errors.items()],
    )


def local_moment(day: date, at: time, local: ZoneInfo) -> tuple[datetime, bool]:
    """A wall-clock time on a day in the application's time zone, in UTC, and whether that time does not exist there.

    When the clocks go forward an hour is skipped: a time in it does not come back the same from UTC, and is refused.
    When they go back an hour happens twice: it is read as its first time, before the change, which is what a person
    who writes 02:30 on that day most often means, and the end is compared with the start in UTC.
    """
    moment = datetime.combine(day, at, local)
    utc = moment.astimezone(UTC)
    again = utc.astimezone(local)
    return utc, (again.date(), again.time()) != (day, at)


def visit_edit(request: Request, visit_id: int, session: DatabaseSession, _person: Admin) -> Response:
    if rows_state(session) != READY:
        return whole_page(request, PATH)
    visit = _visit_or_404(session, visit_id)
    zone = request.app.state.settings.time_zone
    starts, ends = _local(visit.starts_at, zone), _local(visit.ends_at, zone)
    values = {
        "day": starts.date().isoformat(),
        "starts": starts.strftime("%H:%M"),
        "ends": ends.strftime("%H:%M"),
        "version": visit.version,
    }
    return _visit_form(request, visit, _back(request.query_params.get("back", "")), values, {})


def visit_save(
    request: Request,
    visit_id: int,
    session: DatabaseSession,
    _person: Admin,
    day: Annotated[str, Form()] = "",
    starts: Annotated[str, Form()] = "",
    ends: Annotated[str, Form()] = "",
    version: Annotated[str, Form()] = "",
    back: Annotated[str, Form()] = "",
) -> Response:
    """Moves a visit through its form: the keyboard's way, and the way without JavaScript."""
    if rows_state(session) != READY:
        return whole_page(request, PATH)
    visit = _visit_or_404(session, visit_id)
    zone = request.app.state.settings.time_zone
    way_back = _back(back)
    values: dict[str, Any] = {"day": day, "starts": starts, "ends": ends, "version": version}  # USE-03
    clean, errors = read_fields(
        {
            "day": lambda: read_date(
                day, date(2000, 1, 1), date(2099, 12, 31), _("Enter the day of the visit."), needed=True
            ),
            "starts": lambda: read_time(starts, _("Enter when it starts, such as 09:30.")),
            "ends": lambda: read_time(ends, _("Enter when it ends, such as 11:00.")),
        }
    )
    local = ZoneInfo(zone)
    new_start = new_end = datetime.min.replace(tzinfo=UTC)
    if not errors:
        new_start, missing_start = local_moment(clean["day"], clean["starts"], local)
        new_end, missing_end = local_moment(clean["day"], clean["ends"], local)
        skipped = _("That time does not exist on that day: the clocks go forward. Choose a time after the change.")
        if missing_start:
            errors["starts"] = skipped
        if missing_end:
            errors["ends"] = skipped
        if not errors and new_end <= new_start:
            errors["ends"] = _("It must end after it starts.")
    if errors:
        return _visit_form(request, visit, way_back, values, errors, 422)
    late = not (version.isascii() and version.isdigit() and int(version) == visit.version)
    if late and (visit.starts_at, visit.ends_at) != (new_start, new_end):
        now = [(_("Starts"), format_datetime(visit.starts_at, zone)), (_("Ends"), format_datetime(visit.ends_at, zone))]
        return _visit_form(request, visit, way_back, values | {"version": visit.version}, {}, 409, now)
    visit.starts_at, visit.ends_at = new_start, new_end
    if not saved(session):
        visit = _visit_or_404(session, visit_id)
        now = [(_("Starts"), format_datetime(visit.starts_at, zone)), (_("Ends"), format_datetime(visit.ends_at, zone))]
        return _visit_form(request, visit, way_back, values | {"version": visit.version}, {}, 409, now)
    period = Period("week", new_start.astimezone(local).date())
    params = dict(parse_qsl(urlsplit(way_back).query))
    return RedirectResponse(
        period.address(PATH, location=_location(params.get("location", ""))) + f"&moved={visit.id}", status_code=303
    )


def install(application: FastAPI) -> None:
    application.add_api_route(PATH, calendar_page, include_in_schema=False)
    application.add_api_route(f"{PATH}/events", calendar_events, include_in_schema=False)
    application.add_api_route(f"{PATH}/move", move_event, methods=["POST"], include_in_schema=False)
    application.add_api_route("/inspections/{visit_id:int}/edit", visit_edit, include_in_schema=False)
    application.add_api_route("/inspections/{visit_id:int}/edit", visit_save, methods=["POST"], include_in_schema=False)
