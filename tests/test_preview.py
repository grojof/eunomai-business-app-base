"""`[preview]` in `.eunomai/project.toml`: what a connector reads to start the application on a person's computer."""

import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.helpers import ROOT, fetch, preview_running, preview_section, repository_copy

SECTION = preview_section(ROOT)
THIS_COMPUTER = "127.0.0.1"
NOT_A_PROGRAM = {"sh", "bash", "cmd", "powershell", "pwsh", "env", "uv", "uvx", "pip", "pip3"}
THE_CONNECTORS_OWN = re.compile(r"(UV_|PYTHON|LD_|DYLD_|VIRTUAL_ENV$|PATH|SYSTEM|WINDIR$|COMSPEC$|HOME$|USERPROFILE$)")
THE_CONNECTORS_TOO = re.compile(r"(APPDATA|LOCALAPPDATA|TEMP|TMP|TMPDIR)$")


@pytest.fixture(scope="module")
def started(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Path, int]]:
    """A copy with no `.env`, as an export is, started by those exact steps. A copy's `.env` is never copied."""
    copy = repository_copy(tmp_path_factory.mktemp("preview") / "application")
    with preview_running(copy) as port:
        yield copy, port


def test_every_command_is_a_plain_program_with_no_shell():
    for command in [*SECTION["setup"], SECTION["run"]]:
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", command[0])
        assert command[0] not in NOT_A_PROGRAM
        assert not any(re.search(r"[;&|`<>\n\r]|\$\(", word) for word in command)


def test_only_run_knows_the_port_and_it_stays_on_this_computer():
    assert "{port}" in SECTION["run"]
    assert SECTION["run"][SECTION["run"].index("--host") + 1] == THIS_COMPUTER
    assert not any("{" in word for step in SECTION["setup"] for word in step)


def test_run_keeps_the_proxy_headers_off():
    assert "--no-proxy-headers" in SECTION["run"]


def test_the_environment_is_text_and_leaves_the_connectors_own_alone():
    for name, value in SECTION["environment"].items():
        assert isinstance(value, str), name
        assert not THE_CONNECTORS_OWN.match(name) and not THE_CONNECTORS_TOO.match(name), name


def test_nobody_signs_in(started):
    _copy, port = started
    status, html = fetch(port, "/")
    assert status == 200
    assert "Demo User" in html


def test_the_shell_works(started):
    _copy, port = started
    assert fetch(port, "/health")[0] == 200
    assert fetch(port, "/settings")[0] == 200
    assert fetch(port, "/static/ui/app.css")[0] == 200


def test_its_data_goes_to_the_folder_kept_between_versions(started):
    copy, _port = started
    assert (copy.parent / "kept" / "preview.db").is_file()
    assert not (copy / ".data").exists()


def test_files_people_attach_go_there_too():
    assert SECTION["environment"]["APP_UPLOAD_FOLDER"].startswith("{data}/")


def test_the_tests_name_a_browser_the_computer_has():
    tests = tomllib.loads((ROOT / ".eunomai" / "project.toml").read_text(encoding="utf-8"))["tests"]
    assert tests["run"][:2] == ["python", "tools/test.py"]  # in parallel: one at a time did not fit
    assert tests["environment"] == {"APP_BROWSER_CHANNEL": "msedge"}
