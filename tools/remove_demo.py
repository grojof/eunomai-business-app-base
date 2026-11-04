"""Turns a clone into a clean application, once: deletes the demo and what only the demo needs, makes AGENTS.md describe
an application, and gives it a README of its own, while the base's documentation stays in docs/base/. Then run
tools/css.py, and write what the application is at the top of AGENTS.md and README.md.

uv run --frozen python tools/remove_demo.py
uv run --frozen python tools/remove_demo.py --languages es          # keeps Spanish alone; English is always there
uv run --frozen python tools/remove_demo.py --languages es,ca --default-language ca
"""

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_LANGUAGE = "en"
"""The language of the code's texts: it has no folder under locales/, and every application offers it."""
SETTINGS_LANGUAGES = 'languages: list[str] = ["en", "es", "ca"]'
SETTINGS_DEFAULT_LANGUAGE = 'default_language: str = "en"'
ONLY_ON_DEMO = {"A11Y-09", "COMP-03", "DATA-07", "USE-03"}
"""Rules whose only proof is a demo screen. Without the demo nothing proves them automatically, so they stop saying so:
they become `By hand` until the application has a screen, and a test, of its own. A test keeps this set exact."""
DEMO_MIGRATIONS = "*_demo_*.py"
AGENTS_CHANGES = (
    (
        """# AGENTS.md — eunomai-business-app-base

For anyone working in this repository, person or AI assistant. The repository is in English and names no organization,
person or real system: it stays neutral so anyone can clone it.
""",
        """# AGENTS.md

For anyone working in this repository, person or AI assistant.

## What this application is

Not written yet. Whoever owns this application says here, in a few lines, what it does, for whom, and which real systems
it reads or writes. It belongs to its organization: its names, its systems and its real work belong in it.

## Documentation

- This application's documentation is [README.md](README.md) and its own pages in `docs/`, outside `docs/base/`, in
  the application's documentation language. The README is a map: what the application is, for whom and why, how to
  run it, and a link to every page.
- `docs/base/` is how the base works: read it to build, never edit it, since an update of the template replaces it. Link
  to it instead of restating it: one fact, one home.
- When behaviour changes, update the README and the page it affects in the same change. A new page gets its link in
  the README's index.
- Each page of the application's own starts with frontmatter: `type` (`tutorial`, `how-to`, `reference`,
  `explanation` or `decision`), `title` and `description`. `tests/test_docs.py` checks it, and every link.
""",
    ),
    ("| Never imports from `app/demo/` |", "| Never imports from the application's own folders |"),
    (
        "| `app/demo/` | Demo screens, models, generated data, the gallery and their translations | "
        "Deleting it leaves a working application |\n",
        "| `app/<your-folder>/` | This application's screens, models and their translations | "
        "Installed from `app/main.py` |\n",
    ),
    (
        "`app/ui/catalog.py`, then run `tools/components.py`. `app/demo/examples/` is generated too, from daisyUI's "
        "documentation:\nnever edit it, run `tools/gallery.py`. To see a component live, open `/gallery/<name>` in the "
        "demo.\n",
        "`app/ui/catalog.py`, then run `tools/components.py`.\n",
    ),
    (
        """screens call `button`, not a raw `.btn`. daisyUI's examples in
  the gallery are reference material, not a model for a screen. After changing templates, run
""",
        """screens call `button`, not a raw `.btn`. After changing templates, run
""",
    ),
    ("- A new component needs its page in the demo and its tests,", "- A new component needs its tests,"),
    ("and no real people or companies in demo data.", "and no real people's data in tests or examples."),
    (
        "uv run --frozen python tools/gallery.py check        "
        "# generated from daisyUI's documentation: tools/gallery.py\n",
        "",
    ),
    (
        """Everything
but the browser tests, in two commands that each fit; if one is cut, split it by file:

```bash
uv run --frozen pytest -q -m "not browser" --ignore=tests/demo
uv run --frozen pytest -q -m "not browser" tests/demo
```

"""
        "- `tests/demo/test_clean_application.py`, `tests/demo/test_template.py` and `tests/demo/test_new_module.py` "
        "need\n  Tailwind's executable, which `tools/css.py` downloads to `.cache/`. Without it and without network, "
        "add an\n  `--ignore=` for each and say so.\n",
        """Everything
but the browser tests, which fits; if it is cut, split it by file:

```bash
uv run --frozen pytest -q -m "not browser"
```

""",
    ),
)
"""What changes in AGENTS.md: the base describes a neutral demo, and an application is neither of those."""
APPLICATION_README = """# Not named yet

Not written yet: what this application does, in one or two sentences a person who has never seen it understands.

**For whom:** not written yet.

**Why:** not written yet: what it replaces or makes possible.

<!-- A diagram helps when a picture tells it better: the people, the application and the systems it reads or writes,
as a Mermaid flowchart. -->

<a id="run-it"></a>

## Try it

Needs [uv](https://docs.astral.sh/uv/). A copy of `.env.example` gives a fake identity for local work.

```bash
cp .env.example .env
uv run --frozen python -m app.core.sample_data --if-empty   # the migrations, then each module's made-up rows
uv run --frozen uvicorn app.main:app --reload --no-proxy-headers
```

Keep `--no-proxy-headers`: without it, Uvicorn replaces the proxy's address with the one in `X-Forwarded-For`, the
address stops being trusted, and everyone gets 401. Without `.env` the application refuses to start, because production
is the default and production never runs on SQLite.

The tests, and every other check, are in [AGENTS.md](AGENTS.md#checks):

```bash
uv run --frozen python tools/test.py --affected   # what the changes against main can break
uv run --frozen python tools/test.py              # every test, in parallel
```

## Documentation

| Page | What it contains |
|---|---|
| [How the base works](docs/base/specification.md) | The base this application is built on: its data, components, \
layouts and how it is adapted. A reference, kept as it is |

How to work in this repository: [AGENTS.md](AGENTS.md).
"""
"""An application's README, replacing the base's: a map of the application, with places to fill in. Each page the
application adds to docs/ gets a row in its table."""
DEMO_TESTS = (
    '["pytest", "-q", "--ignore=tests/demo/test_clean_application.py", "--ignore=tests/demo/test_template.py", '
    '"--ignore=tests/demo/test_new_module.py"]'
)
DEMO_TESTS_WHY = "those download Tailwind, so CI runs them"
PREVIEW_CHANGES = (
    (
        'setup = [["python", "-m", "app.demo.generate", "--if-empty"]]',
        'setup = [["python", "-m", "app.core.sample_data", "--if-empty"]]',
    ),
    ("demo-admins", "admins"),
    (f"run = {DEMO_TESTS}  # {DEMO_TESTS_WHY}", 'run = ["pytest", "-q"]'),
)
"""The base's generated rows go with the demo: the migrations, then each module's own sample data, are what an
application's first run needs. Nor is there a demo test that downloads."""
ONLY_FOR_THE_BASE = ("tools/make_template.py",)
"""Tools that work on the base and its demo, and have nothing to do in an application."""


def rewrite(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def changed(path: Path, changes: tuple[tuple[str, str], ...]) -> None:
    """A base can have edited the file: what is not there is said, and the rest of the step still happens."""
    text = path.read_text(encoding="utf-8")
    for old, new in changes:
        if old in text:
            text = text.replace(old, new)
        else:
            print(f"{path.name}: not found, so change it by hand: {old.splitlines()[0]}")
    rewrite(path, text)


def chosen_languages(languages: str | None, default: str | None) -> tuple[list[str], str] | None:
    """The folders under locales/ to keep and the default language, or None to keep every language as it is.
    Checked before anything changes, so a mistake leaves the copy whole."""
    if languages is None:
        if default is not None:
            raise SystemExit("--default-language needs --languages")
        return None
    folders = {path.name for path in (ROOT / "locales").iterdir() if path.is_dir()}
    asked = [code.strip() for code in languages.split(",") if code.strip()]
    kept = [code for code in dict.fromkeys(asked) if code != SOURCE_LANGUAGE]
    unknown = [code for code in kept if code not in folders]
    if not kept or unknown:
        raise SystemExit(
            f"--languages takes one or more codes with a folder under locales/ ({', '.join(sorted(folders))}); "
            f"{SOURCE_LANGUAGE} is always offered. Not: {', '.join(unknown) or 'nothing'}. Nothing was changed."
        )
    chosen = default or SOURCE_LANGUAGE  # the last resort only: a browser's own languages come first
    if chosen not in (SOURCE_LANGUAGE, *kept):
        raise SystemExit(f"--default-language must be {SOURCE_LANGUAGE} or one of --languages. Nothing was changed.")
    return kept, chosen


def keep_languages(kept: list[str], default: str) -> None:
    """Every other folder under locales/ goes, and the settings offer English and those, with that default."""
    for folder in (ROOT / "locales").iterdir():
        if folder.is_dir() and folder.name not in kept:
            shutil.rmtree(folder)
    changed(
        ROOT / "app" / "core" / "settings.py",
        (
            (SETTINGS_LANGUAGES, f"languages: list[str] = {json.dumps([SOURCE_LANGUAGE, *kept])}"),
            (SETTINGS_DEFAULT_LANGUAGE, f'default_language: str = "{default}"'),
        ),
    )


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Deletes the demo, once, and leaves a clean application.")
    parser.add_argument("--languages", help="the languages to keep besides English, comma-separated, such as es,ca")
    parser.add_argument("--default-language", help="the last resort when a browser asks for none of them")
    options = parser.parse_args(arguments)
    if not (ROOT / "app" / "demo").exists():
        raise SystemExit("There is no demo here: this is an application already, and nothing was changed.")
    languages = chosen_languages(options.languages, options.default_language)

    for folder in (ROOT / "app" / "demo", ROOT / "tests" / "demo", ROOT / "app" / "ui" / "static" / "placeholders"):
        if folder.exists():
            shutil.rmtree(folder)
    for tool in ONLY_FOR_THE_BASE:
        (ROOT / tool).unlink(missing_ok=True)
    if languages is not None:
        keep_languages(*languages)
    # Lucide's icons stay whole, as vendor.json pins them, and so do the organization's: any screen may use any of them.

    # These migrations hold only the demo's tables. The tooling stays, and the application's own starts from zero.
    for migration in (ROOT / "migrations" / "versions").glob(DEMO_MIGRATIONS):
        migration.unlink()

    for source in (ROOT / "app" / "main.py", ROOT / "migrations" / "env.py"):
        lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
        rewrite(source, "".join(line for line in lines if not line.rstrip().endswith("# demo")))

    stylesheet = ROOT / "app" / "ui" / "styles" / "app.css"
    lines = stylesheet.read_text(encoding="utf-8").splitlines(keepends=True)
    rewrite(stylesheet, "".join(line for line in lines if not line.rstrip().endswith("/* demo */")))

    # The gallery's source. tools/gallery.py stays, with nothing to do, so the update workflow needs no second form.
    (ROOT / "tools" / "tailwind" / "daisyui-docs.json").unlink(missing_ok=True)
    vendored = ROOT / "vendor.json"
    entries = json.loads(vendored.read_text(encoding="utf-8"))
    entries.pop("daisyui-docs", None)
    rewrite(vendored, json.dumps(entries, indent=2) + "\n")

    example = ROOT / ".env.example"
    rewrite(example, example.read_text(encoding="utf-8").replace("demo-admins", "admins"))

    standards = ROOT / "docs" / "base" / "standards.md"
    if standards.exists():
        text = standards.read_text(encoding="utf-8")
        for rule in sorted(ONLY_ON_DEMO):
            text = re.sub(rf"^(\| {rule} \|.*\| )Automatic( \|)$", r"\1By hand\2", text, flags=re.M)
        rewrite(standards, text)

    changed(ROOT / "AGENTS.md", AGENTS_CHANGES)
    changed(ROOT / ".eunomai" / "project.toml", PREVIEW_CHANGES)
    # The base's README describes the base; docs/base/ keeps that, and the application starts its own map.
    rewrite(ROOT / "README.md", APPLICATION_README)


if __name__ == "__main__":
    main()
