"""tools/update_application.py: an application takes a newer version of its template on a branch, its own work kept."""

import shutil
import subprocess
from pathlib import Path

import pytest

from tools import update_application as tool

SOURCE_V1 = '# Made by tools/make_template.py\nbase_commit = "1111111aaaa"\nlayer = "layer-one"\n'
SOURCE_V2 = '# Made by tools/make_template.py\nbase_commit = "2222222bbbb"\nlayer = "layer-one"\n'
V1 = {
    "app/core/settings.py": "first\nsecond\nthird\n",
    "app/core/identity.py": "roles = exact\n",
    "tools/old_tool.py": "print('old')\n",
    "docs/base/specification.md": "one\ntwo\n",
    "app/brand/logo.png": b"\x89PNG\r\n\x1a\nold",
    ".template-source": SOURCE_V1,
}
V2 = {
    "app/core/settings.py": "first\nsecond, better\nthird\n",
    "app/core/identity.py": "roles = patterns\n",
    "tools/new_tool.py": "print('new')\n",
    "docs/base/specification.md": "one\ntwo\nthree\n",
    "app/brand/logo.png": b"\x89PNG\r\n\x1a\nnew",
    ".template-source": SOURCE_V2,
}


def run(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def commit(folder: Path, files: dict, message: str) -> None:
    for path in list(folder.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            path.unlink()
    for name, content in files.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
    run("add", "-A", cwd=folder)
    run("commit", "--quiet", "-m", message, cwd=folder)


def repository(folder: Path) -> Path:
    folder.mkdir()
    run("init", "--quiet", "--initial-branch=main", cwd=folder)
    run("config", "user.email", "tests@example.org", cwd=folder)
    run("config", "user.name", "Tests", cwd=folder)
    run("config", "core.autocrlf", "false", cwd=folder)
    return folder


@pytest.fixture
def template(tmp_path) -> Path:
    folder = repository(tmp_path / "template")
    commit(folder, V1, "template v1")
    commit(folder, V2, "template v2")
    return folder


@pytest.fixture
def application(tmp_path) -> Path:
    """Made from v1 as a git server makes a repository from a template: the files, none of its history. Then its own
    work: a module, a changed identity (as assistants building applications have done) and its name in the settings' last line."""
    folder = repository(tmp_path / "application")
    commit(folder, V1, "made from the template")
    own = dict(V1)
    own["app/courses/routes.py"] = "courses\n"
    own["app/core/identity.py"] = "roles = exact, and departments\n"
    own["app/core/settings.py"] = "first\nsecond\nthird\nname = training\n"
    commit(folder, own, "the application's work")
    return folder


def test_check_says_what_would_change_and_changes_nothing(template, application):
    before = run("rev-parse", "HEAD", cwd=application)
    plan = tool.plan_update(str(template), "HEAD", application)
    assert sorted(plan.changes) == sorted(
        [
            "app/core/settings.py",
            "app/core/identity.py",
            "tools/old_tool.py",
            "tools/new_tool.py",
            "docs/base/specification.md",
            "app/brand/logo.png",
        ]
    )
    assert plan.conflicts == ["app/core/identity.py"]
    assert sorted(plan.changed_by_application) == ["app/core/identity.py", "app/core/settings.py"]
    text = tool.report(plan, application)
    assert "base 1111111" in text and "base 2222222" in text and "1 in conflict" in text
    assert run("rev-parse", "HEAD", cwd=application) == before
    assert run("status", "--porcelain", cwd=application) == ""
    assert run("worktree", "list", "--porcelain", cwd=application).count("worktree ") == 1


def test_an_update_without_conflicts_is_committed_on_its_branch(template, application):
    own = dict(V1)
    own["app/courses/routes.py"] = "courses\n"
    own["app/core/settings.py"] = "first\nsecond\nthird\nname = training\n"
    commit(application, own, "identity back as the template had it")
    plan, branch = tool.update(str(template), "HEAD", application)
    assert branch == "template-2222222" and plan.conflicts == []
    assert run("branch", "--show-current", cwd=application).strip() == branch
    assert run("status", "--porcelain", cwd=application) == ""
    files = lambda name: (application / name).read_text(encoding="utf-8")  # noqa: E731
    assert files("app/core/settings.py") == "first\nsecond, better\nthird\nname = training\n", "both changes kept"
    assert files("app/core/identity.py") == "roles = patterns\n"
    assert files("app/courses/routes.py") == "courses\n", "the application's own file is not touched"
    assert not (application / "tools/old_tool.py").exists() and files("tools/new_tool.py") == "print('new')\n"
    assert (application / "app/brand/logo.png").read_bytes().endswith(b"new")
    assert files(".template-source") == SOURCE_V2


def test_a_conflict_is_left_on_the_branch_for_a_person(template, application):
    plan, _branch = tool.update(str(template), "HEAD", application)
    assert plan.conflicts == ["app/core/identity.py"]
    assert "<<<<<<<" in (application / "app/core/identity.py").read_text(encoding="utf-8")
    assert run("log", "-1", "--format=%s", cwd=application).strip() == "the application's work", "nothing committed"
    assert (application / "app/core/settings.py").read_text(encoding="utf-8").startswith("first\nsecond, better")


def test_an_application_on_the_newest_version_is_up_to_date(template, application):
    shutil.copyfile(template / ".template-source", application / ".template-source")
    run("commit", "--quiet", "-am", "on v2", cwd=application)
    plan, branch = tool.update(str(template), "HEAD", application)
    assert plan.changes == [] and branch == ""
    assert "Up to date" in tool.report(plan, application)


def test_uncommitted_work_is_never_mixed_with_an_update(template, application):
    (application / "app/courses/routes.py").write_text("half done\n", encoding="utf-8")
    with pytest.raises(tool.Refused, match="uncommitted"):
        tool.update(str(template), "HEAD", application)


def test_an_application_from_another_template_is_refused(template, application):
    (application / ".template-source").write_text(SOURCE_V1.replace("layer-one", "another"), encoding="utf-8")
    run("commit", "--quiet", "-am", "another layer", cwd=application)
    with pytest.raises(tool.Refused, match="another template"):
        tool.plan_update(str(template), "HEAD", application)


def test_an_application_without_its_source_is_refused(template, application):
    (application / ".template-source").unlink()
    run("commit", "--quiet", "-am", "no source", cwd=application)
    with pytest.raises(tool.Refused, match="make_template"):
        tool.plan_update(str(template), "HEAD", application)


def test_an_older_version_can_be_asked_for(template, application):
    plan = tool.plan_update(str(template), "HEAD~1", application)
    assert plan.changes == []


def test_from_another_folder_the_check_reads_the_named_application(template, application, capsys):
    """An application made before the tool existed runs it from a newer template's folder."""
    assert tool.main(["--template", str(template), "--application", str(application), "--check"]) == 0
    assert "1 in conflict" in capsys.readouterr().out
    assert tool.main(["--template", str(template), "--application", str(application), "--to", "nowhere"]) == 1
    assert "no branch, tag or commit nowhere" in capsys.readouterr().err
