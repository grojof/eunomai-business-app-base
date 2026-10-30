"""The catalogue and its documentation stay complete, in step with daisyUI and readable by an assistant."""

import json
import os
import re

import pytest

from app.core.templating import environment
from app.ui import catalog
from app.ui.catalog import Component
from tests.helpers import ROOT, repository_copy, run_in
from tools import components

PAGES = ROOT / "docs" / "components"
OFFICIAL = set(components.sections(components.SOURCE.read_text(encoding="utf-8")))
GENERATED_FRONTMATTER = (
    r'---\ntype: reference\ntitle: ".+"\ndescription: ".+"\ntags: \[component, [a-z-]+, [a-z]+\]\n---\n'
)
SMALL_FILE = """\
## daisyUI 5 usage rules
Use it well.

### Enable and apply themes
Themes.

## daisyUI components

### alpha
The first component.

[alpha documentation](https://daisyui.com/components/alpha/)

#### Class names
- component: `alpha`

## A section that came later
It belongs to no component.
"""
OWN_PAGE = """\
---
type: reference
title: Signature
description: Signs a document.
tags: [component, own, available]
---

# Signature

A hand-written page.
"""


@pytest.fixture
def small(tmp_path, monkeypatch):
    """The generator on a tiny official file with one component, writing to an empty folder."""
    source = tmp_path / "llms.txt"
    source.write_text(SMALL_FILE, encoding="utf-8")
    pages = tmp_path / "pages"
    pages.mkdir()
    monkeypatch.setattr(components, "SOURCE", source)
    monkeypatch.setattr(components, "TARGET", pages)
    monkeypatch.setattr(components, "CATEGORIES", {"one": ("One", (Component("alpha"),))})
    return pages


@pytest.mark.rule("COMP-01")
def test_every_official_component_is_in_the_catalogue():
    assert OFFICIAL <= set(catalog.components())


@pytest.mark.rule("COMP-01")
def test_anything_else_in_the_catalogue_is_a_page_written_by_hand():
    for name in set(catalog.components()) - OFFICIAL:
        assert components.MARKER not in (PAGES / f"{name}.md").read_text(encoding="utf-8"), name


@pytest.mark.rule("COMP-01")
def test_the_pages_match_the_official_file_and_the_catalogue():
    for name, content in components.generate().items():
        assert (PAGES / name).read_text(encoding="utf-8") == content, f"run tools/components.py: {name}"


@pytest.mark.rule("COMP-02")
@pytest.mark.parametrize("name", sorted(catalog.components()))
def test_every_page_has_frontmatter_and_a_description(name):
    text = (PAGES / f"{name}.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert components.description_of(text)


@pytest.mark.rule("COMP-02")
@pytest.mark.parametrize("name", sorted(OFFICIAL))
def test_every_generated_page_has_its_status_and_this_repositorys_rules(name):
    text = (PAGES / f"{name}.md").read_text(encoding="utf-8")
    assert re.match(GENERATED_FRONTMATTER, text)
    assert f"**Status:** {catalog.components()[name].status}." in text
    assert "This repository's rules come first." in text
    assert "## Class names" in text


@pytest.mark.rule("COMP-02")
def test_a_component_with_problems_says_why():
    for component in catalog.components().values():
        assert bool(component.note) == (component.status == catalog.PROBLEMS), component.name


def test_the_catalogue_can_be_read_by_a_program():
    entries = json.loads((PAGES / "catalog.json").read_text(encoding="utf-8"))
    assert {entry["name"] for entry in entries} == set(catalog.components())
    for entry in entries:
        assert (ROOT / entry["page"]).exists()
        assert entry["use"]


def test_an_organizations_own_component_keeps_its_hand_written_page(tmp_path, monkeypatch):
    own = tmp_path / "signature.md"
    own.write_text(OWN_PAGE, encoding="utf-8")
    categories = {**catalog.CATEGORIES, "own": ("Own", (Component("signature"),))}
    monkeypatch.setattr(components, "CATEGORIES", categories)
    monkeypatch.setattr(components, "TARGET", tmp_path)
    pages = components.generate()
    assert "signature.md" not in pages
    assert "Signs a document." in pages["README.md"]


def test_a_component_with_no_page_stops_the_generator(tmp_path, monkeypatch):
    categories = {**catalog.CATEGORIES, "own": ("Own", (Component("signature"),))}
    monkeypatch.setattr(components, "CATEGORIES", categories)
    monkeypatch.setattr(components, "TARGET", tmp_path)
    with pytest.raises(ValueError, match="signature"):
        components.generate()


def test_a_section_after_the_components_stays_out_of_the_last_one():
    assert "A section that came later" not in components.sections(SMALL_FILE)["alpha"]


def test_the_rules_must_come_before_their_end():
    backwards = "### Enable and apply themes\nThemes.\n\n## daisyUI 5 usage rules\nUse it well.\n"
    with pytest.raises(ValueError, match="order"):
        components.rules(backwards)


def test_a_component_that_opens_with_a_heading_has_no_description():
    with pytest.raises(ValueError, match="alpha: no description"):
        components.page("alpha", "one", "available", "", "alpha\n\n#### Class names\n- component: `alpha`\n")


def test_a_generated_page_left_behind_stops_the_generator(small):
    (small / "alpha.md").write_text(components.page("alpha", "one", "available", "", "alpha\nOld.\n"), encoding="utf-8")
    (small / "gone.md").write_text(components.page("gone", "one", "available", "", "gone\nOld.\n"), encoding="utf-8")
    with pytest.raises(ValueError, match=r"gone\.md: generated, but its component left"):
        components.generate()


def test_a_page_written_by_hand_is_never_overwritten_by_an_official_name(small):
    written = '---\ndescription: "Mine."\n---\n'
    (small / "alpha.md").write_text(written, encoding="utf-8")
    with pytest.raises(ValueError, match=r"alpha\.md: written by hand"):
        components.generate()
    assert (small / "alpha.md").read_text(encoding="utf-8") == written


def test_a_new_official_component_stops_the_generator(small):
    components.SOURCE.write_text(
        SMALL_FILE.replace(
            "## A section", "### beta\nB.\n\n[beta documentation](https://daisyui.com/components/beta/)\n\n## A section"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="beta"):
        components.generate()


def test_a_small_file_generates_only_its_own_pages(small):
    pages = components.generate()
    assert set(pages) == {"alpha.md", "README.md", "rules.md", "catalog.json"}
    assert "A section that came later" not in pages["alpha.md"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('description: "Signs: a document."', "Signs: a document."),
        ("description: Signs: a document.", "Signs: a document."),
        ("description: 'It''s signed.'", "It's signed."),
        ("description:   Spaces around   ", "Spaces around"),
    ],
)
def test_a_description_may_be_plain_or_quoted(line, expected):
    assert components.description_of(f"---\ntitle: x\n{line}\n---\n\n# x\n") == expected


@pytest.mark.parametrize("text", ["---\ntitle: x\n---\n", "description: outside\n", "---\ndescription:\n---\n"])
def test_a_page_without_a_description_is_refused(text):
    with pytest.raises(ValueError, match="no description"):
        components.description_of(text)


def test_approved_means_a_macro():
    macros = environment.get_template("ui/macros.html").module
    approved = [component for component in catalog.components().values() if component.status == catalog.APPROVED]
    assert approved
    for component in approved:
        assert callable(getattr(macros, component.macro, None)), component.name


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (("Save",), '<button class="btn " type="button">Save</button>'),
        (("Save", "primary", "submit"), '<button class="btn btn-primary" type="submit">Save</button>'),
        (("Go", "ghost", "button", True), '<button class="btn btn-ghost btn-sm" type="button">Go</button>'),
        (("Drop", "danger"), '<button class="btn btn-error" type="button">Drop</button>'),
    ],
)
def test_the_button_macro(arguments, expected):
    assert str(environment.get_template("ui/macros.html").module.button(*arguments)).strip() == expected


def test_the_button_macro_keeps_attributes_and_escapes_everything():
    html = str(
        environment.get_template("ui/macros.html").module.button(
            "<b>", attributes={"hx-get": '/x"y', "aria-pressed": "true"}, loading="Wait"
        )
    )
    assert "&lt;b&gt;" in html
    assert 'hx-get="/x&#34;y"' in html
    assert 'aria-pressed="true"' in html
    assert '<span class="htmx-indicator">Wait</span>' in html


def test_the_button_macro_refuses_a_kind_it_does_not_have():
    with pytest.raises(Exception, match="invented"):
        environment.get_template("ui/macros.html").module.button("Save", "invented")


@pytest.mark.skipif(bool(os.environ.get("BASE_WITHOUT_DEMO")), reason="runs once, on the full repository")
@pytest.mark.parametrize("demo", [True, False], ids=["with the demo", "without the demo"])
def test_the_promised_way_to_add_a_component_passes_the_checks(tmp_path, demo):
    copy = repository_copy(tmp_path / "application")
    if not demo:
        assert run_in(copy, "tools/remove_demo.py").returncode == 0

    list_file = copy / "app" / "ui" / "catalog.py"
    text = list_file.read_text(encoding="utf-8")
    entry = '    "own": (N_("Own"), (Component("signature"),)),\n    "mockups": ('
    list_file.write_text(text.replace('    "mockups": (', entry), encoding="utf-8", newline="\n")
    (copy / "docs" / "components" / "signature.md").write_text(OWN_PAGE, encoding="utf-8", newline="\n")
    tests = ["tests/test_components.py"]
    if demo:
        specimen = (
            '{% from "demo/gallery/macros.html" import specimen %}\n'
            '{% call specimen(c["signature"], statuses) %}<p>{{ _("Title") }}</p>{% endcall %}\n'
        )
        gallery = copy / "app" / "demo" / "templates" / "demo" / "gallery" / "own.html"
        gallery.write_text(specimen, encoding="utf-8", newline="\n")
        tests.append("tests/demo/test_gallery.py")

    assert run_in(copy, "tools/components.py").returncode == 0
    checked = run_in(copy, "tools/components.py", "check")
    assert checked.returncode == 0, checked.stdout
    result = run_in(copy, "-m", "pytest", "-q", "-x", "-m", "not browser", *tests)
    assert result.returncode == 0, result.stdout[-2000:]
    assert "signature" in (copy / "docs" / "components" / "README.md").read_text(encoding="utf-8")
