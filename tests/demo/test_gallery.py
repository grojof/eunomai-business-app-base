"""The gallery shows every official example, tells the truth about each, and works under the application's own rules.

Counts come from daisyUI's pages themselves: nothing here knows how many examples there should be.
"""

import json
import re
from html import unescape
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from app.core.i18n import PSEUDO
from app.demo.gallery import data, highlight, inline_code
from app.main import create_app
from app.ui.catalog import APPROVED, CATEGORIES, components
from tests.conftest import PERSON, build_settings
from tests.helpers import overflows_sideways, run_axe, untranslated, without_official_examples
from tools import gallery as tool
from tools import update_dependencies

BUNDLE = json.loads(tool.SOURCE.read_text(encoding="utf-8"))
OFFICIAL_PAGES = sorted(BUNDLE["pages"])
NAMES = list(components())
ALLOWED = ("Business App", "Demo Person", "daisyUI", "MIT")
REFERENCES = ("for", "popovertarget", "list", "aria-controls", "aria-labelledby", "aria-describedby", "data-dialog")
FRAME_EXCLUDES = ("[data-official]", ".gallery-thumb")


def official_count(name: str) -> int:
    return len(re.findall(r"^```html\s*$", BUNDLE["pages"][name], re.M))


class Page(HTMLParser):
    """Every element of a page as a browser would have it: what is in attributes, not what the code tabs show."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, {name: value or "" for name, value in attrs}))


def elements(html: str) -> list[tuple[str, dict[str, str]]]:
    page = Page()
    page.feed(html)
    return page.elements


@pytest.fixture(scope="module")
def pages():
    client = TestClient(create_app(build_settings()))
    return {name: client.get(f"/gallery/{name}", headers=PERSON).text for name in NAMES}


# The generated data


def test_the_generated_data_is_up_to_date():
    assert tool.stale(tool.generate()) == []


def test_generating_twice_gives_the_same_bytes():
    assert tool.generate() == tool.generate()


def test_every_official_page_is_used():
    assert set(data()) == set(OFFICIAL_PAGES)
    assert len(OFFICIAL_PAGES) > 60


def test_the_licence_stays_with_the_examples():
    notice = (tool.TARGET / "LICENSE.daisyui").read_text(encoding="utf-8")
    assert "Permission is hereby granted" in notice
    assert notice == BUNDLE["licence"]


def test_the_stylesheet_gets_only_the_classes_examples_use():
    names = (tool.TARGET / "classes.txt").read_text(encoding="utf-8").split()
    assert "btn-soft" in names
    assert names == sorted(set(names))


@pytest.mark.rule("COMP-03")
@pytest.mark.parametrize("name", OFFICIAL_PAGES)
def test_every_official_example_is_kept(name):
    assert len(data()[name]["examples"]) == official_count(name)


@pytest.mark.rule("COMP-03")
def test_the_class_tables_are_kept():
    for name, page in data().items():
        written = re.findall(r"^\s+- class:", BUNDLE["pages"][name], re.M)
        assert sum(len(group["items"]) for group in page["classes"]) == len(written), name


def test_titles_and_descriptions_come_with_daisyuis_translations():
    assert data()["button"]["description"]["es"].startswith("Buttons permiten")
    assert data()["button"]["description"]["ca"]
    titles = {example["title"]["en"]: example["title"] for example in data()["button"]["examples"]}
    assert titles["Outline buttons"]["es"] == "Botones de contorno"


# The one transformation


def run(source: str, seen: tool.Seen | None = None) -> dict:
    return tool.transform(source, seen or tool.Seen())


def test_the_prefix_placeholder_goes():
    assert (
        run('<button class="$$btn $$btn-primary">Go</button>')["html"] == '<button class="btn btn-primary">Go</button>'
    )
    assert run('<i style="--$$value:7"></i>')["html"] == '<i data-style="--value:7"></i>'


def test_an_image_from_another_server_becomes_a_local_one_keeping_its_size():
    source = '<img src="https://img.daisyui.com/images/stock/a.webp" alt="A" width="120" height="80" class="w-8" />'
    expected = r'<img src="/static/ui/placeholders/photo-\d\.svg" alt="A" width="120" height="80" class="w-8" />'
    assert re.fullmatch(expected, run(source)["html"])


def test_a_portrait_gets_a_portrait():
    assert "avatar-" in run('<img src="https://img.daisyui.com/images/profile/demo/1@94.webp" />')["html"]


def test_the_same_address_gives_the_same_placeholder():
    source = '<img src="https://img.daisyui.com/x.webp" />'
    assert run(source)["html"] == run(source)["html"]


def test_every_placeholder_a_page_can_ask_for_exists():
    folder = tool.ROOT / "app" / "ui" / "static" / "placeholders"
    for kind in ("photo", "avatar"):
        for number in range(1, tool.PLACEHOLDER_KINDS + 1):
            assert (folder / f"{kind}-{number}.svg").exists()


def test_a_background_from_another_server_becomes_local():
    html = run('<div style="background-image: url(https://img.daisyui.com/a.webp);"></div>')["html"]
    assert re.fullmatch(
        r'<div data-style="background-image: url\(/static/ui/placeholders/photo-\d\.svg\);"></div>', html
    )


def test_dialog_calls_become_data_attributes():
    assert run('<button onclick="box.showModal()">Open</button>')["html"] == '<button data-dialog="box">Open</button>'
    assert run('<button onclick="box.close()">Shut</button>')["html"] == '<button data-dialog-close="box">Shut</button>'


@pytest.mark.parametrize(
    "source",
    [
        '<button onclick="alert(1)">x</button>',
        '<input onchange="this.remove()">',
        '<a href="https://example.org/">x</a>',
        '<iframe src="//example.org/"></iframe>',
        "<div><style>a{}</style></div>",
    ],
)
def test_anything_else_that_would_break_the_policy_stops_the_generator(source):
    with pytest.raises(tool.StructureChanged):
        run(source)


def test_a_style_inside_an_svg_moves_to_its_elements():
    html = run(
        '<svg><defs><style>.a,.b{fill:#111}.b{stroke:#222}</style></defs><path class="a" d="M0"/><g class="b"/></svg>'
    )["html"]
    assert "<style" not in html
    assert 'data-style="fill:#111;"' in html
    assert 'data-style="fill:#111;stroke:#222;"' in html


def test_an_svg_style_with_another_kind_of_selector_stops_the_generator():
    with pytest.raises(tool.StructureChanged, match="plain class"):
        run("<svg><style>path{fill:red}</style></svg>")


def test_an_example_with_a_script_is_not_run():
    result = run('<script src="https://unpkg.com/x"></script><i style="--a:1"></i>')
    assert result["runs"] is False
    assert 'data-style="--a:1"' in result["html"]


def test_the_year_the_documentation_computes_stays_a_placeholder():
    assert run("<p>© {new Date().getFullYear()}</p>")["html"] == "<p>© YYYY</p>"


def test_repeated_ids_and_radio_groups_get_new_names_and_references_follow():
    seen = tool.Seen()
    source = (
        '<label for="a">L</label><input id="a"><input type="radio" name="r"><input type="radio" name="r" checked>'
        '<button popovertarget="a" aria-controls="a b">x</button><a href="#a">y</a><p id="b" aria-labelledby="a"></p>'
        '<button onclick="a.showModal()">z</button>'
    )
    first = run(source, seen)["html"]
    second = run(source, seen)["html"]
    assert first == source.replace('onclick="a.showModal()"', 'data-dialog="a"')
    assert 'id="a-2"' in second
    assert 'for="a-2"' in second
    assert 'popovertarget="a-2"' in second
    assert 'aria-controls="a-2 b-2"' in second
    assert 'href="#a-2"' in second
    assert 'aria-labelledby="a-2"' in second
    assert 'data-dialog="a-2"' in second
    assert second.count('name="r-2"') == 2


def test_a_name_the_frame_uses_is_never_taken():
    assert 'id="main-2"' in run('<div id="main"></div>')["html"]


def test_anchor_names_follow_on_a_page():
    seen = tool.Seen()
    source = '<button style="anchor-name:--a"></button><div style="position-anchor:--a"></div>'
    run(source, seen)
    assert run(source, seen)["html"].count("--a-2") == 2


def test_what_is_fixed_to_the_screen_gets_a_stage():
    assert run('<div class="$$fab"></div>')["kind"] == "stage"
    assert run('<div class="$$modal"></div>')["kind"] == "stage"
    assert run('<dialog class="$$modal"></dialog>')["kind"] == ""
    assert run('<div class="$$dropdown"></div>')["kind"] == "floats"


def test_tailwinds_own_colours_are_flagged():
    assert run('<i class="bg-blue-400"></i>')["palette"] is True
    assert run('<i class="bg-neutral bg-primary"></i>')["palette"] is False


# A page that changes its structure


PAGE = """---
title: Alpha
desc: It does things.
classnames:
  component:
  - class: alpha
    desc: The thing
---

### ~First
#### a subtitle
<div>preview</div>

```html
<div class="$$alpha">One</div>
```
"""


def test_a_small_page_is_read():
    fields, tables, body = tool.read_frontmatter("alpha", PAGE)
    assert fields["title"] == "Alpha"
    assert tables["component"][0]["class"] == "alpha"
    example = tool.read_examples("alpha", body)[0]
    assert (example["title"], example["subtitle"]) == ("~First"[1:], "a subtitle")


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("no frontmatter at all", "no frontmatter"),
        (PAGE.replace("title: Alpha\n", ""), "no title"),
        (PAGE.replace("desc: It does things.\n", ""), "no desc"),
        (PAGE.replace("  - class: alpha", "  * class: alpha"), "not understood"),
        (PAGE.replace("classnames:\n  component:\n  - class: alpha\n    desc: The thing\n", ""), "no class table"),
    ],
)
def test_a_changed_frontmatter_stops_the_generator(text, complaint):
    with pytest.raises(tool.StructureChanged, match=complaint):
        tool.component("alpha", text, {}, tool.Seen())


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        ("### ~First\n<div></div>\n\n### ~Second\n```html\n<i></i>\n```\n", "has no html block"),
        ("### ~Only\n<div></div>\n", "has no html block"),
        ("```html\n<i></i>\n```\n", "no heading"),
        ("### ~Two\n```html\n<i></i>\n```\n```html\n<b></b>\n```\n", "second html block"),
        ("### ~Open\n```html\n<i></i>\n", "never closed"),
        ("Nothing here.\n", "no examples"),
    ],
)
def test_changed_headings_stop_the_generator(body, complaint):
    with pytest.raises(tool.StructureChanged, match=complaint):
        tool.read_examples("alpha", body)


@pytest.fixture
def broken_source(tmp_path, monkeypatch):
    def write(pages):
        bundle = {**BUNDLE, "pages": pages}
        source = tmp_path / "docs.json"
        source.write_text(json.dumps(bundle), encoding="utf-8")
        monkeypatch.setattr(tool, "SOURCE", source)
        monkeypatch.setattr(update_dependencies.gallery, "SOURCE", source)

    return write


def test_a_page_with_no_place_in_the_catalogue_stops_the_generator(broken_source):
    broken_source({**BUNDLE["pages"], "sparkles": PAGE})
    with pytest.raises(tool.StructureChanged, match="sparkles"):
        tool.generate()


def test_a_broken_page_holds_every_daisyui_file_back(broken_source, tmp_path, monkeypatch):
    broken_source({"button": "no frontmatter"})
    (tmp_path / "daisyui.mjs").write_bytes(b"old")
    (tmp_path / "other.js").write_bytes(b"old")
    (tmp_path / "vendor.json").write_text(
        json.dumps(
            {
                "daisyui": {"version": "1.0.0", "target": "daisyui.mjs", "sha384": "a"},
                "other": {"version": "1.0.0", "target": "other.js", "sha384": "c"},
            }
        ),
        encoding="utf-8",
    )
    tools_vendor = update_dependencies.vendor
    monkeypatch.setattr(update_dependencies, "ROOT", tmp_path)
    monkeypatch.setattr(tools_vendor, "VENDOR", tmp_path / "vendor.json")

    def update():
        (tmp_path / "daisyui.mjs").write_bytes(b"new")
        (tmp_path / "other.js").write_bytes(b"new")
        entries = tools_vendor.read_entries()
        for entry in entries.values():
            entry["version"] = "2.0.0"
        tools_vendor.write_entries(entries)
        return ["`daisyui` 1.0.0 to 2.0.0", "`other` 1.0.0 to 2.0.0"], []

    monkeypatch.setattr(tools_vendor, "update", update)
    problems = []
    assert update_dependencies.update_vendored(problems) == ["`other` 1.0.0 to 2.0.0"]
    assert problems[0][:2] == ("daisyui", "1.0.0")
    assert "no frontmatter" in problems[0][2]
    assert tools_vendor.read_entries()["daisyui"]["version"] == "1.0.0"
    assert (tmp_path / "daisyui.mjs").read_bytes() == b"old"


# The pages


@pytest.mark.rule("COMP-03")
def test_the_index_shows_every_component_with_its_status_by_category(client, person):
    html = client.get("/gallery", headers=person).text
    pattern = r'<a [^>]*href="/gallery/([a-z0-9-]+)"[^>]*>[^<]*</a></h3>\s*<span [^>]*data-status="([a-z]+)"'
    assert dict(re.findall(pattern, html)) == {name: component.status for name, component in components().items()}
    assert html.count("data-gallery-section>") == len(CATEGORIES)


@pytest.mark.rule("COMP-03")
def test_the_index_counts_what_daisyui_publishes(client, person):
    total = sum(official_count(name) for name in OFFICIAL_PAGES)
    assert f"{total} official examples" in client.get("/gallery", headers=person).text


@pytest.mark.rule("COMP-03")
@pytest.mark.parametrize("name", NAMES)
def test_every_example_is_on_its_components_page(pages, name):
    html = pages[name]
    assert html.count("data-example>") == (official_count(name) if name in BUNDLE["pages"] else 0)
    assert f'data-status="{components()[name].status}"' in html


@pytest.mark.rule("COMP-03")
def test_a_macro_is_shown_on_the_page_of_its_component(pages):
    for name, component in components().items():
        assert not component.macro or "Our macro" in pages[name], name


@pytest.mark.rule("COMP-03")
def test_a_status_means_what_the_catalogue_says(pages):
    for name, component in components().items():
        if component.status == APPROVED:
            assert "Our macro" in pages[name], name
        if component.note:
            assert component.note[:40] in pages[name].replace("&#39;", "'"), name


def test_every_page_links_its_neighbours(pages):
    for position, name in enumerate(NAMES):
        html = pages[name]
        before, after = NAMES[position - 1], NAMES[(position + 1) % len(NAMES)]
        assert (f'href="/gallery/{before}" rel="prev"' in html) == (position > 0)
        assert (f'href="/gallery/{after}" rel="next"' in html) == (position + 1 < len(NAMES))


def test_an_unknown_component_is_not_found(client, person):
    assert client.get("/gallery/nothing", headers=person).status_code == 404


def test_there_is_one_gallery(client, person):
    assert client.get("/catalogue", headers=person).status_code == 404
    assert 'href="/catalogue"' not in client.get("/", headers=person).text


@pytest.mark.rule("SEC-06")
@pytest.mark.parametrize("name", NAMES)
def test_no_page_has_inline_code_or_reaches_another_server(pages, name):
    html = pages[name]
    for tag, attributes in elements(html):
        assert "style" not in attributes, tag
        assert not [key for key in attributes if key.startswith("on")], (tag, attributes)
        for key in ("src", "href", "poster", "srcset", "action"):
            assert not re.match(r"(?:https?:)?//", attributes.get(key, "")), (tag, attributes)
        if tag == "script" and attributes.get("type") != "application/json":  # JSON is data: nothing runs it
            assert attributes["src"].startswith("/static/")
        assert "url(http" not in attributes.get("data-style", "")
    assert not re.findall(r"<style\b", html)


@pytest.mark.rule("SEC-06")
def test_the_index_has_no_inline_code_either(client, person):
    for tag, attributes in elements(client.get("/gallery", headers=person).text):
        assert "style" not in attributes, tag
        assert not [key for key in attributes if key.startswith("on")], tag


@pytest.mark.rule("SEC-06")
def test_the_code_a_person_copies_is_the_code_that_ran():
    for name, page in data().items():
        for example in page["examples"]:
            if example["runs"]:
                for forbidden in (" style=", "img.daisyui.com", " onclick="):
                    assert forbidden not in example["html"], (name, example["id"])


@pytest.mark.parametrize("name", NAMES)
def test_ids_are_unique_and_references_point_at_them(pages, name):
    found = elements(pages[name])
    ids = [attributes["id"] for _tag, attributes in found if "id" in attributes]
    assert len(ids) == len(set(ids)), [identifier for identifier in ids if ids.count(identifier) > 1]
    for _tag, attributes in found:
        for key in REFERENCES:
            for target in attributes.get(key, "").split():
                assert target in ids, (key, target)


def test_ids_are_unique_on_the_index_too(client, person):
    ids = [a["id"] for _t, a in elements(client.get("/gallery", headers=person).text) if "id" in a]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("name", NAMES)
def test_a_radio_group_belongs_to_one_example(pages, name):
    owner: dict[str, str] = {}
    current = ""
    for tag, attributes in elements(pages[name]):
        if tag == "section" and "data-example" in attributes:
            current = attributes["id"]
        if tag == "input" and attributes.get("type") == "radio" and attributes.get("name"):
            assert owner.setdefault(attributes["name"], current) == current, attributes["name"]


def test_code_is_marked_for_colour_without_changing_its_text():
    source = '<!-- note -->\n<button class="btn" disabled>A & B</button>\n<br />'
    html = str(highlight(source))
    assert 'class="code-attribute"' in html
    plain = re.sub(r"</?span[^>]*>", "", html)
    for escaped, character in (("&#34;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
        plain = plain.replace(escaped, character)
    assert plain == source


def test_backticks_become_code_and_nothing_else_does():
    assert str(inline_code("use `<b>` now")) == "use <code>&lt;b&gt;</code> now"


@pytest.mark.rule("LANG-10")
def test_official_text_left_in_english_says_so(client, person):
    client.cookies.set("language", "es")
    html = client.get("/gallery/button", headers=person).text
    assert '<h4 id="button-sizes-title" class="font-semibold">Tamaños Button</h4>' in html
    assert '<h4 id="soft-buttons-title" class="font-semibold" lang="en">Soft buttons</h4>' in html
    assert 'data-official lang="en"' in html


def test_a_page_comes_in_the_persons_language(client, person):
    client.cookies.set("language", "ca")
    html = unescape(client.get("/gallery/button", headers=person).text)
    assert data()["button"]["description"]["ca"] in html


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize(
    "path", ["/gallery", "/gallery/button", "/gallery/drawer", "/gallery/calendar", "/gallery/alert"]
)
def test_no_frame_has_text_outside_translation(client, person, path):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get(path, headers=person).text, ALLOWED) == []


def test_the_language_check_skips_example_regions_only():
    html = "<p>Frame</p><!--official--><p>Example</p><!--/official--><p>More</p>"
    assert without_official_examples(html) == "<p>Frame</p><p>More</p>"
    assert untranslated(html, ()) == ["Frame", "More"]


@pytest.mark.rule("COMP-03")
def test_the_palette_finds_every_component_in_the_persons_language(client, person):
    client.cookies.set("language", "es")
    html = client.get("/search", headers=person).text
    for name in NAMES:
        assert f'href="/gallery/{name}"' in html
    assert data()["accordion"]["description"]["es"] in unescape(html)


# In a real browser


def watch(page, failures):
    page.on("console", lambda message: failures.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.on("requestfailed", lambda request: failures.append(f"failed: {request.url}"))
    page.on(
        "response",
        lambda response: failures.append(f"{response.status}: {response.url}") if response.status >= 400 else None,
    )
    page.on(
        "request",
        lambda request: (
            failures.append(f"left: {request.url}")
            if not request.url.startswith(("http://127.0.0.1", "data:"))
            else None
        ),
    )


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
@pytest.mark.rule("A11Y-12")
@pytest.mark.parametrize("name", NAMES)
def test_a_page_opens_clean_and_fits_a_phone(open_page, name):
    """Both checks on one load, at a phone's width: what a page asks for and runs does not depend on the width. Each
    page was once opened twice for them, and they were a tenth of the base's whole suite."""
    failures: list[str] = []
    page = open_page("/settings", width=320)
    watch(page, failures)
    page.goto(page.url.replace("/settings", f"/gallery/{name}"))
    page.wait_for_load_state("networkidle")
    styled = page.evaluate("[...document.querySelectorAll('[data-style]')].filter((e) => !e.style.length).length")
    assert styled == 0
    assert failures == []
    assert not overflows_sideways(page)


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_the_index_opens_clean(open_page):
    failures: list[str] = []
    page = open_page("/settings")
    watch(page, failures)
    page.goto(page.url.replace("/settings", "/gallery"))
    page.wait_for_load_state("networkidle")
    assert failures == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize(
    "path", ["/gallery", "/gallery/button", "/gallery/modal", "/gallery/calendar", "/gallery/drawer"]
)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_frame_passes_the_scan(open_page, path, theme):
    assert run_axe(open_page(path, theme=theme, bypass_csp=True), exclude=FRAME_EXCLUDES) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_code_panel_passes_the_scan(open_page, theme):
    page = open_page("/gallery/modal", theme=theme, bypass_csp=True)
    page.get_by_role("tab", name="Code").first.click()
    assert run_axe(page, exclude=FRAME_EXCLUDES) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
def test_the_index_fits_a_phone(open_page):
    assert not overflows_sideways(open_page("/gallery", width=320))


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_preview_and_code_work_with_the_keyboard(open_page):
    page = open_page("/gallery/button")
    preview = page.locator("#button-tab-preview")
    code = page.locator("#button-tab-code")
    preview.focus()
    page.keyboard.press("ArrowRight")
    assert code.evaluate("element => element === document.activeElement")
    assert code.get_attribute("aria-selected") == "true"
    assert preview.get_attribute("tabindex") == "-1"
    assert page.locator("#button-code").is_visible()
    assert not page.locator("#button-preview").is_visible()
    page.keyboard.press("ArrowRight")
    assert preview.evaluate("element => element === document.activeElement")
    page.keyboard.press("End")
    assert code.get_attribute("aria-selected") == "true"
    page.keyboard.press("Home")
    assert preview.get_attribute("aria-selected") == "true"
    page.keyboard.press("ArrowLeft")
    assert code.get_attribute("aria-selected") == "true"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.copy") == "button-source"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.parentElement.id") == "button-code"


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_the_copy_button_works_with_the_keyboard_and_says_so(open_page):
    page = open_page("/gallery/modal", bypass_csp=True)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    button = page.locator('[data-copy="dialog-modal-source"]')
    button.focus()
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('announcements').textContent === 'Copied'")
    assert button.inner_text().strip() == "Copied"
    copied = page.evaluate("navigator.clipboard.readText()").replace("\r\n", "\n")  # as Windows gives it back
    assert copied == data()["modal"]["examples"][0]["html"]
    assert "$$" not in copied
    assert "onclick" not in copied


@pytest.mark.browser
def test_copying_works_without_the_clipboard_interface(open_page):
    page = open_page("/gallery/button", bypass_csp=True)
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined})")
    page.locator('[data-copy="button-source"]').click()
    page.wait_for_function("document.getElementById('announcements').textContent === 'Copied'")


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_a_dialog_opens_without_inline_code_and_returns_focus(open_page):
    page = open_page("/gallery/modal")
    opener = page.locator('[data-dialog="my_modal_1"]')
    opener.press("Enter")
    page.locator("#my_modal_1").wait_for(state="visible")
    page.keyboard.press("Escape")
    page.locator("#my_modal_1").wait_for(state="hidden")
    assert opener.evaluate("element => element === document.activeElement")


@pytest.mark.browser
@pytest.mark.parametrize(
    ("name", "selector"),
    [("fab", ".fab"), ("dock", ".dock"), ("toast", ".toast"), ("drawer", ".drawer-side")],
)
def test_what_is_fixed_to_the_screen_stays_in_its_box(open_page, name, selector):
    page = open_page(f"/gallery/{name}")
    outside = page.evaluate(
        """(selector) => [...document.querySelectorAll("[data-official]")].flatMap((box) => {
            const frame = box.getBoundingClientRect();
            return [...box.querySelectorAll(selector)].filter((element) => {
                const inside = element.getBoundingClientRect();
                return inside.width > 0 && (inside.left < frame.left - 1 || inside.right > frame.right + 1
                    || inside.top < frame.top - 1 || inside.bottom > frame.bottom + 1);
            }).map((element) => box.parentElement.id);
        })""",
        selector,
    )
    assert outside == []


@pytest.mark.browser
def test_an_open_drawer_stays_in_its_box(open_page):
    page = open_page("/gallery/drawer")
    box = page.locator("[data-official]").first
    box.locator(".drawer-button").click()
    side = box.locator(".drawer-side").bounding_box()
    frame = box.bounding_box()
    assert side["y"] >= frame["y"] - 1
    assert side["y"] + side["height"] <= frame["y"] + frame["height"] + 1


@pytest.mark.browser
def test_styles_reach_elements_through_the_cssom(open_page):
    page = open_page("/gallery/radial-progress")
    radial = page.locator(".radial-progress").first
    assert radial.evaluate("element => element.style.getPropertyValue('--value')") != ""


@pytest.mark.browser
def test_trying_an_example_never_leaves_the_page(open_page):
    page = open_page("/gallery/validator")
    before = page.url
    page.evaluate("""() => {
        const form = document.createElement('form');
        document.querySelector('[data-official]').append(form);
        form.requestSubmit();
    }""")
    page.wait_for_timeout(100)
    assert page.url == before


@pytest.mark.browser
def test_the_index_filters_as_a_person_types(open_page):
    page = open_page("/gallery")
    every = page.locator("[data-gallery-card]").count()
    assert every == len(NAMES)
    field = page.get_by_role("searchbox", name="Filter components")
    field.fill("toggle")
    shown = page.locator("[data-gallery-card]:visible")
    assert 0 < shown.count() < every
    assert "Components shown" in page.locator("[data-gallery-count]").inner_text()
    assert page.locator("[data-gallery-section]:visible").count() < len(CATEGORIES)
    field.fill("zzzz")
    assert page.get_by_role("heading", name="No component matches").is_visible()
    field.fill("")
    assert page.locator("[data-gallery-card]:visible").count() == every


@pytest.mark.browser
def test_the_index_of_a_page_marks_where_a_person_is(open_page):
    page = open_page("/gallery/button", width=1440, bypass_csp=True)
    assert page.locator("[data-gallery-index] a").count() == official_count("button")
    page.locator("[data-gallery-index] a").nth(4).click()
    page.wait_for_function("document.querySelector('[data-gallery-index] a[aria-current]')")


@pytest.mark.browser
def test_a_wide_screen_shows_the_index_and_a_narrow_one_does_not(open_page):
    assert open_page("/gallery/button", width=1440).locator("[data-gallery-index]").is_visible()
    assert not open_page("/gallery/button", width=1024).locator("[data-gallery-index]").is_visible()


@pytest.mark.browser
@pytest.mark.rule("A11Y-04")
def test_a_link_to_an_example_stops_clear_of_the_sticky_header(open_page):
    page = open_page("/gallery/button#soft-buttons")
    assert page.evaluate("window.scrollY") > 0
    assert page.evaluate("""() => {
        const header = document.querySelector("body header").getBoundingClientRect().bottom;
        return document.querySelector(location.hash).getBoundingClientRect().top >= header;
    }""")


@pytest.mark.browser
def test_the_palette_finds_a_component_by_its_class(open_page):
    page = open_page("/")
    page.keyboard.press("Control+k")
    page.locator("[data-palette-option]").first.wait_for(state="attached")
    page.keyboard.type("btn-ghost")
    with page.expect_navigation():
        page.keyboard.press("Enter")
    assert page.url.endswith("/gallery/button")
