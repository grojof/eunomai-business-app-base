"""Timelines on their own: what stays in an application after the demo is deleted."""

import itertools
from datetime import date

import pytest

from app.core.gantt import BAR, DAY_WIDTH, HEADER, ROW, SHORTEST_BAR, Task, timeline
from app.core.templating import environment

MACROS = environment.get_template("ui/macros.html").module
TODAY = date(2026, 11, 4)  # a Wednesday
ROWS = [
    None,
    Task(1, "Design", date(2026, 11, 2), date(2026, 11, 6), "info"),
    Task(2, "Build", date(2026, 11, 9), date(2026, 11, 9), "warning", after=(1,)),
    Task(3, "Not planned", None, None),
    Task(4, "Long", date(2026, 11, 2), date(2027, 2, 26), "success", after=(9,)),
]


def drawn(plan):
    return str(
        MACROS.gantt(
            "plan", "The plan", plan, [("Work", False), ("Starts", True)], "A summary", caller=lambda: "<tbody></tbody>"
        )
    )


def test_each_task_is_a_bar_from_its_first_to_its_last_day():
    plan = timeline(ROWS, "day", TODAY, margin=0)
    first, one_day, long = plan.bars
    assert plan.first == date(2026, 11, 2)
    assert (first.x, first.width) == (0, 5 * DAY_WIDTH["day"])
    assert (one_day.x, one_day.width) == (7 * DAY_WIDTH["day"], DAY_WIDTH["day"])
    assert first.y == HEADER + ROW + (ROW - BAR) // 2
    assert long.width == ((date(2027, 2, 26) - date(2026, 11, 2)).days + 1) * DAY_WIDTH["day"]


def test_rows_keep_their_places_with_a_group_and_a_task_with_no_dates():
    plan = timeline(ROWS, "week", TODAY)
    assert plan.rows == 5
    assert plan.height == HEADER + 5 * ROW
    assert [bar.key for bar in plan.bars] == [1, 2, 4]


def test_a_one_day_task_can_be_seen_at_every_scale():
    plan = timeline(ROWS, "month", TODAY)
    assert plan.bars[1].width == SHORTEST_BAR


def test_an_arrow_joins_a_task_to_the_one_that_waits_for_it_and_only_when_both_are_shown():
    plan = timeline(ROWS, "day", TODAY, margin=0)
    assert len(plan.links) == 1
    assert plan.links[0].startswith(f"M{5 * DAY_WIDTH['day']} ")


def test_weekends_are_shaded_and_today_is_marked():
    plan = timeline(ROWS, "day", TODAY, margin=0)
    assert plan.weekends[:2] == [5 * DAY_WIDTH["day"], 6 * DAY_WIDTH["day"]]
    assert plan.today == 2 * DAY_WIDTH["day"]
    assert timeline(ROWS, "day", date(2030, 1, 1)).today is None
    assert timeline(ROWS, "month", TODAY).weekends == []


@pytest.mark.parametrize(("scale", "starts_on"), [("week", 0), ("month", None)])
def test_a_week_starts_on_monday_and_a_month_on_its_first(scale, starts_on):
    plan = timeline([Task(1, "A", date(2026, 11, 12), date(2026, 11, 13))], scale, TODAY)
    if starts_on is None:
        assert plan.first.day == 1
    else:
        assert plan.first.weekday() == starts_on


def test_a_scale_off_its_list_is_a_week():
    assert timeline(ROWS, "decade", TODAY).scale == "week"


def test_month_labels_that_would_cover_each_other_give_way():
    plan = timeline([Task(1, "A", date(2026, 10, 29), date(2026, 11, 20))], "week", TODAY)
    xs = [tick.x for tick in plan.months]
    assert all(later - earlier >= 112 for earlier, later in itertools.pairwise(xs))


def test_the_picture_is_drawn_with_attributes_and_classes_and_named_by_its_summary():
    html = drawn(timeline(ROWS, "day", TODAY))
    assert "style=" not in html
    assert 'class="gantt-bar gantt-bar-warning"' in html
    assert 'role="img" aria-labelledby="plan-summary"' in html
    assert '<p id="plan-summary"' in html
    assert 'marker-end="url(#plan-arrow)"' in html
    assert 'class="gantt-today"' in html
    assert 'role="region" tabindex="0"' in html
    assert '<th scope="col" class="hidden md:table-cell">Starts</th>' in html


def test_the_picture_is_measured_in_rem_so_it_keeps_in_line_with_the_table():
    plan = timeline(ROWS, "day", TODAY)
    html = drawn(plan)
    assert (
        f'width="{plan.width / 16}rem" height="{plan.height / 16}rem" viewBox="0 0 {plan.width} {plan.height}"' in html
    )
