"""The demo through `[preview]`: real screens on real rows, from a copy with no `.env`, on a person's computer."""

from collections.abc import Iterator
from typing import Any

import pytest

from tests.helpers import fetch, preview_running, repository_copy


@pytest.fixture(scope="module")
def port(tmp_path_factory: pytest.TempPathFactory) -> Iterator[int]:
    with preview_running(repository_copy(tmp_path_factory.mktemp("preview") / "application")) as started:
        yield started


def test_the_list_has_its_rows(port):
    status, html = fetch(port, "/equipment")
    assert status == 200
    assert "50,000 pieces of equipment" in html
    assert "EQ-000001" in html


def test_the_made_up_person_is_an_administrator(port):
    assert fetch(port, "/administration")[0] == 200


def test_the_form_opens(port):
    status, html = fetch(port, "/work-orders/new")
    assert status == 200
    assert 'id="field-title"' in html


@pytest.mark.browser
def test_a_person_saves_a_work_order(browser: Any, port):
    context = browser.new_context(locale="en-US")
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{port}/work-orders/new?back=%2Fplanning")
    page.locator("#field-title").fill("Replace the belt")
    page.locator("#field-equipment").fill("EQ-000001")
    page.locator("#field-description").fill("It slips.")
    page.locator("#field-fault").fill("belt")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.get_by_role("radio", name="High").check()
    page.get_by_role("button", name="Save").click()
    page.get_by_text(" saved.").first.wait_for()
    assert "/planning" in page.url
    context.close()
