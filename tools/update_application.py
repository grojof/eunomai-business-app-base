"""Brings an application up to a newer version of its organization's template, through a branch a person reviews.

uv run --frozen python tools/update_application.py --template <template repository> --check
uv run --frozen python tools/update_application.py --template <template repository>
uv run --frozen python tools/update_application.py --template <template repository> --to <branch, tag or commit>
uv run --frozen python tools/update_application.py --template <template repository> --application <folder>

`--template` is the template repository's address or folder, or the name of a remote of this one. The application's
`.template-source` says which version it was made from: that version is found in the template's history, and the
change from it to the newest (or `--to`) is applied here with a three-way merge. A file the application never touched
takes the template's new version; one it changed is merged; where both changed the same lines, the file is left with
conflict markers for a person. The application's own files are not touched.

`--check` changes nothing: it says which version the application is on, which is newest, which of the template's files
the application has changed, and which files the update would change, merge cleanly or leave in conflict.

Without it, the working tree must have nothing uncommitted. The update goes on a new branch, `template-<base>`, and is
committed when nothing is in conflict; otherwise it waits there for a person. It never pushes: whoever runs it pushes
the branch and opens the pull request, which the application's tests and review decide.

An application made before this tool existed does not have it: run it from a newer template's folder, with
`--application` naming the application's.
"""

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ".template-source"
TEMPLATE_REF = "refs/eunomai/template"


GIT_NEEDED = (2, 40)
"""`git merge-tree --merge-base`, which the update needs, is in git 2.40 and later."""


class Refused(Exception):
    pass


def git(*args: str, cwd: Path = ROOT, check: bool = True, data: bytes | None = None) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, input=data, capture_output=True)
    if check and done.returncode != 0:
        raise Refused(f"git {' '.join(args[:2])}: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout.decode(errors="replace")


def source(text: str) -> tuple[str, str]:
    """What identifies a template's version: the base's commit and the layer's hash."""
    try:
        values = tomllib.loads(text)
        return str(values["base_commit"]), str(values["layer"])
    except (tomllib.TOMLDecodeError, KeyError) as error:
        raise Refused(f"{SOURCE} cannot be read: {error}") from None


def git_version() -> tuple[int, ...] | None:
    """The version of the git on this computer; None when there is none. A person's computer, where applications
    are built with an assistant, has none on purpose: this tool is IT's."""
    try:
        said = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
    except OSError:
        return None
    found = re.search(r"(\d+)\.(\d+)", said)
    return (int(found[1]), int(found[2])) if found else None


def check_git() -> None:
    found = git_version()
    if found is None:
        raise Refused("git is needed, and there is none on this computer")
    if found < GIT_NEEDED:
        raise Refused(f"git {GIT_NEEDED[0]}.{GIT_NEEDED[1]} or later is needed, this one is {found[0]}.{found[1]}")


def fetch(template: str, ref: str, cwd: Path) -> str:
    """The template's history, kept under refs of its own; returns the commit `ref` names there: its default branch
    (`HEAD`), a branch, a tag, a commit, or one counted back from them (`HEAD~1`)."""
    git(
        "fetch", "--quiet", "--no-tags", template,
        f"+HEAD:{TEMPLATE_REF}/HEAD", f"+refs/heads/*:{TEMPLATE_REF}/heads/*", f"+refs/tags/*:{TEMPLATE_REF}/tags/*",
        cwd=cwd,
    )  # fmt: skip
    name, _, back = ref.partition("~")
    suffix = f"~{back}" if back else ""
    for candidate in (f"{TEMPLATE_REF}/HEAD" if name == "HEAD" else "", f"{TEMPLATE_REF}/heads/{name}",
                      f"{TEMPLATE_REF}/tags/{name}", name):  # fmt: skip
        if candidate:
            found = git("rev-parse", "--verify", "--quiet", f"{candidate}{suffix}^{{commit}}", cwd=cwd, check=False)
            if found.strip():
                return found.strip()
    raise Refused(f"the template has no branch, tag or commit {ref}")


def origin(wanted: tuple[str, str], newest: str, cwd: Path) -> str:
    """The template's commit this application was made from: the newest one with the same `.template-source`."""
    for commit in git("rev-list", newest, "--", SOURCE, cwd=cwd).split():
        text = git("show", f"{commit}:{SOURCE}", cwd=cwd, check=False)
        if text and source(text) == wanted:
            return commit
    raise Refused(
        f"no version of this template has the application's {SOURCE} (base {wanted[0][:7]}): it was made from "
        "another template, or that version is not in this branch's history"
    )


@dataclass
class Plan:
    origin: str
    newest: str
    changed_by_application: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    clean: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line]


def merge(plan: Plan, cwd: Path) -> tuple[str, list[str]]:
    """Git's own three-way merge of the application and the newest template, with the version the application was
    made from as their base: binary files, deletions and renames included, and nothing written. Returns the merged
    tree, where a file in conflict holds its markers, and those files."""
    done = subprocess.run(
        ["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", f"--merge-base={plan.origin}", "HEAD",
         plan.newest],
        cwd=cwd, capture_output=True,
    )  # fmt: skip
    if done.returncode not in (0, 1):
        raise Refused(f"git merge-tree: {done.stderr.decode(errors='replace').strip()}")
    tree, *conflicts = lines(done.stdout.decode(errors="replace"))
    return tree, sorted(set(conflicts))


def plan_update(template: str, ref: str, cwd: Path = ROOT) -> Plan:
    check_git()
    here = cwd / SOURCE
    if not here.is_file():
        raise Refused(f"no {SOURCE}: this application was not made by tools/make_template.py")
    newest = fetch(template, ref, cwd)
    found = Plan(origin(source(here.read_text(encoding="utf-8")), newest, cwd), newest)
    in_template = set(lines(git("ls-tree", "-r", "--name-only", found.origin, cwd=cwd)))
    found.changed_by_application = [
        path
        for path in lines(git("diff", "--name-only", found.origin, "HEAD", cwd=cwd))
        if path in in_template and path != SOURCE
    ]
    found.changes = [
        path for path in lines(git("diff", "--name-only", found.origin, newest, cwd=cwd)) if path != SOURCE
    ]
    if found.changes:
        found.conflicts = merge(found, cwd)[1]
        found.clean = [path for path in found.changes if path not in found.conflicts]
    return found


def report(plan: Plan, cwd: Path = ROOT) -> str:
    def base(commit: str) -> str:
        return source(git("show", f"{commit}:{SOURCE}", cwd=cwd))[0][:7]

    if not plan.changes:
        return f"Up to date: the application is on the template's newest version (base {base(plan.origin)})."
    out = [
        f"The application is on the template made from base {base(plan.origin)}; the newest is from base "
        f"{base(plan.newest)}.",
        f"The update changes {len(plan.changes)} files: {len(plan.clean)} cleanly, {len(plan.conflicts)} in conflict.",
    ]
    if plan.changed_by_application:
        out.append(f"Files of the template this application changed ({len(plan.changed_by_application)}):")
        out += [f"  {path}" for path in plan.changed_by_application]
    if plan.conflicts:
        out.append("In conflict, for a person to resolve:")
        out += [f"  {path}" for path in plan.conflicts]
    return "\n".join(out)


def update(template: str, ref: str, cwd: Path = ROOT) -> tuple[Plan, str]:
    if lines(git("status", "--porcelain", cwd=cwd)):
        raise Refused("there are uncommitted changes: commit or set them aside first")
    plan = plan_update(template, ref, cwd)
    if not plan.changes:
        return plan, ""
    branch = f"template-{source(git('show', f'{plan.newest}:{SOURCE}', cwd=cwd))[0][:7]}"
    tree, plan.conflicts = merge(plan, cwd)
    git("switch", "--quiet", "--create", branch, cwd=cwd)
    git("read-tree", "-m", "-u", "HEAD", tree, cwd=cwd)  # the working tree and the index become the merged tree
    if plan.conflicts:  # left out of the index, so `git diff` shows the markers and `git add` marks one resolved
        git("reset", "--quiet", "--", *plan.conflicts, cwd=cwd)
    else:
        git("commit", "--quiet", "--message", f"Template made from base {branch.removeprefix('template-')}", cwd=cwd)
    return plan, branch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", required=True, help="the template repository: address, folder or remote")
    parser.add_argument(
        "--to", default="HEAD", help="the template's branch, tag or commit; its default branch if left out"
    )
    parser.add_argument("--check", action="store_true", help="say what the update would do, and change nothing")
    parser.add_argument("--application", type=Path, default=ROOT, help="the application's folder; this one if left out")
    arguments = parser.parse_args(argv)
    folder = arguments.application.resolve()
    try:
        if arguments.check:
            print(report(plan_update(arguments.template, arguments.to, folder), folder))
            return 0
        plan, branch = update(arguments.template, arguments.to, folder)
    except Refused as problem:
        print(f"Nothing was changed: {problem}", file=sys.stderr)
        return 1
    print(report(plan, folder))
    if not branch:
        return 0
    if plan.conflicts:
        print(
            f"\nThe update is on branch {branch}, not committed. Resolve each file in conflict, `git add` it and "
            "commit. uv.lock in conflict: take the template's pyproject.toml change, then `uv lock` again."
        )
        return 2
    print(f"\nCommitted on branch {branch}. Run the tests, push the branch and open a pull request.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
