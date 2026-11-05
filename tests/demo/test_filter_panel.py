"""Planning's filters in a side panel that can be hidden, with its state in the address."""

import re

import pytest

from app.core.i18n import PSEUDO
from tests.demo.support import until
from tests.helpers import overflows_sideways, run_axe_in_both_themes

TOGGLE = "#planning-filter-toggle"
PANEL = "#planning-filter-panel"


def expanded(page):
    return page.locator(TOGGLE).get_attribute("aria-expanded")


def test_the_panel_state_travels_with_every_link(filled):
    html = filled.get("/planning?panel=hidden&status=planned").text
    assert '<aside id="planning-filter-panel"' in html
    assert re.search(r'<aside id="planning-filter-panel"[^>]* hidden>', html)
    assert 'href="/planning?status=planned&amp;sort=equipment&amp;panel=hidden"' in html
    assert '<input type="hidden" name="panel" value="hidden">' in html


def test_a_panel_state_that_is_not_one_is_ignored(filled):
    html = filled.get("/planning?panel=sideways").text
    assert "hidden xl:block" in html


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", ["/planning", "/planning?panel=hidden", "/planning?panel=shown&status=closed"])
@pytest.mark.parametrize("width", [1440, 375])
def test_the_panel_passes_the_scan(open_filled, path, width):
    assert run_axe_in_both_themes(open_filled(path, width=width, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
@pytest.mark.parametrize("path", ["/planning", "/planning?panel=shown"])
def test_the_panel_fits_a_phone_with_longer_texts(open_filled, path):
    assert not overflows_sideways(open_filled(path, language=PSEUDO, width=320))


@pytest.mark.browser
def test_on_a_phone_the_panel_waits_for_its_button(open_filled):
    page = open_filled("/planning", width=375)
    assert not page.locator(PANEL).is_visible()
    assert expanded(page) == "false"
    table = page.locator(".table-scroll").bounding_box()
    assert table["y"] < 400


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
@pytest.mark.rule("USE-05")
def test_the_button_hides_and_shows_the_panel_and_the_address_keeps_it(open_filled):
    page = open_filled("/planning?status=planned", width=1440)
    page.evaluate("window.notReloaded = true")
    assert page.locator(PANEL).is_visible()
    assert expanded(page) == "true"
    page.locator(TOGGLE).focus()
    page.keyboard.press("Enter")
    until(page, f"!document.querySelector('{PANEL}').checkVisibility()")
    until(page, f"document.querySelector('{TOGGLE}').getAttribute('aria-expanded') === 'false'")
    assert page.url.endswith("/planning?status=planned&panel=hidden")
    assert page.evaluate("document.activeElement.id") == "planning-filter-toggle"
    assert page.evaluate("window.notReloaded")
    page.locator("#planning-sort-hours").click()
    page.wait_for_url(re.compile(r"sort=hours.*panel=hidden"))
    assert not page.locator(PANEL).is_visible()
    page.reload()
    assert not page.locator(PANEL).is_visible()
    page.locator(TOGGLE).click()
    until(page, f"document.querySelector('{PANEL}').checkVisibility()")
    assert expanded(page) == "true"
    assert "panel=shown" in page.url


@pytest.mark.browser
def test_on_a_phone_the_button_opens_the_panel_and_its_filters_work(open_filled):
    page = open_filled("/planning", width=375)
    page.locator(TOGGLE).click()
    until(page, f"document.querySelector('{PANEL}').checkVisibility()")
    assert expanded(page) == "true"
    page.select_option("#planning-status", "planned")
    page.wait_for_url(re.compile(r"status=planned"))
    assert "panel=shown" in page.url
    assert page.locator(PANEL).is_visible()


@pytest.mark.browser
@pytest.mark.parametrize(("width", "link", "visible"), [(375, "Show filters", True), (1440, "Hide filters", False)])
def test_without_javascript_a_link_does_it(open_filled, width, link, visible):
    page = open_filled("/planning", width=width, javascript=False)
    assert page.locator(PANEL).is_visible() is not visible
    page.get_by_role("link", name=link).click()
    page.wait_for_load_state()
    assert page.locator(PANEL).is_visible() is visible
    page.locator(PANEL).get_by_role("button", name="Apply").is_visible()
