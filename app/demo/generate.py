"""The demo's data, made from a seed: the same seed and the same number of rows give the same rows, anywhere.

uv run --frozen python -m app.demo.generate

Applies the migrations, then replaces whatever the demo's tables hold. Only in development.

Each row comes from a SHA-512 of the seed and its position, not from `random`: across Python versions, only
`random.random()` promises the same sequence, and a row should not change because the number of rows did.
"""

import argparse
import hashlib
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, insert, text
from sqlalchemy.orm import Session

from app.core.boards import RANK_STEP
from app.core.database import create_database_engine, migrate
from app.core.settings import get_settings
from app.core.uploads import UploadStore
from app.demo.models import (
    EQUIPMENT_STATUSES,
    FIRST_MOMENT,
    LAST_MOMENT,
    LOCATIONS,
    OPEN_STATES,
    WORK_ORDER_STATUSES,
    Equipment,
    Inspection,
    WorkOrder,
    working_days,
)

EQUIPMENT_ROWS = 50_000
WORK_ORDER_EVERY = 5
"""One work order for this many pieces of equipment."""
ORDER_SPREAD = (0, 0, 0, 5, 5, 10)
"""Each six work orders fall on thirty pieces of equipment like this: one has a history of three, one of two, one of
one, and the rest have none yet, so a detail page shows each of those cases."""
SEED = 2027
KINDS = ("Air compressor", "Conveyor belt", "Standby generator", "Cooling tower", "Forklift")
TITLES = (
    "Preventive plan",
    "Safety checks",
    "Oil change",
    "Filter replacement",
    "Belt replacement",
    "Calibration",
    "Leak repair",
    "Electrical inspection",
)
FIRST_INSPECTION = date(2026, 11, 1)
INSPECTION_DAYS = 730
PLANNING_DAYS = 60
SPAN_SECONDS = int((LAST_MOMENT - FIRST_MOMENT).total_seconds())
OLD_ORDER_DAYS = 60
"""Older than this, work is done: nearly all of it is closed, and what is left open is really late."""
OLD_ORDERS_CLOSED = 96
"""Out of a hundred."""


def _numbers(seed: int, table: str, position: int) -> list[int]:
    """Eight numbers that belong to this row alone."""
    digest = hashlib.sha512(f"{seed}/{table}/{position}".encode()).digest()
    return [int.from_bytes(digest[start : start + 8]) for start in range(0, len(digest), 8)]


def _amount(whole: int, fraction: int) -> Decimal:
    """Twenty decimals on purpose: a float cannot hold them, so a mistake shows."""
    return Decimal(f"{whole}.{fraction % 10**20:020d}")


def _status(number: int) -> str:
    """Most equipment works: 80 % in service, 15 % due soon, 5 % stopped."""
    share = number % 100
    return EQUIPMENT_STATUSES[0 if share < 80 else 1 if share < 95 else 2]


def equipment_row(position: int, seed: int = SEED) -> dict[str, Any]:
    numbers = _numbers(seed, "equipment", position)
    number = position + 1
    return {
        "id": number,
        "code": f"EQ-{number:06d}",
        "name": f"{KINDS[numbers[0] % len(KINDS)]} {number}",
        "location": LOCATIONS[numbers[1] % len(LOCATIONS)],
        "status": _status(numbers[2]),
        "next_inspection": FIRST_INSPECTION + timedelta(days=numbers[3] % INSPECTION_DAYS),
        "cost": _amount(1_000 + numbers[4] % 499_000, numbers[5]),
        "updated_at": FIRST_MOMENT + timedelta(seconds=numbers[6] % SPAN_SECONDS),
    }


def _order_status(number: int, opened: datetime) -> str:
    """Old work is done, and newer work is at any step."""
    if (LAST_MOMENT - opened).days <= OLD_ORDER_DAYS:
        return WORK_ORDER_STATUSES[number % len(WORK_ORDER_STATUSES)]
    if number % 100 < OLD_ORDERS_CLOSED:
        return "closed"
    return OPEN_STATES[number // 100 % len(OPEN_STATES)]


def work_order_row(position: int, seed: int = SEED) -> dict[str, Any]:
    numbers = _numbers(seed, "work_order", position)
    opened = FIRST_MOMENT + timedelta(seconds=numbers[1] % SPAN_SECONDS)
    status = _order_status(numbers[0], opened)
    closed = min(opened + timedelta(hours=numbers[6] % 200), LAST_MOMENT) if status == "closed" else None
    planned = None if status == "reported" else opened.date() + timedelta(days=numbers[7] % PLANNING_DAYS)
    if closed and planned:
        planned = min(planned, closed.date())
    return {
        "id": position + 1,
        "equipment_id": (position // len(ORDER_SPREAD)) * 30 + ORDER_SPREAD[position % len(ORDER_SPREAD)] + 1,
        "title": TITLES[numbers[2] % len(TITLES)],
        "status": status,
        "hours": Decimal(numbers[3] % 400) / 4,
        "cost": _amount(50 + numbers[4] % 9_950, numbers[5]),
        "opened_at": opened,
        "closed_at": closed,
        "planned_on": planned,
    }


def ranked_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each order with its place on the board: open work by its planned day, soonest first and unplanned last, and
    closed work most recent first. The rows themselves stay as they are, so their frozen hash does not move."""

    def place(row: dict[str, Any]) -> tuple[str, int, int]:
        if row["status"] == "closed":
            return row["status"], -row["closed_at"].toordinal(), row["id"]
        planned = row["planned_on"].toordinal() if row["planned_on"] else date.max.toordinal()
        return row["status"], planned, row["id"]

    ordered = sorted(orders, key=place)
    ranks = {row["id"]: (position + 1) * RANK_STEP for position, row in enumerate(ordered)}
    return [row | {"rank": ranks[row["id"]]} for row in orders]


def waiting_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each order with the one it waits for: the order before it on the same equipment, when that one ends before this
    one is planned to start, as one job follows another."""
    found = []
    for position, row in enumerate(orders):
        before = orders[position - 1] if position % len(ORDER_SPREAD) in (1, 2, 4) else None
        after_id = None
        if before and before["planned_on"] and row["planned_on"]:
            ends = before["planned_on"] + timedelta(days=working_days(before["hours"], 1))
            after_id = before["id"] if row["planned_on"] >= ends else None
        found.append(row | {"after_id": after_id})
    return found


INSPECTIONS_FROM = date(2026, 9, 1)
INSPECTION_WEEKS = 18
"""The inspection team's visits run from September to the end of the year, on working days."""
VISIT_STARTS = (7, 8, 9, 10, 11, 13, 14)
"""Hours of the day in UTC a visit can start at: in the morning or the afternoon wherever the application is."""


def inspection_rows(equipment: int, seed: int = SEED) -> list[dict[str, Any]]:
    """Two to five visits on each working day, some of them at the same time, lasting one to three hours, and now and
    then one that takes three days."""
    rows: list[dict[str, Any]] = []
    for offset in range(INSPECTION_WEEKS * 7):
        day = INSPECTIONS_FROM + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        numbers = _numbers(seed, "inspection-day", offset)
        for visit in range(2 + numbers[0] % 4):
            each = _numbers(seed, "inspection", offset * 8 + visit)
            starts = datetime(
                day.year, day.month, day.day, VISIT_STARTS[each[0] % len(VISIT_STARTS)], 30 * (each[1] % 2), tzinfo=UTC
            )
            long = each[2] % 40 == 0
            ends = starts + (timedelta(days=2, hours=8) if long else timedelta(hours=1 + each[3] % 3))
            rows.append(
                {"id": len(rows) + 1, "equipment_id": 1 + each[4] % equipment, "starts_at": starts, "ends_at": ends}
            )
    return rows


def replace_rows(session: Session, rows: int = EQUIPMENT_ROWS, seed: int = SEED) -> int:
    """Replaces the demo's tables, and returns how many work orders that made. The caller commits."""
    session.execute(delete(Inspection))
    session.execute(delete(WorkOrder))
    session.execute(delete(Equipment))
    orders = (rows + WORK_ORDER_EVERY - 1) // WORK_ORDER_EVERY
    session.execute(insert(Equipment), [equipment_row(position, seed) for position in range(rows)])
    order_rows = waiting_orders(ranked_orders([work_order_row(position, seed) for position in range(orders)]))
    session.execute(insert(WorkOrder), order_rows)
    visits = inspection_rows(rows, seed)
    session.execute(insert(Inspection), visits)
    if session.get_bind().dialect.name == "postgresql":  # the numbers above were given, so its counters did not move
        for table, last in (("equipment", rows), ("work_order", orders), ("inspection", len(visits))):
            sequence = text("SELECT setval(pg_get_serial_sequence(:table, 'id'), :last)")
            session.execute(sequence, {"table": table, "last": last})
    return orders


def main() -> None:
    parser = argparse.ArgumentParser(description="Fills the demo's tables with generated rows.")
    parser.add_argument("--rows", type=int, default=EQUIPMENT_ROWS, help="how much equipment")
    parser.add_argument("--seed", type=int, default=SEED, help="the same seed gives the same rows")
    arguments = parser.parse_args()
    settings = get_settings()
    if settings.environment != "development":
        raise SystemExit("Demo data replaces the demo's tables: it runs only with APP_ENVIRONMENT=development")
    url = settings.database_url.get_secret_value()
    started = time.perf_counter()
    migrate(url)
    engine = create_database_engine(url)
    with Session(engine) as session:
        orders = replace_rows(session, arguments.rows, arguments.seed)
        session.commit()
    engine.dispose()
    UploadStore(settings.upload_folder, settings.upload_max_bytes).clear()  # their rows have just gone
    print(f"{arguments.rows} equipment rows and {orders} work orders, in {time.perf_counter() - started:.1f} seconds")


if __name__ == "__main__":
    main()
