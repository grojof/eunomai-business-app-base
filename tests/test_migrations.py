"""The migrations: they run on both databases, and they say the same as the models."""

import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import Column, Integer, Table, text

from app.core.columns import COLLATION, ExactDecimal, UtcDateTime
from app.core.database import Base, create_database_engine, migrate
from tests.helpers import ROOT

TABLES = '''"""Two tables, one pointing to the other."""

import sqlalchemy as sa
from alembic import op

revision = "1"
down_revision = None


def upgrade():
    op.create_table("parent", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("old", sa.Integer()))
    op.create_table(
        "child",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("parent.id", ondelete="CASCADE"), nullable=False),
    )
    op.execute("INSERT INTO parent (id) VALUES (1)")
    op.execute("INSERT INTO child (id, parent_id) VALUES (1, 1)")


def downgrade():
    pass
'''
BATCH_CHANGE = '''"""A change that makes SQLite copy the table and drop the old one. PostgreSQL just alters it."""

from alembic import op

revision = "2"
down_revision = "1"


def upgrade():
    with op.batch_alter_table("parent") as batch:
        batch.drop_column("old")


def downgrade():
    pass
'''


EXACT_TABLE = '''"""A table with an exact column, as an application would write it."""

import sqlalchemy as sa
from alembic import op

from app.core.columns import ExactDecimal

revision = "1"
down_revision = None


def upgrade():
    op.create_table(
        "invoice",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount", ExactDecimal()),
        sa.Column("old", sa.Integer()),
    )
    op.execute("INSERT INTO invoice (id, amount) VALUES (1, \'100\'), (2, \'9\')")


def downgrade():
    pass
'''
EXACT_BATCH_CHANGE = '''"""What a clone's next migration may do: on SQLite, it copies the table."""

from alembic import op

revision = "2"
down_revision = "1"


def upgrade():
    with op.batch_alter_table("invoice") as batch:
        batch.drop_column("old")


def downgrade():
    pass
'''


def alembic_config(url: str) -> Config:
    config = Config(toml_file=str(ROOT / "pyproject.toml"))
    config.attributes["database_url"] = url
    return config


@pytest.mark.rule("DATA-06")
def test_models_and_migrations_say_the_same(database_url):
    migrate(database_url)
    command.check(alembic_config(database_url))


@pytest.mark.rule("DATA-06")
def test_the_check_notices_a_table_with_no_migration(database_url):
    migrate(database_url)
    table = Table("forgotten", Base.metadata, Column("id", Integer, primary_key=True))
    try:
        with pytest.raises(CommandError, match="forgotten"):
            command.check(alembic_config(database_url))
    finally:
        Base.metadata.remove(table)


@pytest.mark.rule("DATA-06")
def test_every_migration_goes_down_and_up_again(database_url):
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


def sqlite_shape(url: str) -> dict[str, Any]:
    """What a table really is on SQLite, read from the file: what `alembic check` cannot see, such as a collation."""
    engine = create_database_engine(url)
    with engine.connect() as connection:
        tables = dict(
            connection.execute(
                text("SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'alembic%'")
            ).all()
        )
        shape = {}
        for name, sql in tables.items():
            columns = connection.exec_driver_sql(f"PRAGMA table_info('{name}')").all()
            indexes = connection.exec_driver_sql(f"PRAGMA index_list('{name}')").all()
            keys = connection.exec_driver_sql(f"PRAGMA foreign_key_list('{name}')").all()
            shape[name] = {
                "columns": [tuple(column[1:]) for column in columns],
                "collated": sorted(re.findall(rf'"?(\w+)"? TEXT COLLATE "?{COLLATION}', sql)),
                "checks": sorted(re.findall(r'CONSTRAINT "?(\w+)"? CHECK', sql)),
                "indexes": sorted(index[1] for index in indexes if not index[1].startswith("sqlite_autoindex")),
                "foreign keys": sorted((key[2], key[3], key[6]) for key in keys),
            }
    engine.dispose()
    return shape


@pytest.mark.rule("DATA-06")
def test_each_migration_goes_down_one_and_up_one_leaving_the_same_tables(database_url):
    """Down one and up one, for each: a batch change copies a table, and a copy can lose what `alembic check` cannot
    see. A clone's next migration is caught here too."""
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    sqlite = database_url.startswith("sqlite")
    expected = sqlite_shape(database_url) if sqlite else None
    for revision in ScriptDirectory.from_config(config).walk_revisions():
        command.downgrade(config, str(revision.down_revision or "base"))
        command.upgrade(config, revision.revision)
        command.upgrade(config, "head")
        command.check(config)
        if sqlite:
            assert sqlite_shape(database_url) == expected, revision.revision


@pytest.mark.rule("DATA-06")
def test_the_shape_says_which_columns_are_exact(database_url):
    if not database_url.startswith("sqlite"):
        pytest.skip("a collation is what SQLite needs")
    migrate(database_url)
    shape = sqlite_shape(database_url)
    for table in Base.metadata.tables.values():
        exact = sorted(column.name for column in table.columns if isinstance(column.type, ExactDecimal))
        assert shape[table.name]["collated"] == exact


def scripts_in(folder: Path, *scripts: str) -> Config:
    """The real env.py, with these migrations."""
    (folder / "versions").mkdir(parents=True)
    shutil.copy(ROOT / "migrations" / "env.py", folder / "env.py")
    for number, script in enumerate(scripts, start=1):
        (folder / "versions" / f"{number}_test.py").write_text(script, encoding="utf-8")
    return Config(toml_file=str(ROOT / "pyproject.toml"))


@pytest.mark.rule("DATA-06")
def test_a_batch_change_keeps_the_rows_that_point_to_the_table(database_url, tmp_path):
    config = scripts_in(tmp_path / "scripts", TABLES, BATCH_CHANGE)
    config.set_main_option("script_location", (tmp_path / "scripts").as_posix())
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")
    engine = create_database_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM child")) == 1
        assert list(connection.execute(text("SELECT * FROM parent")).keys()) == ["id"]
    engine.dispose()


@pytest.mark.rule("DATA-02")
def test_a_batch_change_in_any_migration_keeps_an_exact_column_numeric(database_url, tmp_path):
    config = scripts_in(tmp_path / "scripts", EXACT_TABLE, EXACT_BATCH_CHANGE)
    config.set_main_option("script_location", (tmp_path / "scripts").as_posix())
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")
    engine = create_database_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalars(text("SELECT id FROM invoice ORDER BY amount")).all() == [2, 1]
    engine.dispose()


def test_a_generated_migration_writes_the_exact_types_as_they_are_made():
    """`alembic revision --autogenerate` copies a type's repr into the migration: with its arguments, the migration
    would not run, since these types take none. tools/new_module.py and a person adding a table both rely on it."""
    from alembic.autogenerate import render_python_code
    from alembic.operations import ops
    from sqlalchemy import MetaData

    table = Table("sample", MetaData(), Column("amount", ExactDecimal()), Column("moment", UtcDateTime()))
    code = render_python_code(ops.UpgradeOps([ops.CreateTableOp.from_table(table)]))
    assert "app.core.columns.ExactDecimal()" in code and "app.core.columns.UtcDateTime()" in code
