"""How Alembic reaches the database. Each module of models is imported here, or Alembic does not see its tables."""

from pathlib import Path
from typing import Any

from alembic import context

import app.demo.models  # noqa: F401  # demo
from app.core.database import Base, create_database_engine, number_revision
from app.core.settings import get_settings

url = context.config.attributes.get("database_url") or get_settings().database_url.get_secret_value()


def numbered(_context: Any, _revision: Any, directives: list[Any]) -> None:
    number_revision(directives, Path(__file__).resolve().parent / "versions")


def run_offline() -> None:
    """`alembic upgrade head --sql` writes the SQL instead of running it, to read before applying it."""
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_database_engine(url)
    with engine.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # A batch change copies a table and drops the old one. With foreign keys on, that drop would delete or
            # refuse the rows that point to it. SQLite ignores this inside a transaction, hence the commit.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        # Batch on both: a migration written against either database has to run on the other.
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=True,
            process_revision_directives=numbered,
        )
        with context.begin_transaction():
            context.run_migrations()
        if sqlite and connection.exec_driver_sql("PRAGMA foreign_key_check").first():
            raise RuntimeError("The migration left rows pointing to nothing")
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
