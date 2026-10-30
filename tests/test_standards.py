"""The standards keep their promises: each rule has a source and a check, and the code follows the mechanical ones."""

import json
import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests import classes
from tests.conftest import build_settings
from tests.helpers import ROOT, repository_copy, run_in
from tools import remove_demo, vendor

STANDARDS = ROOT / "docs" / "standards.md"
ROW = re.compile(r"^\| (?P<id>[A-Z0-9]+-\d{2}) \| (?P<rule>.+?) \| (?P<source>.+?) \| (?P<check>.+?) \|$", re.M)
ROW_START = re.compile(r"^\|\s*[A-Z][A-Z0-9]*-\d+\s*\|")
WITH_DEMO = (ROOT / "tests" / "demo").exists()
PLUGINS = ("-p", "tests.rule_report", "-p", "no:cacheprovider")
CSS = (ROOT / "app" / "ui" / "static" / "app.css").read_text(encoding="utf-8")


def rules() -> list[re.Match[str]]:
    return list(ROW.finditer(STANDARDS.read_text(encoding="utf-8")))


def malformed_rows(text: str) -> list[str]:
    return [line for line in text.splitlines() if ROW_START.match(line) and not ROW.fullmatch(line)]


def collected_rules(*paths: str) -> dict[str, list[str]]:
    """Each rule with the tests that name it, from pytest's own collection: a comment or a string cannot pass as one."""
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / "rules.json"
        subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-c", "pyproject.toml", *PLUGINS, *paths],
            cwd=ROOT,
            env=os.environ | {"RULE_REPORT": str(report)},
            check=True,
            capture_output=True,
        )
        found: dict[str, list[str]] = {}
        for test, rule in json.loads(report.read_text(encoding="utf-8")):
            found.setdefault(rule, []).append(test)
    return found


@lru_cache
def traced() -> dict[str, list[str]]:
    return collected_rules("tests")


def test_every_rule_has_a_source_or_says_it_is_a_project_decision():
    assert len(rules()) > 30
    for row in rules():
        assert "](http" in row["source"] or row["source"] == "Project decision", row["id"]


def test_rule_identifiers_are_unique():
    identifiers = [row["id"] for row in rules()]
    assert len(identifiers) == len(set(identifiers))


def test_every_row_that_looks_like_a_rule_is_read_as_one():
    assert malformed_rows(STANDARDS.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "line",
    [
        "| A11Y-99 | A rule | Project decision |",
        "| A11Y-9 | A rule | Project decision | By hand |",
        "|SEC-99| A | B | C |",
    ],
)
def test_a_row_that_does_not_parse_is_caught(line):
    assert malformed_rows(line) == [line]


def test_every_automatic_rule_has_a_test_and_every_test_a_rule():
    declared = {row["id"] for row in rules() if row["check"] == "Automatic"}
    tested = set(traced())
    assert declared - tested == set(), "declared automatic, but no test proves it"
    assert tested - {row["id"] for row in rules()} == set(), "a test names a rule that does not exist"
    assert tested - declared == set(), "tested, but the rule does not say so"


def test_a_comment_or_a_string_does_not_count_as_a_test(tmp_path):
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n\n"
        '# @pytest.mark.rule("AAA-01")\n'
        "TEXT = '@pytest.mark.rule(\"AAA-02\")'\n\n\n"
        '@pytest.mark.rule("AAA-03")\n'
        "def test_real():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert set(collected_rules(str(tmp_path))) == {"AAA-03"}


@pytest.mark.skipif(not WITH_DEMO, reason="this compares the demo's tests with the others")
def test_the_rules_proved_only_on_demo_screens_are_exactly_the_listed_ones():
    only_on_demo = {rule for rule, tests in traced().items() if all(t.startswith("tests/demo/") for t in tests)}
    assert only_on_demo == remove_demo.ONLY_ON_DEMO


def test_every_check_is_automatic_manual_or_planned():
    for row in rules():
        assert re.fullmatch(r"Automatic|By hand|Milestone \d", row["check"]), row["id"]


def test_templates_use_no_invented_colours_or_sizes():
    for template in (ROOT / "app").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert re.findall(r"[\w:-]+-\[[^\]]*\]|[\s\"':]\[[a-zA-Z-]+:[^\]\s]+\]", text) == [], template


def crawled_classes() -> set[str]:
    """Every class on every page a person can reach, found by following the links from the start page."""
    application = create_app(build_settings())
    client = TestClient(application, raise_server_exceptions=False)
    person = {"X-Remote-User": "demo.person", "X-Remote-Groups": "admins"}
    found, _links = classes.read_page(client.get("/").text)  # a stranger's page
    found |= classes.read_page(client.get("/missing-page", headers=person).text)[0]
    waiting, seen = ["/"], set()
    while waiting:
        path = waiting.pop()
        if path in seen:
            continue
        seen.add(path)
        page_classes, links = classes.read_page(client.get(path, headers=person).text)
        found |= page_classes
        waiting += [link.split("#")[0] for link in links if link.startswith("/") and not link.startswith("/static")]
    assert len(seen) >= (10 if WITH_DEMO else 1)
    return found


def shell_classes() -> set[str]:
    """The shell draws different classes in each arrangement."""
    arrangements = [{"layout_navigation": navigation} for navigation in ("side", "compact", "top", "hidden")] + [
        {"layout_sticky_header": False, "layout_width": "centered", "layout_density": "compact"}
    ]
    found: set[str] = set()
    person = {"X-Remote-User": "demo.person"}
    for settings in arrangements:
        client = TestClient(create_app(build_settings(**settings)))
        found |= classes.read_page(client.get("/", headers=person).text)[0]
    return found


def template_classes() -> set[str]:
    """Every class in a class attribute, with literals inside {{ ... }}: a branch no page happens to show."""
    found: set[str] = set()
    for template in (ROOT / "app").rglob("*.html"):
        text = re.sub(r"\{#.*?#\}", "", template.read_text(encoding="utf-8"), flags=re.S)
        for attribute in re.findall(r'class="((?:[^"{]|\{\{.*?\}\}|\{%.*?%\}|\{)*)"', text, re.S):
            expressions = re.findall(r"\{[{%].*?[%}]\}", re.sub(r"==\s*'[^']*'", "", attribute), re.S)
            literals = [word for expression in expressions for word in re.findall(r"'([^']*)'", expression)]
            plain = re.sub(r"\{[{%].*?[%}]\}", " ", attribute, flags=re.S)
            found |= set(" ".join([plain, *literals]).split())
    return found


def every_class() -> set[str]:
    sources = [template.read_text(encoding="utf-8") for template in (ROOT / "app").rglob("*.html")]
    return (
        crawled_classes()
        | shell_classes()
        | template_classes()
        | classes.template_literals(sources)
        | classes.catalogue_classes()
    )


@pytest.mark.rule("COMP-04")
def test_every_class_in_use_really_exists():
    assert classes.invented(every_class(), CSS) == set()


@pytest.mark.rule("COMP-04")
def test_no_class_smuggles_in_a_value():
    assert classes.invented_values(every_class()) == set()


@pytest.mark.rule("COMP-04")
def test_the_class_check_catches_an_invented_class_on_a_page():
    found, _links = classes.read_page('<a class="btn btn-invented" href="/">Go</a>')
    assert classes.invented(found, ".btn{color:var(--a)}") == {"btn-invented"}


@pytest.mark.rule("COMP-04")
@pytest.mark.parametrize(
    ("css", "name"),
    [
        (r".\32 xl\:flex{display:flex}", "2xl:flex"),
        (r"@media (hover:hover){.hover\:bg-base-200:hover{color:red}}", "hover:bg-base-200"),
        (r".w-1\/2{width:50%}", "w-1/2"),
        (r".\[color\:\#ff0000\]{color:#ff0000}", "[color:#ff0000]"),
        (".card{color:red;.nested{color:blue}}", "nested"),
        (":where(.menu>li){color:red}", "menu"),
    ],
)
def test_the_class_check_reads_a_stylesheet_correctly(css, name):
    assert name in classes.defined_classes(css)


@pytest.mark.rule("COMP-04")
def test_the_class_check_does_not_count_values_as_classes():
    css = '.btn{width:.125rem;margin:1.5rem}@keyframes x{.5%{top:0}}.a[title=".quoted"]{top:0}/* .comment{} */'
    assert classes.defined_classes(css) == {"btn", "a"}


@pytest.mark.rule("COMP-04")
def test_the_real_stylesheet_reads_without_junk():
    defined = classes.defined_classes(CSS)
    assert {"btn", "menu"} <= defined
    assert not any(re.fullmatch(r"\d.*(?:rem|px|em|%)", name) for name in defined)


@pytest.mark.rule("COMP-04")
def test_literals_in_sets_and_macro_arguments_are_read():
    source = """
    {% macro box(size="size-default", label="") %}<div class="box {{ size }}" title="{{ label }}"></div>{% endmacro %}
    {% set kinds = {"info": "alert-invented"} %}
    {% set compact = layout == "not-a-class" %}
    {{ box("size-invented", label="not-a-class-either") }}
    """
    assert classes.template_literals([source]) == {"size-default", "alert-invented", "size-invented"}


@pytest.mark.rule("COMP-04")
@pytest.mark.parametrize("name", ["bg-[#ff0000]", "text-[13px]", "[color:#ff0000]", "hover:[color:#ff0000]"])
def test_an_invented_value_is_refused(name):
    assert classes.invented_values([name]) == {name}


@pytest.mark.rule("COMP-04")
@pytest.mark.parametrize("name", ["btn", "2xl:flex", "w-1/2", "hover:bg-base-200"])
def test_a_plain_class_is_not_an_invented_value(name):
    assert classes.invented_values([name]) == set()


@pytest.mark.rule("COMP-04")
def test_no_class_lives_where_tailwind_does_not_look():
    """Tailwind reads templates and catalog.py. A class elsewhere would get no CSS, however real it looks."""
    found = {}
    for source in (ROOT / "app").rglob("*.py"):
        if source.name != "catalog.py":
            found[source.name] = classes.misplaced_classes(source.read_text(encoding="utf-8"), python=True)
    for script in (ROOT / "app").rglob("*.js"):
        if "vendor" not in script.parts:
            found[script.name] = classes.misplaced_classes(script.read_text(encoding="utf-8"), python=False)
    assert {name: words for name, words in found.items() if words} == {}


@pytest.mark.rule("COMP-04")
def test_the_check_for_misplaced_classes_finds_one():
    assert classes.misplaced_classes('STYLE = "btn-primary shadow"\n', python=True) == {"btn-primary"}
    assert classes.misplaced_classes('element.className = "badge-error";', python=False) == {"badge-error"}


def test_colours_live_only_in_the_brand():
    for source in (ROOT / "app" / "ui" / "styles").rglob("*.css"):
        assert re.findall(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl|oklch)a?\(", source.read_text(encoding="utf-8")) == []


def test_tailwinds_own_palette_does_not_exist():
    css = (ROOT / "app" / "ui" / "styles" / "app.css").read_text(encoding="utf-8")
    assert "--color-*: initial" in css
    built = (ROOT / "app" / "ui" / "static" / "app.css").read_text(encoding="utf-8")
    assert "--color-blue-500" not in built


def test_no_page_loads_anything_from_another_server():
    for template in (ROOT / "app").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(r"""(?:src|href)=["'](?:https?:)?//""", text), template


@pytest.mark.rule("SEC-10")
def test_vendored_files_match_their_recorded_hash():
    assert vendor.check() == []


def test_scripts_carry_their_integrity(client, person):
    html = client.get("/", headers=person).text
    assert re.search(r'htmx\.min\.js" integrity="sha384-[\w+/=]+"', html)


def test_the_core_never_imports_the_demo():
    for source in (ROOT / "app" / "core").rglob("*.py"):
        assert "app.demo" not in source.read_text(encoding="utf-8").replace("Nothing here imports from app.demo", "")


@pytest.mark.skipif(bool(os.environ.get("BASE_WITHOUT_DEMO")), reason="runs once, on the full repository")
def test_the_whole_base_works_with_the_demo_deleted(tmp_path):
    copy = repository_copy(tmp_path / "application")
    removed = run_in(copy, "tools/remove_demo.py")
    assert removed.returncode == 0, removed.stderr

    assert not (copy / "app" / "demo").exists()
    assert "install_demo" not in (copy / "app" / "main.py").read_text(encoding="utf-8")
    assert "demo-admins" not in (copy / ".env.example").read_text(encoding="utf-8")
    for changed in ("app/main.py", ".env.example", "docs/standards.md"):
        assert b"\r\n" not in (copy / changed).read_bytes(), changed
    rows = {
        row["id"]: row["check"] for row in ROW.finditer((copy / "docs" / "standards.md").read_text(encoding="utf-8"))
    }
    assert {rows[rule] for rule in remove_demo.ONLY_ON_DEMO} == {"By hand"}

    assert not (copy / "tools" / "tailwind" / "daisyui-docs.json").exists()
    assert "daisyui-docs" not in (copy / "vendor.json").read_text(encoding="utf-8")
    assert not (copy / "app" / "ui" / "static" / "placeholders").exists()
    assert "/* demo */" not in (copy / "app" / "ui" / "styles" / "app.css").read_text(encoding="utf-8")

    sources = [*(copy / "app").rglob("*.html"), *(copy / "app").rglob("*.py")]
    shell = "".join(path.read_text(encoding="utf-8") for path in sources)
    icons = copy / "app" / "ui" / "templates" / "ui" / "icons"
    assert [icon.stem for icon in icons.glob("*.svg") if f'"{icon.stem}"' not in shell] == []

    for command in (
        ["tools/css.py"],
        ["tools/css.py", "check"],
        ["tools/components.py", "check"],
        ["tools/gallery.py", "check"],
        ["tools/translations.py", "check"],
        ["tools/vendor.py", "check"],
        ["-m", "pytest", "-q", "-x"],
    ):
        result = run_in(copy, *command)
        assert result.returncode == 0, f"{command}: {result.stdout[-2000:]} {result.stderr[-1000:]}"
    built = copy / "app" / "ui" / "static" / "app.css"
    assert built.stat().st_size < (ROOT / "app" / "ui" / "static" / "app.css").stat().st_size * 0.75
    assert "example-preview" not in built.read_text(encoding="utf-8")
