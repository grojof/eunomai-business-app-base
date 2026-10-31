"""The form components in a real browser: the gallery's specimens, under the application's own policy."""

import pytest

from tests.demo.support import until
from tests.helpers import overflows_sideways, run_axe

SPECIMENS = (
    "input",
    "textarea",
    "select",
    "checkbox",
    "radio",
    "file-input",
    "date-field",
    "number-field",
    "searchable-select",
    "error-summary",
    "field-error",
    "form-actions",
)
OWN_PAGES = ("date-field", "number-field", "searchable-select", "error-summary", "field-error", "form-actions")
"""Pages with no official examples, so a scan reads only what is ours. The others have the frame's exclusions."""
FRAME_EXCLUDES = ("[data-official]", ".gallery-thumb")
SEARCHABLE = "/gallery/searchable-select"
BOX = "#sample-equipment"


def source_value(page, name="sample-equipment"):
    return page.evaluate(f"document.querySelector('select[name={name}]').value")


def listed(page):
    return page.locator(f"{BOX}-options [role=option]:visible").all_inner_texts()


def is_open(page):
    return page.locator(BOX).get_attribute("aria-expanded") == "true"


@pytest.fixture
def box(open_page):
    page = open_page(SEARCHABLE)
    page.locator(BOX).focus()
    return page


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.parametrize("name", OWN_PAGES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_each_own_specimen_passes_the_scan(open_page, name, theme):
    assert run_axe(open_page(f"/gallery/{name}", theme=theme, bypass_csp=True), exclude=FRAME_EXCLUDES) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_open_list_passes_the_scan(open_page, theme):
    page = open_page(SEARCHABLE, theme=theme, bypass_csp=True)
    page.locator(BOX).press("ArrowDown")
    assert run_axe(page, exclude=FRAME_EXCLUDES) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.parametrize("name", SPECIMENS)
def test_each_specimen_fits_a_phone(open_page, name):
    assert not overflows_sideways(open_page(f"/gallery/{name}", width=320))


@pytest.mark.browser
def test_the_combobox_follows_the_aria_pattern(open_page):
    page = open_page(SEARCHABLE)
    box = page.locator(BOX)
    assert box.get_attribute("role") == "combobox"
    assert box.get_attribute("aria-autocomplete") == "list"
    assert box.get_attribute("aria-expanded") == "false"
    assert box.get_attribute("aria-controls") == "sample-equipment-options"
    assert page.get_by_label("Equipment", exact=True).first.get_attribute("id") == "sample-equipment"
    assert page.locator("#sample-equipment-options").get_attribute("role") == "listbox"
    assert not page.locator("select[name=sample-equipment]").is_visible()


@pytest.mark.browser
def test_it_shows_what_is_chosen_and_keeps_what_the_form_sends(open_page):
    page = open_page(SEARCHABLE)
    assert page.locator(BOX).input_value() == "Conveyor belt"
    assert source_value(page) == "b"


@pytest.mark.browser
def test_the_arrow_keys_open_the_list_and_move_through_it(box):
    box.keyboard.press("ArrowDown")
    assert is_open(box)
    assert len(listed(box)) == 6
    active = box.locator(BOX).get_attribute("aria-activedescendant")
    assert box.evaluate(f"document.getElementById('{active}').getAttribute('aria-selected')") == "true"
    assert box.evaluate("document.activeElement.id") == "sample-equipment"
    box.keyboard.press("ArrowDown")
    second = box.locator(BOX).get_attribute("aria-activedescendant")
    assert second != active
    assert box.locator(f"#{active}").get_attribute("aria-selected") == "false"


@pytest.mark.browser
def test_up_from_nothing_goes_to_the_last_option_and_it_wraps(box):
    box.keyboard.press("ArrowUp")
    assert box.locator("[aria-selected=true]").inner_text() == "Standby generator"
    box.keyboard.press("ArrowDown")
    assert box.locator("[aria-selected=true]").inner_text() == "None"


@pytest.mark.browser
def test_typing_narrows_the_list_and_enter_chooses(box):
    box.locator(BOX).fill("")
    box.keyboard.type("tow")
    assert listed(box) == ["Cooling tower"]
    box.keyboard.press("ArrowDown")
    box.keyboard.press("Enter")
    assert not is_open(box)
    assert box.locator(BOX).input_value() == "Cooling tower"
    assert source_value(box) == "c"


@pytest.mark.browser
def test_a_match_ignores_capitals_and_accents(open_page):
    page = open_page(SEARCHABLE, language="es")
    box = page.locator(BOX)
    box.fill("")
    page.keyboard.type("COMPRE")
    assert listed(page) == ["Compresor de aire"]
    box.fill("")
    page.keyboard.type("carretilla")
    assert listed(page) == ["Carretilla elevadora"]


@pytest.mark.browser
def test_a_word_that_matches_nothing_says_so_and_a_screen_reader_hears_it(box):
    box.locator(BOX).fill("")
    box.keyboard.type("zzz")
    assert listed(box) == []
    assert box.locator("[data-combobox-none]:visible").count() == 1
    until(box, "document.querySelector('#announcements').textContent.includes('0')")


@pytest.mark.browser
def test_escape_closes_the_list_and_a_second_escape_empties_the_box(box):
    box.keyboard.press("ArrowDown")
    box.keyboard.press("Escape")
    assert not is_open(box)
    assert box.locator(BOX).input_value() == "Conveyor belt"
    box.keyboard.press("Escape")
    assert box.locator(BOX).input_value() == ""


@pytest.mark.browser
def test_text_that_matches_nothing_goes_back_to_what_was_chosen(box):
    box.locator(BOX).fill("")
    box.keyboard.type("zzz")
    box.keyboard.press("Tab")
    assert box.locator(BOX).input_value() == "Conveyor belt"
    assert source_value(box) == "b"


@pytest.mark.browser
def test_an_empty_box_means_nothing_is_chosen(box):
    box.locator(BOX).fill("")
    box.keyboard.press("Tab")
    assert source_value(box) == ""


@pytest.mark.browser
def test_tab_chooses_the_option_the_arrows_are_on_and_leaves(box):
    box.keyboard.press("ArrowDown")
    box.keyboard.press("ArrowDown")
    box.keyboard.press("Tab")
    assert not is_open(box)
    assert source_value(box) == "a"
    assert box.evaluate("document.activeElement.id") != "sample-equipment"


@pytest.mark.browser
def test_alt_and_the_arrows_open_and_close_without_moving(box):
    box.keyboard.press("Alt+ArrowDown")
    assert is_open(box)
    assert box.locator(BOX).get_attribute("aria-activedescendant") is None
    box.keyboard.press("Alt+ArrowUp")
    assert not is_open(box)


@pytest.mark.browser
def test_a_click_opens_the_list_and_chooses_keeping_focus_in_the_box(open_page):
    page = open_page(SEARCHABLE)
    page.get_by_role("button", name="Show the options").first.click()
    assert is_open(page)
    assert page.evaluate("document.activeElement.id") == "sample-equipment"
    page.locator(f"{BOX}-options [role=option]", has_text="Forklift").click()
    assert not is_open(page)
    assert page.locator(BOX).input_value() == "Forklift"
    assert source_value(page) == "d"


@pytest.mark.browser
def test_the_error_summary_can_land_on_a_searchable_select(open_page):
    page = open_page(SEARCHABLE)
    wrong = page.locator("#sample-wrong")
    assert wrong.get_attribute("role") == "combobox"
    assert wrong.get_attribute("aria-invalid") == "true"
    assert wrong.get_attribute("aria-describedby") == "sample-wrong-error"


@pytest.mark.browser
def test_without_javascript_it_is_a_plain_select(open_page):
    page = open_page(SEARCHABLE, javascript=False)
    select = page.locator("select[name=sample-equipment]")
    assert select.is_visible()
    assert page.locator("[data-combobox] [role=combobox]").count() == 0
    select.select_option("c")
    assert select.input_value() == "c"
    assert page.get_by_label("Equipment", exact=True).first.evaluate("element => element.tagName") == "SELECT"


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_it_works_under_the_security_policy(open_page):
    problems = []
    page = open_page(SEARCHABLE)
    page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.locator(BOX).press("ArrowDown")
    page.keyboard.press("Enter")
    assert problems == []
