"""The work order form: every field, checked at the edge, in three languages, with and without JavaScript."""

import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import i18n
from app.core.database import create_database_engine, migrate
from app.core.i18n import PSEUDO
from app.demo import work_orders
from app.demo.generate import work_order_row
from app.demo.models import LAST_MOMENT, WorkOrder, WorkOrderFile
from app.main import create_app
from tests.conftest import build_settings, page_opener, running_server
from tests.demo.support import fill, until
from tests.helpers import overflows_sideways, run_axe, untranslated

HTMX = {"HX-Request": "true"}
SAME_SITE = {"Sec-Fetch-Site": "same-origin"}
ALLOWED = ("Business App", "Demo Person", "EQ-", "PDF", "PNG", "JPEG", "MB")
ALLOWED += tuple({work_order_row(position)["title"] for position in range(50)})
ALLOWED += ("Air compressor", "Conveyor belt", "Cooling tower", "Forklift", "Standby generator", "pump")
SCREENS = ("/work-orders/new", "/work-orders/1/edit", "/work-orders/1/delete")


def valid(**changes):
    return {
        "title": "Replace the belt",
        "equipment": "EQ-000001",
        "description": "It slips under load.\nSeen on Monday.",
        "fault": "belt_slip",
        "status": "planned",
        "priority": "high",
        "planned_on": "2027-01-15",
        "hours": "7.5",
        "crew": "2",
        "cost": "120.50",
        "stop_needed": "yes",
        "back": "/planning",
        "version": "1",
    } | changes


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
        if order:
            order.equipment  # noqa: B018  # loaded while the session is open
    engine.dispose()
    return order


def count_orders(url):
    engine = create_database_engine(url)
    with Session(engine) as session:
        number = session.scalar(select(func.count()).select_from(WorkOrder))
    engine.dispose()
    return number


def post(client, address, form, **options):
    return client.post(address, data=form, headers=SAME_SITE | options.pop("headers", {}), **options)


# Reaching it


@pytest.mark.rule("SEC-02")
@pytest.mark.parametrize("path", SCREENS)
def test_a_viewer_gets_403_on_each_screen(filled, path):
    filled.headers["X-Remote-Groups"] = "staff"
    assert filled.get(path).status_code == 403


@pytest.mark.rule("SEC-02")
@pytest.mark.parametrize("address", ["/work-orders", "/work-orders/1", "/work-orders/1/delete"])
def test_a_viewer_cannot_write_either(filled, address):
    filled.headers["X-Remote-Groups"] = "staff"
    assert filled.post(address, data=valid(), headers=SAME_SITE).status_code == 403


@pytest.mark.rule("SEC-02")
@pytest.mark.parametrize("path", ["/planning", "/equipment/1?tab=orders", "/equipment/2"])
def test_a_viewer_sees_no_link_to_it(filled, path):
    filled.headers["X-Remote-Groups"] = "staff"
    assert "/work-orders" not in filled.get(path).text


def test_planning_leads_to_a_new_order_and_to_each_order(filled):
    html = filled.get("/planning?location=Roof").text
    assert re.search(r'href="/work-orders/new\?back=[^"]*location%3DRoof', html)
    assert re.search(r'href="/work-orders/\d+/edit\?back=', html)


def test_the_editor_of_a_row_leads_to_all_its_fields(filled):
    assert 'href="/work-orders/1/edit?back=' in filled.get("/planning/1/edit").text


def test_the_equipment_detail_leads_to_a_new_order_for_it(filled):
    html = filled.get("/equipment/1?tab=orders").text
    assert 'href="/work-orders/new?equipment=1&amp;back=' in html
    assert re.search(r'href="/work-orders/\d+/edit\?back=', html)


def test_a_new_order_from_the_equipment_knows_its_code(filled):
    assert 'value="EQ-000001"' in filled.get("/work-orders/new?equipment=1").text


@pytest.mark.parametrize("value", ["x", "-1", "99999999999999999999", "999999", "9" * 5000])
def test_an_equipment_that_is_no_equipment_leaves_the_field_empty(filled, value):
    response = filled.get("/work-orders/new", params={"equipment": value})
    assert response.status_code == 200
    assert 'name="equipment" type="text" value=""' in response.text


@pytest.mark.parametrize("path", ["/work-orders/999999/edit", "/work-orders/99999999999999999999/edit"])
def test_what_does_not_exist_is_not_found(filled, path):
    assert filled.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/work-orders/1/files/1", "/work-orders/1/files/1/delete"])
def test_without_the_rows_a_file_is_simply_not_there(client, person, path):
    assert client.get(path, headers=person).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/work-orders/{0}/edit"),
        ("POST", "/work-orders/{0}"),
        ("GET", "/work-orders/{0}/delete"),
        ("POST", "/work-orders/{0}/delete"),
        ("GET", "/work-orders/1/files/{0}"),
        ("GET", "/work-orders/{0}/files/1/delete"),
        ("POST", "/work-orders/1/files/{0}/delete"),
        ("GET", "/planning/{0}/edit"),
        ("POST", "/planning/{0}"),
        ("GET", "/equipment/{0}"),
    ],
)
def test_an_id_of_thousands_of_digits_is_not_found_on_every_route(filled, method, path):
    assert filled.request(method, path.format("1" * 5000), headers=SAME_SITE).status_code == 404


def test_without_the_rows_it_says_what_to_run(client, person):
    response = client.get("/work-orders/new", headers=person, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/planning")


# Saving


def test_a_new_order_keeps_every_field_exactly(writable):
    client, url = writable
    before = count_orders(url)
    response = post(client, "/work-orders", valid(), follow_redirects=False)
    assert response.status_code == 303
    assert count_orders(url) == before + 1
    number = int(re.search(r"saved=(\d+)", response.headers["location"])[1])
    order = read_order(url, number)
    assert order.title == "Replace the belt"
    assert order.equipment.code == "EQ-000001"
    assert order.description == "It slips under load.\nSeen on Monday."
    assert order.fault == "belt_slip"
    assert order.status == "planned"
    assert order.priority == "high"
    assert order.planned_on == date(2027, 1, 15)
    assert order.hours == Decimal("7.5")
    assert order.crew == 2
    assert order.cost == Decimal("120.50")
    assert order.stop_needed is True
    assert order.opened_at == LAST_MOMENT
    assert order.closed_at is None


def test_an_edit_changes_the_row_and_goes_back(writable):
    client, url = writable
    response = post(client, "/work-orders/1", valid(status="closed"), follow_redirects=False)
    assert response.headers["location"] == "/planning?saved=1"
    order = read_order(url, 1)
    assert order.title == "Replace the belt"
    assert order.closed_at is not None


def test_a_box_left_empty_is_not_ticked_and_a_fault_can_be_unknown(writable):
    client, url = writable
    post(client, "/work-orders/1", valid(fault="", stop_needed=""))
    order = read_order(url, 1)
    assert order.fault is None
    assert order.stop_needed is False


@pytest.mark.rule("LANG-07")
@pytest.mark.parametrize("language", ["es", "ca"])
def test_numbers_are_read_as_the_persons_language_writes_them(writable, language):
    client, url = writable
    client.cookies.set("language", language)
    post(client, "/work-orders/1", valid(hours="1234,5", cost="12.500,25"))
    order = read_order(url, 1)
    assert order.hours == Decimal("1234.5")
    assert order.cost == Decimal("12500.25")


@pytest.mark.rule("LANG-08")
@pytest.mark.parametrize("language", ["en", "es", "ca"])
def test_saving_a_form_nobody_changed_keeps_every_decimal(writable, language):
    """Generated costs have twenty decimals: a form that showed two would round them on every save."""
    client, url = writable
    client.cookies.set("language", language)
    before = read_order(url, 1).cost
    html = client.get("/work-orders/1/edit").text
    cost = re.search(r'name="cost" type="text" value="([^"]*)"', html)[1]
    hours = re.search(r'name="hours" type="text" value="([^"]*)"', html)[1]
    planned = read_order(url, 1).planned_on
    form = valid(cost=cost, hours=hours, planned_on=planned.isoformat() if planned else "")
    assert post(client, "/work-orders/1", form, follow_redirects=False).status_code == 303
    assert read_order(url, 1).cost == before


def test_htmx_goes_to_the_whole_page_after_a_save(writable):
    client, _url = writable
    response = post(client, "/work-orders/1", valid(), headers=HTMX)
    assert response.status_code == 200
    assert response.headers["hx-redirect"] == "/planning?saved=1"


@pytest.mark.parametrize(
    ("back", "where"),
    [
        ("/planning?status=&sort=hours", "/planning?status=&sort=hours&saved=1"),
        ("/equipment/7?tab=orders", "/equipment/7?tab=orders&saved=1"),
        ("https://attacker.example/", "/planning?saved=1"),
        ("//attacker.example/planning", "/planning?saved=1"),
        ("/administration", "/planning?saved=1"),
        ("/equipment/99999999999999999999", "/planning?saved=1"),
        ("//[", "/planning?saved=1"),
    ],
)
@pytest.mark.rule("SEC-13")
def test_a_save_goes_back_where_it_came_from_and_never_elsewhere(writable, back, where):
    client, _url = writable
    response = post(client, "/work-orders/1", valid(back=back), follow_redirects=False)
    assert response.headers["location"] == where


def test_going_back_keeps_the_equipment_list_a_person_came_from(writable):
    client, _url = writable
    back = "/equipment/7?tab=orders&back=%2Fequipment%3Fstatus%3Dstopped"
    response = post(client, "/work-orders/1", valid(back=back), follow_redirects=False)
    assert response.headers["location"] == f"{back}&saved=1"


def test_the_equipment_page_says_what_was_saved(writable):
    client, _url = writable
    assert "Work order 1 saved." in client.get("/equipment/1?tab=orders&saved=1").text
    assert "saved." not in client.get("/equipment/1?tab=orders&saved=x").text


@pytest.mark.rule("SEC-07")
def test_a_save_from_another_site_is_refused(writable):
    client, url = writable
    before = read_order(url, 1).title
    assert client.post("/work-orders/1", data=valid(), headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/work-orders/1/delete", data={}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert read_order(url, 1).title == before


# A failed save


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"title": ""}, "title"),
        ({"title": "x" * 81}, "title"),
        ({"title": "a\x00b"}, "title"),
        ({"equipment": ""}, "equipment"),
        ({"equipment": "EQ-999999"}, "equipment"),
        ({"equipment": "' OR 1=1 --"}, "equipment"),
        ({"description": "x" * 2001}, "description"),
        ({"description": "a\x00b"}, "description"),
        ({"fault": "invented"}, "fault"),
        ({"status": "invented"}, "status"),
        ({"priority": "invented"}, "priority"),
        ({"priority": ""}, "priority"),
        ({"planned_on": "not a date"}, "planned_on"),
        ({"planned_on": "incomplete"}, "planned_on"),
        ({"planned_on": "1999-12-31"}, "planned_on"),
        ({"hours": "many"}, "hours"),
        ({"hours": "-1"}, "hours"),
        ({"hours": "1.234"}, "hours"),
        ({"crew": "1.5"}, "crew"),
        ({"crew": "0"}, "crew"),
        ({"crew": "51"}, "crew"),
        ({"cost": "1e3"}, "cost"),
        ({"cost": "-1"}, "cost"),
        ({"cost": "9999999999"}, "cost"),
        ({"stop_needed": "maybe"}, "stop_needed"),
    ],
)
def test_every_field_is_checked_and_nothing_is_saved(writable, changes, field):
    client, url = writable
    before = read_order(url, 1).title
    number = count_orders(url)
    response = post(client, "/work-orders/1", valid(**changes))
    assert response.status_code == 422
    assert f'href="#field-{field.replace("_", "-")}"' in response.text
    assert read_order(url, 1).title == before
    assert post(client, "/work-orders", valid(**changes)).status_code == 422
    assert count_orders(url) == number


@pytest.mark.rule("USE-03")
def test_a_failed_save_keeps_what_was_typed(writable):
    client, _url = writable
    typed = valid(title="<b>Mine</b>", hours="many", description="Line one\nLine two", priority="low", stop_needed="")
    html = post(client, "/work-orders/1", typed).text
    assert 'value="&lt;b&gt;Mine&lt;/b&gt;"' in html
    assert 'value="many"' in html
    assert ">Line one\nLine two</textarea>" in html
    assert re.search(r'value="low" checked', html)
    assert 'value="belt_slip" selected' in html
    assert 'name="stop_needed" type="checkbox" value="yes" aria' not in html


@pytest.mark.rule("A11Y-08")
def test_errors_are_summed_up_in_the_order_of_the_page_each_with_its_link(writable):
    client, _url = writable
    html = post(client, "/work-orders", valid(hours="many", title="", crew="0")).text
    links = re.findall(r'<li><a class="[^"]*" href="#(field-[a-z-]+)">', html)
    assert links == ["field-title", "field-hours", "field-crew"]
    assert 'aria-invalid="true"' in html
    assert "Check what you entered" in html
    assert "Enter what has to be done." in html
    assert html.index('role="alert"') < html.index('id="field-title"')


def test_htmx_gets_the_form_alone_with_its_errors(writable):
    client, _url = writable
    response = post(client, "/work-orders/1", valid(hours="many"), headers=HTMX)
    assert response.status_code == 200
    assert "<html" not in response.text
    assert "data-focus" in response.text


def test_the_summary_and_the_page_keep_one_order_with_every_field_wrong(uploads):
    client, _url, _folder = uploads
    wrong = {
        "title": "",
        "equipment": "",
        "fault": "invented",
        "description": "a\x00b",
        "status": "invented",
        "planned_on": "not a date",
        "hours": "many",
        "crew": "0",
        "cost": "many",
        "priority": "invented",
        "stop_needed": "maybe",
    }
    html = attach(client, b"", "report.pdf", **wrong).text
    linked = re.findall(r'<li><a class="[^"]*" href="#(field-[a-z-]+)">', html)
    form = html.split("</ul>", 1)[1]
    found = re.findall(r'\sid="(field-[a-z-]+)"', form)
    on_the_page = [name for name in found if not name.endswith(("-hint", "-error"))]
    assert len(linked) == 12
    assert linked == on_the_page


@pytest.mark.parametrize("language", ["es", "ca"])
def test_errors_come_in_the_persons_language(writable, language):
    client, _url = writable
    client.cookies.set("language", language)
    html = post(client, "/work-orders", valid(title="", hours="many")).text
    assert "Enter what has to be done." not in html
    assert "Enter the hours as a number" not in html


# Deleting


def test_the_confirmation_is_a_page_that_names_what_will_be_lost(filled):
    html = filled.get("/work-orders/1/delete?back=/planning").text
    assert "<html" in html
    assert "cannot be undone" in html
    assert f"<li>{work_order_row(0)['title']}, on " in html
    assert "<li>Hours recorded: " in html
    assert 'method="post" action="/work-orders/1/delete"' in html


def test_htmx_gets_it_for_the_dialog(filled):
    html = filled.get("/work-orders/1/delete", headers=HTMX).text
    assert "<html" not in html
    assert 'id="confirm-title"' in html
    assert "autofocus" in html


def test_deleting_removes_the_row_and_says_so(writable):
    client, url = writable
    response = post(
        client, "/work-orders/1/delete", {"back": "/planning?sort=hours", "version": "1"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/planning?sort=hours&deleted=1"
    assert read_order(url, 1) is None
    assert "Work order 1 deleted." in client.get(response.headers["location"]).text


@pytest.mark.parametrize("value", ["x", "1", "99999999999999999999"])
def test_a_deleted_message_needs_a_row_that_really_went(filled, value):
    assert " deleted." not in filled.get("/planning", params={"deleted": value}).text


def test_deleting_what_has_gone_is_not_found(writable):
    client, _url = writable
    post(client, "/work-orders/1/delete", {"back": "/planning", "version": "1"})
    assert post(client, "/work-orders/1/delete", {"back": "/planning", "version": "1"}).status_code == 404


# What the tests cannot read in a page's text


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", SCREENS)
def test_no_text_outside_translation(filled, path):
    filled.cookies.set("language", PSEUDO)
    assert untranslated(filled.get(path).text, ALLOWED) == []


def test_the_screens_call_macros():
    from tests.helpers import ROOT

    for template in (ROOT / "app" / "demo" / "templates" / "demo" / "work_orders").glob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(
            r'<(?:table|select|dialog|input(?! type="hidden"))\b|class="(?:btn|input|select)\b', text
        ), template


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", SCREENS)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 390])
def test_no_detectable_accessibility_failure(open_filled, path, theme, width):
    assert run_axe(open_filled(path, theme=theme, width=width, bypass_csp=True)) == []


@pytest.fixture
def own_rows(browser, tmp_path):
    """A server on rows of its own, for what writes. Without JavaScript it is the same server."""
    url = f"sqlite:///{(tmp_path / 'orders.db').as_posix()}"
    fill(url, 200)
    settings = build_settings(database_url=url, fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port, page_opener(browser, f"http://127.0.0.1:{port}") as opener:
        yield opener


def fill_in(page):
    page.locator("#field-title").fill("Replace the belt")
    page.locator("#field-equipment").fill("EQ-000001")
    page.locator("#field-description").fill("It slips.")


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 390])
def test_a_form_with_errors_passes_the_scan(own_rows, theme, width):
    page = own_rows("/work-orders/new", theme=theme, width=width, bypass_csp=True)
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("#work-order [role=alert]")
    assert run_axe(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 390])
def test_the_open_delete_dialog_passes_the_scan(own_rows, theme, width):
    page = own_rows("/work-orders/1/edit", theme=theme, width=width, bypass_csp=True)
    page.get_by_role("link", name="Delete").click()
    page.wait_for_selector("dialog#confirm[open]")
    assert run_axe(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
@pytest.mark.parametrize("path", SCREENS)
def test_it_fits_a_phone_with_longer_texts(open_filled, path):
    assert not overflows_sideways(open_filled(path, language=PSEUDO, width=320))


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_with_htmx_a_failed_save_stays_keeps_what_was_typed_and_moves_focus_to_the_errors(own_rows):
    page = own_rows("/work-orders/new")
    page.locator("#field-hours").fill("many")
    page.locator("#field-description").fill("Mine")
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("#work-order [role=alert]")
    until(page, "document.activeElement.closest('[role=alert]') !== null")
    assert page.locator("#field-hours").input_value() == "many"
    assert page.locator("#field-description").input_value() == "Mine"
    assert page.url.endswith("/work-orders/new")
    assert page.locator("#field-fault").get_attribute("role") == "combobox"


@pytest.mark.browser
def test_a_link_in_the_summary_lands_on_its_field(own_rows):
    page = own_rows("/work-orders/new")
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("#work-order [role=alert]")
    page.locator("#work-order [role=alert] a").first.click()
    until(page, "document.activeElement.id === 'field-title'")


@pytest.mark.browser
def test_with_htmx_a_save_goes_to_the_list_and_says_so(own_rows):
    page = own_rows("/work-orders/new?back=%2Fplanning")
    fill_in(page)
    page.locator("#field-fault").fill("belt")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.get_by_role("radio", name="High").check()
    page.get_by_role("button", name="Save").click()
    page.wait_for_url("**/planning?saved=*")
    assert page.get_by_text(" saved.").first.is_visible()
    number = re.search(r"saved=(\d+)", page.url)[1]
    edit = own_rows(f"/work-orders/{number}/edit")
    assert edit.locator("#field-fault").input_value() == "Belt slipping"
    assert edit.get_by_role("radio", name="High").is_checked()


def box_and_select(page):
    return page.evaluate(
        """[document.querySelector('#field-fault').value, document.querySelector('select[name=fault]').value]"""
    )


@pytest.mark.browser
def test_text_left_in_the_box_then_escape_and_enter_is_refused_by_the_server_and_stays(own_rows):
    page = own_rows("/work-orders/1/edit")
    page.locator("#field-fault").fill("bearing")
    page.keyboard.press("Escape")
    assert box_and_select(page) == ["bearing", "bearing"]
    page.keyboard.press("Enter")
    page.wait_for_selector("#work-order [role=alert]")
    assert "Choose a fault from the list." in page.locator("#work-order [role=alert]").inner_text()
    assert box_and_select(page) == ["bearing", "bearing"]
    assert page.locator("#field-fault").get_attribute("aria-invalid") == "true"


@pytest.mark.browser
def test_escape_twice_with_a_value_chosen_then_enter_sends_an_empty_box(own_rows):
    page = own_rows("/work-orders/1/edit?back=%2Fplanning")
    page.locator("#field-fault").fill("bearing wear")
    page.keyboard.press("Tab")
    page.get_by_role("button", name="Save").click()
    page.wait_for_url("**/planning?saved=1")

    page = own_rows("/work-orders/1/edit?back=%2Fplanning")
    assert box_and_select(page) == ["Bearing wear", "bearing_wear"]
    page.locator("#field-fault").focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    assert box_and_select(page) == ["", ""]
    page.keyboard.press("Enter")
    page.wait_for_url("**/planning?saved=1")
    page = own_rows("/work-orders/1/edit")
    assert box_and_select(page) == ["", ""]


@pytest.mark.browser
def test_a_date_typed_halfway_is_refused_and_not_cleared_in_silence(own_rows):
    page = own_rows("/work-orders/1/edit")
    date_box = page.locator("#field-planned-on")
    date_box.fill("")
    date_box.focus()
    page.keyboard.type("03")
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("#work-order [role=alert]")
    assert "Enter a date" in page.locator("#work-order [role=alert]").inner_text()


@pytest.mark.browser
def test_without_javascript_every_step_works(own_rows):
    page = own_rows("/planning", javascript=False)
    page.get_by_role("link", name="New work order").click()
    page.wait_for_url(re.compile(r"/work-orders/new"))
    assert page.locator("select[name=fault]").is_visible()
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("#work-order [role=alert]")
    assert "Enter what has to be done." in page.locator("#work-order [role=alert]").inner_text()
    fill_in(page)
    page.locator("select[name=fault]").select_option("belt_slip")
    page.get_by_role("button", name="Save").click()
    page.wait_for_url("**/planning?saved=*")
    number = re.search(r"saved=(\d+)", page.url)[1]

    page.goto(page.url.split("/planning")[0] + f"/work-orders/{number}/edit?back=%2Fplanning")
    page.get_by_role("link", name="Delete").click()
    page.wait_for_url(re.compile(rf"/work-orders/{number}/delete"))
    assert "cannot be undone" in page.locator("main").inner_text()
    page.get_by_role("button", name="Delete it").click()
    page.wait_for_url("**/planning?deleted=*")
    assert page.get_by_text(" deleted.").first.is_visible()


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_the_delete_dialog_starts_on_the_way_out_and_gives_focus_back(own_rows):
    page = own_rows("/work-orders/1/edit")
    link = page.get_by_role("link", name="Delete")
    link.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("dialog#confirm[open]")
    until(page, "document.activeElement.textContent.trim() === 'Keep it'")
    assert "cannot be undone" in page.locator("dialog#confirm").inner_text()
    page.keyboard.press("Escape")
    until(page, "!document.querySelector('dialog#confirm').open")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Delete"


@pytest.mark.browser
def test_the_delete_dialog_deletes(own_rows):
    page = own_rows("/work-orders/1/edit?back=%2Fplanning")
    page.get_by_role("link", name="Delete").click()
    page.wait_for_selector("dialog#confirm[open]")
    page.get_by_role("button", name="Delete it").click()
    page.wait_for_url("**/planning?deleted=1")
    assert page.get_by_text("Work order 1 deleted.").is_visible()


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_it_works_under_its_own_security_policy(own_rows):
    problems = []
    page = own_rows("/work-orders/1/edit")
    page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.locator("#field-hours").fill("many")
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("#work-order [role=alert]")
    page.get_by_role("link", name="Delete").click()
    page.wait_for_selector("dialog#confirm[open]")
    assert problems == []


def test_hours_stay_exact_in_a_language_with_another_decimal(writable):
    i18n._language.set("en")
    client, url = writable
    post(client, "/work-orders/1", valid(hours="12.25"))
    assert read_order(url, 1).hours == Decimal("12.25")


def test_the_migrations_leave_every_old_row_with_the_new_fields(tmp_path):
    url = f"sqlite:///{(tmp_path / 'old.db').as_posix()}"
    fill(url, 10)
    migrate(url)
    order = read_order(url, 1)
    assert (order.priority, order.crew, order.stop_needed, order.description, order.fault) == (
        "normal",
        1,
        False,
        "",
        None,
    )


# Files


PDF = b"%PDF-1.7\n1 0 obj\n"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)


def attach(client, content=PDF, name="report.pdf", address="/work-orders/1", **changes):
    files = {"attachment": (name, content, "application/octet-stream")}
    return client.post(address, data=valid(**changes), files=files, headers=SAME_SITE, follow_redirects=False)


@pytest.fixture
def uploads(database_url, tmp_path):
    """Its own rows and its own folder of files."""
    fill(database_url, 100)
    folder = tmp_path / "files"
    settings = build_settings(database_url=database_url, upload_folder=folder, upload_max_bytes=1024)
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    client.headers.update({"X-Remote-User": "demo.person", "X-Remote-Name": "Demo Person", "X-Remote-Groups": "admins"})
    yield client, database_url, folder


def files_of(url, number):
    engine = create_database_engine(url)
    with Session(engine) as session:
        found = list(session.scalars(select(WorkOrderFile).where(WorkOrderFile.work_order_id == number)))
    engine.dispose()
    return found


def stored(folder):
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


@pytest.mark.rule("SEC-12")
def test_a_file_is_saved_with_its_order_under_a_name_of_ours(uploads):
    client, url, folder = uploads
    assert attach(client).status_code == 303
    row = files_of(url, 1)[0]
    assert row.name == "report.pdf"
    assert row.media_type == "application/pdf"
    assert row.size == len(PDF)
    assert stored(folder) == [row.stored_name]
    assert "report" not in row.stored_name


def test_a_new_order_takes_a_file_too(uploads):
    client, url, _folder = uploads
    response = attach(client, address="/work-orders")
    number = int(re.search(r"saved=(\d+)", response.headers["location"])[1])
    assert [file.name for file in files_of(url, number)] == ["report.pdf"]


def test_a_form_with_no_file_chosen_saves_without_one(uploads):
    client, url, _folder = uploads
    response = client.post("/work-orders/1", data=valid(), files={"attachment": ("", b"")}, headers=SAME_SITE)
    assert response.status_code == 200
    assert files_of(url, 1) == []


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize(
    ("content", "name", "words"),
    [
        (bytes(2000), "report.pdf", "1 KB or smaller"),
        (b"", "report.pdf", "empty"),
        (PDF, "virus.exe", "one of these"),
        (b"MZ an executable", "photo.png", "not really"),
        (PNG, "report.pdf", "does not match"),
        (PDF, "../../etc/passwd.pdf", "Rename"),
        (PDF, "..%2f..%2fpasswd.pdf", "Rename"),
        (PDF, "report.pdf.exe", "one extension"),
    ],
)
def test_a_refused_file_is_an_error_on_its_field_and_nothing_is_kept(uploads, content, name, words):
    client, url, folder = uploads
    before = read_order(url, 1).title
    response = attach(client, content, name)
    assert response.status_code == 422
    assert words in response.text
    assert 'href="#field-attachment"' in response.text
    assert files_of(url, 1) == []
    assert stored(folder) == []
    assert read_order(url, 1).title == before


def test_a_file_in_a_form_that_failed_is_not_kept_and_the_form_says_to_choose_it_again(uploads):
    client, url, folder = uploads
    response = attach(client, title="")
    assert response.status_code == 422
    assert "Choose the file again" in response.text
    assert stored(folder) == []
    assert files_of(url, 1) == []


def test_a_commit_that_fails_leaves_no_file_behind(uploads, monkeypatch):
    client, _url, folder = uploads
    monkeypatch.setattr(work_orders, "_new_order", lambda: WorkOrder(status="reported"))  # no opened_at: it cannot save
    assert attach(client, address="/work-orders").status_code == 500
    assert stored(folder) == []


@pytest.mark.rule("SEC-12")
def test_a_download_is_an_attachment_with_the_real_type(uploads):
    client, url, _folder = uploads
    attach(client, PNG, "foto.png")
    file = files_of(url, 1)[0]
    response = client.get(f"/work-orders/1/files/{file.id}")
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == 'attachment; filename="foto.png"'
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.rule("SEC-02")
def test_a_viewer_cannot_reach_a_file(uploads):
    client, url, _folder = uploads
    attach(client)
    file = files_of(url, 1)[0]
    client.headers["X-Remote-Groups"] = "staff"
    assert client.get(f"/work-orders/1/files/{file.id}").status_code == 403
    assert client.get(f"/work-orders/1/files/{file.id}/delete").status_code == 403
    assert client.post(f"/work-orders/1/files/{file.id}/delete", headers=SAME_SITE).status_code == 403


@pytest.mark.rule("SEC-12")
@pytest.mark.parametrize(
    "path",
    [
        "/work-orders/2/files/1",
        "/work-orders/1/files/999999",
        "/work-orders/1/files/99999999999999999999",
        "/work-orders/1/files/..%2f..%2f.env",
        "/work-orders/1/files/report.pdf",
    ],
)
def test_a_file_is_reached_by_its_numbers_through_its_own_order_and_no_other_way(uploads, path):
    client, _url, _folder = uploads
    attach(client)
    assert client.get(path).status_code == 404


def test_the_form_lists_the_files_of_an_order(uploads):
    client, url, _folder = uploads
    attach(client, name="informe.pdf")
    html = client.get("/work-orders/1/edit").text
    file = files_of(url, 1)[0]
    assert f'href="/work-orders/1/files/{file.id}"' in html
    assert "informe.pdf" in html
    assert f'href="/work-orders/1/files/{file.id}/delete?back=' in html


def test_a_name_that_could_be_markup_stays_text(uploads):
    client, _url, _folder = uploads
    attach(client, name="<b>x.pdf")
    assert "<b>x.pdf" not in client.get("/work-orders/1/edit").text


def test_removing_a_file_asks_and_names_it(uploads):
    client, url, _folder = uploads
    attach(client, name="informe.pdf")
    file = files_of(url, 1)[0]
    html = client.get(f"/work-orders/1/files/{file.id}/delete").text
    assert "<li>informe.pdf</li>" in html
    assert "cannot be undone" in html
    assert 'id="confirm-title"' in client.get(f"/work-orders/1/files/{file.id}/delete", headers=HTMX).text


def test_removing_a_file_takes_it_from_the_disk_and_comes_back_to_the_form(uploads):
    client, url, folder = uploads
    attach(client)
    file = files_of(url, 1)[0]
    response = client.post(
        f"/work-orders/1/files/{file.id}/delete", data={"back": "/planning"}, headers=SAME_SITE, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/work-orders/1/edit?")
    assert files_of(url, 1) == []
    assert stored(folder) == []
    assert "The file was removed." in client.get(response.headers["location"]).text


def test_deleting_an_order_names_its_files_and_takes_them(uploads):
    client, url, folder = uploads
    attach(client)
    attach(client, PNG, "photo.png")
    html = client.get("/work-orders/1/delete").text
    assert "<li>Attached file: report.pdf</li>" in html
    assert "<li>Attached file: photo.png</li>" in html
    assert len(stored(folder)) == 2
    named = re.search(r'name="files" value="([^"]*)"', html)[1]
    form = {"back": "/planning", "version": "2", "files": named}
    client.post("/work-orders/1/delete", data=form, headers=SAME_SITE)
    assert stored(folder) == []
    assert files_of(url, 1) == []


@pytest.fixture
def upload_server(browser, tmp_path):
    url = f"sqlite:///{(tmp_path / 'orders.db').as_posix()}"
    fill(url, 200)
    settings = build_settings(
        database_url=url,
        fake_identity=True,
        fake_groups=["admins"],
        trusted_proxies=[],
        upload_folder=tmp_path / "files",
        upload_max_bytes=2048,
        request_max_bytes=100_000,
    )
    with running_server(create_app(settings)) as port, page_opener(browser, f"http://127.0.0.1:{port}") as opener:
        yield opener, tmp_path / "files"


def choose(page, content=PDF, name="report.pdf"):
    page.locator("#field-attachment").set_input_files({"name": name, "mimeType": "application/pdf", "buffer": content})


@pytest.mark.browser
def test_with_htmx_a_file_goes_with_the_form(upload_server):
    open_page, folder = upload_server
    page = open_page("/work-orders/1/edit?back=%2Fplanning")
    choose(page)
    page.get_by_role("button", name="Save").click()
    page.wait_for_url("**/planning?saved=1")
    assert len(stored(folder)) == 1
    page = open_page("/work-orders/1/edit")
    assert page.get_by_role("link", name="report.pdf", exact=True).is_visible()


@pytest.mark.browser
def test_without_javascript_a_file_goes_with_the_form(upload_server):
    open_page, folder = upload_server
    page = open_page("/work-orders/1/edit?back=%2Fplanning", javascript=False)
    choose(page)
    page.get_by_role("button", name="Save").click()
    page.wait_for_url("**/planning?saved=1")
    assert len(stored(folder)) == 1


@pytest.mark.browser
def test_with_htmx_a_refused_file_stays_in_the_form_with_its_error(upload_server):
    open_page, folder = upload_server
    page = open_page("/work-orders/1/edit")
    page.locator("#field-title").fill("Mine")
    choose(page, b"MZ an executable", "report.pdf")
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("#work-order [role=alert]")
    assert "not really" in page.locator("#work-order [role=alert]").inner_text()
    assert page.locator("#field-title").input_value() == "Mine"
    assert page.locator("#field-attachment").get_attribute("aria-invalid") == "true"
    assert stored(folder) == []


@pytest.mark.browser
def test_with_htmx_a_request_too_long_says_so_and_keeps_what_was_typed(upload_server):
    open_page, _folder = upload_server
    page = open_page("/work-orders/1/edit")
    page.locator("#field-title").fill("Mine")
    choose(page, bytes(150_000))
    page.get_by_role("button", name="Save").click()
    until(page, "!document.querySelector('#request-problem').hidden")
    assert "too large" in page.locator("#request-problem").inner_text()
    assert page.locator("#field-title").input_value() == "Mine"


@pytest.mark.browser
def test_removing_a_file_opens_a_dialog_and_comes_back(upload_server):
    open_page, folder = upload_server
    page = open_page("/work-orders/1/edit?back=%2Fplanning")
    choose(page)
    page.get_by_role("button", name="Save").click()
    page.wait_for_url("**/planning?saved=1")
    page = open_page("/work-orders/1/edit?back=%2Fplanning")
    page.get_by_role("link", name="Remove report.pdf").click()
    page.wait_for_selector("dialog#confirm[open]")
    assert "report.pdf" in page.locator("dialog#confirm").inner_text()
    page.get_by_role("button", name="Remove it").click()
    page.wait_for_url("**/work-orders/1/edit*removed=1*")
    assert page.get_by_text("The file was removed.").is_visible()
    assert stored(folder) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 390])
def test_a_form_with_files_passes_the_scan(upload_server, theme, width):
    open_page, _folder = upload_server
    first = open_page("/work-orders/1/edit?back=%2Fplanning")
    choose(first)
    first.get_by_role("button", name="Save").click()
    first.wait_for_url("**/planning?saved=1")
    page = open_page("/work-orders/1/edit", theme=theme, width=width, bypass_csp=True)
    assert run_axe(page) == []
    assert not overflows_sideways(page)
