"""Checks that need a real browser. They use the Chrome already on the computer: nothing is downloaded."""

import pytest

from app.core.i18n import PSEUDO
from tests.helpers import focus_order, overflows_sideways, run_axe

pytestmark = pytest.mark.browser
PAGES = ["/", "/missing"]


@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_detectable_accessibility_failure(open_page, path, theme):
    page = open_page(path, theme=theme, bypass_csp=True)
    assert run_axe(page) == []


@pytest.mark.rule("A11Y-13")
@pytest.mark.rule("A11Y-02")
@pytest.mark.rule("A11Y-04")
def test_the_skip_link_comes_first_and_moves_focus_to_the_content(open_page):
    page = open_page("/")
    page.keyboard.press("Tab")
    link = page.locator(":focus")
    assert "Skip to content" in link.inner_text()
    box = link.bounding_box()
    assert box["y"] >= 0
    assert link.evaluate("element => getComputedStyle(element).outlineStyle") != "none"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"


@pytest.mark.rule("A11Y-02")
@pytest.mark.rule("A11Y-04")
def test_every_control_is_reached_by_keyboard_with_visible_focus(open_page):
    page = open_page("/")
    expected = page.locator("a[href]:visible, button:visible, summary:visible").count()
    reached = 0
    for _ in range(expected + 2):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.tagName") == "BODY":
            break
        reached += 1
        if page.evaluate("document.activeElement.id") != "main":
            assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
    assert reached >= expected


@pytest.mark.rule("A11Y-04")
def test_the_scroll_padding_clears_the_sticky_header(open_page):
    page = open_page("/")
    padding = page.evaluate("parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop)")
    assert padding >= page.evaluate("document.querySelector('body header').getBoundingClientRect().height")


@pytest.mark.rule("A11Y-02")
def test_focus_follows_the_order_of_the_page(open_page):
    expected, reached = focus_order(open_page("/"))
    assert len(expected) > 1
    assert reached == expected


@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("language", ["en", "ca", PSEUDO])
def test_no_sideways_scrolling_at_320_pixels_even_with_longer_texts(open_page, path, language):
    assert not overflows_sideways(open_page(path, language=language, width=320))


@pytest.mark.rule("USE-09")
def test_the_theme_follows_the_system_and_a_choice_overrides_it(open_page):
    page = open_page("/", theme="system")
    page.emulate_media(color_scheme="dark")
    dark_system = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.emulate_media(color_scheme="light")
    light_system = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert dark_system != light_system

    page = open_page("/", theme="dark")
    page.emulate_media(color_scheme="light")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == dark_system


@pytest.mark.rule("SEC-06")
def test_the_page_works_under_its_own_security_policy(open_page):
    problems = []
    page = open_page("/")
    page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.evaluate("typeof htmx") == "object"
    assert [p for p in problems if "401" not in p and "favicon" not in p] == []


@pytest.mark.rule("SEC-14")
def test_the_browser_refuses_to_run_text_as_code(open_page):
    page = open_page("/")
    # After a pause, as a page's own code would run: Chrome lets its automation tool evaluate directly.
    result = page.evaluate("""async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
        try { eval("1 + 1"); return "ran"; } catch (error) { return error.name; }
    }""")
    assert result == "EvalError"


@pytest.mark.rule("SEC-14")
def test_htmx_has_evaluation_turned_off(open_page):
    page = open_page("/")
    page.wait_for_load_state("networkidle")
    assert page.evaluate("htmx.config.allowEval") is False


@pytest.mark.rule("SEC-06")
def test_htmx_never_writes_a_style_attribute(open_page):
    """It would copy `style` onto swapped elements, which the policy refuses."""
    page = open_page("/")
    page.wait_for_load_state("networkidle")
    assert "style" not in page.evaluate("htmx.config.attributesToSettle")


@pytest.mark.rule("A11Y-02")
def test_escape_closes_the_user_menu_and_returns_to_its_button(open_page):
    page = open_page("/")
    summary = page.get_by_text("Demo User").locator("xpath=ancestor::summary")
    link = page.locator('details[data-menu] a[href="/settings"]')
    summary.press("Enter")
    assert link.is_visible()
    page.keyboard.press("Escape")
    assert not link.is_visible()
    assert summary.evaluate("element => element === document.activeElement")


def test_a_person_can_change_the_language_with_the_keyboard(open_page):
    page = open_page("/", language="en")
    page.locator("[data-preferences='header-language'] summary").press("Enter")
    with page.expect_navigation():
        page.locator('[data-preferences="header-language"] button[value="es"]').press("Enter")
    assert page.locator("html").get_attribute("lang") == "es"
