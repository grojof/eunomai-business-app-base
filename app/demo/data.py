"""Whether the demo's generated rows are there. The first run needs no database, so a screen asks before it reads."""

import logging
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.demo.models import Equipment

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent
READY = "ready"
MISSING = "missing"
UNREACHABLE = "unreachable"
GENERATE = "uv run --frozen python -m app.demo.generate"
"""The command a screen shows when the rows are not there. It applies the migrations too."""


@lru_cache
def _newest_migration() -> str | None:
    return ScriptDirectory.from_config(Config(toml_file=str(ROOT / "pyproject.toml"))).get_current_head()


def rows_state(session: Session) -> str:
    """READY, MISSING or UNREACHABLE. Migrations behind the code count as missing: generating brings them up to date.

    A SQLite file that does not exist stays that way: connecting would create it, and showing a page must not.
    """
    url = session.get_bind().engine.url
    if url.get_backend_name() == "sqlite" and url.database and not Path(url.database).exists():
        return MISSING
    try:
        if MigrationContext.configure(session.connection()).get_current_revision() != _newest_migration():
            return MISSING
        return READY if session.scalar(select(Equipment.id).limit(1)) is not None else MISSING
    except OperationalError:
        logger.exception("The database does not answer")
        return UNREACHABLE
