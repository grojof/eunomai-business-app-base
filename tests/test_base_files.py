"""An application runs only the tests it can break (`tools/test.py --application`, as a connector does on a person's
computer) while the base is as its template left it: its files, by the fingerprints in tests/base_files.json, and the
versions of the packages the base's tests proved. Anything else runs every test, and says why: never a failure."""

import json
from pathlib import Path

import pytest

from tests.helpers import ROOT
from tools import test as runner


def a_base(root: Path) -> None:
    (root / "tests").mkdir()
    (root / "kept.py").write_bytes(b"one\ntwo\n")
    (root / "edited.py").write_bytes(b"one\n")
    (root / "uv.lock").write_text('[[package]]\nname = "jinja2"\nversion = "3.1.6"\n', encoding="utf-8")
    files = {name: runner.digest(root / name) for name in ("kept.py", "edited.py")}
    (root / runner.BASE_FILES).write_text(
        json.dumps({"files": files, "packages": {"jinja2": "3.1.6"}}), encoding="utf-8"
    )


def test_a_base_as_its_template_left_it_leaves_its_own_tests_out(tmp_path, capsys):
    a_base(tmp_path)
    (tmp_path / "kept.py").write_bytes(b"one\r\ntwo\r\n")  # a checkout's line endings do not count
    assert runner.base_changes(tmp_path) == []
    assert runner.only_the_applications(True, tmp_path) is True
    assert runner.only_the_applications(False, tmp_path) is False


def test_a_changed_file_or_package_runs_every_test_and_says_why(tmp_path, capsys):
    """An application may add its own component or a kind of upload, as its documentation says: that costs time."""
    a_base(tmp_path)
    (tmp_path / "edited.py").write_bytes(b"one, edited\n")
    (tmp_path / "uv.lock").write_text('[[package]]\nname = "jinja2"\nversion = "3.2.0"\n', encoding="utf-8")
    assert runner.base_changes(tmp_path) == ["edited.py: changed", "uv.lock: jinja2 3.1.6 -> 3.2.0"]
    assert runner.only_the_applications(True, tmp_path) is False
    assert "every test runs" in capsys.readouterr().out
    (tmp_path / "edited.py").unlink()
    assert "edited.py: missing" in runner.base_changes(tmp_path)


def test_without_a_manifest_every_test_runs(tmp_path, capsys):
    assert runner.base_changes(tmp_path) is None
    assert runner.only_the_applications(True, tmp_path) is False
    assert "No tests/base_files.json" in capsys.readouterr().out


def test_the_template_writes_what_the_runner_reads():
    maker = ROOT / "tools" / "make_template.py"
    if not maker.is_file():
        pytest.skip("only the base makes templates")
    from tools import make_template

    assert make_template.digest(maker) == runner.digest(maker)
    assert make_template.locked(ROOT / "uv.lock") == runner.locked(ROOT / "uv.lock") != {}
    written = make_template.manifest(ROOT)
    assert "app/core/database.py" in written["files"] and ".gitignore" in written["files"]
    assert "app/ui/static/app.css" not in written["files"] and "migrations/env.py" not in written["files"]
    assert not any(name.endswith(".po") for name in written["files"])
    assert written["packages"]["fastapi"]
