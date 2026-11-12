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
    {"bar": "brand"},
    {"navigation": "top", "bar": "brand"},
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


@pytest.mark.browser
@pytest.mark.parametrize("navigation", ["side", "top"])
def test_the_brands_colours_reach_the_bar_and_the_menu(open_page, navigation):
    """With the brand's colours the bar and the menu are drawn in the theme called bar, together; else neither is."""
    background = "element => getComputedStyle(element).backgroundColor"
    page = open_page("/", layout={"navigation": navigation, "bar": "brand"})
    bar = page.locator("header.app-bar")
    assert bar.get_attribute("data-theme") == "bar"
    assert bar.evaluate(background) != page.locator("main .card, main section").first.evaluate(background)
    if navigation == "side":
        assert page.locator("#navigation").evaluate(background) == bar.evaluate(background)
    logo = page.locator("#navigation img:visible" if navigation == "side" else "header.app-bar img").first
    assert logo.evaluate("i => new URL(i.currentSrc).pathname") == "/static/brand/logo-bar-full.svg"
    plain = open_page("/", layout={"navigation": navigation})
    assert plain.locator("header.app-bar").get_attribute("data-theme") is None


@pytest.mark.browser
def test_the_brands_roles_reach_the_focus_the_menu_and_the_icons_only_menu(open_page):
    page = open_page("/", layout={"navigation": "side"})
    page.evaluate(
        "const root = document.documentElement.style;"
        "root.setProperty('--app-focus-color', 'rgb(255, 0, 0)'); root.setProperty('--app-focus-width', '3px');"
        "root.setProperty('--app-selected', 'rgb(0, 128, 0)');"
        "root.setProperty('--app-selected-content', 'rgb(0, 0, 0)')"
    )
    current = page.locator("#navigation a[aria-current]")
    # daisyUI eases a menu item's colours, so the new one is read once it has arrived
    page.wait_for_function(
        "() => getComputedStyle(document.querySelector('#navigation a[aria-current]')).backgroundColor"
        " === 'rgb(0, 128, 0)'"
    )
    current.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    focused = "() => ['outlineColor', 'outlineWidth'].map((name) => getComputedStyle(document.activeElement)[name])"
    assert page.evaluate(focused) == ["rgb(255, 0, 0)", "3px"]
    page = open_page("/", layout={"navigation": "compact"})
    page.evaluate("document.documentElement.style.setProperty('--app-nav-width-compact', '5rem')")
    assert page.locator("#navigation").evaluate("n => n.getBoundingClientRect().width") == 80


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_an_icons_name_shows_on_hover_and_focus_and_escape_hides_it(open_page):
    """WCAG 1.4.13: shown by the pointer or the keyboard, it stays while the pointer moves onto it; Escape hides it."""
    page = open_page("/", layout={"navigation": "compact"})
    tip = page.locator(".nav-tip")
    link = page.locator("#navigation a[href='/settings']")
    link.hover()
    assert tip.is_visible() and tip.text_content() == "Settings"
    tip.hover()
    assert tip.is_visible()
    page.keyboard.press("Escape")
    assert not tip.is_visible()
    link.focus()
    assert tip.is_visible() and tip.get_attribute("aria-hidden") == "true"
    page.locator("main").click(position={"x": 5, "y": 5})  # the focus leaves the link
    link.hover()
    page.keyboard.press("Escape")
    link.hover(position={"x": 4, "y": 4})  # the pointer moves within the link: dismissed means dismissed
    assert not tip.is_visible()
    page.mouse.move(600, 400)
    link.hover()
    assert tip.is_visible()  # back once the pointer has left and returned
    page.evaluate("window.scrollBy(0, 200)")
    tip.wait_for(state="hidden")  # a scroll would leave it beside nothing
    page = open_page("/", layout={"navigation": "side"})
    page.locator("#navigation a[href='/settings']").hover()
    assert not page.locator(".nav-tip").is_visible()  # a wide menu shows its names already


@pytest.mark.browser
def test_with_the_title_in_the_bar_the_trail_goes_there_too(open_page):
    page = open_page("/gallery/badge", layout={"navigation": "side", "page_title": "header"})
    trail = page.locator("header.app-bar nav.breadcrumbs")
    assert trail.get_by_role("link", name="Gallery").is_visible()
    assert not page.locator("main nav.breadcrumbs").is_visible()  # not twice
    page = open_page("/gallery/badge", layout={"navigation": "side", "page_title": "page"})
    assert page.locator("header.app-bar nav.breadcrumbs").count() == 0
    assert page.locator("main nav.breadcrumbs").is_visible()


@pytest.mark.browser
@pytest.mark.parametrize(("navigation", "bar"), [("side", "plain"), ("side", "brand"), ("compact", "brand")])
def test_the_side_menus_logo_lines_up_with_the_top_bar(open_page, navigation, bar):
    """The menu's logo and the bar beside it end on one line, and the logo sits in the bar's middle."""
    page = open_page("/", layout={"navigation": navigation, "bar": bar})
    top_bar = page.locator("header.app-bar").bounding_box()
    block = page.locator("#navigation .app-nav-logo").bounding_box()
    logo = page.locator("#navigation .app-logo:visible").bounding_box()
    assert top_bar and block and logo
    assert abs((block["y"] + block["height"]) - (top_bar["y"] + top_bar["height"])) <= 1
    assert abs((logo["y"] + logo["height"] / 2) - (top_bar["y"] + top_bar["height"] / 2)) <= 2


@pytest.mark.browser
def test_on_a_phone_the_trail_stays_in_the_page(open_page):
    """The bar has no room for it there: it is never lost, nor shown twice."""
    page = open_page("/gallery/badge", layout={"navigation": "side", "page_title": "header"}, width=375)
    assert page.locator("main nav.breadcrumbs").is_visible()
    assert not page.locator("header.app-bar nav.breadcrumbs").is_visible()
