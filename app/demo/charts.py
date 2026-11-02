"""The demo's charts: the dashboard's, from the generated rows, and the gallery's, with values fixed here."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager

from app.core.charts import STATE_COLOURS, ChartData, Point, Series, chart_data, point_data
from app.core.database import exact_sum, total
from app.core.formatters import format_date, format_decimal, format_month, format_percent, rounded
from app.core.i18n import _
from app.demo.equipment import STATUS_LABELS, labels_in_order
from app.demo.models import (
    EQUIPMENT_STATUSES,
    LAST_DAY,
    LAST_MOMENT,
    LOCATIONS,
    OPEN_STATES,
    Equipment,
    WorkOrder,
    overdue,
)

YEAR = 2026
OVERDUE_SHOWN = 5
INSPECTIONS_AHEAD = timedelta(days=30)


@dataclass(frozen=True)
class Figure:
    """One call of the `chart` macro."""

    identifier: str
    title: str
    summary: str
    data: ChartData
    type: str


def months(count: int = 12) -> list[str]:
    return [format_month(date(YEAR, month, 1)) for month in range(1, count + 1)]


Link = Callable[[str], str]
"""Where a part of a chart leads, from the value it stands for."""


def equipment_by_state(session: Session, link: Link | None = None) -> Figure:
    counted = dict(session.execute(select(Equipment.status, func.count()).group_by(Equipment.status)).all())
    values = [counted.get(status, 0) for status in EQUIPMENT_STATUSES]
    everything = sum(values)
    labels = [_(STATUS_LABELS[status][0]) for status in EQUIPMENT_STATUSES]
    share = 100 * counted.get("in_service", 0) // everything if everything else 0
    links = [link(status) for status in EQUIPMENT_STATUSES] if link else []
    return Figure(
        "figure-states",
        _("Equipment by state"),
        _("Of %(total)s pieces of equipment, %(share)s are in service.")
        % {"total": format_decimal(everything), "share": format_percent(share)},
        chart_data(labels, [Series(_("Equipment"), values)], _("State"), colours=STATE_COLOURS, links=links),
        "doughnut",
    )


def equipment_by_location(session: Session, link: Link) -> Figure:
    """Where the equipment is, in the order of the person's language, each place a way to see its equipment."""
    counted = dict(session.execute(select(Equipment.location, func.count()).group_by(Equipment.location)).all())
    places = labels_in_order(LOCATIONS)
    values = [counted.get(place, 0) for place in places]
    largest = max(range(len(places)), key=lambda position: values[position])
    return Figure(
        "figure-locations",
        _("Equipment by location"),
        _("%(place)s holds the most equipment, %(count)s pieces.")
        % {"place": _(places[largest]), "count": format_decimal(values[largest])},
        chart_data(
            [_(place) for place in places],
            [Series(_("Equipment"), values)],
            _("Location"),
            places=0,
            links=[link(place) for place in places],
        ),
        "bar",
    )


def monthly_figures(session: Session, zone: str) -> tuple[Figure, Figure]:
    """Work orders and their cost by month in the application's time zone. It reads the rows and adds up here: SQLite
    cannot add exact columns, and a month depends on the time zone, which the two databases handle differently."""
    time_zone = ZoneInfo(zone)
    opened: list[int] = [0] * 12
    closed: list[int] = [0] * 12
    costs: list[list[Decimal]] = [[] for _month in range(12)]
    rows = session.execute(select(WorkOrder.opened_at, WorkOrder.status, WorkOrder.cost)).all()
    for moment, status, amount in rows:
        month = moment.astimezone(time_zone).month - 1
        (closed if status == "closed" else opened)[month] += 1
        costs[month].append(amount)
    shown = max((month + 1 for month in range(12) if costs[month]), default=1)  # no empty months ahead of the data
    labels = months(shown)
    opened, closed = opened[:shown], closed[:shown]
    by_month = [rounded(exact_sum(month), 0) for month in costs[:shown]]
    busiest = max(range(shown), key=lambda month: opened[month] + closed[month])
    dearest = max(range(shown), key=lambda month: by_month[month])
    orders = Figure(
        "figure-orders",
        _("Work orders by month"),
        _("%(total)s work orders opened this year. The busiest month was %(month)s, with %(count)s.")
        % {
            "total": format_decimal(len(rows)),
            "month": labels[busiest],
            "count": format_decimal(opened[busiest] + closed[busiest]),
        },
        chart_data(
            labels,
            [Series(_("Still open"), opened, "warning"), Series(_("Closed"), closed, "success")],
            _("Month"),
        ),
        "stacked",
    )
    cost = Figure(
        "figure-cost",
        _("Cost of the work by month"),
        _("Work cost %(total)s this year. The dearest month was %(month)s, at %(cost)s.")
        % {
            "total": format_decimal(rounded(exact_sum(row.cost for row in rows), 0)),
            "month": labels[dearest],
            "cost": format_decimal(by_month[dearest]),
        },
        chart_data(labels, [Series(_("Cost"), by_month)], _("Month"), places=0),
        "area",
    )
    return orders, cost


def _closed_share(session: Session, title: str) -> int:
    """How much of one kind of work is done, as a whole percentage."""
    orders = WorkOrder.title == title
    everything = session.scalar(select(func.count()).select_from(WorkOrder).where(orders)) or 0
    done = session.scalar(select(func.count()).select_from(WorkOrder).where(orders, WorkOrder.status == "closed")) or 0
    return 100 * done // everything if everything else 0


def inspections_due(session: Session) -> int:
    limit = LAST_DAY + INSPECTIONS_AHEAD
    return session.scalar(select(func.count()).select_from(Equipment).where(Equipment.next_inspection <= limit)) or 0


def _overdue_item(order: WorkOrder) -> tuple[str, str, str, str]:
    """One line of the Overdue card. An overdue order always has a date: `overdue()` compares it."""
    planned = format_date(order.planned_on) if order.planned_on else ""
    return order.equipment.name, order.title, f"/equipment/{order.equipment_id}?tab=orders", planned


def dashboard_figures(session: Session, zone: str) -> dict[str, Any]:
    """What the dashboard shows when the rows are there."""
    open_orders = WorkOrder.status.in_(OPEN_STATES)
    oldest = session.scalars(
        select(WorkOrder)
        .join(WorkOrder.equipment)
        .options(contains_eager(WorkOrder.equipment))
        .where(overdue())
        .order_by(WorkOrder.planned_on, WorkOrder.id)
        .limit(OVERDUE_SHOWN)
    ).all()
    next_up = session.scalars(select(Equipment).order_by(Equipment.next_inspection, Equipment.id).limit(5)).all()
    orders, cost = monthly_figures(session, zone)
    return {
        "open_orders": session.scalar(select(func.count()).select_from(WorkOrder).where(open_orders)) or 0,
        "all_orders": session.scalar(select(func.count()).select_from(WorkOrder)) or 0,
        "hours": total(session, WorkOrder.hours, WorkOrder.status == "closed"),  # what is open is not worked yet
        "cost": total(session, WorkOrder.cost),
        "next_inspection": next_up[0].next_inspection,
        "next_equipment": next_up[0].name,
        "equipment": [(item.name, item.location, item.next_inspection, STATUS_LABELS[item.status]) for item in next_up],
        "orders_chart": orders,
        "cost_chart": cost,
        "states_chart": equipment_by_state(session, lambda status: f"/equipment?status={status}"),
        "overdue_count": session.scalar(select(func.count()).select_from(WorkOrder).where(overdue())) or 0,
        "overdue_items": [_overdue_item(order) for order in oldest],
        "updated": LAST_MOMENT,
        "plan": [
            ("Preventive plan", _closed_share(session, "Preventive plan"), "primary"),
            ("Spare parts in stock", 88, "success"),
            ("Safety checks", _closed_share(session, "Safety checks"), "warning"),
        ],
    }


def _example(identifier: str, title: str, summary: str, data: ChartData, kind: str) -> Figure:
    return Figure(f"example-{identifier}", title, summary, data, kind)


def _numbers(values: Iterable[int | str]) -> list[Decimal]:
    return [Decimal(value) for value in values]


def chart_examples() -> list[Figure]:
    """One real use of each type, with fixed numbers: the gallery needs no database.

    Polar area stays out, though the macro draws it: it says what a pie or a bar says, less well, since area grows with
    the square of the value, and its scale sits on top of its slices.
    """
    labels = months()[:6]
    planned = _numbers([320, 340, 300, 360, 380, 350])
    worked = _numbers([298, 352, 310, 341, 395, 362])
    hours = _("Hours")
    month = _("Month")
    locations = [_(place) for place in LOCATIONS]
    return [
        _example(
            "bar",
            _("Hours planned and worked"),
            _("Hours worked stayed within 6 % of the plan in every month."),
            chart_data(labels, [Series(_("Planned"), planned), Series(_("Worked"), worked)], month, unit=_("h")),
            "bar",
        ),
        _example(
            "stacked",
            _("Work orders by kind"),
            _("Preventive work is about two thirds of all orders each month."),
            chart_data(
                labels,
                [
                    Series(_("Preventive"), _numbers([82, 88, 79, 90, 95, 87])),
                    Series(_("Corrective"), _numbers([41, 38, 44, 37, 40, 42])),
                ],
                month,
            ),
            "stacked",
        ),
        _example(
            "line",
            _("Stoppages by plant"),
            _("Stoppages fell in the north plant from March and held steady in the south."),
            chart_data(
                labels,
                [
                    Series(_("North plant"), _numbers([14, 15, 13, 9, 8, 7])),
                    Series(_("South plant"), _numbers([9, 8, 10, 9, 9, 8])),
                ],
                month,
            ),
            "line",
        ),
        _example(
            "area",
            _("Cost of the work, added up"),
            _("The year's cost reached 112,000 by June."),
            chart_data(labels, [Series(_("Cost"), _numbers([18000, 37500, 54200, 73100, 92800, 112000]))], month),
            "area",
        ),
        _example(
            "pie",
            _("Equipment by location"),
            _("The workshop and the warehouse hold more than half of the equipment."),
            chart_data(locations, [Series(_("Equipment"), _numbers([31, 14, 9, 12, 34]))], _("Location")),
            "pie",
        ),
        _example(
            "doughnut",
            _("Equipment by state"),
            _("Four in five pieces of equipment are in service."),
            chart_data(
                [_(STATUS_LABELS[status][0]) for status in EQUIPMENT_STATUSES],
                [Series(_("Equipment"), _numbers([40000, 7500, 2500]))],
                _("State"),
                colours=STATE_COLOURS,
            ),
            "doughnut",
        ),
        _example(
            "radar",
            _("Audit by site"),
            _("Both sites score well on safety. The south site is weakest on records."),
            chart_data(
                [_("Safety"), _("Cleanliness"), _("Records"), _("Training"), _("Spare parts")],
                [
                    Series(_("North plant"), _numbers([92, 78, 85, 70, 88])),
                    Series(_("South plant"), _numbers([88, 84, 61, 76, 72])),
                ],
                _("Audit"),
            ),
            "radar",
        ),
        _example(
            "scatter",
            _("Age and cost of repair"),
            _("Older equipment costs more to repair, and the rise steepens after ten years."),
            point_data(
                [
                    (
                        _("Equipment"),
                        [
                            Point(f"EQ-{number:06d}", age, cost)
                            for number, (age, cost) in enumerate(
                                [
                                    (1, 300),
                                    (2, 420),
                                    (3, 380),
                                    (4, 610),
                                    (5, 560),
                                    (6, 700),
                                    (7, 690),
                                    (8, 900),
                                    (9, 860),
                                    (10, 1100),
                                    (11, 1500),
                                    (12, 1420),
                                    (13, 1900),
                                    (14, 2300),
                                ],
                                start=1,
                            )
                        ],
                    )
                ],
                _("Equipment"),
                _("Age, in years"),
                _("Cost of repair"),
            ),
            "scatter",
        ),
        _example(
            "bubble",
            _("Work by location"),
            _("The warehouse takes the most hours, the roof the most money for each order."),
            point_data(
                [
                    (
                        _("Location"),
                        [
                            Point(place, Decimal(x), Decimal(y), Decimal(size))
                            for place, x, y, size in zip(
                                locations,
                                (420, 180, 150, 90, 610),
                                (21000, 8200, 9400, 11800, 24500),
                                (22, 11, 9, 7, 27),
                                strict=True,
                            )
                        ],
                    )
                ],
                _("Location"),
                hours,
                _("Cost"),
                _("Orders"),
            ),
            "bubble",
        ),
        _example(
            "mixed",
            _("Work orders opened and backlog"),
            _("The backlog grew until April, then fell as more orders closed than opened."),
            chart_data(
                labels,
                [
                    Series(_("Opened"), _numbers([123, 126, 123, 127, 135, 129])),
                    Series(_("Backlog"), _numbers([60, 74, 88, 95, 83, 71]), kind="line"),
                ],
                month,
            ),
            "mixed",
        ),
    ]
