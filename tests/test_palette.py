"""The command palette, in every application: opened with the keyboard, a click or a tap, and needing no service."""

import time

import pytest
from fastapi.testclient import TestClient

from app.core.i18n import PSEUDO
from app.core.templating import SearchItem, register_search
from app.main import create_app
from tests.conftest import build_settings
from tests.helpers import ANIMATIONS_FINISHED, run_axe, run_axe_in_both_themes, untranslated
from tools import translations

pages = pytest.mark.browser
ANIMATING = """document.getAnimations()
    .filter((animation) => animation.timeline === document.timeline && animation.effect.target.checkVisibility())
    .filter((animation) => animation.playState === 'running')
    .map((animation) => animation.animationName ?? animation.transitionProperty)"""
ALLOWED = ("Business App", "Demo Person")


def open_palette(page, keys="Control+k"):
    page.keyboard.press(keys)
    page.locator("#palette").wait_for(state="visible")
    page.locator("[data-palette-option]").first.wait_for(state="attached")
    return page.locator("#palette-input")


def active(page):
    return page.evaluate(
        "document.getElementById(document.getElementById('palette-input').getAttribute('aria-activedescendant'))"
        "?.querySelector('[data-palette-label]').textContent"
    )


def test_anything_registered_can_be_found(person):
    application = create_app(build_settings())
    register_search(application.state, lambda: [SearchItem("Invoices", "/invoices", "Records", "Sent and paid")])
    html = TestClient(application).get("/search", headers=person).text
    assert 'href="/invoices"' in html
    assert "Records" in html
    assert "Sent and paid" in html


def test_navigation_is_found_only_by_who_may_open_it(client, person):
    client.app.state.navigation[:0] = []
    from app.core.templating import NavigationItem

    client.app.state.navigation.append(NavigationItem("Secret", "/secret", "shield", role="auditor"))
    assert "/secret" not in client.get("/search", headers=person).text


def test_a_stranger_can_search_nothing(client):
    assert client.get("/search").status_code == 401


def test_search_results_are_escaped(person):
    application = create_app(build_settings())
    register_search(application.state, lambda: [SearchItem("<b>x</b>", "/x", "Group")])
    assert "<b>x</b>" not in TestClient(application).get("/search", headers=person).text


def test_a_path_found_twice_appears_once(person):
    application = create_app(build_settings())
    register_search(application.state, lambda: [SearchItem("Again", "/settings", "Group")])
    assert TestClient(application).get("/search", headers=person).text.count('href="/settings"') == 1


@pytest.mark.rule("LANG-01")
def test_the_palette_is_translated(client, person):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get("/search", headers=person).text, ALLOWED) == []
    assert untranslated(client.get("/", headers=person).text.split("</header>")[1], ALLOWED) == []


@pages
@pytest.mark.rule("A11Y-02")
@pytest.mark.parametrize("keys", ["Control+k", "Meta+k"])
def test_the_shortcut_opens_and_escape_returns_focus(open_page, keys):
    page = open_page("/")
    page.keyboard.press("Tab")
    before = page.evaluate("document.activeElement.outerHTML")
    field = open_palette(page, keys)
    assert field.evaluate("element => element === document.activeElement")
    page.keyboard.press("Escape")
    page.locator("#palette").wait_for(state="hidden")
    assert page.evaluate("document.activeElement.outerHTML") == before


@pages
def test_the_shortcut_closes_it_too(open_page):
    page = open_page("/")
    open_palette(page)
    page.keyboard.press("Control+k")
    page.locator("#palette").wait_for(state="hidden")


@pages
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("width", [1280, 390])
def test_the_open_palette_passes_the_scan(open_page, width):
    page = open_page("/", width=width, bypass_csp=True)
    open_palette(page)
    assert run_axe(page) == []
    page.keyboard.type("nothing like this anywhere")
    assert run_axe_in_both_themes(page) == []
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    assert run_axe(page) == []


@pages
def test_the_wait_before_a_scan_lets_what_fades_in_finish_and_no_more(open_page):
    """It waits for what changes how text looks. An open dialog also starts daisyUI's scroll-driven animation, with no
    end to wait for, and an element that is not drawn may never finish: each cost a scan its three seconds."""
    page = open_page("/")
    open_palette(page)
    started = time.monotonic()
    page.evaluate(ANIMATIONS_FINISHED)
    assert time.monotonic() - started < 1.5
    assert page.evaluate(ANIMATING) == []


@pages
def test_the_wait_does_not_wait_for_what_is_not_drawn(open_page):
    page = open_page("/", layout={"language_control": "select"})
    started = time.monotonic()
    page.evaluate(ANIMATIONS_FINISHED)
    assert time.monotonic() - started < 1.5


@pages
def test_it_follows_the_combobox_pattern(open_page):
    page = open_page("/")
    field = open_palette(page)
    assert field.get_attribute("role") == "combobox"
    assert field.get_attribute("aria-controls") == "palette-results"
    assert field.get_attribute("aria-autocomplete") == "list"
    assert page.locator("#palette-results").get_attribute("role") == "listbox"
    assert page.locator("#palette-results [role=group] [role=option]").count() > 0
    assert page.locator("#palette-results [aria-selected=true]").count() == 1


@pages
@pytest.mark.rule("A11Y-05")
def test_the_selected_option_keeps_its_colours_under_the_pointer(open_page):
    """The pointer's grey on the selected option left its light text on a light background."""
    page = open_page("/")
    open_palette(page)
    selected = page.locator("#palette-results [aria-selected=true]")
    colours = (
        "o => [getComputedStyle(o).backgroundColor, getComputedStyle(o).color,"
        " getComputedStyle(o.querySelector('.palette-icon')).color, getComputedStyle(o.querySelector('.icon')).color]"
    )
    before = selected.evaluate(colours)
    selected.hover()
    after = selected.evaluate(colours)
    assert after == before
    assert after[3] == after[2]  # the icon in its tile's colour: the option's, or the brand's turned round
    tile = "o => getComputedStyle(o.firstElementChild).backgroundColor"
    others = page.locator("#palette-results [aria-selected=false]")
    if others.count():  # an application with a single page has no other option to set it against
        assert selected.evaluate(tile) != others.first.evaluate(tile)  # not the page's grey tile under a light icon


@pages
@pytest.mark.rule("A11Y-02")
def test_arrows_move_and_wrap_and_enter_opens(open_page):
    page = open_page("/")
    open_palette(page)
    page.keyboard.type("settings")
    assert active(page) == "Settings"
    count = page.locator("[data-palette-option]:not([hidden])").count()
    page.keyboard.press("ArrowDown")
    assert count == 1 or active(page) != "Settings"
    for _ in range(count - 1):
        page.keyboard.press("ArrowDown")
    assert active(page) == "Settings"
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowDown")
    assert active(page) == "Settings"
    with page.expect_navigation():
        page.keyboard.press("Enter")
    assert page.url.endswith("/settings")


@pages
def test_no_results_says_so_and_recovers(open_page):
    page = open_page("/")
    open_palette(page)
    page.keyboard.type("zzzz")
    assert page.get_by_text("No results").is_visible()
    assert page.locator("#palette-input").get_attribute("aria-activedescendant") is None
    assert "Results: 0" in page.locator("[data-palette-status]").inner_text()
    page.keyboard.press("Enter")
    assert page.locator("#palette").is_visible()
    page.keyboard.press("Control+a")
    page.keyboard.type("set")
    assert not page.get_by_text("No results").is_visible()


@pages
def test_a_failed_search_says_so(open_page):
    page = open_page("/")
    page.route("**/search", lambda route: route.fulfill(status=500))
    page.keyboard.press("Control+k")
    page.get_by_text("Search is not available").wait_for(state="visible")


@pages
def test_a_click_opens_it_and_a_click_goes_there(open_page):
    page = open_page("/")
    page.get_by_role("button", name="Search").click()
    page.locator("[data-palette-option]").first.wait_for(state="attached")
    page.keyboard.type("settings")
    with page.expect_navigation():
        page.locator("[data-palette-option]:not([hidden])").first.click()
    assert page.url.endswith("/settings")


@pages
def test_on_a_phone_it_has_its_own_close_button(open_page):
    page = open_page("/", width=390)
    page.get_by_role("button", name="Search").click()
    page.locator("#palette").wait_for(state="visible")
    page.get_by_role("button", name="Close").first.click()
    page.locator("#palette").wait_for(state="hidden")


@pages
def test_the_button_shows_the_shortcut_for_the_platform(browser, base_url):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'userAgentData', {get: () => ({platform: 'macOS'})});")
    page.goto(base_url)
    assert page.locator("[data-shortcut]").inner_text() == "⌘ K"
    context.close()


@pages
@pytest.mark.skipif("es" not in translations.REQUIRED, reason="it reads the Spanish text; this application has none")
def test_it_is_in_the_language_of_the_page(open_page):
    page = open_page("/", language="es")
    page.keyboard.press("Control+k")
    assert page.locator("#palette-input").get_attribute("placeholder") == "Escribe para buscar"
