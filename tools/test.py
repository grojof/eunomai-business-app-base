"""The tests, fast: in parallel, then the few that cannot share the computer, one at a time.

    uv run --frozen python tools/test.py              the whole suite
    uv run --frozen python tools/test.py --affected   only what the files changed against main can break (RULES)
    uv run --frozen python tools/test.py --list       says what --affected would run, and runs nothing

The tests run with pytest-xdist, six at a time at most (`--workers`), except those marked `serial`, which run after,
one at a time: they need the computer to themselves. Each database test gets a schema of its own, so the workers
never meet in PostgreSQL.
The browser and the PostgreSQL come from the environment as always (`APP_BROWSER_CHANNEL`, `TEST_DATABASE_URL`).
Plain `pytest` still runs everything one at a time. Standard library only.
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
PYTEST = [sys.executable, "-m", "pytest", "-q"]
NO_TESTS = 5  # pytest's exit code when the selection holds no test: nothing failed
DATABASE = r"database_url|TEST_DATABASE_URL"

# What a change can break, read top to bottom; the first rule that matches a path decides for it. `everything` is the
# whole suite. Tests are found by what their source names, so a new test file follows the same rules.
RULES = (
    (r"tests/(\w+/)*test_\w+\.py", "that test file"),
    (
        r"tests/.*|pyproject\.toml|uv\.lock|tools/test\.py|app/main\.py|app/core/(application|settings|templating)\.py",
        "everything",
    ),
    (r"migrations/.*|app/core/(database|columns)\.py|app/(\w+/)*models\.py", "every database test, on both engines"),
    (r"(app/(\w+/)*locales|locales)/.*|tools/translations\.py", "every test that reads the translations"),
    (r"app/(\w+/)*(\w+)\.py", "test_<module>.py and every test that names the module"),
    (r"docs/.*|[^/]+\.md", "every test that reads the documentation"),
    (r"tools/(\w+)\.py", "every test that names the tool"),
    (r"\.github/workflows/.*", "the workflow tests"),
    (r"vendor\.json", "every test that names vendor.json"),
)


@dataclass
class Selection:
    files: set[Path] = field(default_factory=set)
    everything: bool = False
    database: bool = False
    why: list[str] = field(default_factory=list)


def _tests_naming(pattern: str) -> set[Path]:
    found = re.compile(pattern)
    return {path for path in TESTS.rglob("test_*.py") if found.search(path.read_text(encoding="utf-8"))}


def changed_files() -> list[str]:
    """What differs from main: committed on this branch, staged, changed and new, as git names them."""

    def names(*arguments: str) -> list[str]:
        done = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=True)
        return [line for line in done.stdout.splitlines() if line]

    base = names("merge-base", "main", "HEAD")[0]
    return sorted(set(names("diff", "--name-only", base) + names("ls-files", "--others", "--exclude-standard")))


def select(paths: list[str]) -> Selection:
    chosen = Selection()
    for path in paths:
        for pattern, rule in RULES:
            match = re.fullmatch(pattern, path)
            if not match:
                continue
            if rule == "that test file":
                tests = {ROOT / path} if (ROOT / path).exists() else set()
            elif rule == "everything":
                chosen.everything, tests = True, set()
            elif rule.startswith("every database test"):
                chosen.database, tests = True, _tests_naming(DATABASE)
            elif rule == "every test that reads the translations":
                tests = _tests_naming(r"locales|translations")
            elif rule.startswith("test_<module>"):
                module = match[2]
                tests = _tests_naming(rf"\b{module}\b") | set(TESTS.rglob(f"test_{module}.py"))
            elif rule == "every test that reads the documentation":
                tests = _tests_naming(r'"docs"|"README\.md"|"AGENTS\.md"|docs/base')
            elif rule == "every test that names the tool":
                tests = _tests_naming(rf"\b{match[1]}\b")
            elif rule == "the workflow tests":
                tests = _tests_naming(r"\.github")
            else:
                tests = _tests_naming(r"vendor")
            chosen.files |= tests
            chosen.why.append(f"{path}: {rule}" + (f" ({len(tests)} files)" if tests else ""))
            break
        else:
            chosen.everything = True
            chosen.why.append(f"{path}: no rule knows it, so everything")
    return chosen


def _run(command: list[str]) -> int:
    print("$", " ".join(command), flush=True)
    code = subprocess.run(command, cwd=ROOT).returncode
    return 0 if code == NO_TESTS else code


WORKERS = 6
"""Tests at once, at most: each worker starts its own browser, server and database, and with one per core (20 on a
computer of 2026) the computer ran out of memory. `--workers` changes it."""


def run(files: list[str], workers: int = WORKERS) -> int:
    """Two passes over the same selection: in parallel without `serial`, then `serial` alone."""
    count = str(min(workers, os.cpu_count() or 1))
    first = _run([*PYTEST, "-n", count, "-m", "not serial", *files])
    second = _run([*PYTEST, "-m", "serial", *files])
    return first or second


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The tests, fast.")
    parser.add_argument("--affected", action="store_true", help="only what the changes against main can break")
    parser.add_argument("--list", action="store_true", help="say what --affected would run, and run nothing")
    parser.add_argument("--workers", type=int, default=WORKERS, help=f"tests at once, at most (default {WORKERS})")
    options = parser.parse_args(arguments)
    alone = "TEST_DATABASE_URL is not set: the database tests run on SQLite alone, not on PostgreSQL."
    if not (options.affected or options.list):
        if not os.environ.get("TEST_DATABASE_URL"):
            print(alone)
        return run([], options.workers)
    paths = changed_files()
    chosen = select(paths)
    if (chosen.database or chosen.everything) and not os.environ.get("TEST_DATABASE_URL"):
        print(alone)
    print("Changed against main:" if paths else "Nothing changed against main: no test to run.")
    for line in chosen.why:
        print("  " + line)
    files = sorted(path.relative_to(ROOT).as_posix() for path in chosen.files)
    print("Runs: the whole suite." if chosen.everything else f"Runs: {', '.join(files) or 'no test'}.")
    if options.list or not (chosen.everything or files):
        return 0
    return run([] if chosen.everything else files, options.workers)


if __name__ == "__main__":
    sys.exit(main())
