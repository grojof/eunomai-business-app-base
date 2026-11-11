"""An organization's template, made from this base and a layer: what the layer brings, and nothing it may not touch.

The template is made once, as an organization would, with a fictional layer: its own themes, a font, one language and
its CI. These tests go with the demo: the tool works on the base, and an application has nothing to make it from. Its
own suite runs in tests/demo/test_new_module.py, in a template with a generated module.
"""

import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from tests.helpers import ROOT, run_in
from tools import make_template, remove_demo

THEMES = """@plugin "../../tools/tailwind/daisyui-theme.mjs" {
  name: "light";
  default: true;
  --color-primary: #1f4e79;
  --color-primary-content: #ffffff;
}

@plugin "../../tools/tailwind/daisyui-theme.mjs" {
  name: "dark";
  prefersdark: true;
  --color-primary: #9cc3ee;
  --color-primary-content: #0b1f33;
}

@font-face {
  font-family: "Example Sans";
  src: url("/static/brand/fonts/example-sans.woff2") format("woff2");
  font-display: swap;
}

@theme {
  --font-sans: "Example Sans", ui-sans-serif, system-ui, sans-serif;
}
"""
CI = "name: Tests\non: [pull_request]\njobs: {}\n"
FONT = b"wOF2 not a real font, only bytes to serve"


def a_layer(folder: Path, files: dict[str, bytes] | None = None, **settings: object) -> Path:
    values = {"name": "Example Org apps", "languages": ["es"], "default_language": "es", **settings}
    folder.mkdir(parents=True)
    lines = [f"{key} = {json.dumps(value)}" for key, value in values.items()]
    (folder / "layer.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    default = {
        "app/brand/theme.css": THEMES.encode(),
        "app/brand/fonts/example-sans.woff2": FONT,
        ".gitea/workflows/tests.yml": CI.encode(),
    }
    for name, content in (default if files is None else files).items():
        (folder / "files" / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / "files" / name).write_bytes(content)
    return folder


def make(layer: Path, out: Path, *options: str) -> subprocess.CompletedProcess[str]:
    """The tool as an organization runs it, but for the template's own tests, which run below, one kind at a time."""
    return run_in(ROOT, "tools/make_template.py", "--layer", str(layer), "--out", str(out), "--skip-tests", *options)


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    folder = tmp_path_factory.mktemp("template")
    layer, out = a_layer(folder / "layer"), folder / "template"
    result = make(layer, out)
    assert result.returncode == 0, f"{result.stdout[-3000:]} {result.stderr[-3000:]}"
    return layer, out


def test_the_template_is_an_application_with_nothing_of_the_demo_or_the_bases_tools(made):
    _layer, out = made
    assert not (out / "app" / "demo").exists() and not (out / "tests" / "demo").exists()
    assert not (out / "tools" / "make_template.py").exists()
    assert not (out / ".github").exists(), "the base's own workflows maintain the base, not an organization's template"
    assert not (out / "tests" / "test_workflows.py").exists(), "their tests go with them"
    assert not (out / "CHANGELOG.md").exists() and not (out / "SECURITY.md").exists(), "the base's own"
    assert (out / "LICENSE").is_file() and (out / "THIRD-PARTY-NOTICES.md").is_file(), "kept, as their licences ask"
    assert (out / ".gitea" / "workflows" / "tests.yml").read_text(encoding="utf-8") == CI


def test_it_offers_english_and_the_layers_languages_alone(made):
    _layer, out = made
    assert sorted(path.name for path in (out / "locales").iterdir()) == ["es"]
    settings = (out / "app" / "core" / "settings.py").read_text(encoding="utf-8")
    assert 'languages: list[str] = ["en", "es"]' in settings
    assert 'default_language: str = "es"' in settings


def test_it_bears_the_organizations_name_until_an_application_has_its_own(made):
    _layer, out = made
    assert 'APP_NAME="Example Org apps"' in (out / ".env.example").read_text(encoding="utf-8").splitlines()
    preview = tomllib.loads((out / ".eunomai" / "project.toml").read_text(encoding="utf-8"))["preview"]
    assert preview["environment"]["APP_NAME"] == "Example Org apps"
    assert preview["setup"] == [["python", "-m", "app.core.sample_data", "--if-empty"]]


def test_the_stylesheet_carries_both_themes_and_the_font(made):
    _layer, out = made
    built = (out / "app" / "ui" / "static" / "app.css").read_text(encoding="utf-8")
    assert "#9cc3ee" in built.lower() and "prefers-color-scheme" in built
    assert "/static/brand/fonts/example-sans.woff2" in built and "Example Sans" in built


def test_the_font_is_served_by_the_application_under_its_own_policy(made):
    _layer, out = made
    probe = (
        "from fastapi.testclient import TestClient\n"
        "from app.core.settings import Settings\n"
        "from app.main import create_app\n"
        "settings = Settings(environment='development', database_url='sqlite:///unused.db', _env_file=None)\n"
        "response = TestClient(create_app(settings)).get('/static/brand/fonts/example-sans.woff2')\n"
        "print(response.status_code, response.headers['content-type'], response.headers['content-security-policy'])\n"
    )
    result = run_in(out, "-c", probe)
    assert result.returncode == 0, result.stderr[-2000:]
    status, kind, policy = result.stdout.strip().split(" ", 2)
    assert (status, kind) == ("200", "font/woff2")
    assert "font-src 'self'" in policy


def test_it_says_where_it_came_from_so_the_next_update_can_be_compared(made):
    layer, out = made
    source = tomllib.loads((out / make_template.SOURCE_FILE).read_text(encoding="utf-8"))
    assert len(source["base_commit"]) == 40
    assert source["layer"] == make_template.layer_hash(make_template.read_layer(layer))


def test_the_same_base_and_layer_make_the_same_template(made, tmp_path):
    layer, out = made
    again = tmp_path / "again"
    result = make(layer, again)
    assert result.returncode == 0, f"{result.stdout[-3000:]} {result.stderr[-3000:]}"

    def files(folder: Path) -> dict[str, bytes]:
        skipped = {".cache", ".venv", "__pycache__", ".data", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
        return {
            path.relative_to(folder).as_posix(): path.read_bytes()
            for path in folder.rglob("*")
            if path.is_file() and not skipped & set(path.relative_to(folder).parts) and path.suffix != ".db"
        }

    first, second = files(out), files(again)
    assert sorted(first) == sorted(second)
    assert [name for name in first if first[name] != second[name]] == []


@pytest.mark.parametrize(
    ("files", "settings", "said"),
    [
        ({"app/core/settings.py": b"x"}, {}, "outside app/brand/"),
        ({"AGENTS.md": b"x"}, {}, "outside app/brand/"),
        ({}, {"colour": "blue"}, "unknown keys: colour"),
        ({}, {"name": 'Quote " in it'}, "name is up to 60 characters"),
        ({}, {"languages": []}, "languages is a list"),
    ],
)
def test_a_layer_that_reaches_beyond_its_place_is_refused_before_anything_is_written(tmp_path, files, settings, said):
    layer = a_layer(tmp_path / "layer", files, **settings)
    with pytest.raises(make_template.Refused, match=said):
        make_template.read_layer(layer)


def test_a_folder_with_other_files_or_uncommitted_changes_is_left_alone(tmp_path):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(make_template.Refused, match="neither empty nor a clone"):
        make_template.prepare_out(busy)
    clone = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    (clone / "draft.txt").write_text("not committed", encoding="utf-8")
    with pytest.raises(make_template.Refused, match="uncommitted changes"):
        make_template.prepare_out(clone)
    assert (clone / "draft.txt").exists() and (busy / "notes.txt").exists()
    with pytest.raises(make_template.Refused, match="outside the base"):
        make_template.prepare_out(ROOT / "build-here")


def test_a_clean_clone_keeps_its_history_and_loses_the_rest(tmp_path):
    clone = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    (clone / "old.txt").write_text("from the last template", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(clone), "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "x"],
        check=True,
    )
    make_template.prepare_out(clone)
    assert [entry.name for entry in clone.iterdir()] == [".git"]


@pytest.mark.parametrize(
    ("languages", "default", "said"),
    [
        ("fr", None, "Not: fr"),
        ("en", None, "Not: nothing"),
        ("es", "ca", "must be en or one of"),
        (None, "es", "needs"),
    ],
)
def test_languages_that_cannot_be_kept_are_refused_before_the_demo_goes(languages, default, said):
    with pytest.raises(SystemExit, match=said):
        remove_demo.chosen_languages(languages, default)


def test_the_languages_kept_and_the_default_are_read_from_the_options():
    assert remove_demo.chosen_languages(None, None) is None
    assert remove_demo.chosen_languages("es", None) == (["es"], "en")
    assert remove_demo.chosen_languages("en, ca,ca", "ca") == (["ca"], "ca")
