"""Makes an organization's application template: this base, without its demo, with the organization's layer on top.

uv run --frozen python tools/make_template.py --layer ../our-layer --out ../our-template --ref v1.4.0
uv run --frozen python tools/make_template.py --layer ../our-layer --out ../our-template          # this folder as it is

The layer is a small folder the organization keeps, and the only thing it edits:

    layer.toml   name = "Our applications"     the name an application shows until it is given its own
                 languages = ["es"]            kept besides English, which is always offered
                 default_language = "es"       optional: the last resort, English otherwise
    files/       copied onto the template, only under app/brand/ (themes, logo, fonts, icons) and a CI folder
                 (.gitea/, .github/, .forgejo/)

Each run makes the whole template again: the same base and the same layer give the same files. The base's own
workflows, which maintain it on GitHub, are left out, so the layer brings the organization's CI if it wants one. The
result is checked, then it is left in --out for a person: it never commits or pushes. Review it there, commit it to the
template's repository, and merge it through a pull request. See docs/base/specification.md#an-organizations-template
"""

import argparse
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYER_KEYS = {"name", "languages", "default_language"}
LAYER_FOLDERS = ("app/brand/", ".gitea/", ".github/", ".forgejo/")
"""Where a layer may write. Everything else is the base's, and changes there go to the base, for every organization."""
NAME = re.compile(r'[^\x00-\x1f\x7f"\\]{1,60}')
NOT_COPIED = {".git", ".venv", ".cache", ".data", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
SOURCE_FILE = ".template-source"
BASE_CI_TESTS = "tests/test_workflows.py"
"""The tests of the base's own workflows, which go with them."""
CHECKS = (["tools/css.py"], ["tools/icons.py", "check"], ["tools/translations.py", "check"])
"""The stylesheet made for the layer's brand, then the checks a layer's files could break."""


class Refused(SystemExit):
    """A mistake in the layer or the folders: said plainly, before or instead of a half-made template."""


@dataclass(frozen=True)
class Layer:
    folder: Path
    name: str
    languages: list[str]
    default_language: str
    files: list[Path]


def read_layer(layer: Path) -> Layer:
    """The layer's settings and its files, every one checked before anything is written."""
    settings_file = layer / "layer.toml"
    if not settings_file.is_file():
        raise Refused(f"{layer} has no layer.toml")
    settings = tomllib.loads(settings_file.read_text(encoding="utf-8"))
    unknown = sorted(set(settings) - LAYER_KEYS)
    if unknown:
        raise Refused(f"layer.toml has unknown keys: {', '.join(unknown)}; it takes {', '.join(sorted(LAYER_KEYS))}")
    name = settings.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name) or name != name.strip():
        raise Refused("layer.toml: name is up to 60 characters, with no quotes, backslashes or line breaks")
    languages = settings.get("languages")
    if not isinstance(languages, list) or not languages or not all(isinstance(code, str) for code in languages):
        raise Refused('layer.toml: languages is a list of codes, such as ["es"]')
    default_language = settings.get("default_language", "")
    if not isinstance(default_language, str):
        raise Refused("layer.toml: default_language is a code, such as es")
    files = []
    folder = layer / "files"
    for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
        relative = path.relative_to(folder).as_posix()
        if path.is_symlink():
            raise Refused(f"layer file {relative} is a link: a layer holds real files only")
        if path.is_file():
            if not relative.startswith(LAYER_FOLDERS):
                raise Refused(
                    f"layer file {relative} is outside {', '.join(LAYER_FOLDERS)}: what the base holds is changed in "
                    "the base, for every organization"
                )
            files.append(path)
    return Layer(layer, name, languages, default_language, files)


def layer_hash(layer: Layer) -> str:
    """Which layer made the template: the same files give the same hash, on any computer."""
    digest = hashlib.sha256()
    for path in [layer.folder / "layer.toml", *layer.files]:
        digest.update(path.relative_to(layer.folder).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def git(*arguments: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *arguments], capture_output=True, text=True, check=True).stdout


def prepare_out(out: Path) -> None:
    """An empty folder, or a clone of the template's repository with nothing uncommitted: emptied but for .git."""
    if out == ROOT or out.is_relative_to(ROOT) or ROOT.is_relative_to(out):
        raise Refused(f"{out} must be a folder outside the base")
    if not out.exists():
        out.mkdir(parents=True)
        return
    entries = [entry for entry in out.iterdir() if entry.name != ".git"]
    if not (out / ".git").exists():
        if entries:
            raise Refused(f"{out} is neither empty nor a clone of the template's repository: nothing was changed")
        return
    status = subprocess.run(["git", "-C", str(out), "status", "--porcelain"], capture_output=True, text=True)
    if status.returncode != 0 or status.stdout.strip():
        raise Refused(f"{out} has uncommitted changes: commit or discard them first; nothing was changed")
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def export(ref: str | None, out: Path) -> tuple[str, bool]:
    """The base into `out`, at a version or as this folder is: its commit, and whether it had uncommitted changes."""
    if ref is not None:
        commit = git("rev-parse", "--verify", f"{ref}^{{commit}}").strip()
        archive = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", commit], capture_output=True, check=True
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(out, filter="data")
        return commit, False
    if (ROOT / ".git").exists():
        listed = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
        for name in filter(None, listed):
            source = ROOT / name
            if source.is_file():
                (out / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, out / name)
        return git("rev-parse", "HEAD").strip(), bool(git("status", "--porcelain").strip())
    shutil.copytree(ROOT, out, ignore=shutil.ignore_patterns(*NOT_COPIED, ".env", ".env.*"), dirs_exist_ok=True)
    return "unknown", True


def link_or_copy(source: str, target: str) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def run(out: Path, *arguments: str) -> None:
    done = subprocess.run(
        [sys.executable, *arguments], cwd=out, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if done.returncode != 0:
        raise Refused(f"{' '.join(arguments)} failed in {out}:\n{done.stdout[-3000:]}\n{done.stderr[-2000:]}")


def name_it(out: Path, name: str) -> None:
    """The organization's name until an application is given its own: for local work and for a preview."""
    example = out / ".env.example"
    lines = [line for line in example.read_text(encoding="utf-8").splitlines() if not line.startswith("APP_NAME=")]
    position = next((i + 1 for i, line in enumerate(lines) if line.startswith("APP_ENVIRONMENT=")), len(lines))
    lines.insert(position, f'APP_NAME="{name}"')
    example.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    declaration = out / ".eunomai" / "project.toml"
    text = declaration.read_text(encoding="utf-8")
    anchor = 'APP_ENVIRONMENT = "development"\n'
    if anchor not in text:
        raise Refused(f"{declaration} has no {anchor.strip()} line to put the name after")
    declaration.write_text(text.replace(anchor, f'{anchor}APP_NAME = "{name}"\n', 1), encoding="utf-8", newline="\n")


def make(folder: Path, out: Path, ref: str | None, tests: bool) -> None:
    layer = read_layer(folder)
    prepare_out(out)
    commit, changes = export(ref, out)
    if (ROOT / ".cache").is_dir() and not (out / ".cache").exists():  # Tailwind's executable: 100 MB, only read
        shutil.copytree(ROOT / ".cache", out / ".cache", copy_function=link_or_copy)
    languages = ["--languages", ",".join(layer.languages)]
    if layer.default_language:
        languages += ["--default-language", layer.default_language]
    run(out, "tools/remove_demo.py", *languages)
    shutil.rmtree(out / ".github" / "workflows", ignore_errors=True)
    (out / BASE_CI_TESTS).unlink(missing_ok=True)
    if (out / ".github").is_dir() and not any((out / ".github").iterdir()):
        (out / ".github").rmdir()
    for path in layer.files:
        target = out / path.relative_to(folder / "files")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    name_it(out, layer.name)
    for check in CHECKS:
        run(out, *check)
    if tests:
        run(out, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    (out / SOURCE_FILE).write_text(
        "# Made by tools/make_template.py from eunomai-business-app-base: run it again, never edit this template.\n"
        f'base_commit = "{commit}"\n'
        f"base_had_uncommitted_changes = {'true' if changes else 'false'}\n"
        f'layer = "{layer_hash(layer)}"\n',
        encoding="utf-8",
        newline="\n",
    )


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Makes an organization's application template from this base.")
    parser.add_argument("--layer", type=Path, required=True, help="the organization's layer: layer.toml and files/")
    parser.add_argument("--out", type=Path, required=True, help="an empty folder, or a clean clone of the template")
    parser.add_argument("--ref", help="a version of the base, such as a tag; without it, this folder as it is")
    parser.add_argument("--skip-tests", action="store_true", help="leave the template's own tests for its CI")
    options = parser.parse_args(arguments)
    make(options.layer.resolve(), options.out.resolve(), options.ref, not options.skip_tests)
    print(f"Template made in {options.out}: review it there, then commit it through a pull request.")


if __name__ == "__main__":
    main()
