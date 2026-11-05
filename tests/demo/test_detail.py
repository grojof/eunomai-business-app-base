"""The equipment detail: one record, its tabs and its history, on screen and on paper."""

import re

import pytest
from fastapi.testclient import TestClient

from app.core.i18n import PSEUDO
from app.demo.generate import equipment_row, work_order_row
from app.main import create_app
from tests.conftest import build_settings
from tests.demo.support import until
from tests.helpers import overflows_sideways, run_axe_in_both_themes, untranslated

ALLOWED = (
    "Business App",
    "Demo Person",
    "EQ-",
    "Cooling tower",
    "Standby generator",
    "Leak repair",
    "Safety checks",
    "Oil change",
)
ALLOWED += ("Aug ", "Feb ", "Jan ", "Mar ", "Apr ", "May ", "Jun ", "Jul ", "Sep ", "Oct ", "Nov ", "Dec ", "AM", "PM")
ALLOWED += ("Preventive plan", "Filter replacement", "Belt replacement", "Calibration", "Electrical inspection")


def test_a_piece_of_equipment_shows_what_is_known(filled):
    row = equipment_row(0)
    html = filled.get("/equipment/1").text
    assert row["code"] in html
    assert row["name"] in html
    assert f"{row['cost']:,.2f}" in html
    assert "<dl" in html


def test_the_history_shows_its_orders_newest_first_with_a_total(filled):
    html = filled.get("/equipment/1?tab=orders").text
    orders = [work_order_row(n) for n in range(3)]
    newest = sorted(orders, key=lambda order: order["opened_at"], reverse=True)
    body = html[html.index("<tbody") : html.index("</tbody>")]
    assert re.findall(r'<td class="hidden tabular-nums md:table-cell">(\d+)</td>', body) == [
        str(order["id"]) for order in newest
    ]
    assert "<tfoot>" in html


def test_equipment_with_no_orders_says_so(filled):
    assert "No work orders yet" in filled.get("/equipment/2?tab=orders").text


def test_an_unknown_tab_is_the_first_one(filled):
    assert 'id="tab-overview" class="tab text-base-content tab-active' in filled.get("/equipment/1?tab=nothing").text


@pytest.mark.parametrize("path", ["/equipment/999999", "/equipment/99999999999999999999999", "/equipment/abc"])
def test_what_does_not_exist_is_not_found(filled, path):
    assert filled.get(path).status_code == 404


def test_without_the_rows_it_says_what_to_run(tmp_path, person):
    folder = tmp_path / "nothing-here"
    client = TestClient(create_app(build_settings(database_url=f"sqlite:///{(folder / 'app.db').as_posix()}")))
    assert "uv run --frozen python -m app.demo.generate" in client.get("/equipment/1", headers=person).text
    assert not folder.exists()


def test_the_breadcrumb_goes_back_to_the_list_a_person_came_from(filled):
    html = filled.get("/equipment/1", headers={"Referer": "http://testserver/equipment?status=stopped&sort=cost"}).text
    assert 'href="/equipment?status=stopped&amp;sort=cost"' in html


@pytest.mark.rule("SEC-13")
@pytest.mark.parametrize(
    "referer", ["https://attacker.example/other", "http://testserver/administration", "not an address"]
)
def test_the_breadcrumb_never_leaves_the_list(filled, referer):
    html = filled.get("/equipment/1", headers={"Referer": referer}).text
    assert '<li><a href="/equipment">' in html


def test_a_strange_list_address_in_the_referer_is_read_like_any_other(filled):
    referer = "http://testserver/equipment?sort=x'%20OR%201=1&status=%22%3E%3Cscript%3E"
    assert '<li><a href="/equipment">' in filled.get("/equipment/1", headers={"Referer": referer}).text


def test_tabs_are_links_with_the_current_one_marked(filled):
    html = filled.get("/equipment/1?tab=orders").text
    assert re.search(r'href="/equipment/1\?tab=orders"[^>]*aria-current="page"', html)
    assert 'role="tab"' not in html


def test_htmx_gets_only_the_tabs(filled):
    response = filled.get("/equipment/1?tab=orders", headers={"HX-Request": "true"})
    assert "<html" not in response.text
    assert "data-announce" in response.text
    assert response.headers["vary"] == "HX-Request"


def test_both_tabs_are_on_the_page_for_paper(filled):
    html = filled.get("/equipment/1").text
    assert "print:block" in html
    assert "Maintenance to date" in html
    assert re.search(r"Leak repair|Safety checks|Oil change|plan|Filter|Belt|Calibration|Electrical", html)


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", ["/equipment/1", "/equipment/1?tab=orders", "/equipment/2?tab=orders"])
def test_no_text_outside_translation(filled, path):
    filled.cookies.set("language", PSEUDO)
    assert untranslated(filled.get(path).text, ALLOWED) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", ["/equipment/1", "/equipment/1?tab=orders", "/equipment/2?tab=orders"])
def test_no_detectable_accessibility_failure(open_filled, path):
    assert run_axe_in_both_themes(open_filled(path, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
@pytest.mark.parametrize("path", ["/equipment/1", "/equipment/1?tab=orders"])
def test_it_fits_a_phone_with_longer_texts(open_filled, path):
    assert not overflows_sideways(open_filled(path, language=PSEUDO, width=320))


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_changing_tab_keeps_focus_on_it_and_announces_it(open_filled):
    page = open_filled("/equipment/1")
    tab = page.locator("#tab-orders")
    tab.focus()
    page.keyboard.press("Enter")
    page.wait_for_url("**/equipment/1?tab=orders")
    until(page, "document.querySelector('#tab-orders').getAttribute('aria-current') === 'page'")
    until(page, "document.querySelector('#announcements').textContent === 'Work orders'")
    assert page.evaluate("document.activeElement.id") == "tab-orders"
    assert page.get_by_role("cell", name="Total").count() == 0 or page.locator("tfoot").is_visible()


@pytest.mark.browser
def test_the_back_button_goes_back_a_tab(open_filled):
    page = open_filled("/equipment/1")
    page.locator("#tab-orders").click()
    page.wait_for_url("**/equipment/1?tab=orders")
    until(page, "document.querySelector('tfoot').checkVisibility()")
    page.go_back()
    page.wait_for_url("**/equipment/1")
    until(page, "document.querySelector('#tab-overview').getAttribute('aria-current') === 'page'")


@pytest.mark.browser
def test_tabs_work_without_javascript(open_filled):
    page = open_filled("/equipment/1", javascript=False)
    page.locator("#tab-orders").click()
    page.wait_for_url("**/equipment/1?tab=orders")
    assert page.locator("tfoot").is_visible()


@pytest.mark.browser
def test_paper_shows_both_tabs_and_none_of_the_shell(open_filled):
    page = open_filled("/equipment/1", theme="dark")
    page.emulate_media(media="print")
    assert page.locator("tfoot").is_visible()
    assert page.get_by_text("Maintenance to date").is_visible()
    assert not page.locator("#navigation").is_visible()
    assert not page.locator("header.navbar").is_visible()
    assert not page.locator("[data-print]").is_visible()
    assert not page.locator("nav.breadcrumbs").is_visible()


@pytest.mark.browser
def test_a_dark_theme_prints_light_and_comes_back(open_filled):
    page = open_filled("/equipment/1", theme="dark")
    surface = "getComputedStyle(document.documentElement).getPropertyValue('--color-base-100')"
    dark = page.evaluate(surface)
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    assert page.evaluate(surface) != dark
    page.evaluate("dispatchEvent(new Event('afterprint'))")
    assert page.evaluate(surface) == dark
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page.locator("input.theme-controller").count() > 0


@pytest.mark.browser
def test_a_theme_that_follows_the_system_comes_back_too(open_filled):
    page = open_filled("/equipment/1", theme="system")
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    page.evaluate("dispatchEvent(new Event('afterprint'))")
    assert page.evaluate("document.documentElement.dataset.theme") is None


@pytest.mark.parametrize("referer", ["//[", "http://[", "http://[/equipment?status=stopped"])
def test_a_malformed_referer_is_ignored(filled, referer):
    response = filled.get("/equipment/1", headers={"Referer": referer})
    assert response.status_code == 200
    assert '<li><a href="/equipment">' in response.text


def test_tabs_carry_the_list_a_person_came_from(filled):
    html = filled.get("/equipment/1", headers={"Referer": "http://testserver/equipment?status=stopped"}).text
    assert re.search(r'id="tab-orders"[^>]*href="/equipment/1\?tab=orders&amp;back=', html)


def test_the_breadcrumb_reads_the_list_from_the_address_of_a_tab(filled):
    html = filled.get("/equipment/1", params={"tab": "orders", "back": "/equipment?status=stopped"}).text
    assert '<a href="/equipment?status=stopped">' in html


def test_a_default_list_keeps_the_addresses_of_tabs_clean(filled):
    assert re.search(r'id="tab-orders"[^>]*href="/equipment/1\?tab=orders"', filled.get("/equipment/1").text)


@pytest.mark.parametrize("back", ["//[", "https://attacker.example/equipment?status=stopped&x=1", "/administration"])
def test_a_strange_back_in_a_tab_is_read_like_any_other(filled, back):
    response = filled.get("/equipment/1", params={"tab": "orders", "back": back})
    assert response.status_code == 200
    links = re.findall(r'(?:breadcrumbs.*?<a|id="tab-\w+"[^>]*) href="([^"]*)"', response.text, re.S)
    assert links
    assert not [link for link in links if "attacker" in link or "administration" in link]


@pytest.mark.browser
def test_without_javascript_the_breadcrumb_survives_a_tab(open_filled):
    page = open_filled("/equipment?status=stopped", javascript=False)
    page.locator("#equipment-results tbody th a").first.click()
    page.wait_for_url(re.compile(r"/equipment/\d+"))
    assert page.locator("nav.breadcrumbs a").first.get_attribute("href") == "/equipment?status=stopped"
    page.locator("#tab-orders").click()
    page.wait_for_url(re.compile(r"tab=orders"))
    assert page.locator("nav.breadcrumbs a").first.get_attribute("href") == "/equipment?status=stopped"
    page.locator("#tab-overview").click()
    page.wait_for_load_state()
    assert page.locator("nav.breadcrumbs a").first.get_attribute("href") == "/equipment?status=stopped"


@pytest.mark.browser
def test_with_javascript_the_breadcrumb_survives_a_tab_and_a_reload(open_filled):
    page = open_filled("/equipment?status=stopped")
    page.locator("#equipment-results tbody th a").first.click()
    page.wait_for_url(re.compile(r"/equipment/\d+"))
    page.locator("#tab-orders").click()
    page.wait_for_url(re.compile(r"tab=orders"))
    page.reload()
    assert page.locator("nav.breadcrumbs a").first.get_attribute("href") == "/equipment?status=stopped"
