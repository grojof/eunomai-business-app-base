"""A list's own choices, wide and dense, kept with the person's layout: on the equipment list and in Planning."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import PERSON, build_settings
from tests.demo.support import until
from tests.helpers import overflows_sideways, run_axe

DENSE = {"list_density": "dense"}
WIDE = {"list_width": "wide", "width": "centered"}


def test_a_dense_list_has_smaller_rows(filled):
    assert "table-sm" in filled.get("/equipment").text
    filled.cookies.set("layout_list_density", "dense")
    html = filled.get("/equipment").text
    assert "table-xs table-dense" in html
    assert 'name="layout_list_density" value="normal" aria-pressed="true"' in html


def test_grouped_rows_can_be_dense_too(filled):
    filled.cookies.set("layout_list_density", "dense")
    assert "table-xs table-dense" in filled.get("/planning").text


def test_a_choice_from_the_list_comes_back_to_the_same_list(filled):
    address = "/equipment?status=stopped&sort=cost"
    response = filled.post("/preferences", data={"layout_list_width": "wide", "next": address}, follow_redirects=False)
    assert response.headers["location"] == address
    assert response.cookies["layout_list_width"] == "wide"


def test_htmx_gets_the_list_alone_after_a_choice(filled):
    response = filled.post(
        "/preferences",
        data={"layout_list_density": "dense", "next": "/equipment"},
        headers={"HX-Request": "true", "HX-Trigger": "equipment-list-density"},
    )
    assert "<html" not in response.text
    assert "table-dense" in response.text


def test_an_application_that_fixes_them_offers_no_choice(filled_url):
    settings = build_settings(database_url=filled_url, layout_choices=["navigation"], layout_list_density="dense")
    client = TestClient(create_app(settings))
    client.cookies.set("layout_list_density", "normal")
    html = client.get("/equipment", headers=PERSON).text
    assert "table-dense" in html
    assert "/preferences" not in html.split("<main", 1)[1]


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", ["/equipment", "/planning"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_dense_and_wide_list_passes_the_scan(open_filled, path, theme):
    assert run_axe(open_filled(path, theme=theme, layout=DENSE | WIDE, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.parametrize("path", ["/equipment", "/planning"])
def test_a_dense_list_fits_a_phone(open_filled, path):
    assert not overflows_sideways(open_filled(path, layout=DENSE | WIDE, width=320))


@pytest.mark.browser
def test_a_dense_list_shows_more_rows_and_more_columns(open_filled):
    def seen(page):
        return page.evaluate("""() => {
            const box = document.querySelector('.table-scroll').getBoundingClientRect();
            const rows = [...document.querySelectorAll('[data-results] tbody tr')]
                .filter((row) => row.getBoundingClientRect().bottom <= box.bottom);
            const columns = [...document.querySelectorAll('[data-results] thead th')]
                .filter((cell) => cell.offsetWidth > 0);
            return [rows.length, columns.length];
        }""")

    normal = seen(open_filled("/equipment", width=700))
    dense = seen(open_filled("/equipment", width=700, layout=DENSE))
    assert dense[0] > normal[0]
    assert dense[1] > normal[1]


@pytest.mark.browser
def test_a_wide_list_uses_the_whole_width_of_a_centred_page(open_filled):
    width = "document.querySelector('main').getBoundingClientRect().width"
    narrow = open_filled("/equipment", width=1800, layout={"width": "centered"}).evaluate(width)
    wide = open_filled("/equipment", width=1800, layout=WIDE).evaluate(width)
    assert wide > narrow + 200


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_a_choice_applies_without_reloading_and_keeps_focus(open_filled):
    page = open_filled("/equipment?status=stopped")
    page.evaluate("window.notReloaded = true")
    button = page.get_by_role("button", name="Dense rows")
    button.focus()
    page.keyboard.press("Enter")
    until(page, "!!document.querySelector('.table-dense')")
    assert page.evaluate("window.notReloaded")
    assert page.evaluate("document.activeElement.id") == "equipment-list-density-button"
    assert page.get_by_role("button", name="Dense rows").get_attribute("aria-pressed") == "true"
    assert page.url.endswith("/equipment?status=stopped")
    page.get_by_role("button", name="Whole width").click()
    until(page, "!!document.querySelector('[data-list-wide]')")
    page.reload()
    assert page.locator(".table-dense").count() == 1
    assert page.locator("[data-list-wide]").count() == 1


@pytest.mark.browser
def test_a_choice_works_without_javascript(open_filled):
    page = open_filled("/equipment?status=stopped", javascript=False)
    page.get_by_role("button", name="Dense rows").click()
    page.wait_for_load_state()
    assert page.locator(".table-dense").count() == 1
    assert page.url.endswith("/equipment?status=stopped")
