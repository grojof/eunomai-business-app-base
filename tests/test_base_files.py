"""An application runs only the tests it can break (`tools/test.py --application`, as a connector does on a person's
computer): the base's own were run in the template it was made from. That holds while the base's files are as the
template left them, which this checks against the fingerprints the template wrote in tests/base_files.json."""

import hashlib
import json
from pathlib import Path

import pytest

from tests.helpers import ROOT

MANIFEST = "tests/base_files.json"


def digest(path: Path) -> str:
    """The same fingerprint as tools/make_template.py writes, whatever line endings a checkout gave the file."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def changed_base_files(root: Path) -> list[str]:
    expected = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    problems = []
    for name, fingerprint in sorted(expected.items()):
        path = root / name
        if not path.is_file():
            problems.append(f"{name}: missing")
        elif digest(path) != fingerprint:
            problems.append(f"{name}: changed")
    return problems


def test_the_bases_files_are_as_the_template_left_them():
    if not (ROOT / MANIFEST).is_file():
        pytest.skip("the base itself, or a template made before 0.3.0: every test runs")
    assert changed_base_files(ROOT) == [], (
        "these files are the base's: put them back as the template has them, or run every test (tools/test.py) and "
        "ask IT, since the tests that prove them are left out of tools/test.py --application"
    )


def test_a_changed_or_missing_file_is_named_and_line_endings_do_not_count(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "kept.py").write_bytes(b"one\ntwo\n")
    (tmp_path / "edited.py").write_bytes(b"one\n")
    manifest = {"kept.py": digest(tmp_path / "kept.py"), "edited.py": digest(tmp_path / "edited.py"), "gone.py": "0"}
    (tmp_path / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "kept.py").write_bytes(b"one\r\ntwo\r\n")
    (tmp_path / "edited.py").write_bytes(b"one, edited\n")
    assert changed_base_files(tmp_path) == ["edited.py: changed", "gone.py: missing"]


def test_the_template_writes_the_same_fingerprints():
    maker = ROOT / "tools" / "make_template.py"
    if not maker.is_file():
        pytest.skip("only the base makes templates")
    from tools import make_template

    assert make_template.digest(maker) == digest(maker)
    files = make_template.base_files(ROOT)
    assert "app/core/database.py" in files and "tests/conftest.py" in files
    assert "app/ui/static/app.css" not in files and not any(name.endswith(".po") for name in files)
