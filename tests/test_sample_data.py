"""Each module's sample data: found with nothing to register, filled only where empty, never outside development."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.core import sample_data
from tests.conftest import build_settings


def package(root: Path, name: str, modules: dict[str, str]) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("", encoding="utf-8")
    for module, source in modules.items():
        (folder / f"{module}.py").write_text(source, encoding="utf-8")


FILLS = "def holds_rows(session):\n    return False\n\n\ndef fill(session):\n    pass\n"


def test_every_module_with_sample_data_is_found_and_the_bases_own_folders_are_not(tmp_path, monkeypatch):
    app = tmp_path / "sampleapp"
    package(tmp_path, "sampleapp", {})
    package(app, "orders", {"sample_data": FILLS})
    package(app, "notes", {"sample_data": FILLS})
    package(app, "reports", {"routes": ""})
    package(app, "core", {"sample_data": FILLS})
    (app / "loose").mkdir()
    (app / "loose" / "sample_data.py").write_text(FILLS, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        found = sample_data.modules(app, "sampleapp")
    finally:
        for name in [name for name in sys.modules if name.startswith("sampleapp")]:
            del sys.modules[name]
    assert [module.__name__ for module in found] == ["sampleapp.notes.sample_data", "sampleapp.orders.sample_data"]


def test_a_module_without_both_functions_is_said_plainly(tmp_path, monkeypatch):
    app = tmp_path / "halfapp"
    package(tmp_path, "halfapp", {})
    package(app, "orders", {"sample_data": "def fill(session):\n    pass\n"})
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        with pytest.raises(SystemExit, match="needs holds_rows"):
            sample_data.modules(app, "halfapp")
    finally:
        for name in [name for name in sys.modules if name.startswith("halfapp")]:
            del sys.modules[name]


class Recorder:
    def __init__(self, name: str, holds: bool) -> None:
        self.__name__ = f"app.{name}.sample_data"
        self.holds = holds
        self.filled: list[Session] = []

    def holds_rows(self, session: Session) -> bool:
        return self.holds

    def fill(self, session: Session) -> None:
        self.filled.append(session)


@pytest.fixture
def two_modules(monkeypatch, tmp_path) -> tuple[Recorder, Recorder]:
    url = f"sqlite:///{(tmp_path / 'app.db').as_posix()}"
    monkeypatch.setattr(sample_data, "get_settings", lambda: build_settings(database_url=url))
    full, empty = Recorder("orders", holds=True), Recorder("notes", holds=False)
    monkeypatch.setattr(sample_data, "modules", lambda: [full, empty])
    return full, empty


def test_if_empty_fills_only_the_modules_that_hold_no_rows(two_modules, capsys):
    full, empty = two_modules
    sample_data.main(["--if-empty"])
    assert (len(full.filled), len(empty.filled)) == (0, 1)
    assert "filled notes; left as they were: orders" in capsys.readouterr().out


def test_without_if_empty_every_module_is_filled_again(two_modules):
    full, empty = two_modules
    sample_data.main([])
    assert (len(full.filled), len(empty.filled)) == (1, 1)


def test_sample_data_needs_development(monkeypatch):
    monkeypatch.setattr(sample_data, "get_settings", lambda: build_settings(environment="production"))
    monkeypatch.setattr(sample_data, "modules", lambda: [SimpleNamespace()])
    with pytest.raises(SystemExit, match="only with APP_ENVIRONMENT=development"):
        sample_data.main(["--if-empty"])


def test_an_application_with_no_sample_data_still_gets_its_migrations(monkeypatch, tmp_path, capsys):
    url = f"sqlite:///{(tmp_path / 'new' / 'app.db').as_posix()}"
    monkeypatch.setattr(sample_data, "get_settings", lambda: build_settings(database_url=url))
    monkeypatch.setattr(sample_data, "modules", lambda: [])
    sample_data.main(["--if-empty"])
    assert (tmp_path / "new" / "app.db").is_file()
    assert "filled nothing" in capsys.readouterr().out
