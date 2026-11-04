"""The base's own CI: what its workflows run, on which systems, and how the dependency update reaches a pull request.

They maintain this base on GitHub. An organization's template leaves them out, with this file, and brings its own CI:
see docs/base/specification.md#an-organizations-template
"""

import json
import re

from tests.helpers import ROOT

WORKFLOW = (ROOT / ".github" / "workflows" / "dependencies.yml").read_text(encoding="utf-8")
TESTS_WORKFLOW = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")


def test_the_gallerys_data_reaches_the_pull_request():
    assert "tools/gallery.py\n" in job("update")
    assert "app/demo/examples/" in job("propose")


def test_the_icons_and_their_index_reach_the_pull_request():
    propose = job("propose")
    assert re.search(r"tools/lucide/\[\^/\]\+", propose)
    assert "app/ui/templates/ui/icons/[^/]+" in propose


def job(name):
    return WORKFLOW[WORKFLOW.index(f"\n  {name}:\n") :]


def test_the_database_tests_run_on_a_postgresql_pinned_by_digest():
    tests = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert re.search(r"postgres: postgres:[\d.]+@sha256:[0-9a-f]{64}\n", tests)
    assert "image: ${{ matrix.postgres }}" in tests
    assert "TEST_DATABASE_URL: ${{ matrix.test_database_url }}" in tests
    ubuntu = re.search(r"- os: (\S+)\n\s+postgres: \S+\n\s+test_database_url: postgresql\S+", tests)
    assert ubuntu, "the Ubuntu run must get its database from `include`"
    assert ubuntu[1] in systems(), "`include` adds to a run only if its name is the same"


def test_the_one_linux_job_without_a_database_says_so():
    """Tests with no `TEST_DATABASE_URL` fail a Linux job, so that one cannot pass on SQLite by mistake."""
    update = job("update")[: WORKFLOW.index("\n  propose:\n")]
    assert "TESTS_ON_SQLITE_ALONE:" in update


def test_the_update_job_uses_no_cache():
    update = job("update")[: WORKFLOW.index("\n  propose:\n")]
    assert "enable-cache: false" in update


def test_new_files_reach_the_pull_request_after_the_allowlist():
    propose = job("propose")
    assert "commit -q --no-verify -am" not in propose
    assert propose.index('if [ -n "$unexpected" ]') < propose.index("git add -A") < propose.index("git commit")


def test_a_failed_update_still_reports():
    update = job("update")
    assert re.search(r"upload-artifact@\S+  # \S+\n\s+if: always\(\)", update)
    assert "if: failure()" in update
    assert "problems.md" in update[update.index("if: failure()") :]
    assert "needs.update.result == 'failure'" in job("report")


def test_only_a_tested_update_is_proposed():
    propose = job("propose")
    assert propose[: propose.index("runs-on")].count("always()") == 0
    tested = job("update")
    assert tested.index("pytest") < tested.index("update.tar")


def systems() -> list[str]:
    found = re.search(r"^\s+os: (\[.*?\])$", TESTS_WORKFLOW, re.M)
    assert found, "the matrix lists its systems"
    return list(json.loads(found[1]))


def test_the_tests_run_by_hand_on_ubuntu_and_a_newer_run_cancels_an_older_one():
    """The whole suite runs on a computer before each push; GitHub's minutes confirm now and then."""
    triggers = TESTS_WORKFLOW[TESTS_WORKFLOW.index("\non:\n") : TESTS_WORKFLOW.index("\nconcurrency:")]
    assert "workflow_dispatch:" in triggers and "pull_request" not in triggers
    assert "cancel-in-progress: true" in TESTS_WORKFLOW
    assert systems() == ["ubuntu-latest"]


def test_dependencies_are_brought_up_to_date_once_a_week():
    assert re.search(r'cron: "\d+ \d+ \* \* 1"', WORKFLOW)


def test_the_tests_workflow_keeps_its_rules():
    assert TESTS_WORKFLOW.count("runs-on:") == 1
    assert "runs-on: ${{ matrix.os }}" in TESTS_WORKFLOW
    assert "timeout-minutes: 35" in TESTS_WORKFLOW
    assert 'pytest -q -n auto -m "not serial" --durations=25' in TESTS_WORKFLOW
    assert "pytest -q -m serial" in TESTS_WORKFLOW, "what needs the computer alone runs after, alone"
    assert re.search(r"postgres: postgres:[\d.]+@sha256:[0-9a-f]{64}", TESTS_WORKFLOW)
    assert "image: ${{ matrix.postgres }}" in TESTS_WORKFLOW
    commands = re.findall(r"^\s+- run: (.+)$", TESTS_WORKFLOW, re.M)
    assert commands[0] == "uv lock --check"
    assert all("--frozen" in command for command in commands[1:])
