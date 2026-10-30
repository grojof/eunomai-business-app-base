"""The maintenance tools: a download is trusted only if it proves itself, and one problem never stops the others."""

import base64
import hashlib
import io
import json
import re
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.helpers import ROOT
from tools import css, update_dependencies, vendor

WORKFLOW = (ROOT / ".github" / "workflows" / "dependencies.yml").read_text(encoding="utf-8")


def sha384(content: bytes) -> str:
    return base64.b64encode(hashlib.sha384(content).digest()).decode()


# The stylesheet's executable


@pytest.fixture
def cached(tmp_path, monkeypatch):
    """An executable in a temporary .cache, and the file a download would give."""
    good = b"the real executable"
    entry = {"version": "1.0.0", "executables": {"tool": hashlib.sha256(good).hexdigest()}}
    (tmp_path / "vendor.json").write_text(json.dumps({"tailwindcss": entry}), encoding="utf-8")
    monkeypatch.setattr(css, "ROOT", tmp_path)
    monkeypatch.setattr(css, "executable_name", lambda: "tool")
    path = tmp_path / ".cache" / "tailwindcss" / "1.0.0" / "tool"
    path.parent.mkdir(parents=True)
    return path, good


def serve(monkeypatch, content):
    calls = []

    def urlopen(url, timeout):
        calls.append(url)
        return io.BytesIO(content)

    monkeypatch.setattr(css.urllib.request, "urlopen", urlopen)
    return calls


def test_a_good_cached_executable_is_not_downloaded_again(cached, monkeypatch):
    path, good = cached
    path.write_bytes(good)
    calls = serve(monkeypatch, b"never")
    assert css.executable() == path
    assert calls == []


def test_a_tampered_cached_executable_is_replaced_before_it_runs(cached, monkeypatch):
    path, good = cached
    path.write_bytes(b"something else")
    calls = serve(monkeypatch, good)
    assert css.executable() == path
    assert path.read_bytes() == good
    assert len(calls) == 1
    assert [file.name for file in path.parent.iterdir()] == ["tool"]


def test_a_bad_download_never_reaches_the_cache(cached, monkeypatch):
    path, _good = cached
    path.write_bytes(b"something else")
    serve(monkeypatch, b"also wrong")
    with pytest.raises(RuntimeError, match="does not match"):
        css.executable()
    assert path.read_bytes() == b"something else"
    assert [file.name for file in path.parent.iterdir()] == ["tool"]


@pytest.mark.parametrize(("system", "machine"), [("Windows", "ARM64"), ("FreeBSD", "amd64"), ("Linux", "riscv64")])
def test_an_unsupported_computer_gets_a_clear_message(monkeypatch, system, machine):
    monkeypatch.setattr(css.platform, "system", lambda: system)
    monkeypatch.setattr(css.platform, "machine", lambda: machine)
    with pytest.raises(SystemExit, match=f"no executable for {system} on {machine}"):
        css.executable_name()


@pytest.mark.parametrize(
    ("system", "machine", "musl", "expected"),
    [
        ("Linux", "x86_64", False, "tailwindcss-linux-x64"),
        ("Linux", "aarch64", True, "tailwindcss-linux-arm64-musl"),
        ("Darwin", "x86_64", False, "tailwindcss-macos-x64"),
        ("Windows", "AMD64", False, "tailwindcss-windows-x64.exe"),
    ],
)
def test_each_computer_gets_its_executable(monkeypatch, system, machine, musl, expected):
    monkeypatch.setattr(css.platform, "system", lambda: system)
    monkeypatch.setattr(css.platform, "machine", lambda: machine)
    monkeypatch.setattr(css, "uses_musl", lambda: musl)
    assert css.executable_name() == expected


def test_executable_hashes_come_from_the_published_list(monkeypatch):
    sums = b"aaa  ./tailwindcss-macos-x64\nbbb  ./tailwindcss-linux-x64\n\n"
    monkeypatch.setattr(vendor, "download", lambda url: sums)
    assert vendor.executable_hashes("1.0.0", {"tailwindcss-macos-x64": "old"}) == {"tailwindcss-macos-x64": "aaa"}
    with pytest.raises(vendor.Refused, match=r"tailwindcss-windows-x64\.exe"):
        vendor.executable_hashes("1.0.0", {"tailwindcss-windows-x64.exe": "old"})


# Copied files


@pytest.fixture
def vendored(tmp_path, monkeypatch):
    """One file pinned by a recorded hash, in a temporary repository, and what its URL serves."""
    recorded = b"the recorded file"
    target = tmp_path / "thing.js"
    target.write_bytes(recorded)
    entry = {"version": "1.0.0", "url": "https://x/{version}", "target": "thing.js", "sha384": sha384(recorded)}
    (tmp_path / "vendor.json").write_text(json.dumps({"thing": entry}), encoding="utf-8")
    monkeypatch.setattr(vendor, "ROOT", tmp_path)
    monkeypatch.setattr(vendor, "VENDOR", tmp_path / "vendor.json")
    monkeypatch.setattr(vendor, "newest_allowed", lambda name, current: "1.0.0")
    return target, recorded


def test_the_same_version_with_other_bytes_is_refused(vendored, monkeypatch):
    target, recorded = vendored
    target.unlink()
    monkeypatch.setattr(vendor, "download", lambda url: b"replaced behind the version number")
    changes, refused = vendor.update()
    assert changes == []
    assert refused[0][:2] == ("thing", "1.0.0")
    assert "no longer gives" in refused[0][2]
    assert not target.exists()
    assert vendor.read_entries()["thing"]["sha384"] == sha384(recorded)


def test_the_same_version_with_the_same_bytes_is_restored(vendored, monkeypatch):
    target, recorded = vendored
    target.write_bytes(b"changed by hand")
    monkeypatch.setattr(vendor, "download", lambda url: recorded)
    _changes, refused = vendor.update()
    assert refused == []
    assert target.read_bytes() == recorded


def test_an_intact_file_is_not_downloaded(vendored, monkeypatch):
    def no_download(url):
        raise AssertionError(url)

    monkeypatch.setattr(vendor, "download", no_download)
    assert vendor.update() == ([], [])


def test_a_new_version_records_its_hash(vendored, monkeypatch):
    target, _recorded = vendored
    monkeypatch.setattr(vendor, "newest_allowed", lambda name, current: "1.1.0")
    monkeypatch.setattr(vendor, "download", lambda url: url.encode())
    changes, _refused = vendor.update()
    assert changes == ["`thing` 1.0.0 to 1.1.0"]
    assert target.read_bytes() == b"https://x/1.1.0"
    assert vendor.read_entries()["thing"]["sha384"] == sha384(b"https://x/1.1.0")
    assert vendor.check() == []


def test_one_refusal_does_not_stop_the_others(vendored, monkeypatch):
    second = {"version": "1.0.0", "url": "https://y/{version}", "target": "second.js", "sha384": "?"}
    vendor.write_entries(vendor.read_entries() | {"second": second})
    monkeypatch.setattr(vendor, "newest_allowed", lambda name, current: "1.1.0")

    def download(url):
        if "x" in url:
            raise OSError("the server is down")
        return b"second"

    monkeypatch.setattr(vendor, "download", download)
    changes, refused = vendor.update()
    assert changes == ["`second` 1.0.0 to 1.1.0"]
    assert [item[0] for item in refused] == ["thing"]


def test_no_download_is_trusted_without_a_way_to_check_it():
    for name, entry in vendor.read_entries().items():
        assert "sha384" in entry or "executables" in entry, name
        assert entry.get("url") != vendor.LLMS_URL, "that address serves only the latest version"
        assert "{version}" in entry.get("url", "{version}"), name


def test_the_official_file_follows_daisyuis_version_and_its_wait(monkeypatch):
    entry = vendor.read_entries()["daisyui-llms"]
    assert entry["package"] == "daisyui"
    assert entry["version"] == vendor.read_entries()["daisyui"]["version"]
    now = datetime.now(UTC)
    moments = {"5.0.0": now - timedelta(days=30), "5.0.1": now - timedelta(days=13)}
    registry = {
        "versions": {version: {} for version in moments},
        "time": {version: moment.isoformat() for version, moment in moments.items()},
    }
    monkeypatch.setattr(vendor, "read_json", lambda url: registry)
    monkeypatch.setattr(vendor, "vulnerabilities", lambda name, version: [])
    assert vendor.newest_allowed("daisyui", "5.0.0") == "5.0.0"


def serve_versions(monkeypatch, ages, vulnerable=(), deprecated=()):
    """A registry with these versions, each published that many days ago."""
    now = datetime.now(UTC)
    registry = {
        "versions": {version: {"deprecated": "no"} if version in deprecated else {} for version in ages},
        "time": {version: (now - timedelta(days=days)).isoformat() for version, days in ages.items()},
    }
    monkeypatch.setattr(vendor, "read_json", lambda url: registry)
    monkeypatch.setattr(vendor, "vulnerabilities", lambda name, version: ["CVE"] if version in vulnerable else [])


def test_a_file_never_moves_to_an_older_version(monkeypatch):
    serve_versions(monkeypatch, {"5.0.1": 30, "5.0.2": 3})
    assert vendor.newest_allowed("daisyui", "5.0.2") == "5.0.2"


def test_a_newer_settled_version_is_taken(monkeypatch):
    serve_versions(monkeypatch, {"5.0.1": 30, "5.0.2": 20})
    assert vendor.newest_allowed("daisyui", "5.0.1") == "5.0.2"


def test_a_clean_current_version_makes_a_younger_one_wait(monkeypatch):
    serve_versions(monkeypatch, {"5.0.1": 30, "5.0.2": 20, "5.0.3": 3}, vulnerable={"5.0.1"})
    assert vendor.newest_allowed("daisyui", "5.0.2") == "5.0.2"


def test_a_fix_skips_the_wait_for_a_vulnerable_current_version(monkeypatch):
    serve_versions(monkeypatch, {"5.0.1": 30, "5.0.2": 3}, vulnerable={"5.0.1"})
    assert vendor.newest_allowed("daisyui", "5.0.1") == "5.0.2"


def test_an_older_clean_version_is_no_way_out_of_a_vulnerability(monkeypatch):
    serve_versions(monkeypatch, {"5.0.1": 30, "5.0.2": 20}, vulnerable={"5.0.2"})
    assert vendor.newest_allowed("daisyui", "5.0.2") is None


def test_a_deprecated_current_version_with_nothing_newer_has_no_allowed_version(monkeypatch):
    serve_versions(monkeypatch, {"5.0.1": 30, "5.0.2": 20}, deprecated={"5.0.2"})
    assert vendor.newest_allowed("daisyui", "5.0.2") is None


SKILLS = {
    "SKILL.md": (
        "---\nname: x\nmetadata:\n  source: elsewhere\n---\n\n# Title\n\n## References that you must read\n"
        "list\n\n### Component discovery protocol\nProtocol text\n"
    ),
    "install/SKILL.md": "---\nname: i\n---\nInstall text\n",
    "usage/SKILL.md": "---\nname: u\n---\nUsage text\n",
    "config/SKILL.md": "---\nname: c\n---\nConfig text\n",
    "colors/SKILL.md": "---\nname: k\n---\nColor text\n",
    "components/beta.md": "---\nname: b\n---\n### beta\n",
    "components/alpha.md": "---\nname: a\n---\n### alpha\n",
}


def test_the_official_file_is_built_the_way_the_site_builds_it():
    assert vendor.assemble_llms(SKILLS) == (
        '---\nname: x\nmetadata:\n  source: https://daisyui.com/llms.txt\nalwaysApply: true\napplyTo: "**"\n---\n\n'
        "# Title\n\nInstall text\n\n\nUsage text\n\n\nConfig text\n\n\nColor text\n\n\n"
        "### Component discovery protocol\nProtocol text\n\n## daisyUI components\n\n"
        "### alpha\n\n\n### beta\n"
    )


def tag_archive(version: str, recipe: bytes) -> bytes:
    files = {f"skills/daisyui/{name}": text.encode() for name, text in SKILLS.items()}
    files |= {vendor.LLMS_RECIPE: recipe, "packages/other/SKILL.md": b"ignored"}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(f"daisyui-{version}/{name}")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def test_the_official_file_comes_from_the_versions_tag(monkeypatch):
    urls = []

    def download(url):
        urls.append(url)
        return tag_archive("5.0.0", b"the recipe")

    monkeypatch.setattr(vendor, "download", download)
    content = vendor.daisyui_llms("5.0.0", sha384(b"the recipe")).decode()
    assert urls == ["https://codeload.github.com/saadeghi/daisyui/tar.gz/refs/tags/v5.0.0"]
    assert content == vendor.assemble_llms(SKILLS)


def docs_archive(version: str, pages: bool = True) -> bytes:
    page = "packages/docs/src/routes/(routes)/components/alpha/+page.md"
    files = {
        "LICENSE": b"MIT",
        page if pages else "packages/docs/other.md": b"---\ntitle: Alpha\n---\n",
        "packages/docs/src/translation/es.components.json": b'{"Alpha": "Alfa"}',
        "packages/docs/src/translation/de.components.json": b'{"Alpha": "Nein"}',
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(f"daisyui-{version}/{name}")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def test_the_documentation_comes_from_the_versions_tag_and_is_repeatable(monkeypatch):
    monkeypatch.setattr(vendor, "download", lambda url: docs_archive("5.0.0"))
    content = vendor.daisyui_docs("5.0.0", ["es"])
    assert content == vendor.daisyui_docs("5.0.0", ["es"])
    assert json.loads(content) == {
        "version": "5.0.0",
        "licence": "MIT",
        "pages": {"alpha": "---\ntitle: Alpha\n---\n"},
        "translations": {"es": {"Alpha": "Alfa"}},
    }


@pytest.mark.parametrize(("languages", "pages"), [(["fr"], True), (["es"], False)])
def test_documentation_that_is_not_where_it_was_is_refused(monkeypatch, languages, pages):
    monkeypatch.setattr(vendor, "download", lambda url: docs_archive("5.0.0", pages))
    with pytest.raises(vendor.Refused, match="not where they were"):
        vendor.daisyui_docs("5.0.0", languages)


def test_a_change_in_how_the_site_builds_the_file_is_refused(monkeypatch):
    monkeypatch.setattr(vendor, "download", lambda url: tag_archive("5.0.0", b"a new recipe"))
    with pytest.raises(vendor.Refused, match="changed"):
        vendor.daisyui_llms("5.0.0", sha384(b"the recipe"))


def test_git_never_changes_a_file_whose_hash_is_recorded():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    folders = {"app/ui/static/vendor/** -text", "tests/vendor/** -text", "tools/tailwind/** -text"}
    assert folders | {"app/ui/static/app.css -text"} <= set(attributes)
    for entry in vendor.read_entries().values():
        if "target" in entry:
            assert f"{Path(entry['target']).parent.as_posix()}/** -text" in folders


# The daily update


NEW_SECTION = (
    "\n### sparkles\nIt shines.\n\n[sparkles documentation](https://daisyui.com/components/sparkles/)\n\n"
    "#### Class names\n- component: `sparkles`\n"
)


@pytest.fixture
def repository(tmp_path, monkeypatch):
    """A temporary repository with daisyUI and another copied file, and the real generator pointed at it."""
    source = (ROOT / "tools" / "tailwind" / "daisyui-llms.txt").read_bytes()
    (tmp_path / "llms.txt").write_bytes(source)
    (tmp_path / "daisyui.mjs").write_bytes(b"old daisyui")
    (tmp_path / "other.js").write_bytes(b"old other")
    (tmp_path / "vendor.json").write_text(
        json.dumps(
            {
                "daisyui": {"version": "1.0.0", "target": "daisyui.mjs", "sha384": "a"},
                "daisyui-llms": {"package": "daisyui", "version": "1.0.0", "target": "llms.txt", "sha384": "b"},
                "other": {"version": "1.0.0", "target": "other.js", "sha384": "c"},
            }
        ),
        encoding="utf-8",
    )
    tools_vendor = update_dependencies.vendor
    monkeypatch.setattr(update_dependencies, "ROOT", tmp_path)
    monkeypatch.setattr(tools_vendor, "VENDOR", tmp_path / "vendor.json")
    monkeypatch.setattr(update_dependencies.components, "SOURCE", tmp_path / "llms.txt")
    monkeypatch.setattr(update_dependencies.components, "TARGET", ROOT / "docs" / "components")
    return tmp_path, source


def fake_update(repository, addition):
    """What vendor.update would leave: every file at version 2, and the official file with `addition`."""

    def update():
        folder, source = repository
        (folder / "llms.txt").write_bytes(source + addition)
        (folder / "daisyui.mjs").write_bytes(b"new daisyui")
        (folder / "other.js").write_bytes(b"new other")
        tools_vendor = update_dependencies.vendor
        entries = tools_vendor.read_entries()
        for entry in entries.values():
            entry["version"] = "2.0.0"
        tools_vendor.write_entries(entries)
        return ["`daisyui` 1.0.0 to 2.0.0", "`daisyui-llms` 1.0.0 to 2.0.0", "`other` 1.0.0 to 2.0.0"], []

    return update


def test_a_new_official_component_is_reported_and_stops_nothing(repository, monkeypatch):
    folder, source = repository
    tools_vendor = update_dependencies.vendor
    monkeypatch.setattr(tools_vendor, "update", fake_update(repository, NEW_SECTION.encode()))
    problems = []
    notes = update_dependencies.update_vendored(problems)
    assert notes == ["`other` 1.0.0 to 2.0.0"]
    assert [(name, version) for name, version, _reason in problems] == [("daisyui", "1.0.0")]
    assert "sparkles" in problems[0][2]
    entries = tools_vendor.read_entries()
    assert (entries["daisyui"]["version"], entries["daisyui-llms"]["version"], entries["other"]["version"]) == (
        "1.0.0",
        "1.0.0",
        "2.0.0",
    )
    assert (folder / "llms.txt").read_bytes() == source
    assert (folder / "daisyui.mjs").read_bytes() == b"old daisyui"
    assert (folder / "other.js").read_bytes() == b"new other"


def test_a_daisyui_file_left_behind_holds_all_of_them_back(repository, monkeypatch):
    folder, _source = repository
    tools_vendor = update_dependencies.vendor

    def update():
        (folder / "daisyui.mjs").write_bytes(b"new daisyui")
        entries = tools_vendor.read_entries()
        entries["daisyui"]["version"] = "2.0.0"
        tools_vendor.write_entries(entries)
        return ["`daisyui` 1.0.0 to 2.0.0"], [("daisyui-llms", "1.0.0", "refused")]

    monkeypatch.setattr(tools_vendor, "update", update)
    problems = []
    assert update_dependencies.update_vendored(problems) == []
    assert tools_vendor.read_entries()["daisyui"]["version"] == "1.0.0"
    assert (folder / "daisyui.mjs").read_bytes() == b"old daisyui"
    assert any("different versions" in reason for _name, _version, reason in problems)


def test_every_daisyui_file_is_at_one_version():
    entries = vendor.read_entries().values()
    assert len({entry["version"] for entry in entries if entry.get("package", "") == "daisyui"} | set()) == 1


def test_the_gallerys_data_reaches_the_pull_request():
    assert "tools/gallery.py\n" in job("update")
    assert "app/demo/examples/" in job("propose")


def test_an_update_without_surprises_keeps_everything(repository, monkeypatch):
    tools_vendor = update_dependencies.vendor
    monkeypatch.setattr(tools_vendor, "update", fake_update(repository, b"\n"))
    problems = []
    assert len(update_dependencies.update_vendored(problems)) == 3
    assert problems == []


def test_a_refused_file_reaches_the_problems(repository, monkeypatch):
    tools_vendor = update_dependencies.vendor
    monkeypatch.setattr(tools_vendor, "update", lambda: ([], [("thing", "1.0.0", "no longer gives the file")]))
    problems = []
    assert update_dependencies.update_vendored(problems) == []
    assert problems == [("thing", "1.0.0", "no longer gives the file")]


def test_a_crash_still_writes_the_problems_and_fails(tmp_path, monkeypatch):
    def stop():
        raise RuntimeError("the registry is down")

    monkeypatch.setattr(update_dependencies, "overrides", stop)
    summary, problems = tmp_path / "summary.md", tmp_path / "problems.md"
    monkeypatch.setattr(sys, "argv", ["update", "--summary", str(summary), "--problems", str(problems)])
    assert update_dependencies.main() == 1
    assert "the registry is down" in problems.read_text(encoding="utf-8")
    assert summary.exists()


def test_a_fix_the_limits_refuse_reaches_the_problems(monkeypatch):
    moment = "2026-01-01T00:00:00+00:00"
    published = {"1.0.0": [{"upload_time_iso_8601": moment}], "2.0.0": [{"upload_time_iso_8601": moment}]}
    monkeypatch.setattr(update_dependencies, "installed", lambda: {"thing": "1.0.0"})
    monkeypatch.setattr(update_dependencies, "pypi", lambda name: {"releases": published})
    monkeypatch.setattr(update_dependencies, "write_overrides", lambda values: None)
    monkeypatch.setattr(update_dependencies, "uv", lambda *args: None)
    vulnerable = {"1.0.0": ["CVE-1"], "2.0.0": []}
    monkeypatch.setattr(update_dependencies, "vulnerabilities", lambda name, version: vulnerable[version])
    notes = []
    assert update_dependencies.review(notes, {}) == [("thing", "1.0.0", "2.0.0 fixes CVE-1, but the limits refuse it")]
    assert notes == []


def job(name):
    return WORKFLOW[WORKFLOW.index(f"\n  {name}:\n") :]


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
