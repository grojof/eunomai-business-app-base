"""The tests, fast: in parallel, then the few that cannot share the computer, one at a time.

    uv run --frozen python tools/test.py              the whole suite
    uv run --frozen python tools/test.py --affected   only what the files changed against main can break (RULES)
    uv run --frozen python tools/test.py --list       says what --affected would run, and runs nothing
    uv run --frozen python tools/test.py -- -k board  pytest's own options after --, for both passes
    uv run --frozen python tools/test.py --application   what an application can break, unless its base changed

The tests run with pytest-xdist, as many at a time as the computer has cores and free memory for (`--workers` sets
it), except those marked `serial`, which run after, one at a time: they need the computer to themselves. Idle workers
take tests from busy ones, and the long tests start first, so no worker is left with a queue at the end. Each database
test gets a schema of its own, so the workers never meet in PostgreSQL.
The browser and the PostgreSQL come from the environment as always (`APP_BROWSER_CHANNEL`, `TEST_DATABASE_URL`).
It ends with one line that counts both passes, as pytest's own would. Plain `pytest` still runs everything one at a
time. Standard library only.
"""

import argparse
import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


def changed_files() -> list[str] | None:
    """What differs from main: committed on this branch, staged, changed and new, as git names them. None when git
    cannot say: no git here, or no main branch, local or `origin/main`, to compare with."""

    def names(*arguments: str) -> list[str]:
        done = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=True)
        return [line for line in done.stdout.splitlines() if line]

    for main in ("main", "origin/main"):
        try:
            base = names("merge-base", main, "HEAD")[0]
            return sorted(set(names("diff", "--name-only", base) + names("ls-files", "--others", "--exclude-standard")))
        except OSError, subprocess.CalledProcessError, IndexError:
            continue
    return None


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


SUMMARY = re.compile(r"(?:=+ )?((?:no tests ran|\d).{0,300}?) in ([\d.]+)s(?: \([^)]{0,40}\))?(?: =+)?")
"""pytest's last line. It starts with a count: a line a test printed, such as another suite's total quoted in a
failure, starts with its own text and is not this run's."""
COUNT = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)\b")


BELOW_NORMAL = 0x4000  # Windows' BELOW_NORMAL_PRIORITY_CLASS


def _lower_priority() -> None:
    if sys.platform != "win32":  # Windows takes a flag instead
        os.nice(5)


def _run(command: list[str], low_priority: bool = False) -> tuple[int, dict[str, int], float]:
    """Runs a pass, printing as it goes, and reads its last summary line: its counts and its seconds. A pass at a low
    priority takes whatever the computer leaves free, and gives way to what the person is doing; its browsers and
    servers inherit it."""
    lower: dict[str, Any] = {}
    if low_priority:
        lower = {"creationflags": BELOW_NORMAL} if sys.platform == "win32" else {"preexec_fn": _lower_priority}
    print("$", " ".join(command), flush=True)
    counts: dict[str, int] = {}
    seconds = 0.0
    # Bytes through as they come, in whatever encoding pytest wrote them: only the summary, plain ASCII, is read.
    with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, **lower) as process:
        for raw in process.stdout or ():
            sys.stdout.buffer.write(raw)
            sys.stdout.buffer.flush()
            found = SUMMARY.fullmatch(raw.decode("utf-8", "replace").strip())
            if found and COUNT.search(found[1]):
                counts = {
                    word.rstrip("s") if word.startswith(("error", "warning")) else word: int(number)
                    for number, word in COUNT.findall(found[1])
                }
                seconds = float(found[2])
    code = process.returncode
    return (0 if code == NO_TESTS else code), counts, seconds


MEMORY_PER_WORKER = 1.5 * 2**30
"""Bytes a worker needs: it starts its own browser, server and database. With one per core (20 on a computer of 2026)
the computer ran out of memory; eleven at once, with 15 GB free, did not."""
MOST_WORKERS = 8


def free_memory() -> int | None:
    """Bytes of memory free now, or None where the system does not say."""
    if sys.platform == "win32":

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong)
                for name in ("total", "free", "total_page", "free_page", "total_virtual", "free_virtual", "extended")
            ]

        status = Status()
        status.length = ctypes.sizeof(Status)
        return status.free if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except ValueError, OSError, AttributeError:
        return None


def default_workers() -> int:
    """As many as the cores and the free memory allow, up to MOST_WORKERS."""
    memory = free_memory()
    by_memory = MOST_WORKERS if memory is None else int(memory // MEMORY_PER_WORKER)
    return max(1, min(os.cpu_count() or 1, by_memory, MOST_WORKERS))


def summary(counts: dict[str, int], seconds: float) -> str:
    order = ["failed", "passed", "skipped", "deselected", "xfailed", "xpassed", "error", "warning"]
    words = ", ".join(f"{counts[word]} {word}" for word in order if counts.get(word))
    return f"{words or 'no tests ran'} in {seconds:.2f}s (both passes)"


BASE_FILES = "tests/base_files.json"


def digest(path: Path) -> str:
    """A file's fingerprint, whatever line endings a checkout gave it, as tools/make_template.py writes it."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def locked(lock: Path) -> dict[str, str]:
    """Each package `uv.lock` pins, and its version."""
    if not lock.is_file():
        return {}
    packages = tomllib.loads(lock.read_text(encoding="utf-8")).get("package", [])
    return {str(package["name"]): str(package.get("version", "")) for package in packages}


def base_changes(root: Path = ROOT) -> list[str] | None:
    """What of the base is not as the template left it: its files, by fingerprint, and the versions of the packages its
    tests proved. None when there is no `tests/base_files.json` to tell (the base itself, or an older template)."""
    manifest = root / BASE_FILES
    if not manifest.is_file():
        return None
    expected = json.loads(manifest.read_text(encoding="utf-8"))
    changes = []
    for name, fingerprint in sorted(expected.get("files", {}).items()):
        path = root / name
        if not path.is_file():
            changes.append(f"{name}: missing")
        elif digest(path) != fingerprint:
            changes.append(f"{name}: changed")
    now = locked(root / "uv.lock")
    for name, version in sorted(expected.get("packages", {}).items()):
        if now.get(name) != version:
            changes.append(f"uv.lock: {name} {version} -> {now.get(name, 'removed')}")
    return changes


def only_the_applications(application: bool, root: Path = ROOT) -> bool:
    """`--application` leaves out the tests of the base's machinery, which its template ran, only while the base is as
    the template left it. Otherwise every test runs, and it says why: an application may change the base where its
    documentation says so (its own component, a kind of upload, words for icons), and a changed package may change how
    the base behaves. That costs time, never a failure."""
    if not application:
        return False
    changes = base_changes(root)
    if changes is None:
        print(f"No {BASE_FILES}: every test runs, the base's own included.")
        return False
    if changes:
        print("The base is not as its template left it, so every test runs, the base's own included:")
        for line in changes[:20]:
            print("  " + line)
        return False
    return True


def run(
    files: list[str], workers: int | None = None, options: list[str] | None = None, application: bool = False
) -> int:
    """Two passes over the same selection: in parallel without `serial`, at a low priority, then `serial` alone, at the
    normal one, since those tests measure time. Then one line for both. `application` leaves out the tests marked
    `base`, in both passes: pytest keeps only the last `-m`, so it cannot come from the options."""
    count = str(workers or default_workers())
    extra = options or []
    without = " and not base" if application else ""
    parallel = [*PYTEST, "-n", count, "--dist", "worksteal", "-m", f"not serial{without}", *extra, *files]
    first, counts, seconds = _run(parallel, low_priority=True)
    second, more, more_seconds = _run([*PYTEST, "-m", f"serial{without}", *extra, *files])
    for word, number in more.items():
        counts[word] = counts.get(word, 0) + number
    counts.pop("deselected", None)  # each pass leaves out what the other runs
    print(summary(counts, seconds + more_seconds), flush=True)
    return first or second


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The tests, fast.")
    parser.add_argument("--affected", action="store_true", help="only what the changes against main can break")
    parser.add_argument("--list", action="store_true", help="say what --affected would run, and run nothing")
    parser.add_argument("--workers", type=int, help="tests at once (default: what the cores and free memory allow)")
    parser.add_argument(
        "--application",
        action="store_true",
        help="only what an application can break: the tests marked base ran in its template",
    )
    parser.add_argument("pytest", nargs="*", help="pytest's own options, after --")
    options = parser.parse_args(arguments)
    alone = "TEST_DATABASE_URL is not set: the database tests run on SQLite alone, not on PostgreSQL."
    application = only_the_applications(options.application) if not options.list else options.application
    if not (options.affected or options.list):
        if not os.environ.get("TEST_DATABASE_URL"):
            print(alone)
        return run([], options.workers, options.pytest, application)
    paths = changed_files()
    if paths is None:
        print("git cannot say what changed against main (no git here, or no main branch): the whole suite runs.")
        return 0 if options.list else run([], options.workers, options.pytest, application)
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
    return run([] if chosen.everything else files, options.workers, options.pytest, application)


if __name__ == "__main__":
    sys.exit(main())
