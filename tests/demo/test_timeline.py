"""Planning's timeline: the same rows as the table, as bars beside it, drawn on the server."""

import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.core.database import create_database_engine
from app.core.i18n import PSEUDO
from app.demo.models import Equipment, WorkOrder
from app.main import create_app
from tests.conftest import PERSON, build_settings, page_opener, running_server
from tests.demo.support import announced, fill, until
from tests.helpers import overflows_sideways, run_axe_in_both_themes, untranslated

TIMELINE = "/planning?show=timeline&location=Roof"
ALLOWED = ("Business App", "Demo Person", "Air compressor", "Conveyor belt", "Standby generator", "Cooling tower")
ALLOWED += ("Forklift", "Preventive plan", "Safety checks", "Oil change", "Filter replacement", "Belt replacement")
ALLOWED += ("Calibration", "Leak repair", "Electrical inspection", "January", "February", "March", "April", "May")
ALLOWED += ("June", "July", "August", "September", "October", "November", "December", "Jan ", "Feb ", "Mar ", "Apr ")
ALLOWED += ("Jun ", "Jul ", "Aug ", "Sep ", "Oct ", "Nov ", "Dec ")
ALLOWED += ("Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")  # a month scale's ticks


def a_waiting_pair(url):
    """An open order and the open order it waits for, and the equipment they share."""
    engine = create_database_engine(url)
    before = aliased(WorkOrder)
    with Session(engine) as session:
        row = session.execute(
            select(WorkOrder.id, before.id, Equipment.name)
            .join(before, before.id == WorkOrder.after_id)
            .join(Equipment, Equipment.id == WorkOrder.equipment_id)
            .where(WorkOrder.status != "closed", before.status != "closed")
            .limit(1)
        ).one()
    engine.dispose()
    return row


def test_the_table_stays_the_default_and_the_timeline_is_asked_for(filled):
    assert "gantt-picture" not in filled.get("/planning").text
    html = filled.get(TIMELINE).text
    assert 'class="gantt-picture"' in html
    planned = re.findall(
        r'data-row="(\d+)">\s*<th[^>]*>[^<]*</th>\s*<td class="hidden 2xl:table-cell">(?!Not planned)', html
    )
    assert planned
    assert sorted(re.findall(r'id="planning-timeline-bar-(\d+)"', html)) == sorted(planned)


def test_the_timeline_and_its_scale_live_in_the_address(filled):
    html = filled.get(TIMELINE + "&scale=month").text
    assert '<input type="hidden" name="show" value="timeline">' in html
    assert '<input type="hidden" name="scale" value="month">' in html
    assert re.search(r'id="tab-month"[^>]*aria-current="page"', html)
    assert 'href="/planning?location=Roof&amp;show=timeline&amp;scale=day"' in html


def test_an_arrow_leads_to_a_work_order_that_waits(filled, filled_url):
    waiting, _before, name = a_waiting_pair(filled_url)
    html = filled.get("/planning", params={"show": "timeline", "status": "", "q": name}).text
    assert 'class="gantt-link"' in html
    assert f"Work order {_before}</td>" in html
    assert f"Work order {waiting} " in html


@pytest.mark.rule("LANG-01")
def test_no_text_outside_translation(filled):
    filled.cookies.set("language", PSEUDO)
    assert untranslated(filled.get(TIMELINE).text, ALLOWED) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("width", [1440, 375])
def test_the_timeline_passes_the_scan(open_filled, width):
    assert run_axe_in_both_themes(open_filled(TIMELINE, width=width, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
def test_the_timeline_fits_a_phone_and_scrolls_in_its_own_box(open_filled):
    page = open_filled(TIMELINE, language=PSEUDO, width=320)
    assert not overflows_sideways(page)
    box = page.locator(".gantt-scroll")
    assert box.evaluate("element => element.scrollWidth > element.clientWidth")
    box.focus()
    page.keyboard.press("ArrowRight")
    until(page, "document.querySelector('.gantt-scroll').scrollLeft > 0")


def bars_beside_their_rows(page):
    return page.evaluate("""() => [...document.querySelectorAll('.gantt-bar')].map((bar) => {
        const row = document.querySelector(`[data-row="${bar.id.split('-').at(-1)}"]`).getBoundingClientRect();
        const box = bar.getBoundingClientRect();
        return Math.abs((row.top + row.bottom) / 2 - (box.top + box.bottom) / 2);
    })""")


@pytest.mark.browser
@pytest.mark.parametrize("layout", [{}, {"density": "compact"}])
def test_each_bar_is_beside_its_row(open_filled, layout):
    offsets = bars_beside_their_rows(open_filled(TIMELINE, layout=layout))
    assert offsets
    assert max(offsets) <= 1.5


@pytest.mark.browser
def test_each_bar_is_beside_its_row_at_twice_the_size(open_filled):
    page = open_filled(TIMELINE)
    page.evaluate("document.documentElement.style.fontSize = '200%'")
    assert max(bars_beside_their_rows(page)) <= 1.5


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
@pytest.mark.rule("USE-05")
def test_the_scale_changes_in_place_and_keeps_the_page(open_filled):
    page = open_filled("/planning?show=timeline&size=10&page=2")
    page.evaluate("window.notReloaded = true")
    page.locator("#tab-month").click()
    page.wait_for_url(re.compile(r"scale=month.*page=2|page=2.*scale=month"))
    assert page.locator("#tab-month").get_attribute("aria-current") == "page"
    assert page.evaluate("window.notReloaded")
    page.locator("#tab-table").click()
    until(page, "!document.querySelector('.gantt-picture')")


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_a_work_order_edited_from_the_timeline_comes_back_on_it(open_filled):
    page = open_filled(TIMELINE)
    link = page.locator(".gantt-table [aria-haspopup=dialog]").first
    number = link.get_attribute("id").removeprefix("edit-")
    link.click()
    page.wait_for_selector("#editor[open]")
    page.locator("#field-hours").fill("9")
    page.locator("#editor").get_by_role("button", name="Save").click()
    announced(page, f"Work order {number} saved.")
    assert page.locator(".gantt-picture").count() == 1
    until(page, f"document.activeElement.id === 'edit-{number}'")


@pytest.mark.browser
def test_on_paper_the_picture_fits_under_its_table(open_filled):
    page = open_filled(TIMELINE)
    page.emulate_media(media="print")
    picture = page.locator(".gantt-picture").bounding_box()
    table = page.locator(".gantt-table").bounding_box()
    assert picture["y"] >= table["y"] + table["height"] - 1
    assert picture["width"] <= page.evaluate("document.documentElement.clientWidth")


@pytest.mark.browser
def test_without_javascript_the_tabs_are_links(open_filled):
    page = open_filled("/planning?location=Roof", javascript=False)
    page.get_by_role("link", name="Timeline").click()
    page.wait_for_url(re.compile(r"show=timeline"))
    assert page.locator(".gantt-picture").count() == 1


@pytest.fixture
def far_apart(database_url):
    """Two planned work orders a century apart, as the calendar's route allows."""
    fill(database_url, 200)
    engine = create_database_engine(database_url)
    with Session(engine) as session:
        first, second = session.scalars(select(WorkOrder).where(WorkOrder.status == "planned").limit(2)).all()
        first.planned_on, second.planned_on = date(2000, 1, 3), date(2099, 12, 28)
        session.commit()
    engine.dispose()
    client = TestClient(create_app(build_settings(database_url=database_url)))
    client.headers.update(PERSON)
    return client


def test_a_century_of_work_stays_a_small_picture_and_says_what_it_leaves_out(far_apart):
    response = far_apart.get("/planning?show=timeline&scale=day&status=planned&sort=planned&size=10")
    assert len(response.content) < 300_000
    assert "Shown at a coarser scale" in response.text
    assert "past these dates" in response.text


def test_all_dates_is_the_default_and_fits_what_it_can(filled):
    html = filled.get("/planning?show=timeline&q=Forklift").text
    assert re.search(r'id="tab-fit"[^>]*aria-current="page"', html)


@pytest.mark.browser
def test_a_timeline_wider_than_its_box_says_so_and_one_that_fits_does_not(open_filled):
    page = open_filled("/planning?show=timeline&scale=day&status=", width=1280)
    assert page.locator("[data-gantt-wider]").is_visible()
    page = open_filled("/planning?show=timeline&status=&q=EQ-000001&panel=hidden", width=1920)
    page.wait_for_load_state("load")
    wider = page.locator("[data-gantt-box]").evaluate("box => box.scrollWidth > box.clientWidth + 1")
    assert page.locator("[data-gantt-wider]").is_visible() is wider


@pytest.fixture(scope="module")
def long_job(browser, tmp_path_factory):
    """Planning on rows of its own, with one work order so long that it ends on the last day of any window."""
    folder = tmp_path_factory.mktemp("labels")
    url = f"sqlite:///{(folder / 'labels.db').as_posix()}"
    fill(url, 500)
    engine = create_database_engine(url)
    with Session(engine) as session:
        order = session.scalars(select(WorkOrder).where(WorkOrder.status == "planned").order_by(WorkOrder.id)).first()
        order.planned_on, order.hours, order.crew = date(2026, 12, 30), Decimal(9999), 1
        session.commit()
        number, place = order.id, order.equipment.location
    engine.dispose()
    settings = build_settings(database_url=url, fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port, page_opener(browser, f"http://127.0.0.1:{port}") as opener:
        yield opener, number, place


LABELS_IN_PLACE = """() => {
    const picture = document.querySelector('.gantt-picture').getBoundingClientRect();
    const labels = [...document.querySelectorAll('.gantt-label')].map((label) => label.getBoundingClientRect());
    const past = labels.filter((box) => box.right > picture.right + 0.5 || box.left < picture.left - 0.5).length;
    let overlapping = 0;
    labels.forEach((box, index) => labels.slice(index + 1).forEach((other) => {
        const across = Math.min(box.right, other.right) - Math.max(box.left, other.left);
        const down = Math.min(box.bottom, other.bottom) - Math.max(box.top, other.top);
        if (across > 0.5 && down > 0.5) overlapping += 1;
    }));
    return { count: labels.length, past, overlapping };
}"""


@pytest.mark.browser
@pytest.mark.parametrize("scale", ["fit", "day", "week", "month"])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("layout", [{}, {"density": "compact"}])
def test_every_label_ends_inside_the_picture_and_clear_of_the_others(long_job, scale, theme, layout):
    opener, number, place = long_job
    address = f"/planning?show=timeline&status=&location={place}&sort=planned&dir=desc&size=100&scale={scale}"
    page = opener(address, theme=theme, layout=layout)
    reaches_the_end = page.evaluate(
        """(number) => {
            const rights = [...document.querySelectorAll('.gantt-bar')].map((bar) => bar.getBoundingClientRect().right);
            const long = document.querySelector(`#planning-timeline-bar-${number}`).getBoundingClientRect();
            return long.right >= Math.max(...rights) - 0.5;
        }""",
        number,
    )
    assert reaches_the_end
    found = page.evaluate(LABELS_IN_PLACE)
    assert found["count"] > 10
    assert found["past"] == 0
    assert found["overlapping"] == 0


@pytest.mark.browser
@pytest.mark.parametrize("scale", ["fit", "day", "month"])
def test_every_label_ends_inside_the_picture_at_twice_the_text(long_job, scale):
    opener, _number, place = long_job
    page = opener(f"/planning?show=timeline&status=&location={place}&sort=planned&dir=desc&size=100&scale={scale}")
    page.evaluate("document.documentElement.style.fontSize = '200%'")
    found = page.evaluate(LABELS_IN_PLACE)
    assert found["past"] == 0
    assert found["overlapping"] == 0
