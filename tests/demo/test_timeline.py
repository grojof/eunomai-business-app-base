"""Planning's timeline: the same rows as the table, as bars beside it, drawn on the server."""

import re

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.core.database import create_database_engine
from app.core.i18n import PSEUDO
from app.demo.models import Equipment, WorkOrder
from tests.demo.support import announced, until
from tests.helpers import overflows_sideways, run_axe, untranslated

TIMELINE = "/planning?show=timeline&location=Roof"
ALLOWED = ("Business App", "Demo Person", "Air compressor", "Conveyor belt", "Standby generator", "Cooling tower")
ALLOWED += ("Forklift", "Preventive plan", "Safety checks", "Oil change", "Filter replacement", "Belt replacement")
ALLOWED += ("Calibration", "Leak repair", "Electrical inspection", "January", "February", "March", "April", "May")
ALLOWED += ("June", "July", "August", "September", "October", "November", "December", "Jan ", "Feb ", "Mar ", "Apr ")
ALLOWED += ("Jun ", "Jul ", "Aug ", "Sep ", "Oct ", "Nov ", "Dec ")


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
        r'data-row="(\d+)">\s*<th[^>]*>[^<]*</th>\s*<td class="hidden md:table-cell">(?!Not planned)', html
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
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 375])
def test_the_timeline_passes_the_scan(open_filled, theme, width):
    assert run_axe(open_filled(TIMELINE, theme=theme, width=width, bypass_csp=True)) == []


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
