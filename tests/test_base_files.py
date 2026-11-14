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
    icons = ROOT / "app" / "ui" / "templates" / "ui" / "icons"
    assert make_template.folder_digest(icons) == runner.folder_digest(icons)
    assert make_template.locked(ROOT / "uv.lock") == runner.locked(ROOT / "uv.lock") != {}
    written = make_template.manifest(ROOT)
    assert "app/core/database.py" in written["files"] and ".gitignore" in written["files"]
    assert "app/ui/templates/ui/icons/" in written["files"]  # Lucide's icons, one fingerprint for the folder
    assert not any(name.startswith("app/ui/templates/ui/icons/") and name.endswith(".svg") for name in written["files"])
    assert "app/ui/static/app.css" not in written["files"] and "migrations/env.py" not in written["files"]
    assert not any(name.endswith(".po") for name in written["files"])
    assert written["packages"]["fastapi"]


def test_a_changed_file_keeps_the_base_tests_it_can_break_and_says_why(tmp_path, capsys, monkeypatch):
    """An application's own component or kind of upload changes a file of the base: only the base's tests that file
    can break run besides the application's, chosen as --affected chooses them, not every test for good."""
    monkeypatch.delenv(runner.KEPT, raising=False)
    (tmp_path / "app" / "core").mkdir(parents=True)
    (tmp_path / "app" / "core" / "calendars.py").write_bytes(b"one\n")
    (tmp_path / runner.BASE_FILES).parent.mkdir(exist_ok=True)
    (tmp_path / runner.BASE_FILES).write_text(
        json.dumps({"files": {"app/core/calendars.py": "0" * 64}, "packages": {}}), encoding="utf-8"
    )
    assert runner.only_the_applications(True, tmp_path) is True
    kept = runner.os.environ[runner.KEPT].split(",")
    assert "tests/test_calendars.py" in kept and all(name.startswith("tests/") for name in kept)
    said = capsys.readouterr().out
    assert "the base's own that this can break" in said and "app/core/calendars.py" in said


def test_a_file_every_test_rests_on_still_runs_every_test(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(runner.KEPT, raising=False)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_bytes(b"x\n")
    (tmp_path / runner.BASE_FILES).write_text(
        json.dumps({"files": {"tests/conftest.py": "0" * 64}, "packages": {}}), encoding="utf-8"
    )
    assert runner.only_the_applications(True, tmp_path) is False
    assert "every test runs" in capsys.readouterr().out and runner.KEPT not in runner.os.environ


def test_one_fingerprint_for_the_icon_folder_still_sees_one_icon_changed_or_gone(tmp_path, capsys, monkeypatch):
    """Lucide's icons are most of the base's files: the folder has one fingerprint, and any icon still counts."""
    monkeypatch.delenv(runner.KEPT, raising=False)
    icons = tmp_path / "app" / "ui" / "templates" / "ui" / "icons"
    icons.mkdir(parents=True)
    for name in ("a.svg", "b.svg"):
        (icons / name).write_bytes(b"<svg/>\n")
    (tmp_path / runner.BASE_FILES).parent.mkdir(exist_ok=True)
    (tmp_path / runner.BASE_FILES).write_text(
        json.dumps({"files": {"app/ui/templates/ui/icons/": runner.folder_digest(icons)}, "packages": {}}),
        encoding="utf-8",
    )
    assert runner.base_changes(tmp_path) == []
    (icons / "b.svg").write_bytes(b"<svg>changed</svg>\n")
    assert runner.base_changes(tmp_path) == ["app/ui/templates/ui/icons/: changed"]
    assert runner.only_the_applications(True, tmp_path) is True
    assert "tests/test_icons.py" in runner.os.environ[runner.KEPT].split(",")
    (icons / "b.svg").unlink()
    assert runner.base_changes(tmp_path) == ["app/ui/templates/ui/icons/: changed"]
