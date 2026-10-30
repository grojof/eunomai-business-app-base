"""The gallery shows every component, tells the truth about each, and works under the application's own rules."""

import re

import pytest

from app.core.i18n import PSEUDO
from app.ui.catalog import CATEGORIES, PROBLEMS, components
from tests.helpers import focus_order, overflows_sideways, run_axe, specimen_contents, untranslated

SLUGS = sorted(CATEGORIES)
ALLOWED = ("Business App", "Demo Person", "AB", "example.org")


@pytest.mark.rule("COMP-03")
def test_every_component_is_shown_with_its_status(client, person):
    shown = {}
    for slug in SLUGS:
        html = client.get(f"/gallery/{slug}", headers=person).text
        shown |= dict(re.findall(r'<section id="([a-z0-9-]+)"[^>]*data-status="([a-z]+)"', html))
    assert shown == {name: component.status for name, component in components().items()}


@pytest.mark.rule("COMP-03")
def test_every_specimen_has_something_to_show(client, person):
    contents = {}
    for slug in SLUGS:
        contents |= specimen_contents(client.get(f"/gallery/{slug}", headers=person).text)
    assert set(contents) == set(components())
    assert [name for name, content in contents.items() if not content] == []


@pytest.mark.rule("COMP-03")
def test_the_specimen_check_sees_an_empty_one():
    html = '<section id="empty" data-status="available"><div data-specimen>  </div></section>'
    assert specimen_contents(html) == {"empty": ""}


def test_the_index_counts_every_category(client, person):
    html = client.get("/gallery", headers=person).text
    for slug in SLUGS:
        assert f'href="/gallery/{slug}"' in html


def test_an_unknown_category_is_not_found(client, person):
    assert client.get("/gallery/nothing", headers=person).status_code == 404


@pytest.mark.rule("SEC-06")
@pytest.mark.parametrize("slug", SLUGS)
def test_no_specimen_needs_inline_code_or_another_server(client, person, slug):
    html = client.get(f"/gallery/{slug}", headers=person).text
    assert " style=" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert not re.search(r"""(?:src|href)=["'](?:https?:)?//""", html)


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", ["/gallery", *(f"/gallery/{slug}" for slug in SLUGS)])
def test_no_gallery_page_has_text_outside_translation(client, person, path):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get(path, headers=person).text, ALLOWED) == []


@pytest.mark.browser
@pytest.mark.rule("COMP-03")
@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_only_components_marked_with_problems_may_fail_the_scan(open_page, slug, theme):
    page = open_page(f"/gallery/{slug}", theme=theme, bypass_csp=True)
    assert run_axe(page, exclude=f'[data-status="{PROBLEMS}"]') == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.parametrize("slug", SLUGS)
def test_every_category_fits_a_phone(open_page, slug):
    assert not overflows_sideways(open_page(f"/gallery/{slug}", width=320))


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_a_dialog_opens_without_inline_code_and_returns_focus(open_page):
    page = open_page("/gallery/actions")
    opener = page.locator('[data-dialog="sample-dialog"]')
    opener.press("Enter")
    page.locator("#sample-dialog").wait_for(state="visible")
    page.keyboard.press("Escape")
    page.locator("#sample-dialog").wait_for(state="hidden")
    assert opener.evaluate("element => element === document.activeElement")


@pytest.mark.browser
@pytest.mark.rule("A11Y-02")
def test_focus_follows_the_order_of_a_page_of_controls(open_page):
    expected, reached = focus_order(open_page("/gallery/actions"))
    assert len(expected) > 10
    assert reached == expected


@pytest.mark.browser
@pytest.mark.rule("A11Y-04")
def test_focus_and_links_stop_clear_of_the_sticky_header(open_page):
    clear = """() => {
        const header = document.querySelector("body header").getBoundingClientRect().bottom;
        const element = location.hash ? document.querySelector(location.hash) : document.activeElement;
        return element.getBoundingClientRect().top >= header;
    }"""
    page = open_page("/gallery/data-input#validator")
    assert page.evaluate("window.scrollY") > 0
    assert page.evaluate(clear)
    page = open_page("/gallery/data-input")
    for key in [*["Tab"] * 45, *["Shift+Tab"] * 35]:
        page.keyboard.press(key)
        if page.evaluate("document.activeElement.closest('main') !== null"):
            assert page.evaluate(clear), page.evaluate("document.activeElement.outerHTML")


@pytest.mark.browser
def test_values_written_by_script_reach_the_component(open_page):
    page = open_page("/gallery/feedback")
    radial = page.locator(".radial-progress")
    assert radial.evaluate("element => element.style.getPropertyValue('--value')") == "70"
