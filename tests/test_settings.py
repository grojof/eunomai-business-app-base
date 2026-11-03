"""The settings menu: real shell code, kept by every application unless its settings hide it."""

import re

import pytest
from babel import Locale
from fastapi.testclient import TestClient

from app.core.i18n import PSEUDO
from app.core.settings import LAYOUTS, Settings
from app.main import create_app
from tests.conftest import build_settings
from tests.helpers import ROOT, focus_order, overflows_sideways, run_axe, untranslated
from tools import translations

THEME_CONTROLS = LAYOUTS["theme_control"]
LANGUAGE_CONTROLS = LAYOUTS["language_control"]
ALLOWED = ("Business App", "Demo Person")


def choose(client, person, **fields):
    return client.post("/preferences", data=fields, headers=person, follow_redirects=False)


def with_settings(**overrides):
    return TestClient(create_app(build_settings(**overrides)))


def test_a_choice_is_saved_and_applied(client, person):
    response = choose(client, person, layout_navigation="top", layout_density="compact", layout_theme_control="swap")
    assert {"layout_navigation", "layout_density", "layout_theme_control"} <= set(response.cookies)
    html = client.get("/settings", headers=person).text
    assert 'data-density="compact"' in html
    assert "swap swap-rotate" in html


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("layout_navigation", "sideways"),
        ("layout_density", "tiny"),
        ("layout_theme_control", "wheel"),
        ("layout_language_control", "flags"),
        ("layout_theme_control", ""),
    ],
)
def test_only_listed_values_are_accepted(client, person, field, value):
    assert field not in choose(client, person, **{field: value}).cookies


def test_a_forged_cookie_changes_nothing(client, person):
    client.cookies.set("layout_theme_control", "<script>")
    client.cookies.set("layout_navigation", "sideways")
    html = client.get("/", headers=person).text
    assert "<script>\n" not in html.split("</head>")[1]
    assert "sideways" not in html
    assert "layout_navigation" not in client.get("/", headers=person).cookies


def test_settings_fix_the_starting_look():
    client = with_settings(layout_theme_control="radio", layout_language_control="menu")
    html = client.get("/settings", headers={"X-Remote-User": "someone"}).text
    assert 'data-preferences="header-theme"' in html
    assert "radio radio-sm" in html.split("<main")[0]
    assert "menu-horizontal" in html.split("<main")[0]


def test_an_unknown_choice_in_the_settings_stops_the_application():
    with pytest.raises(ValueError, match="unknown names"):
        Settings(layout_choices=["wallpaper"], _env_file=None)  # type: ignore[call-arg]


def test_an_application_can_hide_the_menu():
    client = with_settings(layout_choices=[])
    person = {"X-Remote-User": "someone"}
    assert client.get("/settings", headers=person).status_code == 404
    assert 'href="/settings"' not in client.get("/", headers=person).text
    assert "/settings" not in client.get("/search", headers=person).text
    client.post("/preferences", data={"layout_navigation": "top"}, headers=person)
    client.cookies.set("layout_density", "compact")
    assert 'data-density="normal"' in client.get("/", headers=person).text
    assert "lg:menu-horizontal" not in client.get("/", headers=person).text


def test_an_application_can_fix_some_choices():
    client = with_settings(layout_choices=["navigation"], layout_density="compact")
    person = {"X-Remote-User": "someone"}
    client.cookies.set("layout_density", "normal")
    html = client.get("/settings", headers=person).text
    assert 'data-density="compact"' in html
    assert 'name="layout_navigation"' in html
    assert 'name="layout_density"' not in html
    assert 'name="layout_theme_control"' not in html


def test_the_menu_is_in_the_user_menu_and_the_palette(client, person):
    assert 'href="/settings"' in client.get("/", headers=person).text
    assert 'href="/settings"' in client.get("/search", headers=person).text


def test_a_two_state_control_sends_light_unless_its_box_is_ticked(client, person):
    response = client.post(
        "/preferences",
        data={"theme": ["light", "dark"]},
        headers=person,
        follow_redirects=False,
    )
    assert response.cookies["theme"] == "dark"
    assert choose(client, person, theme="light").cookies["theme"] == "light"


def test_the_page_needs_no_inline_code(client, person):
    html = client.get("/settings", headers=person).text
    assert " style=" not in html
    assert " onclick=" not in html


@pytest.mark.rule("LANG-01")
def test_the_settings_are_translated(client, person):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get("/settings", headers=person).text, ALLOWED) == []


pages = pytest.mark.browser


@pages
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1280, 390])
def test_the_settings_pass_the_scan_with_every_control_on_the_page(open_page, theme, width):
    assert run_axe(open_page("/settings", theme=theme, width=width, bypass_csp=True)) == []


@pages
@pytest.mark.rule("A11Y-01")
@pytest.mark.parametrize("control", THEME_CONTROLS)
@pytest.mark.parametrize("language", LANGUAGE_CONTROLS)
def test_each_look_of_the_controls_passes_the_scan_in_the_shell(open_page, control, language):
    layout = {"theme_control": control, "language_control": language}
    assert run_axe(open_page("/", layout=layout, bypass_csp=True)) == []
    assert run_axe(open_page("/", layout=layout, theme="dark", width=390, bypass_csp=True)) == []


@pages
@pytest.mark.rule("A11Y-12")
@pytest.mark.parametrize("control", [*THEME_CONTROLS, *LANGUAGE_CONTROLS])
def test_each_look_fits_a_phone(open_page, control):
    field = "theme_control" if control in THEME_CONTROLS else "language_control"
    page = open_page("/settings", width=320, layout={field: control})
    assert not overflows_sideways(page)
    page.get_by_role("group").first.wait_for(state="attached")


@pages
@pytest.mark.rule("A11Y-02")
def test_focus_follows_the_order_of_a_page_of_controls(open_page):
    expected, reached = focus_order(open_page("/settings"))
    assert len(expected) > 20
    assert reached == expected


def header(page, kind):
    return page.locator(f"[data-preferences='header-{kind}']")


def current_theme(page):
    return page.evaluate("document.documentElement.dataset.theme")


@pages
@pytest.mark.rule("A11Y-02")
@pytest.mark.parametrize("control", ["toggle", "swap"])
def test_a_two_state_theme_control_works_with_the_keyboard(open_page, control):
    page = open_page("/", layout={"theme_control": control})
    box = header(page, "theme").get_by_role("checkbox", name="Dark theme")
    box.focus()
    with page.expect_navigation():
        page.keyboard.press("Space")
    assert current_theme(page) == "dark"
    assert page.evaluate("document.activeElement.name") == "theme"
    with page.expect_navigation():
        page.keyboard.press("Space")
    assert current_theme(page) == "light"


@pages
@pytest.mark.rule("A11Y-02")
def test_the_radio_theme_control_works_with_the_keyboard(open_page):
    page = open_page("/", layout={"theme_control": "radio"})
    assert header(page, "theme").get_by_role("group", name="Theme").is_visible()
    header(page, "theme").get_by_role("radio", name="Light").focus()
    with page.expect_navigation():
        page.keyboard.press("ArrowRight")
    assert current_theme(page) == "dark"
    assert page.evaluate("document.activeElement.value") == "dark"


@pages
@pytest.mark.rule("A11Y-02")
def test_the_dropdown_theme_control_works_with_the_keyboard(open_page):
    page = open_page("/")
    header(page, "theme").locator("summary").press("Enter")
    choice = header(page, "theme").get_by_role("radio", name="Light")
    assert choice.is_visible()
    choice.focus()
    with page.expect_navigation():
        page.keyboard.press("ArrowDown")
    assert current_theme(page) == "dark"
    assert page.evaluate("document.activeElement.value") == "dark"
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.tagName") == "SUMMARY"


@pages
@pytest.mark.rule("A11Y-02")
@pytest.mark.parametrize("control", ["dropdown", "menu"])
def test_a_language_control_of_buttons_works_with_the_keyboard(open_page, control):
    page = open_page("/", layout={"language_control": control})
    if control == "dropdown":
        header(page, "language").locator("summary").press("Enter")
    language = translations.REQUIRED[-1]  # whichever languages the application kept
    name = Locale.parse(language).get_display_name(language) or language
    choice = header(page, "language").get_by_role("button", name=name[:1].upper() + name[1:])
    with page.expect_navigation():
        choice.press("Enter")
    assert page.locator("html").get_attribute("lang") == language
    assert page.evaluate("document.activeElement.value") == language


@pages
@pytest.mark.rule("A11Y-02")
def test_the_language_select_waits_for_its_button(open_page):
    page = open_page("/", layout={"language_control": "select"})
    select = header(page, "language").get_by_role("combobox", name="Language")
    select.select_option(translations.REQUIRED[0])
    page.wait_for_timeout(100)
    assert page.locator("html").get_attribute("lang") == "en"
    with page.expect_navigation():
        header(page, "language").get_by_role("button", name="Apply").press("Enter")
    assert page.locator("html").get_attribute("lang") == translations.REQUIRED[0]


@pages
@pytest.mark.rule("A11Y-04")
def test_a_swap_shows_where_focus_is(open_page):
    page = open_page("/", layout={"theme_control": "swap"})
    header(page, "theme").get_by_role("checkbox").focus()
    page.keyboard.press("Tab")
    page.keyboard.press("Shift+Tab")
    outline = "getComputedStyle(document.activeElement.closest('.swap')).outlineStyle"
    assert page.evaluate(outline) == "solid"


@pages
def test_a_toggle_follows_the_system_when_the_theme_does(browser, base_url):
    context = browser.new_context(color_scheme="dark")
    context.add_cookies([{"name": "layout_theme_control", "value": "toggle", "url": base_url}])
    page = context.new_page()
    page.goto(base_url)
    assert page.locator("[data-preferences='header-theme'] input[type=checkbox]").is_checked()
    context.close()


@pages
@pytest.mark.parametrize("navigation", LAYOUTS["navigation"])
def test_a_person_can_try_each_arrangement(open_page, navigation):
    page = open_page("/settings", layout={"navigation": "side" if navigation != "side" else "top"})
    names = {"side": "Side", "compact": "Icons only", "top": "Top", "hidden": "Hidden"}
    with page.expect_navigation():
        page.get_by_role("button", name=names[navigation], exact=True).click()
    assert page.get_by_role("button", name=names[navigation], exact=True).get_attribute("aria-pressed") == "true"
    assert not overflows_sideways(page)


@pages
@pytest.mark.parametrize("control", THEME_CONTROLS)
def test_a_style_chosen_reaches_the_header(open_page, control):
    page = open_page("/settings", layout={"theme_control": "radio" if control != "radio" else "toggle"})
    card = page.locator(f"[data-preferences='layout_theme_control-{control}']")
    with page.expect_navigation():
        card.get_by_role("button").click()
    shown = {"dropdown": "details", "toggle": ".toggle", "swap": ".swap", "radio": "fieldset"}[control]
    assert header(page, "theme").locator(shown).is_visible()
    assert card.get_by_role("button").get_attribute("aria-pressed") == "true"


def test_without_scripts_the_controls_that_need_them_change_places():
    """Chrome keeps the `scripting` media feature on when automation turns scripts off, so the rule itself is read."""
    built = (ROOT / "app" / "ui" / "static" / "app.css").read_text(encoding="utf-8")
    rules = "".join(re.findall(r"@media \(scripting:none\)\{(.*?\})\}", built))
    assert r"noscript\:hidden{display:none}" in rules
    assert r"noscript\:inline-flex{display:inline-flex}" in rules
    control = (ROOT / "app" / "ui" / "templates" / "ui" / "theme_control.html").read_text(encoding="utf-8")
    assert "hidden noscript:inline-flex" in control


@pytest.mark.parametrize(
    ("field", "value"),
    [("layout_page_title", "header"), ("layout_list_width", "wide"), ("layout_list_density", "dense")],
)
def test_the_title_and_the_lists_are_choices_too(client, person, field, value):
    assert choose(client, person, **{field: value}).cookies[field] == value
    assert field not in choose(client, person, **{field: "huge"}).cookies
    assert f'name="{field}"' in client.get("/settings", headers=person).text


def headings(client, person, navigation, title="header", path="/settings"):
    client.cookies.set("layout_navigation", navigation)
    client.cookies.set("layout_page_title", title)
    html = client.get(path, headers=person).text
    header, main = html.split("<main", 1)
    return header.count("<h1"), main.count("<h1")


@pytest.mark.parametrize("navigation", ["side", "compact", "hidden"])
def test_the_title_can_go_to_the_top_bar_and_stays_the_one_h1(client, person, navigation):
    assert headings(client, person, navigation) == (1, 0)
    assert headings(client, person, navigation, "page") == (0, 1)


def test_with_navigation_at_the_top_the_title_stays_in_the_page(client, person):
    assert headings(client, person, "top") == (0, 1)


def test_a_page_with_a_heading_of_its_own_keeps_it(client, person):
    assert headings(client, person, "side", path="/nowhere") == (0, 1)


def test_an_application_can_fix_where_the_title_goes():
    client = with_settings(layout_choices=[], layout_page_title="header")
    person = {"X-Remote-User": "someone"}
    client.cookies.set("layout_page_title", "page")
    assert '<h1 class="page-title-bar' in client.get("/", headers=person).text


TITLE_LAYOUTS = [
    {"navigation": navigation, "page_title": "header", "sticky_header": sticky}
    for navigation in ("side", "compact", "top", "hidden")
    for sticky in ("on", "off")
]


@pages
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("layout", TITLE_LAYOUTS)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_title_in_the_top_bar_passes_the_scan(open_page, layout, theme):
    page = open_page("/settings", theme=theme, layout=layout, bypass_csp=True)
    assert page.locator("h1").count() == 1
    assert page.locator("h1").is_visible()
    assert run_axe(page) == []


@pages
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
@pytest.mark.parametrize("layout", TITLE_LAYOUTS)
def test_a_title_in_the_top_bar_fits_a_phone(open_page, layout):
    page = open_page("/settings", language=PSEUDO, layout=layout, width=320)
    assert not overflows_sideways(page)
    assert page.locator("h1").is_visible()


@pages
def test_a_title_in_the_top_bar_stays_on_paper(open_page):
    page = open_page("/settings", layout={"page_title": "header"})
    page.emulate_media(media="print")
    assert page.locator("h1").is_visible()
    assert not page.get_by_role("button", name="Open menu").is_visible()
