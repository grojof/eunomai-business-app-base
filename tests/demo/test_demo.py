import re

import pytest
from fastapi.testclient import TestClient

from app.core.i18n import PSEUDO
from app.main import create_app
from tests.conftest import build_settings
from tests.helpers import ROOT, overflows_sideways, repository_text_files, run_axe_in_both_themes, untranslated

PAGES = ["/", "/settings", "/administration"]
LAYOUTS = [
    {"navigation": "side"},
    {"navigation": "compact"},
    {"navigation": "top"},
    {"navigation": "hidden"},
    {"sticky_header": "off", "width": "centered"},
    {"density": "compact"},
]
ALLOWED = ("Business App", "Demo Person", "Mar 15, 2027", "Nov 20, 2026", "Jan 12, 2027", "Nov 9, 2026", "May 3, 2027")


def test_the_base_names_no_product_it_does_not_depend_on():
    """The base stays neutral so anyone can clone it. An application may name what it uses: this goes with the demo."""
    word = "co" + "work"
    assert [p.name for p in repository_text_files() if word in p.read_text("utf-8", "replace").lower()] == []


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", [*PAGES, "/inspections"])
def test_no_demo_page_has_text_outside_translation(client, person, path):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get(path, headers=person).text, ALLOWED) == []


@pytest.mark.rule("SEC-02")
def test_administration_needs_its_role(client, person):
    assert client.get("/administration", headers=person).status_code == 200
    person["X-Remote-Groups"] = "staff"
    assert client.get("/administration", headers=person).status_code == 403


@pytest.mark.rule("SEC-02")
def test_navigation_shows_only_what_the_person_may_open(client, person):
    assert 'href="/administration"' in client.get("/", headers=person).text
    person["X-Remote-Groups"] = "staff"
    assert 'href="/administration"' not in client.get("/", headers=person).text


def test_the_current_page_is_marked_for_screen_readers(client, person):
    assert re.search(r'href="/settings"[^>]*aria-current="page"', client.get("/settings", headers=person).text)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "1,250.75"), ("es", "1250,75"), ("ca", "1.250,75")],
)
def test_the_dashboard_formats_numbers_for_the_language(client, person, language, expected):
    client.cookies.set("language", language)
    assert expected in client.get("/", headers=person).text


@pytest.mark.rule("LANG-09")
@pytest.mark.parametrize(("zone", "expected"), [("UTC", "7:30"), ("Europe/Madrid", "8:30")])
def test_a_moment_is_shown_in_the_applications_time_zone(person, zone, expected):
    client = TestClient(create_app(build_settings(time_zone=zone)))
    assert f"{expected}:00" in client.get("/", headers=person).text


def test_a_long_decimal_reaches_the_page_exactly(client, person):
    assert "12,500.1234567890123456789" in client.get("/", headers=person).text


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", PAGES)
def test_no_detectable_accessibility_failure(open_page, path):
    assert run_axe_in_both_themes(open_page(path, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
@pytest.mark.parametrize("path", PAGES)
def test_no_sideways_scrolling_with_longer_texts(open_page, path):
    assert not overflows_sideways(open_page(path, language=PSEUDO, width=320))


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_new_content_gets_focus_and_is_announced(open_page):
    page = open_page("/")
    page.get_by_role("button", name="Show inspections").click()
    page.wait_for_selector(":focus[data-focus]")
    assert "1 inspection is due" in page.locator("#announcements").inner_text()


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_arrangement_passes_the_scan(open_page, layout):
    assert run_axe_in_both_themes(open_page("/", layout=layout, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_arrangement_fits_a_phone(open_page, layout):
    assert not overflows_sideways(open_page("/", layout=layout, width=320))


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_the_menu_opens_on_a_phone_and_closes_with_escape(open_page):
    page = open_page("/", width=375)
    links = page.locator("#navigation a[aria-current]")
    assert not links.is_visible()
    button = page.get_by_role("button", name="Open menu")
    button.press("Enter")
    assert links.is_visible()
    page.keyboard.press("Escape")
    assert not links.is_visible()
    assert button.evaluate("element => element === document.activeElement")


@pytest.mark.browser
def test_values_are_applied_to_content_that_htmx_brings(open_page):
    page = open_page("/", bypass_csp=True)
    answer = '<div id="late" data-style="--value:42"></div>'
    page.route("**/inspections", lambda route: route.fulfill(body=answer, content_type="text/html"))
    page.get_by_role("button", name="Show inspections").click()
    page.wait_for_function("document.querySelector('#late')?.style.getPropertyValue('--value') === '42'")


def test_the_dashboard_calls_macros():
    template = (ROOT / "app" / "demo" / "templates" / "demo" / "dashboard.html").read_text(encoding="utf-8")
    assert not re.search(r'<(?:button|table)\b|class="(?:badge|stat|progress|steps)\b', template)


def test_the_dashboard_uses_real_components(client, person):
    html = client.get("/", headers=person).text
    for name in ('class="stats', 'class="stat"', 'class="badge', 'class="table"', 'class="progress', 'class="steps'):
        assert name in html


def test_the_sidebar_repeats_no_icon(client, person):
    icons = [item.icon for item in client.app.state.navigation]
    assert len(icons) == len(set(icons))


def test_the_gallery_lists_its_components_under_its_navigation_item(client, person):
    html = client.get("/gallery/button", headers=person).text
    assert re.search(r'href="/gallery/button"[^>]*aria-current="page"', html)
    assert 'href="/gallery/modal"' in html
    assert 'href="/gallery/modal"' not in client.get("/", headers=person).text
