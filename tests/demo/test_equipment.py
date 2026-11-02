"""The equipment list: a real screen on the generated rows, by HTTP and in a browser."""

import re
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import create_database_engine
from app.core.i18n import PSEUDO
from app.demo.generate import equipment_row
from app.demo.models import Equipment
from app.main import create_app
from tests.conftest import build_settings
from tests.demo.support import announced, until
from tests.helpers import ROOT, overflows_sideways, run_axe, untranslated

ROW = re.compile(r'<a class="link link-hover" href="/equipment/\d+">(EQ-\d+)</a>')
HTMX = {"HX-Request": "true"}
ALLOWED = ("Business App", "Demo Person", "EQ-", "Air compressor", "Conveyor belt", "Standby generator")
ALLOWED += ("Cooling tower", "Forklift", "Aug ", "Jul ", "Feb ", "Jun ", "Apr ", "Nov ", "Sep ", "May ", "Mar ")
ALLOWED += ("Jan ", "Dec ", "Oct ", "EQ", "nothing")


def codes(html: str) -> list[str]:
    return ROW.findall(html)


def test_the_list_shows_one_page_of_every_row(filled):
    html = filled.get("/equipment").text
    assert len(codes(html)) == 25
    assert "1,000 pieces of equipment" in html
    assert codes(html)[0] == "EQ-000001"


@pytest.mark.rule("USE-05")
def test_an_address_opened_again_gives_the_same_page(filled):
    address = "/equipment?status=in_service&sort=cost&dir=desc&size=10&page=2"
    first = filled.get(address).text
    assert codes(first) == codes(filled.get(address).text)
    assert len(codes(first)) == 10
    assert '<option value="in_service" selected>' in first
    assert '<option value="10" selected>' in first


def test_sorting_by_cost_is_numeric(filled):
    rows = [equipment_row(n) for n in range(1_000)]
    expected = sorted(rows, key=lambda row: (row["cost"], row["id"]))[:25]
    assert codes(filled.get("/equipment?sort=cost&dir=asc").text) == [row["code"] for row in expected]


def test_a_location_sorts_by_what_a_person_reads(filled):
    filled.cookies.set("language", "es")
    html = filled.get("/equipment?sort=location&size=100").text
    shown = re.findall(r"<td class=\"hidden md:table-cell whitespace-nowrap\">([^<\d]+)</td>", html)
    assert shown == sorted(shown, key=str.casefold)


def test_a_state_sorts_by_what_needs_attention(filled):
    html = filled.get("/equipment?sort=status&size=100").text
    body = html[html.index('id="equipment-results"') :]
    assert body.index("Stopped") < body.index("Due soon")
    assert "In service" not in body


def test_each_filter_narrows_the_rows(filled):
    rows = [equipment_row(n) for n in range(1_000)]
    expected = sum(row["status"] == "stopped" and row["location"] == "Roof" for row in rows)
    html = filled.get("/equipment?status=stopped&location=Roof").text
    assert re.search(rf">\s*{expected} pieces of equipment", html)


def test_a_search_finds_a_code_or_a_name(filled):
    assert codes(filled.get("/equipment?q=eq-000007").text) == ["EQ-000007"]
    name = equipment_row(6)["name"]
    assert "EQ-000007" in codes(filled.get("/equipment", params={"q": name}).text)


def test_no_results_says_so_and_offers_a_way_out(filled):
    html = filled.get("/equipment?q=nothing+like+this").text
    assert "No equipment matches" in html
    assert 'href="/equipment"' in html
    assert "<table" not in html[html.index('id="equipment-results"') :]


def test_a_filter_on_the_page_can_be_removed(filled):
    html = filled.get("/equipment?status=stopped&sort=cost").text
    assert 'href="/equipment?sort=cost"' in html
    assert "Remove filter State: Stopped" in html


@pytest.mark.rule("A11Y-09")
def test_htmx_gets_only_what_changed_with_its_address(filled):
    response = filled.get("/equipment?status=stopped&page=1", headers=HTMX | {"HX-Trigger": "equipment-filters"})
    assert "<html" not in response.text
    assert "hx-swap-oob" not in response.text
    assert response.headers["hx-push-url"] == "/equipment?status=stopped"
    assert "data-announce" in response.text


def test_a_link_brings_the_filter_form_in_step(filled):
    response = filled.get("/equipment?sort=cost", headers=HTMX | {"HX-Trigger": "equipment-sort-cost"})
    assert 'hx-swap-oob="true"' in response.text
    assert '<input type="hidden" name="sort" value="cost">' in response.text


def test_the_browser_keeps_pages_and_fragments_apart(filled):
    assert filled.get("/equipment").headers["vary"] == "HX-Request"
    assert filled.get("/equipment", headers=HTMX).headers["vary"] == "HX-Request"


def test_going_back_gets_a_whole_page(filled):
    response = filled.get("/equipment", headers=HTMX | {"HX-History-Restore-Request": "true"})
    assert "<html" in response.text


@pytest.mark.rule("SEC-05")
@pytest.mark.parametrize(
    "query",
    [
        "sort=name;DROP TABLE equipment;--",
        "sort=(SELECT password FROM users)",
        "dir=asc,(SELECT 1)",
        "page=1 OR 1=1",
        "size=1;DELETE FROM equipment",
        "status=' OR '1'='1",
        "location=Roof' UNION SELECT * FROM equipment --",
        "q=' OR 1=1 --",
        "q='; DROP TABLE equipment; --",
        "q=%00",
    ],
)
def test_sql_through_the_address_does_nothing(filled, filled_url, query):
    assert filled.get(f"/equipment?{query}").status_code == 200
    engine = create_database_engine(filled_url)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Equipment)) == 1_000
    engine.dispose()


def test_the_page_tells_what_to_run_when_the_rows_are_not_there(tmp_path, person):
    folder = tmp_path / "nothing-here"
    client = TestClient(create_app(build_settings(database_url=f"sqlite:///{(folder / 'app.db').as_posix()}")))
    response = client.get("/equipment", headers=person)
    assert response.status_code == 200
    assert "uv run --frozen python -m app.demo.generate" in response.text
    assert not folder.exists(), "showing a page must not create a database"


def test_an_empty_table_says_the_same(database_url, person):
    from app.core.database import migrate

    migrate(database_url)
    client = TestClient(create_app(build_settings(database_url=database_url)))
    assert "uv run --frozen python -m app.demo.generate" in client.get("/equipment", headers=person).text


def test_migrations_behind_the_code_say_the_same(tmp_path, person):
    path = tmp_path / "old.db"
    url = f"sqlite:///{path.as_posix()}"
    engine = create_database_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    engine.dispose()
    client = TestClient(create_app(build_settings(database_url=url)))
    assert "uv run --frozen python -m app.demo.generate" in client.get("/equipment", headers=person).text


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", ["/equipment", "/equipment?status=stopped&q=EQ", "/equipment?q=nothing"])
def test_no_text_outside_translation(filled, path):
    filled.cookies.set("language", PSEUDO)
    assert untranslated(filled.get(path).text, ALLOWED) == []


@pytest.mark.rule("LANG-01")
def test_no_text_outside_translation_without_the_rows(client, person):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get("/equipment", headers=person).text, ALLOWED) == []


@pytest.mark.parametrize(("language", "expected"), [("en", "1,000"), ("es", "1000"), ("ca", "1.000")])
def test_counts_follow_the_language(filled, language, expected):
    filled.cookies.set("language", language)
    assert expected in filled.get("/equipment").text


def test_a_cost_shows_two_decimals_in_the_language(filled):
    filled.cookies.set("language", "es")
    cost = equipment_row(0)["cost"]
    whole, fraction = f"{cost:.2f}".split(".")
    grouped = f"{whole[:-3]}.{whole[-3:]}" if len(whole) >= 5 else whole
    assert f"{grouped},{fraction}" in filled.get("/equipment").text


def test_the_screens_call_macros():
    folder = ROOT / "app" / "demo" / "templates" / "demo" / "equipment"
    for template in folder.glob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(r'<(?:table|button|select)\b|class="(?:btn|table|badge|select|input)\b', text), template


def test_every_exact_value_is_read_exactly_at_this_size(large_url):
    engine = create_database_engine(large_url)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Equipment)) == 50_000
    engine.dispose()


def test_a_count_stays_fast_at_fifty_thousand_rows(large_url, person):
    client = TestClient(create_app(build_settings(database_url=large_url)))
    client.get("/equipment", headers=person)  # the first request loads the catalogues and connects
    started = time.perf_counter()
    assert "50,000 pieces of equipment" in client.get("/equipment", headers=person).text
    assert time.perf_counter() - started < 1


def test_the_columns_it_sorts_by_have_their_index():
    columns = {column.name for column in Equipment.__table__.columns if column.index or column.unique}
    assert {"code", "name", "location", "status", "next_inspection", "cost"} <= columns


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", ["/equipment", "/equipment?status=stopped&sort=cost", "/equipment?q=nothing"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_detectable_accessibility_failure(open_filled, path, theme):
    assert run_axe(open_filled(path, theme=theme, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_detectable_failure_without_the_rows(open_page, theme):
    assert run_axe(open_page("/equipment", theme=theme, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
def test_it_fits_a_phone_with_longer_texts(open_filled):
    assert not overflows_sideways(open_filled("/equipment", language=PSEUDO, width=320))


def first_code(page):
    return page.locator("#equipment-results tbody th a").first.inner_text()


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_sorting_keeps_focus_on_its_header_and_announces_the_order(open_filled):
    page = open_filled("/equipment")
    header = page.locator("#equipment-sort-cost")
    header.focus()
    page.keyboard.press("Enter")
    page.wait_for_url("**/equipment?sort=cost")
    until(page, "document.activeElement.id === 'equipment-sort-cost'")
    announced(page, "sorted by Cost, descending")
    assert page.locator("th[aria-sort]").count() == 1
    assert page.locator("th[aria-sort]").get_attribute("aria-sort") == "descending"
    page.keyboard.press("Enter")
    page.wait_for_url("**/equipment?sort=cost&dir=asc")
    until(page, "document.querySelector('th[aria-sort]').getAttribute('aria-sort') === 'ascending'")
    assert page.evaluate("document.activeElement.id") == "equipment-sort-cost"


@pytest.mark.browser
@pytest.mark.rule("USE-05")
@pytest.mark.rule("A11Y-09")
def test_typing_filters_keeps_the_box_and_the_text(open_filled):
    page = open_filled("/equipment")
    box = page.locator("#equipment-search")
    box.focus()
    page.keyboard.type("EQ-00001")
    page.wait_for_url("**/equipment?q=EQ-00001")
    until(page, "document.querySelector('#equipment-results tbody th a').textContent === 'EQ-000010'")
    assert page.evaluate("document.activeElement.id") == "equipment-search"
    assert box.input_value() == "EQ-00001"
    announced(page, "10 pieces of equipment")


@pytest.mark.browser
@pytest.mark.rule("USE-05")
def test_a_filter_and_a_page_survive_a_reload(open_filled):
    page = open_filled("/equipment")
    page.select_option("#equipment-status", "stopped")
    page.wait_for_url("**/equipment?status=stopped")
    code = first_code(page)
    page.reload()
    assert first_code(page) == code
    assert page.locator("#equipment-status").input_value() == "stopped"


@pytest.mark.browser
@pytest.mark.rule("USE-05")
def test_the_back_button_goes_through_each_state(open_filled):
    page = open_filled("/equipment")
    first = first_code(page)
    page.select_option("#equipment-status", "stopped")
    page.wait_for_url("**/equipment?status=stopped")
    until(page, "document.querySelector('th[aria-sort] ~ th') !== null")
    page.locator("#equipment-sort-cost").click()
    page.wait_for_url("**/equipment?status=stopped&sort=cost")
    page.wait_for_selector("th[aria-sort] #equipment-sort-cost")
    sorted_first = first_code(page)

    page.go_back()
    page.wait_for_url("**/equipment?status=stopped")
    page.wait_for_selector("th[aria-sort] #equipment-sort-code")
    assert page.locator("#equipment-status").input_value() == "stopped"
    page.go_back()
    page.wait_for_url("**/equipment")
    page.wait_for_selector("th[aria-sort] #equipment-sort-code")
    assert first_code(page) == first
    assert page.locator("#equipment-status").input_value() == ""

    page.go_forward()
    page.go_forward()
    page.wait_for_url("**/equipment?status=stopped&sort=cost")
    page.wait_for_selector("th[aria-sort] #equipment-sort-cost")
    assert first_code(page) == sorted_first
    assert page.locator('input[name="sort"]').get_attribute("value") == "cost"


@pytest.mark.browser
def test_a_link_that_clears_a_filter_resets_its_control(open_filled):
    page = open_filled("/equipment?status=stopped&q=EQ")
    page.get_by_role("link", name="Clear all").click()
    page.wait_for_url("**/equipment")
    until(page, "document.querySelector('#equipment-status').value === ''")
    assert page.locator("#equipment-search").input_value() == ""


@pytest.mark.browser
def test_sorting_then_filtering_keeps_the_order(open_filled):
    page = open_filled("/equipment")
    page.locator("#equipment-sort-cost").click()
    page.wait_for_url("**/equipment?sort=cost")
    page.wait_for_selector('input[name="sort"]', state="attached")
    page.select_option("#equipment-location", "Roof")
    page.wait_for_url("**/equipment?location=Roof&sort=cost")


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_paging_keeps_focus_and_at_the_end_moves_it_to_the_table(open_filled):
    page = open_filled("/equipment?size=100")
    page.get_by_role("link", name="Next page").focus()
    page.keyboard.press("Enter")
    for number in range(2, 11):
        until(page, f"document.querySelector('#equipment-results a[aria-current]').textContent === '{number}'")
        if number < 10:
            until(page, "document.activeElement.id === 'equipment-next'")
            page.keyboard.press("Enter")
    until(page, "document.activeElement.matches('[data-focus-fallback]')")
    page.wait_for_url("**/equipment?size=100&page=10")


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_a_link_works_from_the_moment_it_arrives(open_filled):
    """The next thing a browser does after a swap may be a second click: a link not wired yet would reload the page."""
    page = open_filled("/equipment?size=100")
    page.evaluate("""() => {
        window.sameDocument = true;
        const next = () => document.getElementById("equipment-next").click();
        document.addEventListener("htmx:afterSwap", () => setTimeout(next), {once: true});
    }""")
    page.get_by_role("link", name="Next page").click()
    until(page, "document.querySelector('#equipment-results a[aria-current]').textContent === '3'")
    assert page.evaluate("window.sameDocument === true")


@pytest.mark.browser
def test_the_page_size_applies_at_once_and_goes_to_the_first_page(open_filled):
    page = open_filled("/equipment?page=3")
    page.locator("#equipment-size").focus()
    page.select_option("#equipment-size", "10")
    page.wait_for_url("**/equipment?size=10")
    until(page, "document.querySelectorAll('#equipment-results tbody tr').length === 10")
    assert page.evaluate("document.activeElement.id") == "equipment-size"


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_the_keyboard_reaches_the_table_box_and_scrolls_it(open_filled):
    page = open_filled("/equipment")
    box = page.locator(".table-scroll")
    assert box.get_attribute("tabindex") == "0"
    box.focus()
    page.keyboard.press("PageDown")
    until(page, "document.querySelector('.table-scroll').scrollTop > 0")
    header = page.locator("#equipment-results thead tr").bounding_box()
    assert header["y"] >= box.bounding_box()["y"] - 1


@pytest.mark.browser
def test_every_header_cell_stays_on_top_while_the_rows_go_past(open_filled):
    """The first column is pinned sideways too, and its cells must pass under the header, not over it."""
    page = open_filled("/equipment")
    page.locator(".table-scroll").evaluate("box => box.scrollIntoView()")
    page.evaluate("document.querySelector('.table-scroll').scrollTop = 400")
    until(page, "document.querySelector('.table-scroll').scrollTop >= 400")
    top = page.locator(".table-scroll").bounding_box()["y"]
    cells = page.locator("#equipment-results thead tr > *")
    assert cells.count() > 1
    for index in range(cells.count()):
        box = cells.nth(index).bounding_box()
        assert abs(box["y"] - top) <= 1, cells.nth(index).inner_text()
        middle = (box["x"] + min(box["width"], 40) / 2, box["y"] + box["height"] / 2)
        assert page.evaluate("([x, y]) => !!document.elementFromPoint(x, y).closest('thead')", middle), index


@pytest.mark.browser
def test_the_table_box_stays_in_the_tab_order_of_the_page(open_filled):
    page = open_filled("/equipment")
    page.locator("#equipment-location").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Export to Excel"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Whole width"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Dense rows"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.matches('.table-scroll')")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "equipment-sort-code"


@pytest.mark.browser
def test_without_javascript_it_all_still_works(open_filled):
    page = open_filled("/equipment", javascript=False)
    assert page.locator("#equipment-results tbody tr").count() == 25
    page.locator("#equipment-sort-cost").click()
    page.wait_for_url("**/equipment?sort=cost")
    apply = page.locator("#equipment-filters").get_by_role("button", name="Apply")
    assert apply.is_visible()
    page.select_option("#equipment-status", "in_service")
    apply.click()
    page.wait_for_url(re.compile(r"status=in_service"))
    assert re.search(r"sort=cost", page.url)
    assert page.locator("#equipment-status").input_value() == "in_service"
    page.get_by_role("link", name="Next page").click()
    page.wait_for_url(re.compile(r"page=2"))
    assert page.locator("th[aria-sort] #equipment-sort-cost").count() == 1


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_the_list_works_under_its_own_security_policy(open_filled):
    problems = []
    page = open_filled("/equipment")
    page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
    page.locator("#equipment-sort-cost").click()
    page.wait_for_url("**/equipment?sort=cost")
    page.wait_for_load_state("networkidle")
    assert problems == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
@pytest.mark.parametrize(
    ("status", "words"),
    [(500, "did not work"), (403, "permission"), (404, "no longer here")],
)
def test_a_failed_request_says_so_where_a_person_can_see_and_hear_it(open_filled, status, words):
    page = open_filled("/equipment")
    page.route("**/equipment?sort=cost*", lambda route: route.fulfill(status=status, body="nothing"))
    page.locator("#equipment-sort-cost").click()
    until(page, "!document.querySelector('#request-problem').hidden")
    problem = page.locator("#request-problem")
    assert problem.is_visible()
    assert words in problem.inner_text()
    assert problem.get_attribute("role") == "alert"


@pytest.mark.browser
def test_a_server_that_cannot_be_reached_says_so(open_filled):
    page = open_filled("/equipment")
    page.route("**/equipment?sort=cost*", lambda route: route.abort())
    page.locator("#equipment-sort-cost").click()
    until(page, "!document.querySelector('#request-problem').hidden")
    assert "cannot be reached" in page.locator("#request-problem").inner_text()


@pytest.mark.browser
def test_the_message_of_a_failed_request_goes_when_the_next_one_starts(open_filled):
    page = open_filled("/equipment")
    page.route("**/equipment?sort=cost*", lambda route: route.fulfill(status=500, body="nothing"))
    page.locator("#equipment-sort-cost").click()
    until(page, "!document.querySelector('#request-problem').hidden")
    page.locator("#equipment-sort-name").click()
    until(page, "document.querySelector('#request-problem').hidden")


@pytest.mark.browser
def test_the_message_of_a_failed_request_can_be_closed(open_filled):
    page = open_filled("/equipment")
    page.route("**/equipment?sort=cost*", lambda route: route.fulfill(status=500, body="nothing"))
    page.locator("#equipment-sort-cost").click()
    until(page, "!document.querySelector('#request-problem').hidden")
    page.locator("#request-problem button").click()
    assert not page.locator("#request-problem").is_visible()


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_focus_lands_on_the_empty_state_when_no_table_comes_back(open_filled):
    page = open_filled("/equipment?q=nothing+like+this&status=stopped")
    page.locator("a[aria-label^='Remove filter State']").focus()
    page.keyboard.press("Enter")
    page.wait_for_url("**/equipment?q=nothing+like+this")
    until(page, "document.activeElement !== document.body")
    assert page.evaluate("document.activeElement.matches('[data-focus-fallback]')")
    assert "No equipment matches" in page.evaluate("document.activeElement.textContent")


@pytest.mark.browser
@pytest.mark.parametrize("width", [1440, 1024])
@pytest.mark.parametrize("path", ["/equipment", "/planning"])
def test_the_actions_header_lines_up_with_what_is_under_it(open_filled, path, width):
    edges = open_filled(path, width=width).evaluate("""() => {
        const header = document.createRange();
        header.selectNodeContents([...document.querySelectorAll('[data-results] thead th')].at(-1));
        const links = [...document.querySelectorAll('[data-results] tbody td:last-child a')];
        const parts = [...links.at(-1).children].filter((part) => part.getBoundingClientRect().width > 0);
        return [header.getBoundingClientRect().right, parts.at(-1).getBoundingClientRect().right];
    }""")
    assert abs(edges[0] - edges[1]) <= 1
