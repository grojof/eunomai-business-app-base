"""Daily dependency maintenance: the newest versions the rules allow (docs/specification.md#dependencies), nothing else.

    uv run python tools/update_dependencies.py --summary summary.md --problems problems.md

Writes what changed, every package included, and the problems no allowed version solves. A problem with one
dependency never stops the others, so a security update is not lost: it goes to the problems, which keep an issue
open, and the rest goes ahead.
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import components
import vendor

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "uv.lock"
OVERRIDES = re.compile(r"^exclude-newer-package = \{.*\}$", re.M)
WINDOW = timedelta(days=14)
INACTIVE = timedelta(days=3 * 365)
EXCEPTIONS = {"colorama": "only pytest needs it, only on Windows, never on a server; stable, not archived"}
"""Packages accepted despite the activity or source rules. A known vulnerability is never excepted."""


def uv(*args: str) -> None:
    subprocess.run(["uv", *args], cwd=ROOT, check=True, capture_output=True)


def pins() -> dict[str, str]:
    packages = tomllib.loads(LOCK.read_text(encoding="utf-8"))["package"]
    return {p["name"]: p["version"] for p in packages if p["name"] != "business-app-base" and "version" in p}


def installed() -> dict[str, str]:
    """The packages that really install, leaving out those for web browsers (emscripten)."""
    exported = subprocess.run(
        ["uv", "export", "--frozen", "--no-emit-project", "--no-hashes", "--format", "requirements.txt"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    found = re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;]+)(.*)$", exported, re.M)
    return {name: version for name, version, marker in found if "emscripten" not in marker}


def overrides() -> dict[str, str]:
    return dict(tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["uv"].get("exclude-newer-package", {}))


def write_overrides(values: dict[str, str]) -> None:
    body = ", ".join(f'{name} = "{date}"' for name, date in sorted(values.items()))
    line = f"exclude-newer-package = {{ {body} }}" if body else "exclude-newer-package = {}"
    text = OVERRIDES.sub(line, PYPROJECT.read_text(encoding="utf-8"))
    PYPROJECT.write_text(text, encoding="utf-8", newline="\n")


def pypi(name: str) -> dict[str, Any]:
    result: dict[str, Any] = vendor.read_json(f"https://pypi.org/pypi/{name}/json")
    return result


def vulnerabilities(name: str, version: str) -> list[str]:
    query = {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
    found = vendor.read_json("https://api.osv.dev/v1/query", json.dumps(query).encode()).get("vulns", [])
    return [item["id"] for item in found]


def released(data: dict[str, Any]) -> dict[str, datetime]:
    """Stable, not yanked versions with the moment each one was published."""
    return {
        version: min(datetime.fromisoformat(f["upload_time_iso_8601"].replace("Z", "+00:00")) for f in files)
        for version, files in data["releases"].items()
        if files and not re.search(r"[a-z]", version) and not all(f.get("yanked") for f in files)
    }


def key(version: str) -> list[int]:
    return [int(part) for part in re.findall(r"\d+", version)]


def fixed_version(name: str, data: dict[str, Any], current: str) -> str | None:
    newer = [v for v in released(data) if key(v) > key(current)]
    return next((v for v in sorted(newer, key=key, reverse=True) if not vulnerabilities(name, v)), None)


def has_source(data: dict[str, Any]) -> bool:
    links = [*(data["info"].get("project_urls") or {}).values(), data["info"].get("home_page") or ""]
    return any(re.match(r"https://", link or "") for link in links)


def review(notes: list[str], current: dict[str, str]) -> list[tuple[str, str, str]]:
    problems: list[tuple[str, str, str]] = []
    for _ in range(5):  # a fix can bring other packages: check again until stable
        problems, moved = [], False
        now = datetime.now(UTC)
        for name, version in installed().items():
            data = pypi(name)
            found = vulnerabilities(name, version)
            if found:
                fix = fixed_version(name, data, version)
                if fix is None:
                    problems.append((name, version, "known vulnerability, no fixed version: " + ", ".join(found)))
                    continue
                moment = released(data)[fix] + timedelta(minutes=1)
                current[name] = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
                write_overrides(current)
                uv("lock", "--upgrade-package", name)
                if installed().get(name) == version:
                    problems.append((name, version, f"{fix} fixes {', '.join(found)}, but the limits refuse it"))
                    continue
                notes.append(f"`{name}` {version} to {fix}: fixes {', '.join(found)}")
                moved = True
                continue
            versions = released(data)
            if name in EXCEPTIONS:
                continue
            if version not in versions:
                problems.append((name, version, "yanked or a pre-release"))
            elif now - max(versions.values()) > INACTIVE:
                problems.append((name, version, "no release in three years"))
            elif not has_source(data):
                problems.append((name, version, "no public source repository"))
        if not moved:
            break
    return problems


def update_vendored(problems: list[tuple[str, str, str]]) -> list[str]:
    """The copied files. If daisyUI's new file breaks docs/components/, such as a component that is not in the
    catalogue, daisyUI stays where it was until a person decides, and everything else goes ahead."""
    daisyui = {name: e for name, e in vendor.read_entries().items() if e.get("package", name) == "daisyui"}
    files = {ROOT / e["target"]: (ROOT / e["target"]).read_bytes() for e in daisyui.values()}
    notes, refused = vendor.update()
    problems += refused
    try:
        components.generate()
    except ValueError as error:
        for path, content in files.items():
            path.write_bytes(content)
        vendor.write_entries(vendor.read_entries() | daisyui)
        problems.append(("daisyui", daisyui["daisyui"]["version"], f"not updated: {error}"))
        notes = [note for note in notes if not note.startswith("`daisyui")]
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--problems", type=Path, required=True)
    args = parser.parse_args()
    notes: list[str] = []
    before = pins()

    problems: list[tuple[str, str, str]] = []
    finished = True
    try:
        current = overrides()
        limit = datetime.now(UTC) - WINDOW
        dropped = [n for n, date in current.items() if datetime.fromisoformat(date.replace("Z", "+00:00")) < limit]
        for name in dropped:
            del current[name]
        write_overrides(current)
        uv("lock", "--upgrade")

        problems += review(notes, current)
        notes += update_vendored(problems)
        notes += [
            f"`{name}`: the vulnerability exception is no longer needed" for name in dropped if name not in current
        ]
    except Exception as error:  # what is known still reaches the issue: a silent stop is the worst outcome
        problems.append(("the update", "-", f"stopped: {type(error).__name__}: {error}"))
        finished = False

    after = pins()
    changed = [
        (n, before.get(n, "-"), after.get(n, "-"))
        for n in sorted(set(before) | set(after))
        if before.get(n) != after.get(n)
    ]
    lines = ["## Dependency update", ""]
    if changed:
        lines += ["| Package | Before | After |", "|---|---|---|"]
        lines += [f"| `{name}` | {old} | {new} |" for name, old, new in changed]
    lines += [""] + [f"- {note}" for note in notes]
    args.summary.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    args.problems.write_text("".join(f"- `{n}` {v}: {r}\n" for n, v, r in problems), encoding="utf-8")
    return 0 if finished else 1


if __name__ == "__main__":
    sys.exit(main())
