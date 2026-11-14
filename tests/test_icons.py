"""Icons come from Lucide's pinned set or the organization's own, only through the `icon` macro, found by search.
Illustrations are files shown as images, holding nothing that runs or loads from elsewhere."""

import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

from app.core import templating
from app.core.application import CONTENT_SECURITY_POLICY
from app.core.gantt import Task, timeline
from app.core.templating import environment
from tests.helpers import ROOT
from tools import icons, vendor

LUCIDE_X = (ROOT / "app" / "ui" / "templates" / "ui" / "icons" / "x.svg").read_text(encoding="utf-8")
OWN_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M4 12h16"/></svg>\n'
)


def macro():
    return environment.get_template("ui/macros.html").module


# The set


@pytest.mark.rule("COMP-05")
def test_the_whole_set_is_there_and_matches_its_index():
    names = icons.lucide_names()
    assert len(names) > 1800
    assert names == set(json.loads(icons.INDEX.read_text(encoding="utf-8"))["icons"])
    assert (icons.LUCIDE / "LICENSE").read_text(encoding="utf-8").startswith("ISC License")


@pytest.mark.rule("COMP-05")
def test_the_tool_check_passes():
    assert icons.problems() == []


@pytest.mark.rule("COMP-05")
def test_any_icon_of_the_set_renders_through_the_macro_with_nothing_else_added():
    html = str(macro().icon("truck", "size-4")).strip()
    assert html.startswith('<span class="icon inline-flex shrink-0 size-4" aria-hidden="true">')
    assert "lucide-truck" in html
    assert html.count("<svg") == 1


DRAWINGS = {
    "x": "c1e53fc9bbe1a0a0",
    "search": "185937a98ae03072",
    "menu": "eb8121ff66622980",
    "triangle-alert": "2c9139e4a3097dd0",
    "chevron-down": "be2f2e86753c4c6b",
    "gauge": "3b509f5d0d1fa1de",
    "wrench": "bd8649d464e778ce",
    "calendar-range": "304161afe7bc1c16",
}
"""Icons every screen shows, as Lucide 1.59 drew them. A new version may change any other drawing; one of these
changed waits for a person to look at it, and then its fingerprint here."""


def test_the_icons_already_used_keep_their_drawings():
    for name, fingerprint in DRAWINGS.items():
        text = (icons.LUCIDE / f"{name}.svg").read_text(encoding="utf-8")
        drawing = re.sub(r"\A<!-- @license lucide-static v[0-9.]+ - ISC -->\n", "", text)
        assert drawing.startswith("<svg"), name
        assert hashlib.sha256(drawing.encode()).hexdigest()[:16] == fingerprint, f"Lucide changed how {name} looks"


@pytest.mark.rule("COMP-05")
def test_an_icon_added_by_hand_to_lucides_folder_is_named(tmp_path):
    folder = tmp_path / "icons"
    folder.mkdir()
    (folder / "x.svg").write_text(LUCIDE_X, encoding="utf-8")
    (folder / "drawn.svg").write_text(OWN_ICON, encoding="utf-8")
    index = {"icons": {"x": {"tags": [], "categories": []}, "gone": {"tags": [], "categories": []}}}
    found = icons.index_problems(folder, index)
    assert any("drawn.svg" in problem and "app/brand/icons/" in problem for problem in found)
    assert any("gone" in problem for problem in found)


# What templates and code ask for


@pytest.fixture
def application(tmp_path):
    """A small application folder: the icon macro, macros that pass names on, and the code that gives them."""
    templates = tmp_path / "ui" / "templates" / "ui"
    templates.mkdir(parents=True)
    (templates / "macros.html").write_text(
        '{% macro icon(name, size="size-5") %}<span>{% include ["ui/icons/" ~ name ~ ".svg"] %}</span>{% endmacro %}\n'
        '{% macro button(text, name="") %}<button>{% if name %}{{ icon(name) }}{% endif %}{{ text }}</button>'
        "{% endmacro %}\n"
        "{% macro actions(items) %}{% for label, href, picture in items %}"
        '<a href="{{ href }}">{{ icon(picture) }}{{ label }}</a>{% endfor %}{% endmacro %}\n',
        encoding="utf-8",
    )
    (templates / "page.html").write_text(
        '{{ icon("x") }}{{ icon("arrow-up" if up == "yes" else "unknown-down") }}{{ icon(item.icon or "missing-or") }}'
        '{{ button("Save", name="missing-button") }}{{ actions([("A", "/a", "missing-row"), ("B", "/b", "x")]) }}'
        "{% for value, label, name in theme_options %}{{ icon(name) }}{% endfor %}"
        '{{ icon("chevron-" ~ direction) }}',
        encoding="utf-8",
    )
    (tmp_path / "navigation.py").write_text(
        "from dataclasses import dataclass\n\n\n@dataclass\nclass Item:\n    label: str\n    path: str\n"
        '    icon: str = "missing-default"\n\n\n'
        'ITEMS = [Item("A", "/", "missing-positional"), Item("B", "/b", icon="missing-keyword"), Item("C", "/c")]\n'
        'OTHER = render(theme_options=[("light", "Light", "missing-theme"), ("dark", "Dark", "x")])\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.rule("COMP-05")
def test_every_name_asked_for_is_found_wherever_it_is_written(application):
    asked = {name for name, _where in icons.requested(application)}
    assert asked == {
        "x",
        "arrow-up",
        "unknown-down",
        "missing-or",
        "missing-button",
        "missing-row",
        "missing-default",
        "missing-positional",
        "missing-keyword",
        "missing-theme",
    }


@pytest.mark.rule("COMP-05")
def test_a_name_that_does_not_exist_is_reported_with_where_it_is(application):
    found = icons.unknown_names(application, {"x", "arrow-up"}, {"trash-2": "trash"})
    assert any(problem.startswith("ui/templates/ui/page.html:1: no icon named missing-button") for problem in found)
    assert any("navigation.py:11: no icon named missing-positional" in problem for problem in found)
    assert len(found) == 8


@pytest.mark.rule("COMP-05")
def test_an_old_name_says_which_name_replaced_it(tmp_path):
    (tmp_path / "page.html").write_text('{% macro icon(name) %}{% endmacro %}{{ icon("trash-2") }}', encoding="utf-8")
    assert icons.unknown_names(tmp_path, {"trash"}, {"trash-2": "trash"}) == [
        "page.html:1: no icon named trash-2: it is Lucide's old name for trash"
    ]


@pytest.mark.rule("COMP-05")
def test_every_name_the_application_asks_for_exists():
    assert icons.unknown_names() == []
    asked = {name for name, _where in icons.requested()}
    assert {"x", "search", "sliders-horizontal", "monitor", "sun", "triangle-alert", "hash"} <= asked
    if (ROOT / "app" / "demo").exists():
        assert {"gauge", "clipboard-list", "trash", "rotate-ccw-clock", "eye", "shapes"} <= asked


# Nothing drawn by hand


@pytest.mark.rule("COMP-05")
@pytest.mark.parametrize(
    ("path", "content", "reason"),
    [
        ("ui/templates/page.html", '<p><svg viewBox="0 0 24 24"><path d="M0 0"/></svg></p>', "an inline SVG"),
        ("ui/templates/page.html", '{% include "ui/icons/x.svg" %}', "an icon outside the icon macro"),
        ("core/code.py", 'ICON = "<svg viewBox=\\"0 0 24 24\\"></svg>"\n', "an inline SVG"),
        ("ui/static/app.js", "element.innerHTML = '<svg></svg>';", "an inline SVG"),
        ("ui/styles/extra.css", '.x { background: url("data:image/svg+xml,%3Csvg%3E") }', "an inline SVG"),
        ("ui/static/arrow.svg", OWN_ICON, "an SVG file outside"),
        ("demo/static/logo.svg", OWN_ICON, "an SVG file outside"),
    ],
)
def test_an_icon_drawn_by_hand_is_refused(tmp_path, path, content, reason):
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text(content, encoding="utf-8")
    found = icons.drawn_by_hand(tmp_path)
    assert len(found) == 1
    assert found[0].startswith(path) and reason in found[0]


@pytest.mark.rule("COMP-05")
@pytest.mark.parametrize(
    "path",
    [
        "ui/templates/ui/icons/x.svg",
        "brand/icons/own.svg",
        "brand/logo.svg",
        "ui/static/illustrations/team.svg",
        "ui/static/illustrations/people/team.svg",
        "ui/static/placeholders/photo-1.svg",
        "demo/examples/button.json",
        "ui/static/app.css",
        "ui/static/vendor/library.js",
    ],
)
def test_the_places_where_an_svg_belongs_are_not_refused(tmp_path, path):
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text(OWN_ICON, encoding="utf-8")
    assert icons.drawn_by_hand(tmp_path) == []


def test_the_icon_macro_itself_may_include_icons():
    assert icons.drawn_by_hand(ROOT / "app") == []


# The organization's icons


@pytest.fixture
def own_folder(tmp_path, monkeypatch):
    folder = tmp_path / "brand-icons"
    folder.mkdir()
    (folder / "pallet-jack.svg").write_text(OWN_ICON, encoding="utf-8")
    monkeypatch.setattr(templating.BRAND_ICONS, "searchpath", [str(folder)])
    return folder


@pytest.mark.rule("COMP-05")
def test_the_macro_finds_an_organizations_icon(own_folder):
    html = str(macro().icon("pallet-jack"))
    assert 'aria-hidden="true"' in html
    assert '<path d="M4 12h16"/>' in html


@pytest.mark.rule("COMP-05")
def test_lucide_and_the_organization_never_share_a_name(tmp_path):
    (tmp_path / "x.svg").write_text(OWN_ICON, encoding="utf-8")
    (tmp_path / "pallet-jack.svg").write_text(OWN_ICON, encoding="utf-8")
    found = icons.own_problems(tmp_path, {"x", "truck"})
    assert found == [f"{tmp_path.name}/x.svg: Lucide has an icon named x: give yours another name, such as x-ours"]


@pytest.mark.rule("COMP-05")
@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (('viewBox="0 0 24 24"', 'viewBox="0 0 48 48"'), "viewBox"),
        (('width="24"', 'width="48"'), "width"),
        (('stroke="currentColor"', 'stroke="#c00"'), "a colour of its own"),
        (('<path d="M4 12h16"/>', '<path fill="red" d="M4 12h16"/>'), "a colour of its own"),
        (('<path d="M4 12h16"/>', '<path style="opacity: .5" d="M4 12h16"/>'), "style"),
        (('<path d="M4 12h16"/>', '<style>path { opacity: .5 }</style><path d="M4 12h16"/>'), "<style>"),
        (('<path d="M4 12h16"/>', '<path id="line" d="M4 12h16"/>'), "an id"),
        (('stroke="currentColor"', 'stroke="none"'), "currentColor"),
        (('<path d="M4 12h16"/>', '<path onclick="alert(1)" d="M4 12h16"/>'), "onclick"),
    ],
)
def test_an_organizations_icon_that_would_not_look_like_the_rest_is_named_with_why(tmp_path, change, reason):
    (tmp_path / "pallet-jack.svg").write_text(OWN_ICON.replace(*change), encoding="utf-8")
    found = icons.own_problems(tmp_path, set())
    assert found and all(problem.startswith(f"{tmp_path.name}/pallet-jack.svg: ") for problem in found)
    assert any(reason in problem for problem in found), found


def test_an_organizations_icon_like_lucides_passes(tmp_path):
    (tmp_path / "pallet-jack.svg").write_text(OWN_ICON, encoding="utf-8")
    (tmp_path / "tags.json").write_text(json.dumps({"icons": {"pallet-jack": {"tags": ["forklift"]}}}), "utf-8")
    assert icons.own_problems(tmp_path, {"truck"}) == []


@pytest.mark.parametrize(
    ("tags", "reason"),
    [
        ({"icons": {"missing": {"tags": ["x"]}}}, "no icon named missing"),
        ({"pallet-jack": ["x"]}, "the same form as Lucide's index"),
        ({"icons": {"pallet-jack": {"tags": "forklift"}}}, "a list of words"),
    ],
)
def test_an_organizations_tags_file_must_match_its_icons(tmp_path, tags, reason):
    (tmp_path / "pallet-jack.svg").write_text(OWN_ICON, encoding="utf-8")
    (tmp_path / "tags.json").write_text(json.dumps(tags), encoding="utf-8")
    assert any(reason in problem for problem in icons.own_problems(tmp_path, set()))


def test_the_organization_starts_with_an_empty_tags_file():
    assert json.loads((icons.OWN / "tags.json").read_text(encoding="utf-8")) == {"icons": {}}


# Search


def names_found(query: str, **options) -> list[str]:
    return [found.icon.name for found in icons.search(query, **options)]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("truck", "truck"),
        ("lorry", "truck"),
        ("camión", "truck"),
        ("camion", "truck"),
        ("camiones", "truck"),
        ("camió", "truck"),
        ("factura", "receipt"),
        ("albarà", "clipboard-check"),
        ("paperera", "trash"),
        ("trash-2", "trash"),
        ("orden de trabajo", "clipboard-list"),
    ],
)
def test_search_finds_by_name_tag_old_name_and_our_words(query, expected):
    found = names_found(query)
    assert expected in found[:3], found[:5]


def test_search_finds_the_organizations_icons_and_says_whose_they_are(tmp_path):
    (tmp_path / "pallet-jack.svg").write_text(OWN_ICON, encoding="utf-8")
    (tmp_path / "tags.json").write_text(json.dumps({"icons": {"pallet-jack": {"tags": ["zorblat"]}}}), "utf-8")
    found = icons.search("zorblat", own=tmp_path)
    assert found[0].icon.name == "pallet-jack"
    assert found[0].icon.source == "organization"


def test_every_synonym_points_at_a_real_current_icon():
    synonyms = json.loads(icons.SYNONYMS.read_text(encoding="utf-8"))
    assert set(synonyms) == {"es", "ca"}
    catalogue = icons.catalogue()
    for language, words in synonyms.items():
        assert len(words) >= 80, language
        normalised = [icons.normalise(word) for word in words]
        assert len(normalised) == len(set(normalised)), language
        for word, names in words.items():
            for name in names:
                assert name in catalogue, (language, word, name)
                assert not catalogue[name].deprecated, (language, word, name)


@pytest.mark.base  # the base's own machinery: an application cannot change it while the base is as made
def test_lucides_english_tags_alone_find_few_spanish_or_catalan_words():
    """Why the synonyms exist: without them, most common business words find nothing useful."""
    synonyms = json.loads(icons.SYNONYMS.read_text(encoding="utf-8"))
    for words in synonyms.values():
        found = sum(bool(set(names) & set(names_found(word, synonyms={})[:10])) for word, names in words.items())
        assert found / len(words) < 0.5


def test_the_search_tool_runs_from_the_command_line():
    result = subprocess.run(
        [sys.executable, "tools/icons.py", "search", "camió"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert re.search(r"^truck\b", result.stdout, re.M)


# Illustrations


SAFE_ILLUSTRATION = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60"><defs><linearGradient id="g">'
    '<stop offset="0" stop-color="#246"/></linearGradient></defs>'
    "<style>@keyframes move { to { transform: translateX(160px) } } .box { animation: move 2s infinite }</style>"
    '<rect class="box" width="40" height="40" fill="url(#g)"><animate attributeName="x" values="0;160" dur="2s"/>'
    "</rect></svg>"
)


@pytest.mark.rule("SEC-16")
def test_an_animated_self_contained_illustration_is_safe():
    assert icons.unsafe(SAFE_ILLUSTRATION) == []


@pytest.mark.rule("SEC-16")
@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (("<defs>", "<script>alert(1)</script><defs>"), "a <script>"),
        (("<defs>", '<script xmlns="http://www.w3.org/1999/xhtml">alert(1)</script><defs>'), "outside SVG"),
        (('<rect class="box"', '<rect onload="alert(1)" class="box"'), "an event attribute: onload"),
        (('<rect class="box"', '<a href="javascript:alert(1)"><rect/></a><rect class="box"'), "javascript:"),
        (('<rect class="box"', '<image href="data:image/svg+xml;base64,PHN2Zz4="/><rect class="box"'), "outside"),
        (('<rect class="box"', '<image href="https://example.com/a.png"/><rect class="box"'), "outside the file"),
        (
            ('<rect class="box"', '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="other.svg#a"/><rect'),
            "outside the file",
        ),
        (('fill="url(#g)"', 'fill="url(https://example.com/a.svg#g)"'), "outside the file"),
        (("<style>", "<style>@import url(/static/ui/app.css);"), "@import"),
        (("@keyframes", ".a { background: url(//example.com/a.png) } @keyframes"), "outside the file"),
        (('<rect class="box"', '<foreignObject><p>text</p></foreignObject><rect class="box"'), "<foreignObject>"),
        (("<svg xmlns", '<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns'), "DOCTYPE"),
        (("<svg xmlns", '<?xml-stylesheet href="https://example.com/a.css"?><svg xmlns'), "xml-stylesheet"),
        (('attributeName="x" values="0;160"', 'attributeName="href" values="javascript:alert(1)"'), "javascript:"),
        (("</svg>", ""), "not well-formed"),
    ],
)
def test_an_illustration_that_could_run_or_load_something_is_named_with_why(change, reason):
    found = icons.unsafe(SAFE_ILLUSTRATION.replace(*change, 1))
    assert any(reason in problem for problem in found), found


@pytest.mark.rule("SEC-16")
def test_a_raster_image_inside_an_illustration_is_allowed():
    picture = '<image href="data:image/png;base64,iVBORw0KGgo=" width="10" height="10"/>'
    assert icons.unsafe(SAFE_ILLUSTRATION.replace("<defs>", picture + "<defs>")) == []


@pytest.mark.rule("SEC-16")
def test_every_image_file_the_base_shows_is_checked_and_named(tmp_path):
    folder = tmp_path / "ui" / "static" / "illustrations" / "people"
    folder.mkdir(parents=True)
    (folder / "team.svg").write_text(SAFE_ILLUSTRATION.replace("<defs>", "<script>x</script><defs>"), "utf-8")
    (tmp_path / "brand").mkdir()
    (tmp_path / "brand" / "logo.svg").write_text(SAFE_ILLUSTRATION, encoding="utf-8")
    assert icons.image_problems(tmp_path) == ["ui/static/illustrations/people/team.svg: a <script>"]


@pytest.mark.rule("SEC-16")
def test_the_illustrations_have_their_place_and_no_page_inlines_one():
    assert icons.ILLUSTRATIONS.is_dir()
    assert icons.image_problems() == []
    for template in (ROOT / "app").rglob("*.html"):
        assert "illustrations/" not in re.sub(r'(?:src|href)="[^"]*"', "", template.read_text(encoding="utf-8"))


ANIMATED = {
    "smil": '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">'
    '<rect width="200" height="60" fill="#eee"/><rect y="10" width="40" height="40" fill="#246">'
    '<animate attributeName="x" values="0;160;0" dur="2s" repeatCount="indefinite"/></rect></svg>',
    "css": '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">'
    "<style>@keyframes move { from { transform: translateX(0) } to { transform: translateX(160px) } }"
    ".box { animation: move 2s linear infinite alternate }</style>"
    '<rect width="200" height="60" fill="#eee"/><rect class="box" y="10" width="40" height="40" fill="#246"/></svg>',
    "still": '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">'
    '<rect width="200" height="60" fill="#eee"/><rect y="10" width="40" height="40" fill="#246"/></svg>',
}


@pytest.mark.browser
@pytest.mark.rule("SEC-16")
@pytest.mark.base  # the base's own machinery: an application cannot change it while the base is as made
def test_an_animated_illustration_moves_in_a_page_under_the_policy(browser, tmp_path):
    """Served as the application serves its static files, with the same policy on the page and on the SVG. An image
    never runs scripts, and Chrome applies the page's policy to it, not the SVG's: SMIL and a <style> block animate."""
    from app.main import create_app
    from tests.conftest import build_settings, running_server

    for name, text in ANIMATED.items():
        (tmp_path / f"{name}.svg").write_text(text, encoding="utf-8")
        assert icons.unsafe(text) == []
    (tmp_path / "probe.css").write_text(
        "".join(f".bg-{name} {{ width: 200px; height: 60px; background: url({name}.svg) }}" for name in ANIMATED),
        encoding="utf-8",
    )
    application = create_app(build_settings(fake_identity=True, fake_groups=["admins"], trusted_proxies=[]))
    application.router.routes.insert(0, Mount("/static/ui/illustrations", StaticFiles(directory=tmp_path)))
    body = "".join(
        f'<img id="img-{name}" src="/static/ui/illustrations/{name}.svg" alt="" width="200" height="60">'
        f'<div id="bg-{name}" class="bg-{name}"></div>'
        for name in ANIMATED
    )

    async def page() -> HTMLResponse:
        head = '<link rel="stylesheet" href="/static/ui/illustrations/probe.css">'
        return HTMLResponse(f"<!doctype html><html lang=en><head><title>t</title>{head}</head><body>{body}</body>")

    application.add_api_route("/illustrations-probe", page)
    with running_server(application) as port:
        context = browser.new_context()
        try:
            opened = context.new_page()
            response = opened.goto(f"http://127.0.0.1:{port}/illustrations-probe")
            assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
            svg = context.request.get(f"http://127.0.0.1:{port}/static/ui/illustrations/css.svg")
            assert svg.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
            opened.wait_for_timeout(300)
            first = {
                f"{kind}-{name}": opened.locator(f"#{kind}-{name}").screenshot()
                for kind in ("img", "bg")
                for name in ANIMATED
            }
            opened.wait_for_timeout(700)
            moved = {key for key, shot in first.items() if opened.locator(f"#{key}").screenshot() != shot}
            assert moved == {"img-smil", "img-css", "bg-smil", "bg-css"}
        finally:
            context.close()


def test_a_check_of_the_real_folders_runs_from_the_command_line():
    result = subprocess.run([sys.executable, "tools/icons.py", "check"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_vendor_check_covers_only_lucides_folder():
    folders = [entry["folder"] for entry in vendor.read_entries().values() if "folder" in entry]
    assert folders == ["app/ui/templates/ui/icons"]
    assert Path("app/brand/icons").as_posix() not in json.dumps(vendor.read_entries())


TIMELINE = '{% macro gantt(identifier) %}<svg viewBox="0 0 10 10"><rect width="1" height="1"/></svg>{% endmacro %}'


@pytest.mark.rule("COMP-05")
def test_the_gantt_chart_is_the_one_picture_drawn_inline_and_only_in_its_macro(tmp_path):
    macros = tmp_path / "ui" / "templates" / "ui" / "macros.html"
    macros.parent.mkdir(parents=True)
    macros.write_text(TIMELINE, encoding="utf-8")
    assert icons.drawn_by_hand(tmp_path) == []
    macros.write_text(TIMELINE + '{% macro badge() %}<svg viewBox="0 0 24 24"></svg>{% endmacro %}', encoding="utf-8")
    assert len(icons.drawn_by_hand(tmp_path)) == 1
    elsewhere = tmp_path / "ui" / "templates" / "page.html"
    macros.write_text("", encoding="utf-8")
    elsewhere.write_text(TIMELINE, encoding="utf-8")
    assert icons.drawn_by_hand(tmp_path)[0].startswith("ui/templates/page.html")


@pytest.mark.rule("SEC-16")
def test_a_timelines_picture_holds_nothing_that_runs_or_loads():
    plan = timeline(
        [
            None,
            Task(1, "<script>", date(2026, 11, 2), date(2026, 11, 4)),
            Task(2, "B", date(2026, 11, 6), date(2026, 11, 6), after=(1,)),
        ],
        "day",
        date(2026, 11, 3),
    )
    macros = environment.get_template("ui/macros.html").module
    html = str(macros.gantt("plan", "Plan", plan, [("Work", False)], "Summary", caller=lambda: ""))
    picture = html[html.index('<svg id="plan-picture"') : html.rindex("</svg>") + 6].replace(
        "<svg ", f'<svg xmlns="{icons.SVG}" ', 1
    )
    assert icons.unsafe(picture) == []
    assert "&lt;script&gt;" in picture
