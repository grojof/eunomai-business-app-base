"""The demo's generated data, and the demo without a database."""

import hashlib
from collections.abc import Iterator
from datetime import UTC, date
from io import StringIO

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import create_database_engine, exact_sum, migrate, total
from app.demo import generate
from app.demo.generate import equipment_row, replace_rows, work_order_row
from app.demo.models import EQUIPMENT_STATUSES, WORK_ORDER_STATUSES, Equipment, WorkOrder
from app.main import create_app
from tests.conftest import build_settings
from tests.helpers import ROOT

FROZEN = "bb550dcd2cb2adcdf8df3a55150d9a6b2f31e2fbd8f933e3560517ff4b89b927"
"""The hash of the first thousand rows. If it changes, the demo's data changed on everyone's computer."""


@pytest.fixture
def session(database_url: str) -> Iterator[Session]:
    migrate(database_url)
    engine = create_database_engine(database_url)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.mark.rule("DATA-07")
def test_the_same_seed_gives_the_same_rows():
    assert [equipment_row(n) for n in range(100)] == [equipment_row(n) for n in range(100)]
    assert [work_order_row(n) for n in range(100)] == [work_order_row(n) for n in range(100)]


@pytest.mark.rule("DATA-07")
def test_another_seed_gives_other_rows():
    assert equipment_row(1, seed=1) != equipment_row(1, seed=2)


@pytest.mark.rule("DATA-07")
def test_the_rows_are_the_same_on_every_computer_and_python():
    rows = [row for n in range(1_000) for row in (equipment_row(n), work_order_row(n))]
    text = "\n".join("|".join(str(value) for value in row.values()) for row in rows)
    assert hashlib.sha256(text.encode()).hexdigest() == FROZEN


@pytest.mark.rule("DATA-07")
def test_a_row_is_the_same_however_many_are_asked_for(database_url):
    engine_rows = []
    migrate(database_url)
    engine = create_database_engine(database_url)
    for count in (10, 20):
        with Session(engine) as session:
            replace_rows(session, rows=count)
            session.commit()
            engine_rows.append(session.scalars(select(Equipment.cost).order_by(Equipment.id).limit(10)).all())
    engine.dispose()
    assert engine_rows[0] == engine_rows[1]
    assert engine_rows[0] == [equipment_row(n)["cost"] for n in range(10)]


def test_rows_look_like_the_demo():
    rows = [equipment_row(n) for n in range(5_000)]
    assert {row["status"] for row in rows} == set(EQUIPMENT_STATUSES)
    assert sum(row["status"] == "in_service" for row in rows) > 3_500
    assert all(date(2026, 11, 1) <= row["next_inspection"] < date(2028, 11, 1) for row in rows)
    assert all(-row["cost"].as_tuple().exponent == 20 for row in rows)
    assert all(row["updated_at"].tzinfo is UTC for row in rows)
    orders = [work_order_row(n) for n in range(1_000)]
    assert {row["status"] for row in orders} == set(WORK_ORDER_STATUSES)
    assert all((row["closed_at"] is not None) == (row["status"] == "closed") for row in orders)


@pytest.mark.rule("DATA-07")
def test_fifty_thousand_rows_arrive_whole(session):
    assert replace_rows(session) == 10_000
    session.commit()
    assert session.scalar(select(func.count()).select_from(Equipment)) == 50_000
    assert session.scalar(select(func.count()).select_from(WorkOrder)) == 10_000
    assert session.get(Equipment, 1).cost == equipment_row(0)["cost"]
    last = session.get(Equipment, 50_000)
    assert (last.code, last.next_inspection) == ("EQ-050000", equipment_row(49_999)["next_inspection"])
    assert session.get(WorkOrder, 10_000).equipment.id == 49_986
    assert total(session, Equipment.cost) == exact_sum(equipment_row(n)["cost"] for n in range(50_000))


def test_generating_again_replaces_the_rows(session):
    replace_rows(session, rows=20)
    replace_rows(session, rows=10)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Equipment)) == 10
    assert session.scalar(select(func.count()).select_from(WorkOrder)) == 2


def test_a_new_row_after_generating_gets_a_free_number(session):
    replace_rows(session, rows=10)
    session.commit()
    row = equipment_row(10) | {"code": "NEW"}
    del row["id"]
    session.add(Equipment(**row))
    session.commit()
    assert session.scalar(select(Equipment.id).where(Equipment.code == "NEW")) == 11


def test_a_status_outside_the_list_is_refused(session):
    row = equipment_row(0) | {"status": "invented"}
    session.add(Equipment(**row))
    with pytest.raises(IntegrityError):
        session.flush()


def test_a_work_order_goes_with_its_equipment(session):
    replace_rows(session, rows=5)
    session.commit()
    session.delete(session.get(Equipment, 1))
    session.commit()
    assert session.scalar(select(func.count()).select_from(WorkOrder)) == 0


def test_generating_needs_development(monkeypatch):
    monkeypatch.setattr(generate, "get_settings", lambda: build_settings(environment="production"))
    monkeypatch.setattr("sys.argv", ["generate"])
    with pytest.raises(SystemExit, match="only with APP_ENVIRONMENT=development"):
        generate.main()


def test_the_command_generates_from_nothing(monkeypatch, tmp_path, capsys):
    url = f"sqlite:///{(tmp_path / 'new' / 'app.db').as_posix()}"
    monkeypatch.setattr(generate, "get_settings", lambda: build_settings(database_url=url))
    monkeypatch.setattr("sys.argv", ["generate", "--rows", "20"])
    generate.main()
    assert "20 equipment rows and 4 work orders" in capsys.readouterr().out
    engine = create_database_engine(url)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Equipment)) == 20
    engine.dispose()


def test_the_first_migration_gives_postgresql_its_exact_types():
    """Written by Alembic, with no server: the columns a real PostgreSQL would get."""
    config = Config(toml_file=str(ROOT / "pyproject.toml"), output_buffer=(output := StringIO()))
    config.attributes["database_url"] = "postgresql+psycopg://application@localhost/application"
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "cost NUMERIC(38, 20) NOT NULL" in sql
    assert "updated_at TIMESTAMP WITH TIME ZONE NOT NULL" in sql
    assert "FLOAT" not in sql
    assert "ADD COLUMN planned_on DATE" in sql
    assert "CREATE INDEX ix_equipment_cost ON equipment (cost)" in sql


@pytest.mark.parametrize("path", ["/", "/inspections", "/administration", "/settings", "/gallery", "/gallery/button"])
def test_the_demo_works_with_no_database_set_up(tmp_path, person, path):
    folder = tmp_path / "nothing-here"
    settings = build_settings(database_url=f"sqlite:///{(folder / 'app.db').as_posix()}")
    client = TestClient(create_app(settings))
    assert client.get(path, headers=person).status_code == 200
    assert client.get("/health").status_code == 200
    assert not folder.exists(), "showing a page must not create a database"
