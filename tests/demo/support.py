"""What the demo's tests share. Fixtures are in conftest.py: pytest must be the only one to import that file."""

import time
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from sqlalchemy.orm import Session

from app.core.database import create_database_engine, migrate
from app.demo.generate import replace_rows


def fill(url: str, rows: int) -> None:
    migrate(url)
    engine = create_database_engine(url)
    with Session(engine) as session:
        replace_rows(session, rows=rows)
        session.commit()
    engine.dispose()


def until(page: Any, expression: str, seconds: int = 15) -> None:
    """Waits for a condition. `wait_for_function` runs through eval, which this application's policy refuses.
    It returns as soon as the condition holds, so a long limit costs nothing when the test passes: it only spares a
    test that is right from failing on a computer busy with other tests."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if page.evaluate(expression):
                return
        except PlaywrightError:  # the page was reloading, which going back does on purpose
            pass
        page.wait_for_timeout(25)
    raise AssertionError(f"still not true: {expression}")


def announced(page: Any, text: str) -> None:
    until(page, f"document.querySelector('#announcements').textContent.includes({text!r})")
