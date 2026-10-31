"""Databases with the demo's generated rows, for the screens that read them."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import create_database_engine, migrate
from app.demo.generate import replace_rows
from app.main import create_app
from tests.conftest import ENGINES, PERSON, build_settings, empty_database, page_opener, running_server

ROWS = 1_000
"""Enough for several pages, every filter and work orders, and quick to make."""


def fill(url: str, rows: int) -> None:
    migrate(url)
    engine = create_database_engine(url)
    with Session(engine) as session:
        replace_rows(session, rows=rows)
        session.commit()
    engine.dispose()


@pytest.fixture(scope="session", params=ENGINES)
def filled_url(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    with empty_database(request.param, tmp_path_factory.mktemp("filled")) as url:
        fill(url, ROWS)
        yield url


@pytest.fixture(scope="session", params=ENGINES)
def large_url(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The whole demo, 50,000 rows, for what must hold at that size."""
    with empty_database(request.param, tmp_path_factory.mktemp("large")) as url:
        fill(url, 50_000)
        yield url


@pytest.fixture
def filled(filled_url: str) -> TestClient:
    """A client of the application on generated rows, with a person's headers."""
    client = TestClient(create_app(build_settings(database_url=filled_url)), raise_server_exceptions=False)
    client.headers.update(PERSON)
    return client


@pytest.fixture(scope="session")
def filled_base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The real application on generated rows in SQLite, for the browser checks."""
    folder: Path = tmp_path_factory.mktemp("browser")
    url = f"sqlite:///{(folder / 'test.db').as_posix()}"
    fill(url, ROWS)
    settings = build_settings(database_url=url, fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port:
        yield f"http://127.0.0.1:{port}"


@pytest.fixture
def open_filled(browser: Any, filled_base_url: str) -> Iterator[Callable[..., Any]]:
    with page_opener(browser, filled_base_url) as opener:
        yield opener
