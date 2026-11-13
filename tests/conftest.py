import atexit
import inspect
import os
import re
import shutil
import socket
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from gettext import NullTranslations
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url

from app.core import i18n
from app.core.database import migrate
from app.core.settings import Settings
from app.main import create_app

PERSON = {"X-Remote-User": "demo.person", "X-Remote-Name": "Demo Person", "X-Remote-Groups": "staff|admins"}
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
"""A PostgreSQL to run the database tests on as well. Nothing in it is touched: each test gets a schema of its own."""
_MIGRATED: list[str] = []
_SYSTEM_TEMPORARY = tempfile.gettempdir()
"""Read as the tests start: a test that sends temporary files elsewhere, to watch them, must not find this run's
database folder among them because it happened to be the first to ask for the database."""


def migrated_database() -> str:
    """Where a test looks unless it asks for a database: SQLite with every migration applied, the application's own
    included, made once per run. A page that reads one of the application's tables finds it empty, not missing, so an
    application never edits this file for its start page; and a person's own `.data/` never changes what tests see."""
    if not _MIGRATED:
        folder = Path(tempfile.mkdtemp(prefix="eunomai-business-app-base-tests-", dir=_SYSTEM_TEMPORARY))
        atexit.register(shutil.rmtree, folder, ignore_errors=True)
        url = f"sqlite:///{(folder / 'migrated.db').as_posix()}"
        migrate(url)
        _MIGRATED.append(url)
    return _MIGRATED[0]


def postgresql_is_missing(environment: Mapping[str, str]) -> bool:
    """On GitHub Actions on Linux the tests must reach PostgreSQL: a job whose database setting went wrong would run on
    SQLite alone and pass. Only the Dependencies workflow means to do that, and says so in `TESTS_ON_SQLITE_ALONE`."""
    on_linux_ci = environment.get("GITHUB_ACTIONS") == "true" and environment.get("RUNNER_OS") == "Linux"
    return on_linux_ci and not environment.get("TEST_DATABASE_URL") and not environment.get("TESTS_ON_SQLITE_ALONE")


def pytest_configure(config: pytest.Config) -> None:
    if postgresql_is_missing(os.environ):
        raise pytest.UsageError("TEST_DATABASE_URL is empty on Linux in CI: these tests would not reach PostgreSQL")


CLOCK = re.compile(r"time\.sleep|deadline|wait_for_timeout|time\.time\(\)|monotonic|perf_counter")
"""A test that measures or waits on the clock needs the computer to itself: beside other tests it only gets slower,
and then wrong. It is marked `serial` by what its body calls, so a new one is too; tools/test.py runs those after the
others, alone. `@pytest.mark.serial` marks any other test that must not share the computer."""


BASE_TESTS = frozenset(
    {
        "test_assets.py",
        "test_boards.py",
        "test_brand.py",
        "test_calendars.py",
        "test_charts.py",
        "test_components.py",
        "test_excel.py",
        "test_form_macros.py",
        "test_gantt.py",
        "test_identity.py",
        "test_input.py",
        "test_macros.py",
        "test_new_module.py",
        "test_palette.py",
        "test_preview.py",
        "test_settings.py",
        "test_tables.py",
        "test_test_runner.py",
        "test_tools.py",
        "test_update_application.py",
        "test_uploads.py",
    }
)
"""The files whose tests prove the base's own machinery: the shell, the macros, the data helpers, the tools. An
application does not change them (tests/test_base_files.py checks it), and the template it was made from ran them, so
`tools/test.py --application`, which a connector runs on a person's computer, leaves them out. The tests that read the
whole application (its templates, texts, models, migrations, rules, documentation) are not here."""


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    waits: dict[Any, bool] = {}
    for item in items:
        if item.path.name in BASE_TESTS and item.path.parent.name == "tests":
            item.add_marker(pytest.mark.base)
        function = getattr(item, "function", None)
        if function is None:
            continue
        if function not in waits:
            waits[function] = bool(CLOCK.search(inspect.getsource(function)))
        if waits[function]:
            item.add_marker(pytest.mark.serial)
    workers = int(getattr(config, "workerinput", {}).get("workercount", 1))
    items[:] = long_first(items, workers)


def long_first(items: list[Any], workers: int) -> list[Any]:
    """The tests marked `long` at the head of the workers' shares, one each in turn: pytest-xdist gives each worker a
    run of consecutive tests, so all of them first would leave one worker with every long test, one after another, and
    a long test last would leave the others waiting for it. Every worker orders them the same, as xdist requires."""
    long = [item for item in items if item.get_closest_marker("long")]
    rest = [item for item in items if not item.get_closest_marker("long")]
    share = max(1, len(items) // max(1, workers))
    places = {(number % workers) * share + number // workers: item for number, item in enumerate(long)}
    ordered: list[Any] = []
    for item in rest:
        while len(ordered) in places:
            ordered.append(places.pop(len(ordered)))
        ordered.append(item)
    return ordered + [places[place] for place in sorted(places)]


def build_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "development",
        "trusted_proxies": ["testclient"],
        "role_groups": {"admin": ["admins"]},
        "database_url": migrated_database(),
    }
    if overrides.get("environment") == "production":
        values["database_url"] = "postgresql+psycopg://application@localhost/application"  # nothing connects to it
    return Settings(**(values | overrides), _env_file=None)  # type: ignore[call-arg]


ENGINES = ["sqlite", "postgresql"] if TEST_DATABASE_URL else ["sqlite"]


@contextmanager
def empty_database(engine_name: str, folder: Path) -> Iterator[str]:
    """An empty database on one engine. The folder of the SQLite file does not exist yet, on purpose."""
    if engine_name == "sqlite":
        yield f"sqlite:///{(folder / 'database' / 'test.db').as_posix()}"
        return
    schema = f"test_{uuid4().hex}"
    administrator = create_engine(TEST_DATABASE_URL)
    with administrator.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
    # A lock that nobody will release fails the test, instead of holding the whole run until its time limit.
    options = f"-csearch_path={schema} -clock_timeout=30s"
    url = make_url(TEST_DATABASE_URL).update_query_dict({"options": options})
    yield url.render_as_string(hide_password=False)
    with administrator.begin() as connection:
        connection.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
    administrator.dispose()


@pytest.fixture(params=ENGINES)
def database_url(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[str]:
    with empty_database(request.param, tmp_path) as url:
        yield url


@pytest.fixture(autouse=True)
def source_language() -> None:
    """Every test starts in the language of the code. A test that activates another leaves it active for the next
    one on its worker, and which one that is changes with how the tests are shared out."""
    i18n._language.set("en")
    i18n._translations.set(NullTranslations())


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(build_settings()), raise_server_exceptions=False)


@pytest.fixture
def person() -> dict[str, str]:
    return dict(PERSON)


@contextmanager
def running_server(application: FastAPI, proxy_headers: bool = False) -> Iterator[int]:
    """A real uvicorn on a real port, which it returns. Without proxy headers, as it runs behind a proxy."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning", proxy_headers=proxy_headers)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    """The real application, for the browser checks."""
    settings = build_settings(fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port:
        yield f"http://127.0.0.1:{port}"


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        # A browser the computer has, never one downloaded: Chrome by default, Edge with APP_BROWSER_CHANNEL=msedge.
        chrome = playwright.chromium.launch(channel=os.environ.get("APP_BROWSER_CHANNEL", "chrome"))
        yield chrome
        chrome.close()


@contextmanager
def page_opener(browser: Any, base_url: str) -> Iterator[Callable[..., Any]]:
    contexts = []

    def opener(
        path: str,
        theme: str = "light",
        language: str = "en",
        width: int = 1280,
        bypass_csp: bool = False,
        layout: dict[str, str] | None = None,
        javascript: bool = True,
    ) -> Any:
        context = browser.new_context(
            viewport={"width": width, "height": 800}, bypass_csp=bypass_csp, java_script_enabled=javascript
        )
        contexts.append(context)
        context.add_cookies(
            [
                {"name": "theme", "value": theme, "url": base_url},
                {"name": "language", "value": language, "url": base_url},
                *({"name": f"layout_{k}", "value": v, "url": base_url} for k, v in (layout or {}).items()),
            ]
        )
        page = context.new_page()
        page.goto(base_url + path)
        return page

    yield opener
    for context in contexts:
        context.close()


@pytest.fixture
def open_page(browser: Any, base_url: str) -> Iterator[Callable[..., Any]]:
    with page_opener(browser, base_url) as opener:
        yield opener
