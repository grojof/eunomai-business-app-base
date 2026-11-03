"""The demo through `[preview]`: real screens on real rows, from a copy with no `.env`, on a person's computer."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.database import create_database_engine
from app.demo.generate import equipment_row
from app.demo.models import Equipment
from tests.helpers import fetch, preview_running, repository_copy


@pytest.fixture(scope="module")
def first(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Path, int]]:
    folder = tmp_path_factory.mktemp("preview")
    with preview_running(repository_copy(folder / "application")) as started:
        yield folder, started


@pytest.fixture(scope="module")
def port(first: tuple[Path, int]) -> int:
    return first[1]


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


def test_a_new_version_keeps_what_was_saved(first, tmp_path):
    """The connector starts each version from a new copy, with the same kept folder: the rows stay, and are not made
    again."""
    folder, _port = first
    engine = create_database_engine(f"sqlite:///{(folder / 'kept' / 'preview.db').as_posix()}")
    with Session(engine) as session:
        row = equipment_row(50_000)
        del row["id"]
        session.execute(insert(Equipment), [row])
        session.commit()
    engine.dispose()
    with preview_running(repository_copy(tmp_path / "application"), folder / "kept") as port:
        status, html = fetch(port, "/equipment")
    assert status == 200
    assert "50,001 pieces of equipment" in html
