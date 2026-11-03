"""Each module's sample data: made-up rows, so a person trying the application sees its screens filled.

uv run --frozen python -m app.core.sample_data              # every module's rows, made again
uv run --frozen python -m app.core.sample_data --if-empty   # only modules that hold no rows yet: what a preview runs

Applies the migrations first, either way, so it is all a preview's setup needs. Only in development. A module brings its
own in `app/<module>/sample_data.py`, with two functions, and nothing to register:

    def holds_rows(session: Session) -> bool: ...   # whether the module's tables hold any row
    def fill(session: Session) -> None: ...         # replaces the module's rows with the made-up ones

The caller commits. The rows are invented: no real people or companies. See docs/base/specification.md#adapting-it
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


def modules(folder: Path = APP, package: str = "app") -> list[ModuleType]:
    """Every package of `folder` with a `sample_data.py`, in name order, each checked for both functions."""
    found = []
    for path in sorted(folder.iterdir()):
        if path.name in SHARED or not (path / "__init__.py").is_file() or not (path / "sample_data.py").is_file():
            continue
        module = importlib.import_module(f"{package}.{path.name}.sample_data")
        if not callable(getattr(module, "holds_rows", None)) or not callable(getattr(module, "fill", None)):
            raise SystemExit(f"{package}/{path.name}/sample_data.py needs holds_rows(session) and fill(session)")
        found.append(module)
    return found


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fills each module's tables with made-up rows.")
    parser.add_argument("--if-empty", action="store_true", help="leave a module whose tables hold rows as it is")
    options = parser.parse_args(arguments)
    settings = get_settings()
    if settings.environment != "development":
        raise SystemExit("Sample data is made up: it runs only with APP_ENVIRONMENT=development")
    url = settings.database_url.get_secret_value()
    migrate(url)
    filled, left = [], []
    engine = create_database_engine(url)
    with Session(engine) as session:
        for module in modules():
            name = module.__name__.split(".")[-2]
            if options.if_empty and module.holds_rows(session):
                left.append(name)
                continue
            module.fill(session)
            filled.append(name)
        session.commit()
    engine.dispose()
    print(f"Sample data: filled {', '.join(filled) or 'nothing'}; left as they were: {', '.join(left) or 'nothing'}")


if __name__ == "__main__":
    main()
