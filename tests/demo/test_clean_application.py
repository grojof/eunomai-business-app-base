"""Deleting the demo leaves a sound application. These tests go with the demo: an application has nothing to delete.

Each runs in a copy, in the way a person would, with nothing set that a person would not set: a run that left a test out
would hide the very thing it is here to find.
"""

import re
import subprocess
from pathlib import Path

import pytest

from tests.helpers import ROOT, preview_section, repository_copy, run_in
from tests.test_components import add_a_component, check_the_added_component
from tests.test_standards import ROW, traced
from tools import remove_demo


def succeeded(result: subprocess.CompletedProcess[str], what: object) -> None:
    assert result.returncode == 0, f"{what}: {result.stdout[-2000:]} {result.stderr[-1000:]}"


def own_tests_pass(folder: Path, *arguments: str) -> None:
    """The application's own tests, and no test may stay out because the demo has gone."""
    result = run_in(folder, "-m", "pytest", "-q", "-x", "-rs", *arguments)
    succeeded(result, arguments)
    assert " passed" in result.stdout.splitlines()[-1]
    assert [line for line in result.stdout.splitlines() if line.startswith("SKIPPED") and "demo" in line.lower()] == []


@pytest.fixture(scope="module")
def application(tmp_path_factory: pytest.TempPathFactory) -> Path:
    copy = repository_copy(tmp_path_factory.mktemp("clean") / "application")
    succeeded(run_in(copy, "tools/remove_demo.py"), "tools/remove_demo.py")
    succeeded(run_in(copy, "tools/css.py"), "tools/css.py")
    return copy


def test_the_rules_proved_only_on_demo_screens_are_exactly_the_listed_ones():
    only_on_demo = {rule for rule, tests in traced().items() if all(t.startswith("tests/demo/") for t in tests)}
    assert only_on_demo == remove_demo.ONLY_ON_DEMO


def test_nothing_of_the_demo_stays(application):
    assert not (application / "app" / "demo").exists()
    assert not (application / "tests" / "demo").exists()
    assert "install_demo" not in (application / "app" / "main.py").read_text(encoding="utf-8")
    assert "app.demo" not in (application / "migrations" / "env.py").read_text(encoding="utf-8")
    assert list((application / "migrations" / "versions").glob("*.py")) == []
    assert (application / "migrations" / "script.py.mako").exists()
    assert "demo-admins" not in (application / ".env.example").read_text(encoding="utf-8")
    assert not (application / "tools" / "tailwind" / "daisyui-docs.json").exists()
    assert "daisyui-docs" not in (application / "vendor.json").read_text(encoding="utf-8")
    assert not (application / "app" / "ui" / "static" / "placeholders").exists()
    assert "/* demo */" not in (application / "app" / "ui" / "styles" / "app.css").read_text(encoding="utf-8")


def test_the_preview_needs_only_the_migrations(application):
    assert preview_section(application)["setup"] == [["alembic", "upgrade", "head"]]
    assert "demo" not in (application / ".eunomai" / "project.toml").read_text(encoding="utf-8")


def test_the_files_it_changes_keep_their_line_endings(application):
    for changed in ("app/main.py", "migrations/env.py", ".env.example", "docs/standards.md", ".eunomai/project.toml"):
        assert b"\r\n" not in (application / changed).read_bytes(), changed


def test_a_rule_only_the_demo_proved_says_it_is_checked_by_hand(application):
    text = (application / "docs" / "standards.md").read_text(encoding="utf-8")
    rows = {row["id"]: row["check"] for row in ROW.finditer(text)}
    assert {rows[rule] for rule in remove_demo.ONLY_ON_DEMO} == {"By hand"}


def test_every_icon_left_is_used(application):
    sources = [*(application / "app").rglob("*.html"), *(application / "app").rglob("*.py")]
    shell = "".join(path.read_text(encoding="utf-8") for path in sources)
    icons = application / "app" / "ui" / "templates" / "ui" / "icons"
    assert [icon.stem for icon in icons.glob("*.svg") if f'"{icon.stem}"' not in shell] == []


def test_agents_md_describes_an_application(application):
    text = (application / "AGENTS.md").read_text(encoding="utf-8")
    assert re.findall(r"^## .+", text, re.M)[0] == "## What this application is"
    assert not re.search(r"\bdemo\b|gallery|business-app-base|neutral|tests/demo", text, re.I)
    assert b"\r\n" not in (application / "AGENTS.md").read_bytes()
    for link in re.findall(r"\]\((?!http)([^)#]+)", text):
        assert (application / link).exists(), link


def test_it_changes_all_of_agents_md_and_a_base_that_edited_it_hears_what_it_missed(tmp_path, capsys):
    source = ROOT / "AGENTS.md"
    assert all(old in source.read_text(encoding="utf-8") for old, _new in remove_demo.AGENTS_CHANGES)
    edited = tmp_path / "AGENTS.md"
    edited.write_text("# Our base\n\n- A new component needs its page in the demo and its tests,\n", encoding="utf-8")
    remove_demo.changed(edited, remove_demo.AGENTS_CHANGES[5:6])
    assert edited.read_text(encoding="utf-8") == "# Our base\n\n- A new component needs its tests,\n"
    remove_demo.changed(edited, remove_demo.AGENTS_CHANGES[:1])
    assert "AGENTS.md: not found, so change it by hand: # AGENTS.md — business-app-base" in capsys.readouterr().out


def test_a_second_run_changes_nothing(application):
    agents = application / "AGENTS.md"
    before = agents.read_bytes()
    again = run_in(application, "tools/remove_demo.py")
    assert again.returncode != 0
    assert "an application already" in again.stderr
    assert agents.read_bytes() == before


def test_the_stylesheet_shrinks(application):
    built = application / "app" / "ui" / "static" / "app.css"
    assert built.stat().st_size < (ROOT / "app" / "ui" / "static" / "app.css").stat().st_size * 0.75
    assert "example-preview" not in built.read_text(encoding="utf-8")


@pytest.mark.parametrize("check", ["css", "components", "gallery", "translations", "vendor"])
def test_every_tool_check_passes(application, check):
    succeeded(run_in(application, f"tools/{check}.py", "check"), check)


def test_the_applications_own_tests_pass(application):
    own_tests_pass(application, "-m", "not browser")


@pytest.mark.browser
def test_the_applications_own_browser_tests_pass(application):
    own_tests_pass(application, "-m", "browser")


def test_the_promised_way_to_add_a_component_passes_the_checks_with_the_demo(tmp_path):
    copy = repository_copy(tmp_path / "application")
    add_a_component(copy)
    specimen = copy / "app" / "demo" / "templates" / "demo" / "gallery" / "specimens" / "signature.html"
    specimen.write_text('<p>{{ _("Save") }}</p>\n', encoding="utf-8", newline="\n")
    check_the_added_component(copy, "tests/test_components.py", "tests/demo/test_gallery.py")
