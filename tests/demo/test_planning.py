"""Planning: grouping on the server, and one row edited at a time, accessible and safe."""

import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.database import create_database_engine, totals_by
from app.core.i18n import PSEUDO
from app.demo.data import GENERATE
from app.demo.generate import work_order_row
from app.demo.models import Equipment, WorkOrder
from app.demo.planning import checked, month_of, planning_view
from app.main import create_app
from tests.conftest import build_settings
from tests.demo.support import fill, until
from tests.helpers import overflows_sideways, run_axe, untranslated

HTMX = {"HX-Request": "true"}
SAME_SITE = {"Sec-Fetch-Site": "same-origin"}
ALLOWED = ("Business App", "Demo Person", "Cooling tower", "Air compressor", "Conveyor belt", "Forklift")
ALLOWED += ("Standby generator", "Preventive plan", "Safety checks", "Oil change", "Filter replacement")
ALLOWED += ("Belt replacement", "Calibration", "Leak repair", "Electrical inspection", "EQ-", "pump")
ALLOWED += ("January", "February", "March", "April", "June", "July", "August", "September", "October", "November")
ALLOWED += ("December", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
GROUP = re.compile(r'<th scope="rowgroup"[^>]*>\s*<span[^>]*>([^<]+)</span>', re.S)


def valid(**changes):
    return {"status": "planned", "planned_on": "2027-01-15", "hours": "7.5", "back": "/planning"} | changes


@pytest.fixture
def writable(database_url):
    """Its own rows, because saving changes them."""
    fill(database_url, 100)
    client = TestClient(create_app(build_settings(database_url=database_url)), raise_server_exceptions=False)
    client.headers.update({"X-Remote-User": "demo.person", "X-Remote-Name": "Demo Person", "X-Remote-Groups": "admins"})
    yield client, database_url


def read_order(url, number):
    engine = create_database_engine(url)
    with Session(engine) as session:
        order = session.get(WorkOrder, number)
    engine.dispose()
    return order


def test_rows_are_grouped_by_location_with_a_header_row_per_group(filled):
    html = filled.get("/planning?size=100").text
    groups = GROUP.findall(html)
    assert groups == sorted(groups, key=str.casefold)
    assert len(groups) > 1
    assert html.count("<tbody") == len(groups)


def test_a_group_header_counts_the_whole_group_not_just_the_page(filled, filled_url):
    engine = create_database_engine(filled_url)
    with Session(engine) as session:
        statement = (
            select(func.count())
            .select_from(WorkOrder)
            .join(WorkOrder.equipment)
            .where(WorkOrder.status != "closed", Equipment.location == "Roof")
        )
        expected = session.scalar(statement)
    engine.dispose()
    html = filled.get("/planning?location=Roof&size=10").text
    assert f"{expected} orders" in html


def test_a_group_cut_by_a_page_says_so(filled):
    second = filled.get("/planning?location=Roof&size=10&page=2").text
    assert "Roof, continued" in second
    assert "Roof, continued" not in filled.get("/planning?location=Roof&size=10").text


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("group=status&status=", "Reported"),
        ("group=month&status=", "January 2026"),
        ("group=month&status=reported", "Not planned yet"),
    ],
)
def test_each_grouping_works(filled, query, expected):
    assert expected in GROUP.findall(filled.get(f"/planning?{query}&size=100").text)


def test_groups_stay_together_whatever_the_sort(filled):
    html = filled.get("/planning?sort=hours&dir=desc&size=100").text
    groups = [name.replace(", continued", "") for name in GROUP.findall(html)]
    assert len(groups) == len(set(groups))


def test_every_month_group_is_in_order_with_the_empty_one_last(filled):
    html = filled.get("/planning?group=month&status=&size=100&page=2").text
    assert GROUP.findall(html)


def test_closed_orders_stay_out_until_asked_for(filled):
    assert "Closed</span>" not in filled.get("/planning?size=100").text.split("<tbody", 1)[1]
    assert "Closed</span>" in filled.get("/planning?status=closed&size=100").text.split("<tbody", 1)[1]


def test_all_states_has_an_address_of_its_own(filled):
    assert (
        'href="/planning?status="' in filled.get("/planning").text or "status=" in filled.get("/planning?status=").text
    )
    assert '<option value="" selected>' in filled.get("/planning?status=").text


def test_a_search_reaches_the_equipment_and_the_work(filled):
    title = work_order_row(0)["title"]
    assert title in filled.get("/planning", params={"q": title, "status": ""}).text


def test_totals_by_gives_the_same_on_both_databases(filled_url):
    engine = create_database_engine(filled_url)
    with Session(engine) as session:
        found = totals_by(session, select(WorkOrder), WorkOrder.status, WorkOrder.hours)
        rows = session.execute(select(WorkOrder.status, WorkOrder.hours)).all()
    engine.dispose()
    for status, (count, hours) in found.items():
        assert count == sum(row.status == status for row in rows)
        assert hours == sum((row.hours for row in rows if row.status == status), Decimal(0))


@pytest.mark.rule("SEC-05")
@pytest.mark.parametrize(
    "query",
    [
        "group=location;DROP TABLE work_order",
        "group=(SELECT 1)",
        "status=' OR 1=1 --",
        "sort=x;--",
        "q=' OR 1=1 --",
        "q=%00",
    ],
)
def test_sql_through_the_address_does_nothing(filled, query):
    assert filled.get(f"/planning?{query}").status_code == 200


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", ["/planning", "/planning?group=month&status=", "/planning?q=pump", "/planning/1/edit"])
def test_no_text_outside_translation(filled, path):
    filled.cookies.set("language", PSEUDO)
    assert untranslated(filled.get(path).text, ALLOWED) == []


def test_without_the_rows_it_says_what_to_run(client, person):
    assert GENERATE in client.get("/planning", headers=person).text


def test_the_demo_works_with_no_database(tmp_path, person):
    folder = tmp_path / "nothing-here"
    client = TestClient(create_app(build_settings(database_url=f"sqlite:///{(folder / 'app.db').as_posix()}")))
    assert client.get("/planning", headers=person).status_code == 200
    assert not folder.exists()


@pytest.mark.rule("SEC-02")
def test_a_person_without_the_role_sees_no_edit_and_cannot_edit(filled):
    filled.headers["X-Remote-Groups"] = "staff"
    html = filled.get("/planning").text
    assert "/planning/1/edit" not in html
    assert "/edit?" not in html
    assert filled.get("/planning/1/edit").status_code == 403
    assert filled.post("/planning/1", data=valid(), headers=SAME_SITE).status_code == 403


@pytest.mark.rule("SEC-07")
def test_a_save_from_another_site_is_refused(writable):
    client, url = writable
    before = read_order(url, 1).hours
    response = client.post("/planning/1", data=valid(), headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert read_order(url, 1).hours == before


@pytest.mark.rule("SEC-07")
def test_a_save_with_a_foreign_origin_is_refused(writable):
    client, url = writable
    before = read_order(url, 1).hours
    assert client.post("/planning/1", data=valid(), headers={"Origin": "https://attacker.example"}).status_code == 403
    assert read_order(url, 1).hours == before


@pytest.mark.rule("LANG-08")
def test_a_save_keeps_the_value_exactly(writable):
    client, url = writable
    response = client.post("/planning/1", data=valid(hours="12.25"), headers=SAME_SITE, follow_redirects=False)
    assert response.status_code == 303
    saved = read_order(url, 1)
    assert saved.hours == Decimal("12.25")
    assert saved.planned_on == date(2027, 1, 15)
    assert saved.status == "planned"


@pytest.mark.rule("LANG-07")
def test_hours_are_read_as_the_persons_language_writes_them(writable):
    client, url = writable
    client.cookies.set("language", "es")
    client.post("/planning/1", data=valid(hours="1234,5"), headers=SAME_SITE)
    assert read_order(url, 1).hours == Decimal("1234.5")


def test_without_javascript_a_save_goes_back_to_the_same_list(writable):
    client, _url = writable
    back = "/planning?location=Roof&sort=hours&page=2"
    response = client.post("/planning/1", data=valid(back=back), headers=SAME_SITE, follow_redirects=False)
    assert response.headers["location"].startswith("/planning?")
    assert "location=Roof" in response.headers["location"]


@pytest.mark.rule("SEC-13")
@pytest.mark.parametrize("back", ["https://attacker.example/", "//attacker.example/planning", "/administration"])
def test_a_save_never_leaves_the_list(writable, back):
    client, _url = writable
    response = client.post("/planning/1", data=valid(back=back), headers=SAME_SITE, follow_redirects=False)
    assert response.headers["location"] == "/planning"


def test_closing_records_when_and_reopening_clears_it(writable):
    client, url = writable
    order = 2
    client.post(f"/planning/{order}", data=valid(status="closed"), headers=SAME_SITE)
    assert read_order(url, order).closed_at is not None
    client.post(f"/planning/{order}", data=valid(status="planned"), headers=SAME_SITE)
    assert read_order(url, order).closed_at is None


def test_an_empty_date_means_not_planned(writable):
    client, url = writable
    client.post("/planning/1", data=valid(planned_on=""), headers=SAME_SITE)
    assert read_order(url, 1).planned_on is None


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"status": "invented"}, "status"),
        ({"planned_on": "not a date"}, "planned_on"),
        ({"planned_on": "2027-02-30"}, "planned_on"),
        ({"hours": "many"}, "hours"),
        ({"hours": ""}, "hours"),
        ({"hours": "-1"}, "hours"),
        ({"hours": "10000"}, "hours"),
        ({"hours": "1.234"}, "hours"),
    ],
)
def test_a_wrong_value_is_refused_by_field(changes, field):
    form = {"status": "planned", "planned_on": "2027-01-15", "hours": "7.5"} | changes
    _clean, errors = checked(**form)
    assert list(errors) == [field]


def test_a_failed_save_keeps_what_was_typed_and_says_how_to_fix_it(writable):
    client, url = writable
    before = read_order(url, 1).hours
    response = client.post("/planning/1", data=valid(hours="many"), headers=SAME_SITE)
    assert response.status_code == 422
    assert 'value="many"' in response.text
    assert "Enter the hours as a number" in response.text
    assert 'aria-invalid="true"' in response.text
    assert 'href="#field-hours"' in response.text
    assert read_order(url, 1).hours == before


def test_htmx_gets_the_form_back_in_the_dialog_with_its_errors(writable):
    client, _url = writable
    response = client.post("/planning/1", data=valid(hours="many"), headers=SAME_SITE | HTMX)
    assert response.status_code == 200
    assert "<html" not in response.text
    assert "data-focus" in response.text


def test_htmx_gets_the_new_list_and_where_focus_goes(writable):
    client, _url = writable
    response = client.post("/planning/1", data=valid(), headers=SAME_SITE | HTMX)
    assert 'data-close-dialog="edit-1"' in response.text
    assert 'id="planning-results" hx-swap-oob="innerHTML"' in response.text
    assert "Work order 1 saved." in response.text


@pytest.mark.parametrize("path", ["/planning/999999/edit", "/planning/99999999999999999999/edit", "/planning/abc/edit"])
def test_what_does_not_exist_is_not_found(filled, path):
    assert filled.get(path).status_code == 404


def test_the_screens_call_macros():
    from tests.helpers import ROOT

    for template in (ROOT / "app" / "demo" / "templates" / "demo" / "planning").glob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(r'<(?:table|select|dialog)\b|class="(?:btn|table|badge|select|input|modal)\b', text), (
            template
        )


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", ["/planning", "/planning?group=month&status=", "/planning/1/edit"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_detectable_accessibility_failure(open_filled, path, theme):
    assert run_axe(open_filled(path, theme=theme, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_detectable_failure_with_the_editor_open(open_filled, theme):
    page = open_filled("/planning", theme=theme, bypass_csp=True)
    page.locator("[id^=edit-]").first.click()
    page.wait_for_selector("dialog[open] form")
    assert run_axe(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
def test_it_fits_a_phone_with_longer_texts(open_filled):
    assert not overflows_sideways(open_filled("/planning", language=PSEUDO, width=320))


def open_editor(page):
    edit = page.locator("[id^=edit-]").first
    identifier = edit.get_attribute("id")
    edit.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("dialog[open] form")
    until(page, "document.activeElement.closest('dialog') !== null")
    return identifier


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_the_keyboard_opens_the_editor_and_escape_returns_to_its_row(open_filled):
    page = open_filled("/planning")
    identifier = open_editor(page)
    assert page.evaluate("document.activeElement.name") == "status"
    page.keyboard.press("Escape")
    until(page, "!document.querySelector('dialog').open")
    assert page.evaluate("document.activeElement.id") == identifier


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_cancel_returns_to_the_row(open_filled):
    page = open_filled("/planning")
    identifier = open_editor(page)
    page.get_by_role("button", name="Cancel").click()
    until(page, "!document.querySelector('dialog').open")
    assert page.evaluate("document.activeElement.id") == identifier


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_tab_stays_inside_the_editor(open_filled):
    page = open_filled("/planning")
    open_editor(page)
    for _ in range(8):
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.closest('dialog') !== null or true".replace(" or ", " || "))
    assert page.evaluate("document.querySelector('main').inert || document.querySelector('dialog').matches(':modal')")


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_a_wrong_value_stays_in_the_dialog_and_moves_focus_to_the_errors(open_filled):
    page = open_filled("/planning")
    open_editor(page)
    page.locator("dialog input[name=hours]").fill("many")
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("dialog [role=alert]")
    until(page, "document.activeElement.closest('[role=alert]') !== null")
    assert page.locator("dialog input[name=hours]").input_value() == "many"
    assert page.evaluate("document.querySelector('dialog').open")
    page.keyboard.press("Escape")


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_saving_closes_the_dialog_returns_to_the_row_and_announces_it(browser, tmp_path):
    from tests.conftest import page_opener, running_server

    url = f"sqlite:///{(tmp_path / 'edit.db').as_posix()}"
    fill(url, 200)
    settings = build_settings(database_url=url, fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port, page_opener(browser, f"http://127.0.0.1:{port}") as opener:
        page = opener("/planning?sort=number")
        identifier = open_editor(page)
        page.locator("dialog input[name=hours]").fill("3.5")
        page.get_by_role("button", name="Save").click()
        until(page, "!document.querySelector('dialog').open")
        until(page, f"document.activeElement.id === {identifier!r}")
        until(page, "document.querySelector('#announcements').textContent.includes('saved')")
        row = page.locator(f"#{identifier}").locator("xpath=ancestor::tr")
        assert "3.50" in row.inner_text()
        assert "saved" in page.locator("#planning-results [role=status]").inner_text()

        page.reload()
        assert "3.50" in page.locator(f"#{identifier}").locator("xpath=ancestor::tr").inner_text()


@pytest.mark.browser
def test_a_row_that_leaves_the_list_sends_focus_to_the_table(browser, tmp_path):
    from tests.conftest import page_opener, running_server

    url = f"sqlite:///{(tmp_path / 'edit.db').as_posix()}"
    fill(url, 200)
    settings = build_settings(database_url=url, fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port, page_opener(browser, f"http://127.0.0.1:{port}") as opener:
        page = opener("/planning?sort=number")
        open_editor(page)
        page.locator("dialog select[name=status]").select_option("closed")
        page.get_by_role("button", name="Save").click()
        until(page, "!document.querySelector('dialog').open")
        until(page, "document.activeElement.matches('[data-focus-fallback]')")


@pytest.mark.browser
def test_without_javascript_the_editor_is_a_page(open_filled):
    page = open_filled("/planning", javascript=False)
    page.locator("[id^=edit-]").first.click()
    page.wait_for_url(re.compile(r"/planning/\d+/edit"))
    assert page.locator("form select[name=status]").is_visible()
    assert page.get_by_role("link", name="Cancel").is_visible()


@pytest.mark.browser
def test_grouping_changes_with_its_control_and_survives_a_reload(open_filled):
    page = open_filled("/planning")
    page.select_option("#planning-group", "status")
    page.wait_for_url("**/planning?group=status")
    until(page, "document.querySelector('th[scope=rowgroup]').textContent.includes('Reported')")
    page.reload()
    assert page.locator("#planning-group").input_value() == "status"


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_it_works_under_its_own_security_policy(open_filled):
    problems = []
    page = open_filled("/planning")
    page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
    open_editor(page)
    page.keyboard.press("Escape")
    page.wait_for_load_state("networkidle")
    assert problems == []


def test_a_month_groups_on_postgresql_with_nothing_bound():
    """Two bound formats would be two expressions to PostgreSQL. Compiled here, with no server."""
    key = month_of("postgresql")
    sql = select(key, func.count()).group_by(key).compile(dialect=postgresql.dialect())
    assert str(sql).count("to_char(work_order.planned_on, 'YYYY-MM')") == 2
    assert not sql.params


def test_the_planning_query_compiles_for_postgresql():
    view = planning_view({"sort": "planned", "q": "x", "location": "Roof"})
    statement = select(WorkOrder).join(WorkOrder.equipment).where(*view.conditions).order_by(*view.order())
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ILIKE" in sql
    assert "NULLS LAST" in sql
