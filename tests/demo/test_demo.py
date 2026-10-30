import pytest

from app.core.i18n import PSEUDO
from tests.helpers import overflows_sideways, run_axe, untranslated

PAGES = ["/", "/catalogue", "/administration"]
ALLOWED = ("Business App", "Demo Person")


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", [*PAGES, "/inspections"])
def test_no_demo_page_has_text_outside_translation(client, person, path):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get(path, headers=person).text, ALLOWED) == []


@pytest.mark.rule("SEC-02")
def test_administration_needs_its_role(client, person):
    assert client.get("/administration", headers=person).status_code == 200
    person["X-Remote-Groups"] = "staff"
    assert client.get("/administration", headers=person).status_code == 403


@pytest.mark.rule("SEC-02")
def test_navigation_shows_only_what_the_person_may_open(client, person):
    assert 'href="/administration"' in client.get("/", headers=person).text
    person["X-Remote-Groups"] = "staff"
    assert 'href="/administration"' not in client.get("/", headers=person).text


def test_the_current_page_is_marked_for_screen_readers(client, person):
    assert 'href="/catalogue" aria-current="page"' in client.get("/catalogue", headers=person).text


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "1,250.75"), ("es", "1250,75"), ("ca", "1.250,75")],
)
def test_the_dashboard_formats_numbers_for_the_language(client, person, language, expected):
    client.cookies.set("language", language)
    assert expected in client.get("/", headers=person).text


def test_a_long_decimal_reaches_the_page_exactly(client, person):
    assert "12,500.1234567890123456789" in client.get("/", headers=person).text


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_detectable_accessibility_failure(open_page, path, theme):
    assert run_axe(open_page(path, theme=theme, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
@pytest.mark.parametrize("path", PAGES)
def test_no_sideways_scrolling_with_longer_texts(open_page, path):
    assert not overflows_sideways(open_page(path, language=PSEUDO, width=320))


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_new_content_gets_focus_and_is_announced(open_page):
    page = open_page("/")
    page.get_by_role("button", name="Show inspections").click()
    page.wait_for_selector(":focus[data-focus]")
    assert "1 inspection is due" in page.locator("#announcements").inner_text()
