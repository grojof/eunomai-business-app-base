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

from app.core.database import create_database_engine, migrate
from app.core.settings import get_settings
from app.demo.models import EQUIPMENT_STATUSES, WORK_ORDER_STATUSES, Equipment, WorkOrder

EQUIPMENT_ROWS = 50_000
WORK_ORDER_EVERY = 5
"""One piece of equipment in this many has a work order."""
SEED = 2027
KINDS = ("Air compressor", "Conveyor belt", "Standby generator", "Cooling tower", "Forklift")
LOCATIONS = ("Workshop", "Packing", "Plant room", "Roof", "Warehouse")
TITLES = ("Preventive plan", "Safety checks")
FIRST_INSPECTION = date(2026, 11, 1)
INSPECTION_DAYS = 730
START = datetime(2026, 1, 1, tzinfo=UTC)
YEAR_SECONDS = 365 * 24 * 60 * 60


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
        "updated_at": START + timedelta(seconds=numbers[6] % YEAR_SECONDS),
    }


def work_order_row(position: int, seed: int = SEED) -> dict[str, Any]:
    numbers = _numbers(seed, "work_order", position)
    status = WORK_ORDER_STATUSES[numbers[0] % len(WORK_ORDER_STATUSES)]
    opened = START + timedelta(seconds=numbers[1] % YEAR_SECONDS)
    return {
        "id": position + 1,
        "equipment_id": position * WORK_ORDER_EVERY + 1,
        "title": TITLES[numbers[2] % len(TITLES)],
        "status": status,
        "hours": Decimal(numbers[3] % 400) / 4,
        "cost": _amount(50 + numbers[4] % 9_950, numbers[5]),
        "opened_at": opened,
        "closed_at": opened + timedelta(hours=numbers[6] % 200) if status == "closed" else None,
    }


def replace_rows(session: Session, rows: int = EQUIPMENT_ROWS, seed: int = SEED) -> int:
    """Replaces the demo's tables, and returns how many work orders that made. The caller commits."""
    session.execute(delete(WorkOrder))
    session.execute(delete(Equipment))
    orders = (rows + WORK_ORDER_EVERY - 1) // WORK_ORDER_EVERY
    session.execute(insert(Equipment), [equipment_row(position, seed) for position in range(rows)])
    session.execute(insert(WorkOrder), [work_order_row(position, seed) for position in range(orders)])
    if session.get_bind().dialect.name == "postgresql":  # the numbers above were given, so its counters did not move
        for table, last in (("equipment", rows), ("work_order", orders)):
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
    print(f"{arguments.rows} equipment rows and {orders} work orders, in {time.perf_counter() - started:.1f} seconds")


if __name__ == "__main__":
    main()
