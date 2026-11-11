"""The files copied into the repository: vendor.json says which, and from where.

    uv run --frozen python tools/vendor.py check    every file matches its recorded hash
    uv run --frozen python tools/vendor.py update   move each to the newest version allowed, within its major version

Nothing runs npm. How each file is pinned:

- A package from the registry: its tarball is checked against the integrity the registry publishes.
- daisyui.mjs and daisyui-theme.mjs: GitHub release assets, for which nobody publishes a checksum. They are pinned by
  the hash recorded here on first download: a later download of the same version must give exactly those bytes.
- daisyUI's llms.txt: daisyui.com serves only the latest one, so it is rebuilt from the skill files at the version's git
  tag, the way the site builds it. The result was compared with the site for 5.7.50: byte for byte the same.
- daisyUI's documentation source: the gallery's examples and daisyUI's own translations of them. daisyui.com has no
  file for this, so its pages are collected from the same tag into one file, pinned by the hash recorded here.
- Tailwind's executables: the hashes come from the release's sha256sums.txt, and tools/css.py checks them on every run.
- Lucide's icons: a whole folder, taken from lucide-static's tarball, which the registry's integrity checks. It holds
  every icon the package lists in tags.json, and its licence. The folder is pinned by one hash of every file's name and
  content, so an icon added by hand, changed or removed fails the check.
- Lucide's index: each icon's tags, categories and old names, from Lucide's repository at the version's git tag, which
  publishes no checksum: pinned by the hash recorded here, and moved with the icons or not at all.

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
LUCIDE_LISTING = "package/tags.json"
"""Every icon lucide-static offers, by name. Its icons/ folder also has each old name as a copy: those stay out."""
LUCIDE_ICON = re.compile(r"icons/([a-z0-9-]+)\.json")
LUCIDE_CATEGORY = re.compile(r"categories/([a-z0-9-]+)\.json")


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


def newest_allowed(name: str, current: str, below: str | None = None) -> str | None:
    """The newest stable version of this major one that passes the rules, never older than `current`, and older
    than `below` when a person held the package back.

    A settled version comes first. Otherwise `current` stays, unless it is vulnerable: only then may a newer version
    skip the wait. None means nothing qualifies, `current` included.
    """
    package = read_json("https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@"))
    major = current.split(".")[0] + "."
    released: dict[str, datetime] = {
        version: datetime.fromisoformat(package["time"][version].replace("Z", "+00:00"))
        for version, data in package["versions"].items()
        if version.startswith(major)
        and "-" not in version
        and not data.get("deprecated")
        and (below is None or version_key(version) < version_key(below))
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
    request = urllib.request.Request(url, headers={"User-Agent": "eunomai-business-app-base"})
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


def archive_files(url: str) -> Iterator[tuple[str, bytes]]:
    """Each file of a git tag's archive, with its path inside the repository: the archive's top folder goes."""
    with tarfile.open(fileobj=io.BytesIO(download(url))) as archive:
        for member in archive.getmembers():
            extracted = archive.extractfile(member) if member.isfile() else None
            if extracted is not None:
                yield member.name.partition("/")[2], extracted.read()


def tag_files(version: str) -> Iterator[tuple[str, bytes]]:
    """Each file of a daisyUI version's git tag."""
    return archive_files(f"https://codeload.github.com/saadeghi/daisyui/tar.gz/refs/tags/v{version}")


def lucide_old_names(version: str) -> set[str]:
    """The names a version still ships a drawing for but no longer lists: Lucide keeps an icon's old name for a while
    after renaming it, and its metadata gives the new name (see tools/icons.py aliases)."""
    with tarfile.open(fileobj=io.BytesIO(tarball("lucide-static", version))) as archive:
        names = archive.getnames()
        listed = set(json.loads(archive.extractfile(LUCIDE_LISTING).read()))  # type: ignore[union-attr]
    drawn = {name.removeprefix("package/icons/").removesuffix(".svg") for name in names}
    return {name for name in drawn - listed if f"package/icons/{name}.svg" in names}


def lucide_icons(version: str) -> dict[str, bytes]:
    """The icon folder for one version: each listed icon as `<name>.svg`, as published, and the licence."""
    with tarfile.open(fileobj=io.BytesIO(tarball("lucide-static", version))) as archive:
        files = {
            member.name: extracted.read()
            for member in archive.getmembers()
            if member.isfile() and (extracted := archive.extractfile(member)) is not None
        }
    if LUCIDE_LISTING not in files or "package/LICENSE" not in files:
        raise Refused(f"lucide-static {version}: no list of icons or no licence where they were")
    listed = sorted(json.loads(files[LUCIDE_LISTING]))
    missing = [name for name in listed if f"package/icons/{name}.svg" not in files]
    if missing:
        raise Refused(f"lucide-static {version}: listed icons with no drawing: {missing}")
    return {f"{name}.svg": files[f"package/icons/{name}.svg"] for name in listed} | {
        "LICENSE": files["package/LICENSE"]
    }


def index_text(version: str, licence: str, categories: dict[str, str], icons: dict[str, dict[str, Any]]) -> str:
    """JSON with one line per icon and per category, so a new version reads as a list of the icons that changed."""

    def lines(items: dict[str, Any]) -> str:
        return ",\n".join(
            f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
            for key, value in sorted(items.items())
        )

    head = f'{{\n "version": {json.dumps(version)},\n "licence": {json.dumps(licence, ensure_ascii=False)},\n'
    return head + f' "categories": {{\n{lines(categories)}\n }},\n "icons": {{\n{lines(icons)}\n }}\n}}\n'


def lucide_index(version: str, url: str) -> bytes:
    """Each icon's tags, categories, old names and whether it is deprecated, from the version's tag."""
    icons: dict[str, dict[str, Any]] = {}
    categories: dict[str, str] = {}
    licence = ""
    for path, content in archive_files(url.format(version=version)):
        icon = LUCIDE_ICON.fullmatch(path)
        category = LUCIDE_CATEGORY.fullmatch(path)
        if icon:
            data = json.loads(content)
            aliases = sorted(alias["name"] if isinstance(alias, dict) else alias for alias in data.get("aliases", []))
            entry: dict[str, Any] = {"tags": data.get("tags", []), "categories": data.get("categories", [])}
            if aliases:
                entry["aliases"] = aliases
            if data.get("deprecated"):
                entry["deprecated"] = True
            icons[icon[1]] = entry
        elif category:
            categories[category[1]] = json.loads(content)["title"]
        elif path == "LICENSE":
            licence = content.decode("utf-8")
    unknown = sorted({name for icon in icons.values() for name in icon["categories"]} - set(categories))
    if not icons or not categories or not licence or unknown:
        raise Refused(f"lucide-index {version}: icons, categories {unknown} or licence not where they were")
    return index_text(version, licence, categories, icons).encode("utf-8")


def folder_digest(files: dict[str, bytes]) -> str:
    """One hash for a whole folder: every file's name and content, in the order of their names."""
    return sha384("".join(f"{name}\0{sha384(content)}\n" for name, content in sorted(files.items())).encode())


def read_folder(folder: Path) -> dict[str, bytes]:
    if not folder.is_dir():
        return {}
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def write_folder(folder: Path, files: dict[str, bytes]) -> None:
    """The folder holds exactly these files afterwards."""
    for name in set(read_folder(folder)) - set(files):
        (folder / name).unlink()
    for name, content in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(content)


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
    if "archive" in entry:
        return lucide_index(version, entry["archive"])
    if "url" in entry:
        return download(entry["url"].format(version=version))
    return fetch(name, version, entry["file"])


def check() -> list[str]:
    problems = []
    for name, entry in read_entries().items():
        if "folder" in entry:
            if folder_digest(read_folder(ROOT / entry["folder"])) != entry["sha384"]:
                problems.append(f"{name}: {entry['folder']} does not match vendor.json")
            continue
        if "target" not in entry:  # an executable: tools/css.py checks it every time it runs
            continue
        path = ROOT / entry["target"]
        if not path.exists() or sha384(path.read_bytes()) != entry["sha384"]:
            problems.append(f"{name}: {entry['target']} does not match vendor.json")
    return problems


def _update_entry(name: str, entry: dict[str, Any], changes: list[str]) -> str | None:
    """Moves one entry. The same version must give the same bytes: anything else was replaced behind its number."""
    held = entry.get("held")
    package = entry.get("package", name)
    version = (
        newest_allowed(package, entry["version"], held["below"]) if held else newest_allowed(package, entry["version"])
    )
    if held:  # said every week, so a hold is a decision someone keeps making, not one forgotten
        changes.append(f"`{name}` held below {held['below']}: {held['reason']}")
    if version is None:
        return "no allowed version"
    if "executables" in entry:
        if version != entry["version"]:
            entry.update(version=version, executables=executable_hashes(version, entry["executables"]))
            changes.append(f"`{name}` to {version}")
        return None
    if "folder" in entry:
        return _update_folder(name, entry, version, changes)
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


def _update_folder(name: str, entry: dict[str, Any], version: str, changes: list[str]) -> str | None:
    """Lucide's icons, as a whole. A screen may use any of them, so a version that removes one waits for a person."""
    folder = ROOT / entry["folder"]
    same_version = version == entry["version"]
    present = read_folder(folder)
    if same_version and folder_digest(present) == entry["sha384"]:
        return None
    files = lucide_icons(version)
    if same_version and folder_digest(files) != entry["sha384"]:
        raise Refused(f"version {version} no longer gives the folder recorded in vendor.json")
    if not same_version:
        removed = sorted(Path(item).stem for item in set(present) - set(files) if item.endswith(".svg"))
        renamed = set(lucide_old_names(version)) if removed else set()
        if gone := [icon for icon in removed if icon not in renamed]:
            raise Refused(f"version {version} removes icons a screen may use: {gone}")
        if removed:  # an application that still asks for one is told its new name by tools/icons.py check
            changes.append(
                f"Lucide renamed {', '.join(f'`{icon}`' for icon in removed)}: see its new name in tools/lucide"
            )
    write_folder(folder, files)
    changes.append(f"`{name}` {entry['version']} to {version}")
    entry.update(version=version, sha384=folder_digest(files))
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
