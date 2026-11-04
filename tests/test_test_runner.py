"""tools/test.py: what a change can break, by fixed rules, and the two passes of a fast run."""

import pytest

from tests.helpers import ROOT
from tools import test as runner


def names(selection: runner.Selection) -> set[str]:
    return {path.name for path in selection.files}


def test_a_changed_test_file_runs_itself_alone() -> None:
    chosen = runner.select(["tests/test_docs.py"])
    assert names(chosen) == {"test_docs.py"} and not chosen.everything


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "uv.lock",
        "tests/conftest.py",
        "tests/helpers.py",
        "app/core/settings.py",
        "something/unknown.txt",
    ],
)
def test_what_everything_rests_on_or_no_rule_knows_runs_everything(path: str) -> None:
    assert runner.select([path]).everything


def test_the_data_layer_runs_every_database_test() -> None:
    chosen = runner.select(["app/core/columns.py"])
    assert chosen.database and {"test_database.py", "test_migrations.py"} <= names(chosen)
    assert "test_icons.py" not in names(chosen)


def test_a_module_runs_its_own_tests_and_those_that_name_it() -> None:
    chosen = runner.select(["app/core/gantt.py"])
    assert "test_gantt.py" in names(chosen) and not chosen.everything


def test_documentation_runs_the_tests_that_read_it() -> None:
    chosen = runner.select(["docs/base/specification.md"])
    assert {"test_docs.py", "test_standards.py"} <= names(chosen) and not chosen.everything


def test_texts_run_the_tests_that_read_the_translations() -> None:
    assert "test_language.py" in names(runner.select(["locales/es/LC_MESSAGES/messages.po"]))


def test_a_tool_runs_the_tests_that_name_it() -> None:
    assert "test_new_module.py" in names(runner.select(["tools/new_module.py"]))


@pytest.mark.skipif(
    not (ROOT / "tests" / "test_workflows.py").exists(),
    reason="an organization's template leaves out the base's workflows and the tests that read them",
)
def test_the_workflows_run_their_tests() -> None:
    assert "test_workflows.py" in names(runner.select([".github/workflows/tests.yml"]))


def test_every_choice_says_why() -> None:
    chosen = runner.select(["docs/base/specification.md", "something/unknown.txt"])
    assert len(chosen.why) == 2 and "everything" in chosen.why[1]


def test_a_fast_run_is_two_passes_over_the_same_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(runner, "_run", lambda command: commands.append(command) or 0)
    assert runner.run(["tests/test_docs.py"]) == 0
    assert commands[0][-5:] == [
        "-n",
        str(min(runner.WORKERS, runner.os.cpu_count() or 1)),
        "-m",
        "not serial",
        "tests/test_docs.py",
    ]
    assert commands[1][-3:] == ["-m", "serial", "tests/test_docs.py"]


def test_a_test_that_waits_on_the_clock_is_serial_and_this_one_is_not(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("serial") is None
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_collection_modifyitems" in conftest and "item.add_marker(pytest.mark.serial)" in conftest
