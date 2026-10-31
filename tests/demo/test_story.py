"""The demo's data tells one story: it ends on one day, old work is done, and every screen says the same."""

import json
import re
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.database import create_database_engine
from app.demo.generate import equipment_row, work_order_row
from app.demo.models import WorkOrder
from app.main import create_app
from tests.conftest import PERSON, build_settings
from tests.demo.support import fill

LAST_DAY = date(2026, 10, 31)
FIRST_DAY = date(2026, 1, 1)
ORDERS = [work_order_row(position) for position in range(10_000)]
OLD = [row for row in ORDERS if (LAST_DAY - row["opened_at"].date()).days > 60]
NEW = [row for row in ORDERS if (LAST_DAY - row["opened_at"].date()).days <= 60]
EARLIEST = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=12)
LATEST = datetime(2026, 10, 31, tzinfo=UTC) + timedelta(hours=12)


def open_orders_stat(html: str) -> int:
    return int(re.search(r'<div class="stat-value[^>]*>([\d,]+)<', html)[1].replace(",", ""))


def test_nothing_happens_before_the_first_day_or_after_the_last():
    moments = [row["opened_at"] for row in ORDERS]
    moments += [row["closed_at"] for row in ORDERS if row["closed_at"]]
    moments += [equipment_row(position)["updated_at"] for position in range(2_000)]
    assert min(moments).date() == FIRST_DAY
    assert max(moments).date() == LAST_DAY


@pytest.mark.parametrize("zone", ["Pacific/Honolulu", "Europe/Madrid", "Asia/Tokyo"])
def test_no_time_zone_pushes_a_moment_into_another_month(zone):
    from zoneinfo import ZoneInfo

    assert EARLIEST.astimezone(ZoneInfo(zone)).date() == FIRST_DAY
    assert LATEST.astimezone(ZoneInfo(zone)).date() == LAST_DAY
    assert all(EARLIEST <= row["opened_at"] <= LATEST for row in ORDERS)


def test_old_orders_are_nearly_all_closed():
    closed = sum(row["status"] == "closed" for row in OLD) / len(OLD)
    assert 0.94 < closed < 0.98


def test_new_orders_spread_across_the_states():
    states = {row["status"] for row in NEW}
    assert states == {"reported", "planned", "in_progress", "checked", "closed"}
    for state in states:
        assert sum(row["status"] == state for row in NEW) / len(NEW) > 0.1


def test_a_closed_order_was_not_planned_after_it_closed():
    for row in ORDERS:
        if row["status"] == "closed" and row["planned_on"]:
            assert row["planned_on"] <= row["closed_at"].date()


def test_monthly_charts_stop_at_the_last_month_with_data(filled):
    html = filled.get("/").text
    for config in re.findall(r'<script type="application/json">(.*?)</script>', html, re.S):
        chart = json.loads(config)
        if chart["type"] in ("stacked", "area"):
            assert chart["labels"][-1] == "Oct"
            assert len(chart["labels"]) == 10


def test_the_overdue_card_counts_open_orders_planned_before_today(filled):
    orders = [work_order_row(position) for position in range(200)]
    late = [row for row in orders if row["status"] != "closed" and row["planned_on"] and row["planned_on"] < LAST_DAY]
    html = filled.get("/").text
    card = html[html.index('id="overdue-title"') :]
    assert late
    assert re.search(rf">\s*{len(late)} open work orders? planned before today", card)
    assert "Nothing overdue" not in html


def test_the_overdue_card_shows_the_five_oldest_and_leads_to_planning(filled):
    orders = [work_order_row(position) for position in range(200)]
    late = [row for row in orders if row["status"] != "closed" and row["planned_on"] and row["planned_on"] < LAST_DAY]
    oldest = sorted(late, key=lambda row: (row["planned_on"], row["id"]))[:5]
    html = filled.get("/").text
    card = html[html.index('id="overdue-title"') :]
    for row in oldest:
        assert f'href="/equipment/{row["equipment_id"]}?tab=orders"' in card
    assert 'href="/planning?due=overdue&amp;group=month"' in card


def test_the_dashboard_and_planning_count_the_same(filled):
    dashboard = filled.get("/").text
    open_orders = open_orders_stat(dashboard)
    assert re.search(rf">\s*{open_orders} work orders\s*<", filled.get("/planning").text)
    card = dashboard[dashboard.index('id="overdue-title"') :]
    overdue = int(re.search(r"(\d+) open work orders? planned before today", card)[1])
    assert re.search(rf">\s*{overdue} work orders?\s*<", filled.get("/planning?due=overdue&group=month").text)


def test_the_months_of_a_chart_add_up_to_the_stat(filled):
    html = filled.get("/").text
    charts = [json.loads(c) for c in re.findall(r'<script type="application/json">(.*?)</script>', html, re.S)]
    orders = next(chart for chart in charts if chart["type"] == "stacked")
    still_open, closed = [[int(value) for value in line["values"]] for line in orders["series"]]
    assert sum(still_open) == open_orders_stat(html)
    assert sum(still_open) + sum(closed) == 200


def test_the_empty_overdue_card_stays_when_there_are_none(database_url):
    fill(database_url, 100)
    engine = create_database_engine(database_url)
    with Session(engine) as session:
        session.execute(update(WorkOrder).where(WorkOrder.status != "closed").values(planned_on=LAST_DAY))
        session.commit()
    engine.dispose()
    client = TestClient(create_app(build_settings(database_url=database_url)))
    assert "Nothing overdue" in client.get("/", headers=PERSON).text


def test_the_empty_overdue_card_stays_for_the_first_run(client, person):
    assert "Nothing overdue" in client.get("/", headers=person).text


def test_inspections_due_come_from_the_rows(filled):
    rows = [equipment_row(position) for position in range(1_000)]
    due = sum(row["next_inspection"] <= LAST_DAY + timedelta(days=30) for row in rows)
    assert f"{due} inspections are due in the next 30 days" in filled.get("/inspections").text


def test_the_plan_comes_from_the_rows(filled):
    orders = [work_order_row(position) for position in range(200)]
    preventive = [row for row in orders if row["title"] == "Preventive plan"]
    share = 100 * sum(row["status"] == "closed" for row in preventive) // len(preventive)
    html = filled.get("/").text
    assert re.search(rf'value="{share}" max="100" aria-label="Preventive plan"', html)
