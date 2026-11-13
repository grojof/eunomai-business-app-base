"""Each module's sample data: made-up rows, so a person trying the application sees its screens filled.

uv run --frozen python -m app.core.sample_data              # every module's rows, made again
uv run --frozen python -m app.core.sample_data --if-empty   # only modules that hold no rows yet: what a preview runs

Applies the migrations first, either way, so it is all a preview's setup needs. Only in development. A module brings its
own in `app/<module>/sample_data.py`, with two functions, and nothing to register:

    def holds_rows(session: Session) -> bool: ...   # whether the module's tables hold any row
    def fill(session: Session) -> None: ...         # replaces the module's rows with the made-up ones

and, when its rows point to another module's, two more things:

    AFTER = ("audits",)                             # the modules whose rows must be there first
    def empty(session: Session) -> None: ...        # takes its rows away, before the modules it points to refill

The caller commits. The rows are invented: no real people or companies. See docs/base/adapting-it.md#adapting-it
"""

import argparse
import importlib
from pathlib import Path
from types import ModuleType

from sqlalchemy.orm import Session

from app.core.database import create_database_engine, migrate
from app.core.settings import get_settings

APP = Path(__file__).resolve().parent.parent
SHARED = {"core", "ui", "brand"}
"""The base's own folders of app/: they have no tables of their own to fill."""


def name_of(module: ModuleType) -> str:
    return module.__name__.split(".")[-2]


def in_order(found: list[ModuleType]) -> list[ModuleType]:
    """Each module after those its `AFTER` names, and otherwise in name order. Refused when one names a module that
    has no sample data, or when two wait for each other."""
    by_name = {name_of(module): module for module in found}
    ordered: list[ModuleType] = []
    waiting: list[str] = []

    def place(name: str) -> None:
        if by_name[name] in ordered:
            return
        if name in waiting:
            raise SystemExit(f"Sample data: {' -> '.join([*waiting, name])} wait for each other")
        waiting.append(name)
        for first in getattr(by_name[name], "AFTER", ()):
            if first not in by_name:
                raise SystemExit(f"Sample data: {name} comes after {first}, which has no sample_data.py")
            place(first)
        waiting.pop()
        ordered.append(by_name[name])

    for name in sorted(by_name):
        place(name)
    return ordered


def modules(folder: Path = APP, package: str = "app") -> list[ModuleType]:
    """Every package of `folder` with a `sample_data.py`, each checked for both functions, in the order they fill."""
    found = []
    for path in sorted(folder.iterdir()):
        if path.name in SHARED or not (path / "__init__.py").is_file() or not (path / "sample_data.py").is_file():
            continue
        module = importlib.import_module(f"{package}.{path.name}.sample_data")
        if not callable(getattr(module, "holds_rows", None)) or not callable(getattr(module, "fill", None)):
            raise SystemExit(f"{package}/{path.name}/sample_data.py needs holds_rows(session) and fill(session)")
        found.append(module)
    return in_order(found)


def fill_all(session: Session, *, if_empty: bool = False) -> tuple[list[str], list[str]]:
    """Every module's rows, in order: the names filled, and those left as they were. Made again, the modules that
    point to others are emptied first, last to first, so no row is left pointing to one that went."""
    found = modules()
    chosen = [module for module in found if not (if_empty and module.holds_rows(session))]
    if not if_empty:
        for module in reversed(found):
            if callable(empty := getattr(module, "empty", None)):
                empty(session)
    for module in chosen:
        module.fill(session)
    return [name_of(module) for module in chosen], [name_of(module) for module in found if module not in chosen]


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fills each module's tables with made-up rows.")
    parser.add_argument("--if-empty", action="store_true", help="leave a module whose tables hold rows as it is")
    options = parser.parse_args(arguments)
    settings = get_settings()
    if settings.environment != "development":
        raise SystemExit("Sample data is made up: it runs only with APP_ENVIRONMENT=development")
    url = settings.database_url.get_secret_value()
    migrate(url)
    engine = create_database_engine(url)
    with Session(engine) as session:
        filled, left = fill_all(session, if_empty=options.if_empty)
        session.commit()
    engine.dispose()
    print(f"Sample data: filled {', '.join(filled) or 'nothing'}; left as they were: {', '.join(left) or 'nothing'}")


if __name__ == "__main__":
    main()
