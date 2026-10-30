"""The JavaScript files copied into the repository: vendor.json says which, and from where.

    uv run python tools/vendor.py check    every file matches its recorded hash
    uv run python tools/vendor.py update   move each to the newest version the rules allow, within its major version

Nothing runs npm: the package's tarball is read directly from the registry and checked against its published integrity.
"""

import base64
import hashlib
import io
import json
import sys
import tarfile
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor.json"
WINDOW = timedelta(days=14)


def read_json(url: str, data: bytes | None = None) -> Any:
    headers = {"Content-Type": "application/json"} if data else {}
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=30) as response:
        return json.load(response)


def vulnerabilities(name: str, version: str) -> list[str]:
    query = {"package": {"name": name, "ecosystem": "npm"}, "version": version}
    found = read_json("https://api.osv.dev/v1/query", json.dumps(query).encode()).get("vulns", [])
    return [item["id"] for item in found]


def version_key(version: str) -> list[int]:
    return [int(part) for part in version.split(".")]


def sha384(content: bytes) -> str:
    return base64.b64encode(hashlib.sha384(content).digest()).decode()


def newest_allowed(name: str, current: str) -> str | None:
    """The newest stable version of this major one that passes the rules; a security fix skips the wait."""
    package = read_json("https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@"))
    major = current.split(".")[0] + "."
    released: dict[str, datetime] = {
        version: datetime.fromisoformat(package["time"][version].replace("Z", "+00:00"))
        for version, data in package["versions"].items()
        if version.startswith(major) and "-" not in version and not data.get("deprecated")
    }
    limit = datetime.now(UTC) - WINDOW
    settled = sorted((v for v, date in released.items() if date <= limit), key=version_key, reverse=True)
    for version in settled[:10]:
        if not vulnerabilities(name, version):
            return version
    for version in sorted(released, key=version_key, reverse=True):  # every settled version is vulnerable
        if not vulnerabilities(name, version):
            return version
    return None


def fetch(name: str, version: str, member: str) -> bytes:
    metadata = read_json(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}/{version}")
    with urllib.request.urlopen(metadata["dist"]["tarball"], timeout=60) as response:
        tarball = response.read()
    algorithm, expected = metadata["dist"]["integrity"].split("-", 1)
    if base64.b64encode(hashlib.new(algorithm, tarball).digest()).decode() != expected:
        raise RuntimeError(f"{name} {version}: the tarball does not match its published integrity")
    with tarfile.open(fileobj=io.BytesIO(tarball)) as archive:
        extracted = archive.extractfile(f"package/{member}")
        if extracted is None:
            raise RuntimeError(f"{name} {version}: no {member} in the package")
        return extracted.read()


def check() -> list[str]:
    problems = []
    for name, entry in json.loads(VENDOR.read_text(encoding="utf-8")).items():
        path = ROOT / entry["target"]
        if not path.exists() or sha384(path.read_bytes()) != entry["sha384"]:
            problems.append(f"{name}: {entry['target']} does not match vendor.json")
    return problems


def update() -> list[str]:
    entries = json.loads(VENDOR.read_text(encoding="utf-8"))
    changes = []
    for name, entry in entries.items():
        version = newest_allowed(name, entry["version"])
        if version is None:
            print(f"{name}: no allowed version", file=sys.stderr)
            continue
        target = ROOT / entry["target"]
        if version == entry["version"] and target.exists():
            continue
        content = fetch(name, version, entry["file"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        changes.append(f"`{name}` {entry['version']} to {version}")
        entry.update(version=version, sha384=sha384(content))
    VENDOR.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8", newline="\n")
    return changes


def main() -> int:
    if sys.argv[1:] == ["check"]:
        problems = check()
        print("\n".join(problems) or "vendored files match")
        return 1 if problems else 0
    if sys.argv[1:] == ["update"]:
        print("\n".join(update()) or "no change")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
