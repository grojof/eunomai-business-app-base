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


def test_a_fast_run_is_two_passes_over_the_same_selection_and_one_line_for_both(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commands: list[list[str]] = []
    passes = iter([(0, {"passed": 10, "skipped": 1, "deselected": 3}, 20.5), (0, {"passed": 3, "deselected": 11}, 4.5)])
    priorities: list[bool] = []

    def fake(command: list[str], low_priority: bool = False) -> tuple[int, dict[str, int], float]:
        commands.append(command)
        priorities.append(low_priority)
        return next(passes)

    monkeypatch.setattr(runner, "_run", fake)
    assert runner.run(["tests/test_docs.py"], workers=4, options=["-k", "board"]) == 0
    assert commands[0][-9:] == [
        "-n",
        "4",
        "--dist",
        "worksteal",
        "-m",
        "not serial",
        "-k",
        "board",
        "tests/test_docs.py",
    ]
    assert commands[1][-5:] == ["-m", "serial", "-k", "board", "tests/test_docs.py"]
    assert priorities == [True, False], "the serial pass measures time: it keeps the normal priority"
    assert capsys.readouterr().out.splitlines()[-1] == "13 passed, 1 skipped in 25.00s (both passes)"


def test_the_line_for_both_passes_reads_as_pytests_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """The connector reads the counts of a person's run from the last line, as it reads pytest's."""
    line = runner.summary({"passed": 13, "failed": 2}, 25)
    found = runner.SUMMARY.fullmatch(line)
    assert found and {word: int(n) for n, word in runner.COUNT.findall(found[1])} == {"failed": 2, "passed": 13}


def test_a_failed_pass_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    passes = iter([(1, {"failed": 1}, 1.0), (0, {"passed": 1}, 1.0)])
    monkeypatch.setattr(runner, "_run", lambda command, low_priority=False: next(passes))
    assert runner.run([], workers=2) == 1


@pytest.mark.parametrize(
    ("free", "cores", "workers"), [(None, 20, 8), (3 * 2**30, 20, 2), (64 * 2**30, 4, 4), (0, 4, 1)]
)
def test_workers_follow_the_cores_and_the_free_memory(
    monkeypatch: pytest.MonkeyPatch, free: int | None, cores: int, workers: int
) -> None:
    monkeypatch.setattr(runner, "free_memory", lambda: free)
    monkeypatch.setattr(runner.os, "cpu_count", lambda: cores)
    assert runner.default_workers() == workers


def test_pytests_own_options_go_after_a_double_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(
        runner,
        "run",
        lambda files, workers=None, options=None, application=False: calls.append((files, options, application)) or 0,
    )
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://example.test/x")
    assert runner.main(["--", "--ignore=tests/demo/test_template.py", "-x"]) == 0
    assert runner.main(["--application"]) == 0
    assert calls == [([], ["--ignore=tests/demo/test_template.py", "-x"], False), ([], [], True)]


def test_an_application_leaves_out_the_bases_own_tests_in_both_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """pytest keeps only the last `-m`: the marker joins each pass's own, or the passes would mix."""
    commands: list[list[str]] = []
    monkeypatch.setattr(runner, "_run", lambda command, low_priority=False: commands.append(command) or (0, {}, 0.0))
    runner.run([], 2, [], application=True)
    markers = [command[len(command) - command[::-1].index("-m")] for command in commands]  # pytest's, not python's
    assert markers == ["not serial and not base", "serial and not base"]


def test_a_test_that_waits_on_the_clock_is_serial_and_this_one_is_not(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("serial") is None
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_collection_modifyitems" in conftest and "item.add_marker(pytest.mark.serial)" in conftest


class Item:
    def __init__(self, name: str, long: bool = False) -> None:
        self.name, self.long = name, long

    def get_closest_marker(self, name: str) -> object:
        return self.long if name == "long" else None


def test_the_long_tests_head_each_workers_share_one_each():
    from tests.conftest import long_first

    items = [Item(f"t{n}") for n in range(10)] + [Item("a", long=True), Item("b", long=True)]
    names = [item.name for item in long_first(items, workers=3)]
    assert sorted(names) == sorted(item.name for item in items)
    assert names.index("a") == 0 and names.index("b") == 4  # the heads of the first two shares of four
    assert [item.name for item in long_first(items, workers=1)][:2] == ["a", "b"]
