"""The migrations: they run on both databases, and they say the same as the models."""

import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import Column, Integer, Table, text

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
