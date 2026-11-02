"""Timelines on their own: what stays in an application after the demo is deleted."""

import itertools
from datetime import date, timedelta

import pytest

from app.core.gantt import (
    BAR,
    DAY_WIDTH,
    FIT_WIDTH,
    HEADER,
    LABEL_GAP,
    MAX_WIDTH,
    ROW,
    SHORTEST_BAR,
    Task,
    label_width,
    timeline,
)
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


def test_a_scale_off_its_list_fits_the_tasks():
    assert timeline(ROWS, "decade", TODAY).asked == "fit"


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
    assert '<th scope="col" class="hidden 2xl:table-cell">Starts</th>' in html


def test_the_picture_is_measured_in_rem_so_it_keeps_in_line_with_the_table():
    plan = timeline(ROWS, "day", TODAY)
    html = drawn(plan)
    assert (
        f'width="{plan.width / 16}rem" height="{plan.height / 16}rem" viewBox="0 0 {plan.width} {plan.height}"' in html
    )


FAR = [Task(1, "Early", date(2000, 1, 3), date(2000, 1, 7)), Task(2, "Late", date(2099, 12, 21), date(2099, 12, 24))]


def test_a_span_too_wide_for_its_scale_takes_a_coarser_one_and_never_grows_past_its_limit():
    plan = timeline(FAR, "day", TODAY)
    assert plan.width <= MAX_WIDTH
    assert plan.scale == "month"
    assert plan.asked == "day"
    assert len(drawn(plan)) < 200_000


def test_what_falls_past_the_window_is_counted_and_not_drawn():
    plan = timeline(FAR, "day", TODAY)
    assert plan.last - plan.first < date(2099, 1, 1) - date(2000, 1, 1)
    assert [bar.key for bar in plan.bars] == [1]
    assert plan.outside == 1


def test_a_span_that_fits_keeps_the_scale_it_was_asked_for():
    plan = timeline(ROWS[:3], "day", TODAY)
    assert (plan.scale, plan.outside) == ("day", 0)


@pytest.mark.parametrize(("days", "expected"), [(10, "day"), (40, "week"), (400, "month")])
def test_fit_takes_the_finest_scale_that_shows_every_task_without_scrolling(days, expected):
    task = Task(1, "A", date(2026, 1, 5), date(2026, 1, 5) + timedelta(days=days))
    plan = timeline([task], "fit", TODAY)
    assert plan.scale == expected
    assert plan.width <= FIT_WIDTH or expected == "month"


def label_end(bar):
    """Where a label's text ends, as the layout reckons it."""
    return bar.label_x + label_width(bar.text) if bar.anchor == "start" else bar.label_x


def test_a_label_after_its_bar_has_room_in_the_picture():
    task = Task(1, "Electrical inspection", date(2026, 11, 2), date(2026, 11, 20))
    plan = timeline([task], "day", TODAY, margin=0)
    bar = plan.bars[0]
    assert (bar.anchor, bar.label_x) == ("start", bar.x + bar.width + LABEL_GAP)
    assert label_end(bar) <= plan.width


def test_a_label_that_would_pass_the_room_goes_inside_a_wide_bar_or_before_it():
    long_name = "A very long name for a piece of work " * 4
    wide = Task(1, long_name, date(2026, 11, 2), date(2027, 4, 30))
    late = Task(2, long_name, date(2027, 4, 29), date(2027, 4, 30))
    plan = timeline([wide, late], "day", TODAY, margin=0)
    inside, before = plan.bars
    assert inside.anchor == "start" and inside.inside
    assert inside.label_x >= inside.x
    assert before.anchor == "end" and before.label_x <= before.x
    for bar in plan.bars:
        assert 0 <= (bar.label_x - label_width(bar.text) if bar.anchor == "end" else bar.label_x)
        assert label_end(bar) <= plan.width


@pytest.mark.parametrize("scale", ["fit", "day", "week", "month"])
def test_no_label_ends_past_the_picture_at_any_scale(scale):
    rows = [
        Task(
            n,
            f"Preventive plan {n}",
            date(2026, 1, 5) + timedelta(days=9 * n),
            date(2026, 1, 9) + timedelta(days=9 * n),
        )
        for n in range(12)
    ]
    plan = timeline(rows, scale, TODAY)
    assert all(label_end(bar) <= plan.width for bar in plan.bars)
    assert all(bar.label_x >= 0 for bar in plan.bars)


def test_a_label_too_long_for_any_place_is_shortened_and_kept_whole_for_a_screen_reader():
    task = Task(1, "x" * 400, date(2026, 11, 2), date(2026, 11, 2))
    plan = timeline([task], "day", TODAY, margin=0)
    bar = plan.bars[0]
    assert bar.text.endswith("…")
    assert label_end(bar) <= plan.width
    assert bar.label == "x" * 400
