"""The files copied into the repository: vendor.json says which, and from where.

    uv run python tools/vendor.py check    every file matches its recorded hash
    uv run python tools/vendor.py update   move each to the newest version the rules allow, within its major version

Nothing runs npm. How each file is pinned:

- A package from the registry: its tarball is checked against the integrity the registry publishes.
- daisyui.mjs and daisyui-theme.mjs: GitHub release assets, for which nobody publishes a checksum. They are pinned by
  the hash recorded here on first download: a later download of the same version must give exactly those bytes.
- daisyUI's llms.txt: daisyui.com serves only the latest one, so it is rebuilt from the skill files at the version's git
  tag, the way the site builds it. The result was compared with the site for 5.7.50: byte for byte the same.
- daisyUI's documentation source: the gallery's examples and daisyUI's own translations of them. daisyui.com has no
  file for this, so its pages are collected from the same tag into one file, pinned by the hash recorded here.
- Tailwind's executables: the hashes come from the release's sha256sums.txt, and tools/css.py checks them on every run.

Every version passes the same rules: nothing younger than two weeks, unless it fixes a known vulnerability.
"""

import base64
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor.json"
WINDOW = timedelta(days=14)
LLMS_URL = "https://daisyui.com/llms.txt"
LLMS_RECIPE = "packages/docs/src/routes/llms.txt/+server.js"
"""Where daisyUI builds its llms.txt. `assemble_llms` follows it, so a change there must be read by a person."""
DOCS_PAGE = re.compile(r"packages/docs/src/routes/\(routes\)/components/([a-z0-9-]+)/\+page\.md")
DOCS_TRANSLATION = re.compile(r"packages/docs/src/translation/([a-z]+)\.components\.json")
DOCS_LICENCE = "LICENSE"


class Refused(RuntimeError):
    """A file that must not be accepted: the update stops for that file, reports it, and goes on with the others."""


def read_json(url: str, data: bytes | None = None) -> Any:
    headers = {"Content-Type": "application/json"} if data else {}
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=30) as response:
        return json.load(response)


def read_entries() -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = json.loads(VENDOR.read_text(encoding="utf-8"))
    return entries


def write_entries(entries: dict[str, dict[str, Any]]) -> None:
    VENDOR.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8", newline="\n")


def vulnerabilities(name: str, version: str) -> list[str]:
    query = {"package": {"name": name, "ecosystem": "npm"}, "version": version}
    found = read_json("https://api.osv.dev/v1/query", json.dumps(query).encode()).get("vulns", [])
    return [item["id"] for item in found]


def version_key(version: str) -> list[int]:
    return [int(part) for part in version.split(".")]


def sha384(content: bytes) -> str:
    return base64.b64encode(hashlib.sha384(content).digest()).decode()


def newest_allowed(name: str, current: str) -> str | None:
    """The newest stable version of this major one that passes the rules, never older than `current`.

    A settled version comes first. Otherwise `current` stays, unless it is vulnerable: only then may a newer version
    skip the wait. None means nothing qualifies, `current` included.
    """
    package = read_json("https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@"))
    major = current.split(".")[0] + "."
    released: dict[str, datetime] = {
        version: datetime.fromisoformat(package["time"][version].replace("Z", "+00:00"))
        for version, data in package["versions"].items()
        if version.startswith(major) and "-" not in version and not data.get("deprecated")
    }
    limit = datetime.now(UTC) - WINDOW
    candidates = sorted((v for v in released if version_key(v) >= version_key(current)), key=version_key, reverse=True)
    for version in [v for v in candidates if released[v] <= limit][:10]:
        if not vulnerabilities(name, version):
            return version
    if not vulnerabilities(name, current):
        return current if current in released else None
    return next((version for version in candidates if not vulnerabilities(name, version)), None)


def tarball(name: str, version: str) -> bytes:
    """A package as published, checked against its published integrity."""
    metadata = read_json(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}/{version}")
    with urllib.request.urlopen(metadata["dist"]["tarball"], timeout=120) as response:
        content: bytes = response.read()
    algorithm, expected = metadata["dist"]["integrity"].split("-", 1)
    if base64.b64encode(hashlib.new(algorithm, content).digest()).decode() != expected:
        raise Refused(f"{name} {version}: the tarball does not match its published integrity")
    return content


def fetch(name: str, version: str, member: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(tarball(name, version))) as archive:
        extracted = archive.extractfile(f"package/{member}")
        if extracted is None:
            raise Refused(f"{name} {version}: no {member} in the package")
        return extracted.read()


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "business-app-base"})
    with urllib.request.urlopen(request, timeout=120) as response:
        content: bytes = response.read()
    return content


def executable_hashes(version: str, names: dict[str, str]) -> dict[str, str]:
    url = f"https://github.com/tailwindlabs/tailwindcss/releases/download/v{version}/sha256sums.txt"
    lines = [line.split() for line in download(url).decode().splitlines() if line.strip()]
    published = {path.removeprefix("./"): digest for digest, path in lines}
    missing = sorted(set(names) - set(published))
    if missing:
        raise Refused(f"tailwindcss {version}: no published hash for {missing}")
    return {name: published[name] for name in names}


def _frontmatter(text: str) -> str:
    """The site's withRuntimeFrontmatter: it points `source` at the site and adds two settings."""
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return text
    end = text.index("\n---\n", 4)
    lines = text[4:end].split("\n")
    lines = [
        line[: len(line) - len(line.lstrip())] + f"source: {LLMS_URL}" if line.lstrip().startswith("source:") else line
        for line in lines
    ]
    if not any(line.startswith("alwaysApply:") for line in lines):
        lines.append("alwaysApply: true")
    if not any(line.startswith("applyTo:") for line in lines):
        lines.append('applyTo: "**"')
    return "---\n" + "\n".join(lines) + "\n---\n" + text[end + 5 :]


def assemble_llms(skills: dict[str, str]) -> str:
    """The same steps as daisyUI's LLMS_RECIPE, on its files under skills/daisyui/, named relative to that folder."""

    def body(name: str) -> str:
        return re.sub(r"\A---\r?\n[\s\S]*?\r?\n---\r?\n?", "", skills[name])

    root = skills["SKILL.md"]
    references = root.find("## References that you must read")
    protocol = root.find("### Component discovery protocol")
    parts = [
        root.rstrip() if references == -1 else root[:references].rstrip(),
        *(body(f"{group}/SKILL.md") for group in ("install", "usage", "config", "colors")),
        "" if protocol == -1 else root[protocol:].strip(),
        "## daisyUI components",
        *(body(name) for name in sorted(skills) if name.startswith("components/")),
    ]
    return _frontmatter("\n\n".join(part for part in parts if part))


def tag_files(version: str) -> Iterator[tuple[str, bytes]]:
    """Each file of a version's git tag, with its path inside the repository."""
    url = f"https://codeload.github.com/saadeghi/daisyui/tar.gz/refs/tags/v{version}"
    with tarfile.open(fileobj=io.BytesIO(download(url))) as archive:
        for member in archive.getmembers():
            extracted = archive.extractfile(member) if member.isfile() else None
            if extracted is not None:
                yield member.name.removeprefix(f"daisyui-{version}/"), extracted.read()


def daisyui_llms(version: str, recipe: str) -> bytes:
    """llms.txt for one version, from the tag's archive, refused if the site's way of building it has changed."""
    skills: dict[str, str] = {}
    found_recipe = b""
    for path, content in tag_files(version):
        if path == LLMS_RECIPE:
            found_recipe = content
        elif re.fullmatch(r"skills/daisyui/(SKILL\.md|[a-z]+/SKILL\.md|components/[a-z0-9-]+\.md)", path):
            skills[path.removeprefix("skills/daisyui/")] = content.decode("utf-8")
    if sha384(found_recipe) != recipe:
        raise Refused(f"daisyui-llms {version}: {LLMS_RECIPE} changed: compare it with vendor.assemble_llms")
    return assemble_llms(skills).encode("utf-8")


def daisyui_docs(version: str, languages: list[str]) -> bytes:
    """The documentation's component pages and their translations, from the tag, as one repeatable file."""
    pages: dict[str, str] = {}
    translations: dict[str, dict[str, str]] = {}
    licence = ""
    for path, content in tag_files(version):
        page = DOCS_PAGE.fullmatch(path)
        translation = DOCS_TRANSLATION.fullmatch(path)
        if page:
            pages[page[1]] = content.decode("utf-8")
        elif translation and translation[1] in languages:
            translations[translation[1]] = json.loads(content)
        elif path == DOCS_LICENCE:
            licence = content.decode("utf-8")
    missing = sorted(set(languages) - set(translations))
    if not pages or not licence or missing:
        raise Refused(f"daisyui-docs {version}: pages, licence or translations {missing} not where they were")
    bundle = {"version": version, "licence": licence, "pages": pages, "translations": translations}
    return (json.dumps(bundle, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def content_of(name: str, entry: dict[str, Any], version: str) -> bytes:
    if "recipe" in entry:
        return daisyui_llms(version, entry["recipe"])
    if "languages" in entry:
        return daisyui_docs(version, entry["languages"])
    if "url" in entry:
        return download(entry["url"].format(version=version))
    return fetch(name, version, entry["file"])


def check() -> list[str]:
    problems = []
    for name, entry in read_entries().items():
        if "target" not in entry:  # an executable: tools/css.py checks it every time it runs
            continue
        path = ROOT / entry["target"]
        if not path.exists() or sha384(path.read_bytes()) != entry["sha384"]:
            problems.append(f"{name}: {entry['target']} does not match vendor.json")
    return problems


def _update_entry(name: str, entry: dict[str, Any], changes: list[str]) -> str | None:
    """Moves one entry. The same version must give the same bytes: anything else was replaced behind its number."""
    version = newest_allowed(entry.get("package", name), entry["version"])
    if version is None:
        return "no allowed version"
    if "executables" in entry:
        if version != entry["version"]:
            entry.update(version=version, executables=executable_hashes(version, entry["executables"]))
            changes.append(f"`{name}` to {version}")
        return None
    target = ROOT / entry["target"]
    same_version = version == entry["version"]
    if same_version and target.exists() and sha384(target.read_bytes()) == entry["sha384"]:
        return None
    content = content_of(name, entry, version)
    if same_version and sha384(content) != entry["sha384"]:
        raise Refused(f"version {version} no longer gives the file recorded in vendor.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    changes.append(f"`{name}` {entry['version']} to {version}")
    entry.update(version=version, sha384=sha384(content))
    return None


def update() -> tuple[list[str], list[tuple[str, str, str]]]:
    """What moved, and each entry that could not, as (name, version, reason). One refusal never stops the others."""
    entries = read_entries()
    changes: list[str] = []
    refused: list[tuple[str, str, str]] = []
    for name, entry in entries.items():
        try:
            reason = _update_entry(name, entry, changes)
        except (Refused, OSError, ValueError, KeyError, tarfile.TarError) as error:
            reason = f"{type(error).__name__}: {error}"
        if reason:
            refused.append((name, entry["version"], reason))
    write_entries(entries)
    return changes, refused


def main() -> int:
    if sys.argv[1:] == ["check"]:
        problems = check()
        print("\n".join(problems) or "vendored files match")
        return 1 if problems else 0
    if sys.argv[1:] == ["update"]:
        changes, refused = update()
        print("\n".join(changes) or "no change")
        for name, version, reason in refused:
            print(f"{name} {version}: {reason}", file=sys.stderr)
        return 1 if refused else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
