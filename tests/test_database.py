"""The database layer, on SQLite always and on PostgreSQL when TEST_DATABASE_URL gives one."""

import inspect
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import ForeignKey, Integer, MetaData, case, cast, delete, func, select, text, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.schema import CreateTable

from app.core.columns import canonical
from app.core.database import (
    Base,
    DatabaseSession,
    InexactQuery,
    create_database_engine,
    exact_sum,
    get_session,
    total,
)
from app.core.settings import Settings
from app.main import create_app
from tests.conftest import build_settings
from tests.helpers import ROOT

SAMPLE = "12500.1234567890123456789"


class Tables(DeclarativeBase):
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    type_annotation_map = Base.type_annotation_map


class Sample(Tables):
    __tablename__ = "sample"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[Decimal | None]
    moment: Mapped[datetime | None]


class Child(Tables):
    __tablename__ = "child"

    id: Mapped[int] = mapped_column(primary_key=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("sample.id", ondelete="CASCADE"))


@pytest.fixture
def session(database_url: str) -> Iterator[Session]:
    engine = create_database_engine(database_url)
    Tables.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def engine_of(session: Session) -> str:
    return session.get_bind().dialect.name


def stored(session: Session, *amounts: Decimal | int | None) -> None:
    session.add_all(Sample(amount=amount) for amount in amounts)
    session.commit()


# Which database


@pytest.mark.rule("DATA-01")
@pytest.mark.parametrize("url", ["sqlite:///.data/app.db", "sqlite://", "sqlite+pysqlite:///a.db", "SQLITE:///a.db"])
def test_production_refuses_sqlite(url):
    with pytest.raises(ValueError, match="PostgreSQL"):
        build_settings(environment="production", database_url=url)


@pytest.mark.rule("DATA-01")
def test_production_is_the_default_and_refuses_the_default_database(monkeypatch):
    monkeypatch.delenv("APP_ENVIRONMENT")
    with pytest.raises(ValueError, match="never runs in production"):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.rule("DATA-01")
def test_the_application_really_does_not_start_on_sqlite_in_production(tmp_path):
    """As a server would load it, in a folder with no .env file."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("APP_")}
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=tmp_path,
        env=environment | {"PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert "SQLite never runs in production" in result.stderr


@pytest.mark.rule("DATA-01")
def test_production_starts_on_postgresql_without_connecting():
    assert create_app(build_settings(environment="production")).state.sessions is not None


@pytest.mark.parametrize("url", ["mysql://host/base", "not an address"])
def test_any_other_database_is_refused(url):
    with pytest.raises(ValueError, match="database_url"):
        build_settings(database_url=url)


def test_the_database_password_stays_out_of_messages():
    url = "postgresql://user:long" + "pass@host/base"
    assert "longpass" not in repr(build_settings(database_url=url))
    with pytest.raises(ValueError, match="default_language") as refused:
        build_settings(database_url=url, default_language="xx")
    assert "longpass" not in str(refused.value)


def test_the_sqlite_file_stays_out_of_git():
    assert ".data/\n" in (ROOT / ".gitignore").read_text(encoding="utf-8")


# Exact decimals


@pytest.mark.rule("DATA-02")
@pytest.mark.parametrize(
    "value",
    [
        SAMPLE,
        f"-{SAMPLE}",
        "0",
        "1000",
        "0.00000000000000000001",
        "999999999999999999.99999999999999999999",
    ],
)
def test_a_value_comes_back_exactly(session, value):
    stored(session, Decimal(value))
    session.expire_all()
    amount = session.scalar(select(Sample.amount))
    assert isinstance(amount, Decimal)
    assert format(amount, "f") == value


@pytest.mark.rule("DATA-02")
def test_each_database_stores_the_type_it_should(session):
    stored(session, Decimal("1.50"))
    query = {
        "sqlite": "SELECT typeof(amount), amount FROM sample",
        "postgresql": "SELECT pg_typeof(amount)::text, amount::text FROM sample",
    }[engine_of(session)]
    kind, value = session.execute(text(query)).one()
    assert (kind, value) == {
        "sqlite": ("text", "1.5"),
        "postgresql": ("numeric", "1.50000000000000000000"),
    }[engine_of(session)]


@pytest.mark.rule("DATA-02")
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1.50"), "1.5"),
        (Decimal("1.500"), "1.5"),
        (Decimal("-0.00"), "0"),
        (Decimal("1E+3"), "1000"),
        (Decimal("100"), "100"),
        (100, "100"),
        (Decimal("123456789012345678.12345678901234567891"), "123456789012345678.12345678901234567891"),
    ],
)
def test_one_value_has_one_text(value, expected):
    assert canonical(value) == expected


@pytest.mark.rule("DATA-02")
@pytest.mark.parametrize("value", [1.5, float("nan"), True, "1.5"])
def test_a_float_or_anything_else_inexact_is_refused(session, value):
    session.add(Sample(amount=value))
    with pytest.raises(StatementError, match="takes a Decimal or an int"):
        session.flush()


@pytest.mark.rule("DATA-02")
@pytest.mark.parametrize("build", [lambda: Sample.amount == 1.5, lambda: Sample.amount > 1.5])
def test_a_float_in_a_query_is_refused(session, build):
    with pytest.raises(StatementError, match="takes a Decimal or an int"):
        session.execute(select(Sample).where(build()))


@pytest.mark.rule("DATA-02")
@pytest.mark.parametrize(
    "value",
    ["1E+18", "-1E+18", "0.000000000000000000001", "12500.123456789012345678901", "NaN", "Infinity"],
)
def test_a_value_the_column_cannot_hold_whole_is_refused_on_both_databases(session, value):
    """PostgreSQL alone would round the extra decimals without a word."""
    session.add(Sample(amount=Decimal(value)))
    with pytest.raises(StatementError, match="An exact column holds"):
        session.flush()


@pytest.mark.rule("DATA-02")
def test_no_model_or_migration_declares_an_inexact_column():
    sources = [*(ROOT / "app").rglob("*.py"), *(ROOT / "migrations").rglob("*.py")]
    found = {
        path.name: inexact_columns(path.read_text(encoding="utf-8")) for path in sources if path.name != "columns.py"
    }
    assert {name: words for name, words in found.items() if words} == {}


@pytest.mark.rule("DATA-02")
@pytest.mark.parametrize(
    "line",
    [
        "weight: Mapped[float]",
        'sa.Column("a", sa.Float(), nullable=False)',
        "cost = Column(Numeric(10, 2))",
        "Double()",
    ],
)
def test_the_check_for_inexact_columns_finds_one(line):
    assert inexact_columns(line) != []


def inexact_columns(source: str) -> list[str]:
    """Numeric only through ExactDecimal: a Numeric of its own would be a float on SQLite."""
    return re.findall(r"Mapped\[float|\b(?:Float|Double|DOUBLE|REAL|Numeric)\(", source)


@pytest.mark.rule("DATA-02")
def test_each_engine_gets_its_own_column_types():
    table = CreateTable(Sample.__table__)  # type: ignore[arg-type]
    on_postgresql = str(table.compile(dialect=postgresql.dialect()))
    on_sqlite = str(table.compile(dialect=sqlite.dialect()))
    assert "amount NUMERIC(38, 20)" in on_postgresql
    assert "moment TIMESTAMP WITH TIME ZONE" in on_postgresql
    assert "amount TEXT COLLATE exact_decimal" in on_sqlite
    assert "moment DATETIME" in on_sqlite


# Ordering and adding


NUMBERS = ["-50", "-5", "-0.5", "0", "0.5", "9", "10", "100", "1000.5"]


@pytest.mark.rule("DATA-03")
def test_ordering_is_numeric_on_both_databases(session):
    stored(session, *(Decimal(number) for number in reversed(NUMBERS)))
    ascending = session.scalars(select(Sample.amount).order_by(Sample.amount)).all()
    descending = session.scalars(select(Sample.amount).order_by(Sample.amount.desc())).all()
    assert [format(number, "f") for number in ascending] == NUMBERS
    assert [format(number, "f") for number in descending] == NUMBERS[::-1]


@pytest.mark.rule("DATA-03")
def test_ordering_written_by_hand_is_numeric_too(session):
    stored(session, Decimal("9"), Decimal("100"), Decimal("-5"))
    rows = session.execute(text("SELECT amount FROM sample ORDER BY amount")).scalars()
    assert [Decimal(row) for row in rows] == [Decimal("-5"), Decimal("9"), Decimal("100")]


@pytest.mark.rule("DATA-03")
def test_comparing_is_numeric_on_both_databases(session):
    stored(session, *(Decimal(number) for number in NUMBERS))
    above = session.scalars(select(Sample.amount).where(Sample.amount > Decimal("9.5"))).all()
    assert sorted(above) == [Decimal("10"), Decimal("100"), Decimal("1000.5")]
    between = select(Sample.amount).where(Sample.amount.between(Decimal("-5"), Decimal("0.5")))
    assert sorted(session.scalars(between)) == [Decimal("-5"), Decimal("-0.5"), Decimal("0"), Decimal("0.5")]
    assert session.scalar(select(func.max(Sample.amount))) == Decimal("1000.5")
    assert session.scalar(select(func.min(Sample.amount))) == Decimal("-50")
    assert session.scalar(select(func.count(Sample.amount))) == len(NUMBERS)
    assert session.scalar(select(Sample.amount).where(Sample.amount == Decimal("0.50"))) == Decimal("0.5")


INEXACT = {
    "sum": lambda: select(func.sum(Sample.amount)),
    "average": lambda: select(func.avg(Sample.amount)),
    "sqlite's total": lambda: select(func.coalesce(func.sum(Sample.amount), 0)),
    "a function": lambda: select(func.abs(Sample.amount)),
    "a function in the order": lambda: select(Sample.id).order_by(func.coalesce(Sample.amount, 0)),
    "adding": lambda: select(Sample.amount + 1),
    "multiplying in the order": lambda: select(Sample.id).order_by(Sample.amount * 2),
    "changing the sign": lambda: select(-Sample.amount),
    "cast": lambda: select(cast(Sample.amount, Integer)),
    "case in the order": lambda: select(Sample.id).order_by(case((Sample.id > 1, Sample.amount), else_=Decimal(0))),
    "update": lambda: update(Sample).values(amount=Sample.amount + 1),
    "inside a subquery": lambda: select(func.sum(select(Sample.amount).subquery().c.amount)),
}


@pytest.mark.rule("DATA-03")
@pytest.mark.parametrize("build", INEXACT.values(), ids=INEXACT.keys())
def test_what_sqlite_would_answer_with_a_float_fails_loudly(session, build):
    stored(session, Decimal("0.1"), Decimal("0.2"))
    if engine_of(session) == "sqlite":
        with pytest.raises(InexactQuery, match="not be exact"):
            session.execute(build())
    else:
        session.execute(build())


def test_a_float_sum_on_sqlite_is_really_wrong(tmp_path):
    """Why the refusal exists: this is what SQLite answers when nothing stops it."""
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Tables.metadata.create_all(engine)
    with Session(engine) as session:
        stored(session, Decimal("0.1"), Decimal("0.2"))
        assert isinstance(session.execute(text("SELECT sum(amount) FROM sample")).scalar(), float)
    engine.dispose()


def test_other_columns_add_up_as_usual(session):
    stored(session, Decimal("1"), Decimal("2"))
    assert session.scalar(select(func.sum(Sample.id))) == 3


@pytest.mark.rule("DATA-03")
def test_total_is_the_same_exact_answer_on_both_databases(session):
    value = Decimal("123456789012345678.12345678901234567891")
    stored(session, value, value, value, None)
    expected = Decimal("370370367037037034.37037036703703703673")
    assert sum([value, value, value]) != expected, "Python's sum rounds to 28 digits"
    assert total(session, Sample.amount) == expected
    assert exact_sum([value, None, value, value]) == expected


@pytest.mark.rule("DATA-03")
def test_total_of_a_part_or_of_nothing(session):
    stored(session, Decimal("0.1"), Decimal("0.2"), Decimal("5"))
    assert total(session, Sample.amount, Sample.amount < Decimal("1")) == Decimal("0.3")
    assert total(session, Sample.amount, Sample.amount > Decimal("9")) == 0


# Moments


@pytest.mark.rule("LANG-15")
def test_a_moment_in_any_zone_is_stored_in_utc_and_comes_back_aware(session):
    madrid = datetime(2026, 7, 1, 2, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    session.add(Sample(moment=madrid))
    session.commit()
    session.expire_all()
    moment = session.scalar(select(Sample.moment))
    assert moment == madrid
    assert moment.tzinfo is UTC
    assert (moment.day, moment.hour) == (1, 0)


@pytest.mark.rule("LANG-15")
@pytest.mark.parametrize("value", [datetime(2026, 7, 1, 12, 0), date(2026, 7, 1), "2026-07-01"])
def test_a_moment_without_a_zone_is_refused(session, value):
    session.add(Sample(moment=value))
    with pytest.raises(StatementError, match="needs a datetime with its time zone"):
        session.flush()


@pytest.mark.rule("LANG-15")
def test_moments_order_by_the_instant_not_by_the_clock(session):
    new_york = datetime(2026, 7, 1, 1, 0, tzinfo=ZoneInfo("America/New_York"))  # 05:00 UTC
    madrid = datetime(2026, 7, 1, 2, 0, tzinfo=ZoneInfo("Europe/Madrid"))  # 00:00 UTC
    session.add_all([Sample(moment=new_york), Sample(moment=madrid)])
    session.commit()
    assert session.scalars(select(Sample.moment).order_by(Sample.moment)).all() == [madrid, new_york]
    assert session.scalars(select(Sample.moment).where(Sample.moment > madrid)).all() == [new_york]


@pytest.mark.rule("LANG-15")
def test_sqlite_keeps_a_moment_as_utc_text(session):
    if engine_of(session) != "sqlite":
        pytest.skip("PostgreSQL has a type of its own")
    session.add(Sample(moment=datetime(2026, 7, 1, 2, 0, tzinfo=ZoneInfo("Europe/Madrid"))))
    session.commit()
    assert session.execute(text("SELECT moment FROM sample")).scalar() == "2026-07-01 00:00:00.000000"


# Foreign keys


@pytest.mark.rule("DATA-04")
def test_a_row_cannot_point_to_nothing(session):
    session.add(Child(sample_id=99))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.rule("DATA-04")
def test_deleting_a_row_follows_its_foreign_keys(session):
    session.add(Sample(id=1))
    session.flush()
    session.add(Child(sample_id=1))
    session.commit()
    session.execute(delete(Sample))
    assert session.scalar(select(func.count()).select_from(Child)) == 0


# A session per request


def application_on(database_url: str) -> FastAPI:
    application = create_app(build_settings(database_url=database_url))
    Tables.metadata.create_all(application.state.sessions.kw["bind"])

    def save(session: DatabaseSession) -> JSONResponse:
        session.add(Sample(amount=Decimal("1.5")))
        session.commit()
        return JSONResponse({})

    def forget(session: DatabaseSession) -> JSONResponse:
        session.add(Sample(amount=Decimal("2.5")))
        session.flush()
        return JSONResponse({})

    def fail(session: DatabaseSession) -> JSONResponse:
        session.add(Sample(amount=Decimal("3.5")))
        session.flush()
        raise RuntimeError

    for route in (save, forget, fail):
        application.add_api_route(f"/{route.__name__}", route)
    return application


def test_a_request_saves_only_what_its_route_commits(database_url, person):
    application = application_on(database_url)
    client = TestClient(application, raise_server_exceptions=False)
    assert client.get("/save", headers=person).status_code == 200
    assert client.get("/forget", headers=person).status_code == 200
    assert client.get("/fail", headers=person).status_code == 500
    with application.state.sessions() as session:
        assert session.scalars(select(Sample.amount)).all() == [Decimal("1.5")]
    application.state.sessions.kw["bind"].dispose()


def async_routes_with_a_session(application: FastAPI) -> list[str]:
    routes = [route for route in application.routes if isinstance(route, APIRoute)]
    return [
        route.path
        for route in routes
        if inspect.iscoroutinefunction(route.endpoint)
        and any(dependency.call is get_session for dependency in route.dependant.dependencies)
    ]


@pytest.mark.rule("DATA-05")
def test_no_route_that_uses_the_database_stops_the_server():
    assert async_routes_with_a_session(create_app(build_settings())) == []


@pytest.mark.rule("DATA-05")
def test_the_check_for_routes_finds_one():
    application = create_app(build_settings())

    async def blocks(session: DatabaseSession) -> None:
        session.commit()

    application.add_api_route("/blocks", blocks)
    assert async_routes_with_a_session(application) == ["/blocks"]
