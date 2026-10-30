"""The standards keep their promises: each rule has a source and a check, and the code follows the mechanical ones."""

import os
import re

import pytest

from tests.helpers import ROOT
from tools import vendor

STANDARDS = ROOT / "docs" / "standards.md"
ROW = re.compile(r"^\| (?P<id>[A-Z0-9]+-\d{2}) \| (?P<rule>.+?) \| (?P<source>.+?) \| (?P<check>.+?) \|$", re.M)


def rules() -> list[re.Match[str]]:
    return list(ROW.finditer(STANDARDS.read_text(encoding="utf-8")))


def rules_under_test() -> set[str]:
    found: set[str] = set()
    for test in (ROOT / "tests").rglob("test_*.py"):
        found |= set(re.findall(r'mark\.rule\("([A-Z0-9]+-\d{2})"\)', test.read_text(encoding="utf-8")))
    return found


def test_every_rule_has_a_source_or_says_it_is_a_project_decision():
    assert len(rules()) > 30
    for row in rules():
        assert "](http" in row["source"] or row["source"] == "Project decision", row["id"]


def test_rule_identifiers_are_unique():
    identifiers = [row["id"] for row in rules()]
    assert len(identifiers) == len(set(identifiers))


@pytest.mark.skipif(not (ROOT / "tests" / "demo").exists(), reason="some rules are proved on demo screens")
def test_every_automatic_rule_has_a_test_and_every_test_a_rule():
    declared = {row["id"] for row in rules() if row["check"] == "Automatic"}
    tested = rules_under_test()
    assert declared - tested == set(), "declared automatic, but no test proves it"
    assert tested - {row["id"] for row in rules()} == set(), "a test names a rule that does not exist"
    assert tested - declared == set(), "tested, but the rule does not say so"


def test_every_check_is_automatic_manual_or_planned():
    for row in rules():
        assert re.fullmatch(r"Automatic|By hand|Milestone \d", row["check"]), row["id"]


def test_templates_use_no_invented_colours_or_sizes():
    for template in (ROOT / "app").rglob("*.html"):
        found = re.findall(r"[\w:-]+-\[[^\]]*\]", template.read_text(encoding="utf-8"))
        assert found == [], template


def test_colours_live_only_in_the_brand():
    for source in (ROOT / "app" / "ui" / "styles").rglob("*.css"):
        assert re.findall(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl|oklch)a?\(", source.read_text(encoding="utf-8")) == []


def test_tailwinds_own_palette_does_not_exist():
    css = (ROOT / "app" / "ui" / "styles" / "app.css").read_text(encoding="utf-8")
    assert "--color-*: initial" in css
    built = (ROOT / "app" / "ui" / "static" / "app.css").read_text(encoding="utf-8")
    assert "--color-blue-500" not in built


def test_no_page_loads_anything_from_another_server():
    for template in (ROOT / "app").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(r"""(?:src|href)=["'](?:https?:)?//""", text), template


@pytest.mark.rule("SEC-10")
def test_vendored_files_match_their_recorded_hash():
    assert vendor.check() == []


def test_scripts_carry_their_integrity(client, person):
    html = client.get("/", headers=person).text
    assert re.search(r'htmx\.min\.js" integrity="sha384-[\w+/=]+"', html)


def test_the_core_never_imports_the_demo():
    for source in (ROOT / "app" / "core").rglob("*.py"):
        assert "app.demo" not in source.read_text(encoding="utf-8").replace("Nothing here imports from app.demo", "")


@pytest.mark.skipif(bool(os.environ.get("BASE_WITHOUT_DEMO")), reason="runs once, on the full repository")
def test_the_application_works_with_the_demo_deleted(tmp_path):
    import shutil
    import subprocess
    import sys

    copy = tmp_path / "application"
    ignored = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")
    shutil.copytree(ROOT, copy, ignore=ignored)
    subprocess.run([sys.executable, "tools/remove_demo.py"], cwd=copy, check=True)
    assert not (copy / "app" / "demo").exists()
    assert "install_demo" not in (copy / "app" / "main.py").read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-m", "not browser"],
        cwd=copy,
        env=os.environ | {"BASE_WITHOUT_DEMO": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout[-2000:]
