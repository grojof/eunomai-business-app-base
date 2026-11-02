"""A chart that filters a list: on the dashboard it leads to the list, on the equipment page it filters it in place."""

import re

import pytest

from app.core.i18n import PSEUDO
from tests.demo.support import announced, until
from tests.helpers import overflows_sideways, run_axe

CHARTS_READY = "document.documentElement.dataset.chartsReady !== undefined"
PLACES = "#figure-locations-summary"


def click_part(page, summary, index):
    """Clicks the middle of one bar or slice, where a person would."""
    point = page.evaluate(
        """([summary, index]) => {
            const canvas = document.querySelector(summary).closest('figure').querySelector('canvas');
            const element = Chart.getChart(canvas).getDatasetMeta(0).data[index];
            const { x, y } = element.tooltipPosition();
            const box = canvas.getBoundingClientRect();
            return [box.x + x, box.y + y + 4];
        }""",
        [summary, index],
    )
    page.mouse.click(*point)


def test_the_equipment_page_has_charts_whose_tables_filter_it(filled):
    html = filled.get("/equipment?status=stopped").text
    assert 'id="figure-locations-link-1"' in html
    assert 'hx-include="#equipment-filters"' in html
    assert 'href="/equipment?status=stopped&amp;location=' in html


def test_the_list_alone_comes_back_without_its_charts(filled):
    html = filled.get("/equipment?location=Roof", headers={"HX-Request": "true"}).text
    assert "data-chart" not in html


def test_the_dashboard_leads_from_each_state_to_its_list(filled):
    html = filled.get("/").text
    assert 'href="/equipment?status=stopped"' in html


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-10")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_equipment_page_with_its_charts_passes_the_scan(open_filled, theme):
    page = open_filled("/equipment", theme=theme, bypass_csp=True)
    until(page, CHARTS_READY)
    page.locator(f"{PLACES} >> xpath=ancestor::figure//summary").click()
    assert run_axe(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
def test_the_equipment_page_fits_a_phone(open_filled):
    page = open_filled("/equipment", language=PSEUDO, width=320)
    until(page, CHARTS_READY)
    assert not overflows_sideways(page)


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
@pytest.mark.rule("USE-05")
def test_a_bar_filters_the_list_in_place_and_keeps_its_other_filters(open_filled):
    page = open_filled("/equipment?status=stopped&sort=cost")
    until(page, CHARTS_READY)
    page.evaluate("window.notReloaded = true")
    place = page.locator("#figure-locations-link-2").text_content()
    click_part(page, PLACES, 1)
    until(page, "location.search.includes('location=')")
    assert re.search(r"status=stopped.*location=.*sort=cost", page.url)
    assert page.evaluate("window.notReloaded")
    assert page.locator("#equipment-location option:checked").inner_text() == place
    assert page.locator("#equipment-status").input_value() == "stopped"
    announced(page, "sorted by Cost")
    assert page.locator(PLACES).count() == 1


@pytest.mark.browser
def test_the_pointer_says_a_part_can_be_chosen(open_filled):
    page = open_filled("/equipment")
    until(page, CHARTS_READY)
    canvas = page.locator(PLACES).locator("xpath=ancestor::figure//canvas")
    box = canvas.bounding_box()
    page.mouse.move(box["x"] + 2, box["y"] + 2)
    assert canvas.evaluate("element => element.style.cursor") == ""
    point = canvas.evaluate(
        """(canvas) => {
            const { x, y } = Chart.getChart(canvas).getDatasetMeta(0).data[0].tooltipPosition();
            const box = canvas.getBoundingClientRect();
            return [box.x + x, box.y + y + 4];
        }"""
    )
    page.mouse.move(*point)
    until(page, f"document.querySelector('{PLACES}').closest('figure').querySelector('canvas').style.cursor")
    assert canvas.evaluate("element => element.style.cursor") == "pointer"


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_the_keyboard_filters_through_the_charts_table(open_filled):
    page = open_filled("/equipment")
    until(page, CHARTS_READY)
    summary = page.locator("#figure-states-summary").locator("xpath=ancestor::figure//summary")
    summary.focus()
    page.keyboard.press("Enter")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "figure-states-link-1"
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r"status=in_service"))
    assert page.evaluate("document.activeElement.id") == "figure-states-link-1"
    assert page.locator("#equipment-status").input_value() == "in_service"


@pytest.mark.browser
def test_a_slice_on_the_dashboard_leads_to_its_list(open_filled):
    page = open_filled("/")
    until(page, CHARTS_READY)
    click_part(page, "#figure-states-summary", 2)
    page.wait_for_url("**/equipment?status=stopped")
    assert page.locator("#equipment-status").input_value() == "stopped"


@pytest.mark.browser
def test_without_javascript_the_tables_links_lead_there(open_filled):
    page = open_filled("/equipment?status=stopped", javascript=False)
    page.locator("#figure-locations-summary").locator("xpath=ancestor::figure//summary").click()
    page.locator("#figure-locations-link-1").click()
    page.wait_for_url(re.compile(r"status=stopped&location="))
    assert page.locator("#equipment-status").input_value() == "stopped"
