"""Two people editing one row: the second to save is told, keeps what was typed, and chooses."""

import io
import re
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import create_database_engine
from app.demo import planning, work_orders
from app.demo.models import WorkOrder, WorkOrderFile
from app.main import create_app
from tests.conftest import build_settings, page_opener, running_server
from tests.demo.support import fill, until
from tests.helpers import ROOT, run_axe

HTMX = {"HX-Request": "true"}
SAME_SITE = {"Sec-Fetch-Site": "same-origin"}
PDF = b"%PDF-1.7\n1 0 obj\n"
PLANNING = "/planning/1"
FORM = "/work-orders/1"


def plan(**changes):
    return {
        "status": "planned",
        "planned_on": "2027-01-15",
        "hours": "7.5",
        "back": "/planning",
        "version": "1",
    } | changes


def whole(**changes):
    return {
        "title": "Replace the belt",
        "equipment": "EQ-000001",
        "description": "Mine.",
        "fault": "",
        "status": "planned",
        "priority": "normal",
        "planned_on": "2027-01-15",
        "hours": "7.5",
        "crew": "2",
        "cost": "120.50",
        "back": "/planning",
        "version": "1",
    } | changes


@pytest.fixture
def writable(database_url, tmp_path):
    fill(database_url, 100)
    settings = build_settings(database_url=database_url, upload_folder=tmp_path / "files")
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    client.headers.update({"X-Remote-User": "demo.person", "X-Remote-Name": "Demo Person", "X-Remote-Groups": "admins"})
    yield client, database_url, tmp_path / "files"


def read_order(url, number=1):
    engine = create_database_engine(url)
    with Session(engine) as session:
        order = session.get(WorkOrder, number)
    engine.dispose()
    return order


def someone_else_saves(url, **values):
    """Another person's save, as SQLAlchemy's version counter makes it."""
    engine = create_database_engine(url)
    with Session(engine) as session:
        order = session.get(WorkOrder, 1)
        for name, value in values.items():
            setattr(order, name, value)
        session.commit()
    engine.dispose()


def save(client, address, form, **options):
    return client.post(address, data=form, headers=SAME_SITE | options.pop("headers", {}), **options)


def test_a_row_starts_at_one_and_a_save_moves_it_on(writable):
    client, url, _files = writable
    assert read_order(url).version == 1
    save(client, PLANNING, plan(hours="3"))
    assert read_order(url).version == 2


def test_a_save_that_changes_nothing_moves_nothing(writable):
    client, url, _files = writable
    save(client, PLANNING, plan())
    save(client, PLANNING, plan(version="2"))
    assert read_order(url).version == 2


@pytest.mark.parametrize("path", ["/planning/1/edit", "/work-orders/1/edit"])
def test_a_form_carries_the_version_it_was_read_at(writable, path):
    client, url, _files = writable
    someone_else_saves(url, title="Theirs")
    assert '<input type="hidden" name="version" value="2">' in client.get(path).text


def test_a_second_save_on_planning_is_told_and_keeps_what_was_typed(writable):
    client, url, _files = writable
    someone_else_saves(url, hours=Decimal("99"))
    response = save(client, PLANNING, plan(hours="3.5"))
    assert response.status_code == 409
    assert "Someone else changed this work order" in response.text
    assert 'value="3.5"' in response.text
    assert read_order(url).hours == Decimal("99")


def test_the_conflict_says_what_is_saved_now(writable):
    client, url, _files = writable
    someone_else_saves(url, hours=Decimal("99"), status="checked")
    html = save(client, PLANNING, plan(hours="3.5")).text
    assert "99.00" in html.split("Someone else changed", 1)[1].split("</dl>", 1)[0]
    assert "Checked" in html.split("Someone else changed", 1)[1].split("</dl>", 1)[0]


def test_saving_again_after_being_told_replaces_it_on_purpose(writable):
    client, url, _files = writable
    someone_else_saves(url, hours=Decimal("99"))
    html = save(client, PLANNING, plan(hours="3.5")).text
    newest = re.search(r'name="version" value="(\d+)"', html)[1]
    assert newest == "2"
    assert save(client, PLANNING, plan(hours="3.5", version=newest), follow_redirects=False).status_code == 303
    assert read_order(url).hours == Decimal("3.5")


def test_htmx_gets_the_conflict_in_the_dialog(writable):
    client, url, _files = writable
    someone_else_saves(url, hours=Decimal("99"))
    response = save(client, PLANNING, plan(), headers=HTMX)
    assert response.status_code == 200
    assert "<html" not in response.text
    assert "data-focus" in response.text
    assert "Someone else changed" in response.text


@pytest.mark.parametrize("version", ["", "x", "-1", "99999999999999999999", "٣"])
def test_a_version_that_cannot_be_read_saves_nothing(writable, version):
    client, url, _files = writable
    assert save(client, PLANNING, plan(hours="3.5", version=version)).status_code == 409
    assert read_order(url).version == 1


def test_a_late_save_that_says_the_same_as_the_row_is_no_conflict(writable):
    """A double click, or two people who agree: there is nothing to choose between."""
    client, url, _files = writable
    assert save(client, PLANNING, plan(hours="3.5"), follow_redirects=False).status_code == 303
    assert save(client, PLANNING, plan(hours="3.5"), follow_redirects=False).status_code == 303
    assert read_order(url).version == 2


def test_errors_come_before_a_conflict_and_keep_the_old_version(writable):
    client, url, _files = writable
    someone_else_saves(url, hours=Decimal("99"))
    response = save(client, PLANNING, plan(hours="many"))
    assert response.status_code == 422
    assert '<input type="hidden" name="version" value="1">' in response.text


@pytest.mark.parametrize(
    ("patched", "address", "form"),
    [(planning, PLANNING, plan()), (work_orders, FORM, whole())],
    ids=["planning", "form"],
)
def test_a_save_that_gets_in_between_reading_and_writing_is_caught_by_the_database(
    writable, monkeypatch, patched, address, form
):
    """Both read the same version. Only the `WHERE version` of the UPDATE can tell, on either database."""
    client, url, _files = writable
    real = patched.checked

    def another_save_meanwhile(*arguments):
        result = real(*arguments)
        someone_else_saves(url, hours=Decimal("99"))
        return result

    monkeypatch.setattr(patched, "checked", another_save_meanwhile)
    response = save(client, address, form)
    assert response.status_code == 409
    assert "Someone else changed" in response.text
    assert read_order(url).hours == Decimal("99")


def test_a_row_deleted_in_between_is_still_not_found(writable, monkeypatch):
    client, url, _files = writable
    real = planning.checked

    def deleted_meanwhile(*arguments):
        result = real(*arguments)
        engine = create_database_engine(url)
        with engine.begin() as connection:
            connection.execute(update(WorkOrder).where(WorkOrder.id == 1).values(version=5))
            connection.execute(WorkOrder.__table__.delete().where(WorkOrder.id == 1))
        engine.dispose()
        return result

    monkeypatch.setattr(planning, "checked", deleted_meanwhile)
    assert save(client, PLANNING, plan()).status_code == 404


def test_the_whole_form_has_the_same_answer_and_keeps_every_field(writable):
    client, url, _files = writable
    someone_else_saves(url, title="Theirs", crew=7)
    response = save(client, FORM, whole(title="Mine", description="Typed by me"))
    assert response.status_code == 409
    assert 'value="Mine"' in response.text
    assert ">Typed by me</textarea>" in response.text
    told = response.text.split("Someone else changed", 1)[1].split("</dl>", 1)[0]
    assert "Theirs" in told
    assert "7" in told
    assert read_order(url).title == "Theirs"


def test_a_file_sent_with_a_conflict_is_not_kept_and_the_form_says_to_choose_it_again(writable):
    client, url, folder = writable
    someone_else_saves(url, title="Theirs")
    files = {"attachment": ("report.pdf", PDF, "application/pdf")}
    response = client.post(FORM, data=whole(title="Mine"), files=files, headers=SAME_SITE)
    assert response.status_code == 409
    assert "Choose the file again" in response.text
    assert not folder.exists() or not list(folder.iterdir())


def test_two_people_can_each_add_a_file(writable):
    client, url, _files = writable
    files = {"attachment": ("report.pdf", PDF, "application/pdf")}
    same = whole(title=read_order(url).title, status=read_order(url).status)
    first = client.post(FORM, data=same, files=files, headers=SAME_SITE, follow_redirects=False)
    second = client.post(FORM, data=same, files=files, headers=SAME_SITE, follow_redirects=False)
    assert (first.status_code, second.status_code) == (303, 303)
    engine = create_database_engine(url)
    with Session(engine) as session:
        assert len(session.scalars(select(WorkOrderFile)).all()) == 2
    engine.dispose()


def test_a_delete_that_comes_late_shows_what_is_there_now(writable):
    client, url, _files = writable
    someone_else_saves(url, title="Theirs")
    response = save(client, "/work-orders/1/delete", {"back": "/planning", "version": "1"})
    assert response.status_code == 409
    assert "<li>Theirs, on " in response.text
    assert "changed since" in response.text
    assert '<input type="hidden" name="version" value="2">' in response.text
    assert read_order(url) is not None
    done = save(client, "/work-orders/1/delete", {"back": "/planning", "version": "2"}, follow_redirects=False)
    assert done.status_code == 303
    assert read_order(url) is None


def test_a_delete_that_gets_in_between_is_caught_too(writable, monkeypatch):
    client, url, _files = writable
    real = work_orders.read_version

    def another_save_meanwhile(text):
        result = real(text)
        someone_else_saves(url, title="Theirs")
        return result

    monkeypatch.setattr(work_orders, "read_version", another_save_meanwhile)
    assert save(client, "/work-orders/1/delete", {"back": "/planning", "version": "1"}).status_code == 409
    assert read_order(url).title == "Theirs"


@pytest.fixture
def two_people(browser, tmp_path):
    url = f"sqlite:///{(tmp_path / 'orders.db').as_posix()}"
    fill(url, 200)
    settings = build_settings(database_url=url, fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port, page_opener(browser, f"http://127.0.0.1:{port}") as opener:
        yield opener


def open_row(page, number):
    page.locator(f"#edit-{number}").click()
    page.wait_for_selector("dialog[open] form")


@pytest.mark.browser
@pytest.mark.rule("USE-03")
@pytest.mark.rule("A11Y-09")
def test_in_two_browsers_the_second_is_told_in_the_dialog_with_focus_and_what_was_typed(two_people):
    first = two_people("/planning?sort=number")
    second = two_people("/planning?sort=number")
    number = first.locator("[id^=edit-]").first.get_attribute("id").removeprefix("edit-")
    open_row(first, number)
    open_row(second, number)
    first.locator("dialog input[name=hours]").fill("3.5")
    first.get_by_role("button", name="Save").click()
    until(first, "!document.querySelector('dialog').open")

    second.locator("dialog input[name=hours]").fill("8.25")
    second.get_by_role("button", name="Save").click()
    second.wait_for_selector("dialog [role=alert]")
    until(second, "document.activeElement.closest('[role=alert]') !== null")
    assert "3.50" in second.locator("dialog [role=alert]").inner_text()
    assert second.locator("dialog input[name=hours]").input_value() == "8.25"

    second.get_by_role("button", name="Save").click()
    until(second, "!document.querySelector('dialog').open")
    until(second, f"document.querySelector('#edit-{number}').closest('tr').textContent.includes('8.25')")


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 390])
def test_the_conflict_passes_the_scan(two_people, theme, width):
    first = two_people("/work-orders/1/edit", theme=theme, width=width, bypass_csp=True)
    second = two_people("/work-orders/1/edit")
    second.locator("#field-title").fill("Theirs")
    second.get_by_role("button", name="Save").click()
    second.wait_for_url("**/planning*")

    first.locator("#field-title").fill("Mine")
    first.get_by_role("button", name="Save").click()
    first.wait_for_selector("#work-order [role=alert]")
    assert "Theirs" in first.locator("#work-order [role=alert]").inner_text()
    assert first.locator("#field-title").input_value() == "Mine"
    assert run_axe(first) == []


@pytest.mark.browser
def test_without_javascript_the_second_is_told_on_the_page(two_people):
    first = two_people("/work-orders/1/edit", javascript=False)
    second = two_people("/work-orders/1/edit")
    second.locator("#field-title").fill("Theirs")
    second.get_by_role("button", name="Save").click()
    second.wait_for_url("**/planning*")

    first.locator("#field-title").fill("Mine")
    first.get_by_role("button", name="Save").click()
    first.wait_for_selector("#work-order [role=alert]")
    assert "Someone else changed" in first.locator("#work-order [role=alert]").inner_text()
    assert first.locator("#field-title").input_value() == "Mine"


def test_every_migration_compiles_for_postgresql_with_no_server():
    """Here and on any computer: nothing connects. The Ubuntu job runs them on a real one."""
    config = Config(toml_file=str(ROOT / "pyproject.toml"))
    config.attributes["database_url"] = "postgresql+psycopg://application@localhost/application"
    config.output_buffer = io.StringIO()
    command.upgrade(config, "head", sql=True)
    sql = config.output_buffer.getvalue()
    assert "CREATE TABLE work_order " in sql
    assert "ALTER TABLE work_order ADD COLUMN version INTEGER DEFAULT '1' NOT NULL" in sql
    assert "ADD COLUMN stop_needed BOOLEAN DEFAULT false NOT NULL" in sql
