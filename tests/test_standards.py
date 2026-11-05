"""The standards keep their promises: each rule has a source and a check, and the code follows the mechanical ones."""

import json
import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests import classes
from tests.conftest import build_settings
from tests.helpers import ROOT
from tools import vendor

STANDARDS = ROOT / "docs" / "base" / "standards.md"
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


def test_every_check_is_automatic_manual_or_planned():
    for row in rules():
        assert re.fullmatch(r"Automatic|By hand|Milestone \d", row["check"]), row["id"]


def test_templates_use_no_invented_colours_or_sizes():
    for template in (ROOT / "app").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert re.findall(r"[\w:-]+-\[[^\]]*\]|[\s\"':]\[[a-zA-Z-]+:[^\]\s]+\]", text) == [], template


def kind_of_page(address: str) -> tuple[str, tuple[str, ...]]:
    """A page and the parameters it is asked with, whatever their values: `/calendar?date=…` is one kind of page, not
    one per week. A link to the next week leads to another next week, and a crawl that followed them never ended."""
    parts = urlsplit(address)
    return parts.path, tuple(sorted({name for name, _value in parse_qsl(parts.query, keep_blank_values=True)}))


def crawled_classes() -> set[str]:
    """Every class on every kind of page a person can reach, found by following the links from the start page."""
    application = create_app(build_settings())
    client = TestClient(application, raise_server_exceptions=False)
    person = {"X-Remote-User": "demo.person", "X-Remote-Groups": "admins"}
    found, _links = classes.read_page(client.get("/").text)  # a stranger's page
    found |= classes.read_page(client.get("/missing-page", headers=person).text)[0]
    waiting, seen = ["/"], set()
    while waiting:
        path = waiting.pop()
        if kind_of_page(path) in seen:
            continue
        seen.add(kind_of_page(path))
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


def test_the_crawl_visits_each_kind_of_page_once_whatever_the_values():
    assert kind_of_page("/calendar?date=2026-11-02&view=week") == kind_of_page("/calendar?view=month&date=2031-01-06")
    assert kind_of_page("/calendar") != kind_of_page("/calendar?date=2026-11-02")
    assert kind_of_page("/equipment?status=") == ("/equipment", ("status",))


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
    assert classes.misplaced_in(ROOT / "app") == {}


@pytest.mark.rule("COMP-04")
def test_the_check_for_misplaced_classes_finds_one():
    assert classes.misplaced_classes('STYLE = "btn-primary shadow"\n', python=True) == {"btn-primary"}
    assert classes.misplaced_classes('element.className = "badge-error";', python=False) == {"badge-error"}


@pytest.mark.rule("COMP-04")
def test_the_check_for_misplaced_classes_does_not_depend_on_the_order_of_the_folder(tmp_path):
    """Keyed by name, only the last `__init__.py` read would count, and each computer reads them in its own order."""
    application = tmp_path / "vendor" / "app"
    for name, text in (("a", ""), ("b", 'STYLE = "btn-primary"\n'), ("c", "")):
        (application / name).mkdir(parents=True)
        (application / name / "__init__.py").write_text(text, encoding="utf-8")
    (application / "a" / "own.js").write_text('element.className = "badge-error";', encoding="utf-8")
    (application / "vendor").mkdir()
    (application / "vendor" / "theirs.js").write_text('element.className = "badge-error";', encoding="utf-8")
    assert classes.misplaced_in(application) == {"a/own.js": {"badge-error"}, "b/__init__.py": {"btn-primary"}}


@pytest.mark.rule("COMP-04")
def test_an_icons_name_is_not_a_misplaced_class(monkeypatch):
    assert classes.misplaced_classes('ICON = "btn-arrow"\n', python=True) == {"btn-arrow"}
    monkeypatch.setattr(classes, "ICONS", {"btn-arrow"})
    assert classes.misplaced_classes('ICON = "btn-arrow"\n', python=True) == set()


@pytest.mark.rule("COMP-04")
def test_an_icon_named_like_a_daisyui_class_is_still_caught_as_a_class():
    """Lucide has an icon called `badge-info`, which is also daisyUI's class: in Python it would get no CSS."""
    assert (ROOT / "app" / "ui" / "templates" / "ui" / "icons" / "badge-info.svg").exists()
    assert classes.misplaced_classes('KIND = "badge-info"\n', python=True) == {"badge-info"}
    assert classes.misplaced_classes('ICON = "calendar-range"\n', python=True) == set()


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
