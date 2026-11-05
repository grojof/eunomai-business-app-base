"""The calendar: FullCalendar on the server's events and words, in the application's time zone, moved on the server."""

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import create_database_engine
from app.core.i18n import PSEUDO
from app.demo.models import Inspection, WorkOrder
from app.main import create_app
from tests.conftest import PERSON, build_settings, running_server
from tests.demo.support import fill, until
from tests.helpers import overflows_sideways, run_axe_in_both_themes, untranslated
from tools import vendor

SAME_SITE = {"Sec-Fetch-Site": "same-origin"}
ZONE = "Europe/Madrid"
READY = "document.documentElement.dataset.calendarReady !== undefined"
WEEK = "/calendar?view=week&date=2026-10-28&location=Roof"
ALLOWED = ("Business App", "Demo Person", "Air compressor", "Conveyor belt", "Standby generator", "Cooling tower")
ALLOWED += ("Forklift", "Preventive plan", "Safety checks", "Oil change", "Filter replacement", "Belt replacement")
ALLOWED += ("Calibration", "Leak repair", "Electrical inspection", "AM", "PM", "Oct ", "Nov ", "Sep ", "Dec ")


def visits(url):
    engine = create_database_engine(url)
    with Session(engine) as session:
        found = session.scalars(select(Inspection).order_by(Inspection.starts_at, Inspection.id)).all()
    engine.dispose()
    return found


def read(url, model, number):
    engine = create_database_engine(url)
    with Session(engine) as session:
        row = session.get(model, number)
    engine.dispose()
    return row


@pytest.fixture
def writable(database_url):
    fill(database_url, 200)
    client = TestClient(create_app(build_settings(database_url=database_url, time_zone=ZONE)))
    client.headers.update(PERSON | SAME_SITE)
    return client, database_url


def config_of(html):
    return json.loads(
        re.search(r'<section id="calendar".*?<script type="application/json">(.*?)</script>', html, re.S)[1]
    )


def test_the_page_carries_the_words_the_zone_and_the_period(filled):
    filled.cookies.set("language", "es")
    config = config_of(filled.get(WEEK).text)
    assert config["view"] == "week"
    assert config["date"] == "2026-10-28"
    assert config["extra"] == {"location": "Roof"}
    words = config["words"]
    assert (words["todayText"], words["todayHint"]["week"]) == ("Hoy", "Hoy")
    assert words["viewHint"] == {"month": "Vista de mes", "week": "Vista de semana", "list": "Vista de agenda"}
    assert words["prevHint"]["month"] == "Mes anterior"


@pytest.mark.parametrize("language", ["es", "ca"])
def test_every_hint_holds_the_words_of_its_button(filled, language):
    """WCAG 2.5.3: what a screen reader says starts with what a person sees."""
    filled.cookies.set("language", language)
    words = config_of(filled.get(WEEK).text)["words"]
    assert all(words["todayText"] in hint for hint in words["todayHint"].values())
    assert words["moreLinkText"] in words["moreLinkHint"] or "{n}" in words["moreLinkHint"]


def test_a_period_off_its_lists_is_the_demos_month(filled):
    config = config_of(filled.get("/calendar?view=year&date=2026-02-30").text)
    assert (config["view"], config["date"]) == ("month", "2026-10-31")


def test_without_javascript_the_agenda_and_its_links_are_there(filled):
    html = filled.get(WEEK).text
    assert "data-calendar-fallback" in html
    assert 'href="/calendar?view=week&amp;date=2026-11-04&amp;location=Roof"' in html
    assert re.search(r'<a class="link link-hover" href="/inspections/\d+/edit\?back=', html)


def test_events_come_as_json_with_their_moments_in_utc(filled):
    events = filled.get("/calendar/events?start=2026-10-26T00:00:00Z&end=2026-11-02T00:00:00Z").json()
    timed = [event for event in events if not event["allDay"]]
    all_day = [event for event in events if event["allDay"]]
    assert timed and all_day
    assert all(event["start"].endswith("Z") and event["editable"] for event in timed)
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", event["end"]) for event in all_day)
    assert all(event["url"].startswith(("/inspections/", "/planning/")) for event in events)


@pytest.mark.parametrize(
    "query", ["start=x&end=y", "start=2026-11-01&end=2026-10-01", "start=2026-01-01&end=2026-12-31"]
)
def test_a_range_that_is_not_one_is_refused(filled, query):
    assert filled.get(f"/calendar/events?{query}").status_code == 400


def test_someone_who_may_not_move_gets_events_that_do_not_move(filled_url):
    client = TestClient(create_app(build_settings(database_url=filled_url)))
    staff = PERSON | {"X-Remote-Groups": "staff"}
    events = client.get("/calendar/events?start=2026-10-26&end=2026-11-02", headers=staff).json()
    assert not any(event["editable"] for event in events)
    assert config_of(client.get(WEEK, headers=staff).text)["canMove"] is False


@pytest.mark.rule("LANG-09")
@pytest.mark.rule("LANG-15")
def test_a_drop_is_read_with_its_offset_and_saved_in_utc(writable):
    client, url = writable
    visit = visits(url)[0]
    length = visit.ends_at - visit.starts_at
    answer = client.post(
        "/calendar/move",
        data={
            "event": f"visit-{visit.id}",
            "start": "2026-11-04T09:30:00+01:00",
            "end": "",
            "version": str(visit.version),
        },
    )
    assert answer.status_code == 200
    saved = read(url, Inspection, visit.id)
    assert saved.starts_at == datetime(2026, 11, 4, 8, 30, tzinfo=UTC)
    assert saved.ends_at - saved.starts_at == length
    assert answer.json()["version"] == visit.version + 1
    assert "4 Nov 2026" in answer.json()["message"] or "Nov 4, 2026" in answer.json()["message"]


def test_a_drop_of_a_work_order_moves_its_day(writable):
    client, url = writable
    engine = create_database_engine(url)
    with Session(engine) as session:
        order = session.scalars(select(WorkOrder).where(WorkOrder.status == "planned")).first()
    engine.dispose()
    answer = client.post(
        "/calendar/move", data={"event": f"order-{order.id}", "start": "2026-11-09", "version": str(order.version)}
    )
    assert answer.status_code == 200
    assert read(url, WorkOrder, order.id).planned_on.isoformat() == "2026-11-09"


def test_a_drop_after_someone_elses_is_refused_and_moves_nothing(writable):
    client, url = writable
    visit = visits(url)[0]
    form = {"event": f"visit-{visit.id}", "start": "2026-11-04T09:30:00Z", "version": str(visit.version)}
    assert client.post("/calendar/move", data=form).status_code == 200
    answer = client.post("/calendar/move", data=form | {"start": "2026-11-05T09:30:00Z"})
    assert answer.status_code == 409
    assert "Someone else changed this first" in answer.json()["message"]
    assert read(url, Inspection, visit.id).starts_at == datetime(2026, 11, 4, 9, 30, tzinfo=UTC)


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize("start", ["2026-11-04T09:30:00", "tomorrow", "2026-11-04T25:00:00Z", "0026-11-04T09:30:00Z"])
def test_a_moment_without_its_zone_or_out_of_reason_is_refused(writable, start):
    client, url = writable
    visit = visits(url)[0]
    answer = client.post(
        "/calendar/move", data={"event": f"visit-{visit.id}", "start": start, "version": str(visit.version)}
    )
    assert answer.status_code == 422
    assert read(url, Inspection, visit.id).starts_at == visit.starts_at


@pytest.mark.rule("SEC-02")
def test_moving_needs_its_role(writable):
    client, url = writable
    visit = visits(url)[0]
    staff = PERSON | SAME_SITE | {"X-Remote-Groups": "staff"}
    form = {"event": f"visit-{visit.id}", "start": "2026-11-04T09:30:00Z", "version": "1"}
    assert client.post("/calendar/move", data=form, headers=staff).status_code == 403
    assert client.get(f"/inspections/{visit.id}/edit", headers=staff).status_code == 403


def test_the_form_moves_a_visit_in_the_applications_time_zone(writable):
    client, url = writable
    visit = visits(url)[0]
    form = {"day": "2026-11-10", "starts": "10:00", "ends": "11:30", "version": str(visit.version), "back": WEEK}
    response = client.post(f"/inspections/{visit.id}/edit", data=form, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/calendar?view=week&date=2026-11-10&location=Roof&moved={visit.id}"
    saved = read(url, Inspection, visit.id)
    assert (saved.starts_at, saved.ends_at) == (
        datetime(2026, 11, 10, 9, tzinfo=UTC),
        datetime(2026, 11, 10, 10, 30, tzinfo=UTC),
    )
    assert "is now on" in client.get(response.headers["location"]).text


@pytest.mark.rule("USE-03")
@pytest.mark.rule("A11Y-08")
def test_a_form_with_errors_keeps_what_was_typed(writable):
    client, url = writable
    visit = visits(url)[0]
    form = {"day": "2026-11-10", "starts": "12:00", "ends": "11:00", "version": str(visit.version), "back": WEEK}
    response = client.post(f"/inspections/{visit.id}/edit", data=form)
    assert response.status_code == 422
    assert 'href="#field-ends"' in response.text
    assert 'value="12:00"' in response.text


def test_a_form_after_someone_elses_save_says_what_they_saved(writable):
    client, url = writable
    visit = visits(url)[0]
    form = {"day": "2026-11-10", "starts": "10:00", "ends": "11:00", "version": str(visit.version), "back": WEEK}
    client.post(f"/inspections/{visit.id}/edit", data=form)
    response = client.post(f"/inspections/{visit.id}/edit", data=form | {"starts": "08:00"})
    assert response.status_code == 409
    assert "Someone else changed this visit" in response.text


@pytest.mark.rule("SEC-13")
def test_the_way_back_never_leaves_the_calendar(writable):
    client, url = writable
    visit = visits(url)[0]
    form = {
        "day": "2026-11-10",
        "starts": "10:00",
        "ends": "11:00",
        "version": str(visit.version),
        "back": "//elsewhere.example/x",
    }
    location = client.post(f"/inspections/{visit.id}/edit", data=form, follow_redirects=False).headers["location"]
    assert location.startswith("/calendar?")


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", [WEEK, "/calendar?view=month&date=2026-11-02"])
def test_no_text_outside_translation(filled, path):
    filled.cookies.set("language", PSEUDO)
    assert untranslated(filled.get(path).text, ALLOWED) == []


def test_fullcalendar_and_its_theme_are_pinned_and_past_the_two_week_rule():
    entries = vendor.read_entries()
    names = [name for name, entry in entries.items() if entry.get("package", name) == "fullcalendar"]
    assert len(names) == 5
    assert {entries[name]["version"] for name in names} == {"7.1.3"}
    try:
        published = vendor.read_json("https://registry.npmjs.org/fullcalendar")["time"]["7.1.3"]
    except OSError:
        pytest.skip("the registry cannot be reached")
    assert datetime.now(UTC) - datetime.fromisoformat(published) >= vendor.WINDOW


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("view", ["month", "week", "agenda"])
@pytest.mark.parametrize("language", ["en", "es", "ca"])
def test_the_calendar_passes_the_scan(open_filled, view, language):
    page = open_filled(f"/calendar?view={view}&date=2026-10-28", language=language, bypass_csp=True)
    until(page, READY)
    assert run_axe_in_both_themes(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.parametrize("font", ["", "Impact", "monospace"])
def test_more_events_lead_to_the_agenda_of_their_week_and_pass_the_scan(open_filled, font):
    """A box over the month hid part of the events under it, and how much depended on the font: Linux's failed the
    target-size check where Windows' did not. Impact here does the same on Windows. The agenda hides nothing."""
    page = open_filled("/calendar?view=month&date=2026-10-28", bypass_csp=True)
    if font:
        page.add_style_tag(content=f"*, *::before {{ font-family: {font} !important; }}")
    until(page, READY)
    page.locator(".calendar-more").first.click()
    until(page, "location.search.includes('view=agenda')")
    assert page.locator(".calendar-popover").count() == 0
    assert run_axe_in_both_themes(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
@pytest.mark.parametrize("view", ["month", "week", "agenda"])
def test_the_calendar_fits_a_phone(open_filled, view):
    page = open_filled(f"/calendar?view={view}&date=2026-10-28&location=Roof", language=PSEUDO, width=320)
    until(page, READY)
    assert not overflows_sideways(page)


@pytest.mark.browser
def test_its_words_are_ours_in_spanish_and_catalan(open_filled):
    page = open_filled(WEEK, language="es")
    until(page, READY)
    assert page.get_by_role("button", name="Hoy").count() == 1
    assert page.get_by_role("button", name="Semana anterior").count() == 1
    assert page.get_by_role("tab", name="Vista de semana").count() == 1
    page = open_filled(WEEK, language="ca")
    until(page, READY)
    assert page.get_by_role("button", name="Avui").count() == 1
    assert page.get_by_role("tab", name="Vista d'agenda").count() == 1


@pytest.mark.browser
@pytest.mark.rule("USE-05")
def test_the_view_and_the_day_live_in_the_address(open_filled):
    page = open_filled("/calendar?view=week&date=2026-11-16")
    until(page, READY)
    assert page.locator("[role=tab][aria-selected=true]").inner_text() == "Week"
    page.get_by_role("button", name="Next week").click()
    until(page, "location.search.includes('date=2026-11-23')")
    page.get_by_role("tab", name="Month view").click()
    until(page, "location.search.includes('view=month')")
    page.reload()
    until(page, READY)
    assert page.locator("[role=tab][aria-selected=true]").inner_text() == "Month"


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_the_theme_follows_without_a_reload_and_nothing_breaks_the_policy(open_filled):
    problems = []
    page = open_filled(WEEK, theme="system")
    page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
    page.emulate_media(color_scheme="light")
    until(page, READY)
    read = "getComputedStyle(document.querySelector('.calendar-button')).backgroundColor"
    light = page.evaluate(read)
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    until(page, f"{read} !== {json.dumps(light)}")
    assert problems == []


@pytest.fixture
def madrid(browser, tmp_path):
    """A server in Madrid's time, and a browser in New York's, on rows of their own."""
    url = f"sqlite:///{(tmp_path / 'calendar.db').as_posix()}"
    fill(url, 200)
    settings = build_settings(
        database_url=url, time_zone=ZONE, fake_identity=True, fake_groups=["admins"], trusted_proxies=[]
    )
    with running_server(create_app(settings)) as port:
        base = f"http://127.0.0.1:{port}"
        context = browser.new_context(viewport={"width": 1280, "height": 900}, timezone_id="America/New_York")
        context.add_cookies([{"name": "language", "value": "en", "url": base}])
        yield context, base, url
        context.close()


@pytest.mark.browser
@pytest.mark.rule("LANG-09")
def test_a_drag_keeps_the_applications_time_whatever_the_browsers(madrid):
    context, base, url = madrid
    first = visits(url)
    visit = next(
        row
        for row in first
        if row.starts_at >= datetime(2026, 10, 26, tzinfo=UTC) and row.ends_at - row.starts_at <= timedelta(hours=3)
    )
    week = visit.starts_at.date() - timedelta(days=visit.starts_at.weekday())
    page = context.new_page()
    page.goto(f"{base}/calendar?view=week&date={week.isoformat()}")
    until(page, READY)
    event = page.locator(f"a.calendar-event[href^='/inspections/{visit.id}/']")
    local = visit.starts_at.astimezone(ZoneInfo(ZONE))
    assert f"{local.hour % 12 or 12}:{local.minute:02d}" in event.inner_text()
    box = event.bounding_box()
    slot = page.locator(".calendar-frame [data-time='09:00:00']").first.bounding_box()["height"]
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 6)
    page.mouse.down()
    for step in range(1, 11):
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 6 + slot * 2 * step / 10)
        page.wait_for_timeout(30)
    page.mouse.up()
    until(page, "document.querySelector('#announcements').textContent.includes('is now on')")
    assert read(url, Inspection, visit.id).starts_at == visit.starts_at + timedelta(hours=1)


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_the_keyboard_reaches_an_event_and_moves_it_with_its_form(madrid):
    context, base, url = madrid
    page = context.new_page()
    page.goto(f"{base}/calendar?view=agenda&date=2026-10-28")
    until(page, READY)
    link = page.locator("a.calendar-event[href^='/inspections/']").first
    number = int(re.search(r"/inspections/(\d+)/", link.get_attribute("href"))[1])
    link.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r"/inspections/\d+/edit"))
    page.locator("#field-day").fill("2026-11-12")
    page.locator("#field-starts").fill("10:15")
    page.locator("#field-ends").fill("11:15")
    page.get_by_role("button", name="Save").click()
    page.wait_for_url(re.compile(r"/calendar\?view=week&date=2026-11-12"))
    assert read(url, Inspection, number).starts_at == datetime(2026, 11, 12, 9, 15, tzinfo=UTC)
    assert "is now on" in page.locator("main").inner_text()


@pytest.mark.browser
def test_a_calendar_that_htmx_brings_is_drawn_again(open_filled):
    page = open_filled(WEEK)
    until(page, READY)
    page.evaluate("window.notReloaded = true")
    page.select_option("#calendar-location", "Workshop")
    until(page, "location.search.includes('location=Workshop')")
    until(page, "document.querySelectorAll('.calendar-frame').length === 1")
    until(page, "document.querySelector('#calendar [data-calendar-fallback]').hidden")
    assert page.evaluate("window.notReloaded")


@pytest.mark.browser
def test_without_javascript_the_agenda_moves_through_the_days(open_filled):
    page = open_filled(WEEK, javascript=False)
    assert page.locator("[data-calendar-fallback]").is_visible()
    page.get_by_role("link", name="Next").click()
    page.wait_for_url(re.compile(r"date=2026-11-04"))
    assert page.locator("[data-calendar-fallback] h3").count() >= 1


@pytest.mark.browser
def test_without_the_library_the_agenda_stays(open_filled):
    page = open_filled("/", bypass_csp=True)
    page.route("**/fullcalendar.js", lambda route: route.abort())
    page.goto(page.url.rstrip("/") + WEEK)
    page.wait_for_load_state("networkidle")
    assert page.locator("[data-calendar-fallback]").is_visible()


def planned_order(url):
    engine = create_database_engine(url)
    with Session(engine) as session:
        order = session.scalars(select(WorkOrder).where(WorkOrder.status == "planned").order_by(WorkOrder.id)).first()
    engine.dispose()
    return order


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize("end", ["2026-11-03T09:00:00Z", "2099-12-31T09:00:00Z", "nonsense"])
def test_a_drop_keeps_the_visits_length_whatever_end_it_sends(writable, end):
    client, url = writable
    visit = visits(url)[0]
    length = visit.ends_at - visit.starts_at
    form = {"event": f"visit-{visit.id}", "start": "2026-11-04T09:30:00Z", "end": end, "version": str(visit.version)}
    assert client.post("/calendar/move", data=form).status_code == 200
    saved = read(url, Inspection, visit.id)
    assert saved.ends_at - saved.starts_at == length


def test_only_a_planned_work_order_moves_on_the_calendar(writable):
    client, url = writable
    engine = create_database_engine(url)
    with Session(engine) as session:
        closed = session.scalars(select(WorkOrder).where(WorkOrder.status == "closed")).first()
    engine.dispose()
    answer = client.post(
        "/calendar/move", data={"event": f"order-{closed.id}", "start": "2026-11-09", "version": str(closed.version)}
    )
    assert answer.status_code == 409
    assert "Only planned work" in answer.json()["message"]
    assert read(url, WorkOrder, closed.id).planned_on == closed.planned_on


def test_a_work_order_of_many_months_is_in_the_feed_of_its_last_days(writable):
    client, url = writable
    order = planned_order(url)
    engine = create_database_engine(url)
    with engine.begin() as connection:
        connection.execute(
            WorkOrder.__table__.update()
            .where(WorkOrder.id == order.id)
            .values(planned_on=datetime(2026, 1, 5).date(), hours=Decimal(9999), crew=1)
        )
    engine.dispose()
    events = client.get("/calendar/events?start=2029-06-04&end=2029-06-11").json()
    assert f"order-{order.id}" in [event["id"] for event in events]


def test_the_way_back_reads_its_address_as_an_address(writable):
    client, url = writable
    visit = visits(url)[0]
    back = "/calendar?view=week&date=2026-10-28&location=Plant+room"
    html = client.get(f"/inspections/{visit.id}/edit", params={"back": back}).text
    assert 'name="back" value="/calendar?view=week&amp;date=2026-10-28&amp;location=Plant+room"' in html
    form = {"day": "2026-11-10", "starts": "10:00", "ends": "11:00", "version": str(visit.version), "back": back}
    location = client.post(f"/inspections/{visit.id}/edit", data=form, follow_redirects=False).headers["location"]
    assert "location=Plant+room" in location


@pytest.mark.rule("LANG-09")
def test_a_time_the_clocks_skip_is_refused_and_says_why(writable):
    client, url = writable
    visit = visits(url)[0]
    form = {"day": "2026-03-29", "starts": "02:30", "ends": "03:30", "version": str(visit.version), "back": WEEK}
    response = client.post(f"/inspections/{visit.id}/edit", data=form)
    assert response.status_code == 422
    assert "does not exist" in response.text
    assert read(url, Inspection, visit.id).starts_at == visit.starts_at


@pytest.mark.rule("LANG-09")
def test_a_time_that_happens_twice_is_its_first_and_the_end_comes_after_it_in_utc(writable):
    client, url = writable
    visit = visits(url)[0]
    form = {"day": "2026-10-25", "starts": "02:30", "ends": "02:45", "version": str(visit.version), "back": WEEK}
    assert client.post(f"/inspections/{visit.id}/edit", data=form, follow_redirects=False).status_code == 303
    saved = read(url, Inspection, visit.id)
    assert saved.starts_at == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert saved.ends_at == datetime(2026, 10, 25, 0, 45, tzinfo=UTC)


@pytest.mark.browser
def test_a_refusal_that_is_not_json_says_the_calendars_own_words(madrid):
    """A short visit, as the drag above takes: the first one of the week could be long or late, and two slots down
    from it miss the grid, so nothing was dropped and nothing refused, one run in three."""
    context, base, url = madrid
    visit = next(
        row
        for row in visits(url)
        if row.starts_at >= datetime(2026, 10, 26, tzinfo=UTC) and row.ends_at - row.starts_at <= timedelta(hours=3)
    )
    week = visit.starts_at.date() - timedelta(days=visit.starts_at.weekday())
    page = context.new_page()
    page.route(
        "**/calendar/move", lambda route: route.fulfill(status=500, body="<html>Oops</html>", content_type="text/html")
    )
    page.goto(f"{base}/calendar?view=week&date={week.isoformat()}")
    until(page, READY)
    event = page.locator(f"a.calendar-event[href^='/inspections/{visit.id}/']")
    box = event.bounding_box()
    slot = page.locator(".calendar-frame [data-time='09:00:00']").first.bounding_box()["height"]
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 6)
    page.mouse.down()
    for step in range(1, 11):
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 6 + slot * 2 * step / 10)
        page.wait_for_timeout(30)
    page.mouse.up()
    until(page, "document.querySelector('#announcements').textContent.includes('It is back where it was')")
    assert "JSON" not in page.locator("#announcements").text_content()
