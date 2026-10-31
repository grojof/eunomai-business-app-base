"""The form macros on their own: what stays in an application after the demo is deleted."""

import re
from collections.abc import Callable

import pytest
from markupsafe import Markup, escape

from app.core.templating import environment

MACROS = environment.get_template("ui/macros.html").module
OPTIONS = [("a", "First"), ("b", "Second")]
FIELDS: dict[str, Callable[..., Markup]] = {
    "text": lambda **given: MACROS.input_field("box", "Box", "", "box", **given),
    "textarea": lambda **given: MACROS.textarea_field("box", "Box", "", "box", **given),
    "select": lambda **given: MACROS.select_field("box", "Box", OPTIONS, "a", "box", **given),
    "date": lambda **given: MACROS.date_field("box", "Box", "", "box", **given),
    "number": lambda **given: MACROS.number_field("box", "Box", "", "box", **given),
    "searchable": lambda **given: MACROS.searchable_select("box", "Box", OPTIONS, "a", "box", **given),
    "file": lambda **given: MACROS.file_field("box", "Box", "box", **given),
    "checkbox": lambda **given: MACROS.checkbox_field("box", "Box", False, "box", **given),
}


def control(html: str) -> str:
    """The opening tag of the field's control: the one with its id. A template inside it is not the page yet."""
    found = re.search(r'<(?:input|textarea|select)\b[^>]*\bid="box"[^>]*>', html.split("<template", 1)[0])
    assert found, html
    return found[0]


@pytest.mark.rule("A11Y-08")
@pytest.mark.parametrize("field", FIELDS)
def test_every_field_has_a_visible_label(field):
    html = str(FIELDS[field]())
    assert re.search(r'<label\b[^>]*\bfor="box"[^>]*>', html)
    assert "sr-only" not in html.split("</label>", 1)[0]
    assert ">Box" in html


@pytest.mark.rule("A11Y-08")
@pytest.mark.parametrize("field", FIELDS)
def test_a_hint_is_tied_to_its_field(field):
    html = str(FIELDS[field](hint="How to fill it"))
    assert 'id="box-hint"' in html
    assert 'aria-describedby="box-hint"' in control(html)
    assert "aria-invalid" not in control(html)


@pytest.mark.rule("A11Y-08")
@pytest.mark.parametrize("field", FIELDS)
def test_an_error_is_tied_to_its_field_and_marks_it_invalid(field):
    html = str(FIELDS[field](error="Fix this"))
    assert 'id="box-error"' in html
    tag = control(html)
    assert 'aria-invalid="true"' in tag
    assert 'aria-describedby="box-error"' in tag


@pytest.mark.rule("A11Y-08")
@pytest.mark.parametrize("field", FIELDS)
def test_a_hint_stays_while_there_is_an_error(field):
    tag = control(str(FIELDS[field](hint="How to fill it", error="Fix this")))
    assert 'aria-describedby="box-hint box-error"' in tag


@pytest.mark.rule("A11Y-08")
@pytest.mark.parametrize("field", set(FIELDS) - {"checkbox"})
def test_the_error_comes_before_the_control_with_the_hint_above_it(field):
    html = str(FIELDS[field](hint="How to fill it", error="Fix this"))
    assert html.index('id="box-hint"') < html.index('id="box-error"') < html.index(control(html))


@pytest.mark.rule("A11Y-08")
@pytest.mark.parametrize("field", set(FIELDS) - {"checkbox"})
def test_an_optional_field_says_so_and_a_required_one_tells_assistive_technology(field):
    assert "(optional)" in str(FIELDS[field](required=False))
    assert "(optional)" not in str(FIELDS[field]())
    required = str(FIELDS[field](required=True))
    assert "(optional)" not in required
    assert re.search(r"\srequired(?:=\"\")?[\s>]", control(required))


def test_a_small_select_is_only_for_a_filter_bar():
    assert "select-sm" in str(MACROS.select_field("box", "Box", OPTIONS, "a", "box", small=True))
    assert "select-sm" not in str(FIELDS["select"]())


def test_a_value_comes_back_as_it_was_typed_and_escaped():
    typed = '"><script>alert(1)</script>'
    assert f'value="{escape(typed)}"' in str(MACROS.input_field("box", "Box", typed, "box"))
    assert f">{escape(typed)}</textarea>" in str(MACROS.textarea_field("box", "Box", typed, "box"))
    assert f'value="{escape(typed)}"' in str(MACROS.number_field("box", "Box", typed, "box"))


def test_a_text_area_uses_daisyuis_class_and_keeps_its_rows():
    html = str(MACROS.textarea_field("box", "Box", "", "box", rows=6))
    assert 'class="textarea w-full"' in html
    assert 'rows="6"' in html


def test_a_date_field_is_native_and_can_say_its_limits():
    tag = control(str(MACROS.date_field("box", "Box", "2027-03-15", "box", earliest="2000-01-01", latest="2099-12-31")))
    assert 'type="date"' in tag
    assert 'value="2027-03-15"' in tag
    assert 'min="2000-01-01"' in tag
    assert 'max="2099-12-31"' in tag


def test_a_number_is_text_a_person_types_never_the_browsers_number_field():
    """`type=number` sends the browser's form of a decimal, and reads a comma as nothing in English."""
    decimal = control(str(MACROS.number_field("box", "Box", "1,5", "box")))
    assert 'type="text"' in decimal
    assert 'inputmode="decimal"' in decimal
    assert 'inputmode="numeric"' in control(str(MACROS.number_field("box", "Box", "3", "box", decimals=0)))


def test_a_checkbox_is_ticked_only_when_it_says_so():
    assert " checked" not in control(str(MACROS.checkbox_field("box", "Box", False, "box")))
    tag = control(str(MACROS.checkbox_field("box", "Box", True, "box")))
    assert " checked" in tag
    assert 'class="checkbox' in tag
    assert 'value="yes"' in tag


def radios(**given) -> str:
    return str(MACROS.radio_group("box", "Box", OPTIONS, "b", "box", **given))


@pytest.mark.rule("A11Y-08")
def test_radios_are_a_named_group_and_the_first_one_takes_the_link_of_an_error():
    html = radios()
    assert "<fieldset" in html
    assert "<legend" in html
    assert re.search(r'<input[^>]*id="box"[^>]*value="a"', html)
    assert re.search(r'<input[^>]*value="b"[^>]*checked', html)
    assert html.count('name="box"') == 2
    assert html.count('type="radio"') == 2
    assert html.count("<label") == 2


@pytest.mark.rule("A11Y-08")
def test_radios_tie_a_hint_and_an_error_to_the_group():
    html = radios(hint="How to choose", error="Choose one")
    group = re.search(r"<fieldset[^>]*>", html)[0]
    assert 'role="radiogroup"' in group
    assert 'aria-invalid="true"' in group
    assert 'aria-describedby="box-hint box-error"' in group


def test_a_searchable_select_is_a_plain_select_until_a_script_makes_it_more():
    html = str(MACROS.searchable_select("box", "Box", OPTIONS, "b", "box", every="None"))
    page, parts = html.split("<template", 1)
    assert "data-combobox" in page
    assert '<option value="b" selected>Second</option>' in page
    assert '<option value="">None</option>' in page
    assert 'name="box"' in page
    assert 'role="combobox"' not in page
    assert 'role="combobox"' in parts
    assert 'aria-autocomplete="list"' in parts
    assert 'aria-expanded="false"' in parts
    assert 'role="listbox"' in parts


def test_a_file_field_uses_daisyuis_class_and_says_what_it_takes():
    tag = control(str(MACROS.file_field("box", "Box", "box", accept=".pdf,.png")))
    assert 'type="file"' in tag
    assert 'class="file-input w-full"' in tag
    assert 'accept=".pdf,.png"' in tag
    assert "file-input-error" in control(str(MACROS.file_field("box", "Box", "box", error="Too big")))


@pytest.mark.rule("A11Y-08")
def test_the_summary_lists_each_error_as_a_link_to_its_field_and_takes_focus():
    html = str(MACROS.error_summary("Check what you entered", [("box", "Fix this"), ("other", "And this")]))
    assert 'role="alert"' in html
    assert 'tabindex="-1"' in html
    assert "data-focus" in html
    assert '<a class="underline" href="#box">Fix this</a>' in html
    assert '<a class="underline" href="#other">And this</a>' in html


def test_form_actions_put_the_way_out_after_the_main_action():
    html = str(MACROS.form_actions("Save", "/back", "Cancel"))
    assert html.index("btn-primary") < html.index('href="/back"')
    assert 'type="submit"' in html
    assert str(MACROS.form_actions("Save", caller=lambda: "EXTRA")).count("EXTRA") == 1


def test_a_danger_link_has_daisyuis_colour():
    assert "btn-error" in str(MACROS.link_button("Delete", "/delete", "danger"))


def asking(**given) -> str:
    what = {"lost": ["Two attached files", "7.50 hours"], "action": "/delete", "fields": [("version", 3)]} | given
    return str(
        MACROS.confirmation(
            "ask", "Delete work order 5?", "This cannot be undone.", confirm="Delete", cancel="Keep", **what
        )
    )


@pytest.mark.rule("USE-04")
def test_a_confirmation_names_what_will_be_lost():
    html = asking()
    assert "This cannot be undone." in html
    assert "<li>Two attached files</li>" in html
    assert "<li>7.50 hours</li>" in html


def test_a_confirmation_asks_with_a_post_and_its_own_fields():
    html = asking()
    assert 'method="post" action="/delete"' in html
    assert '<input type="hidden" name="version" value="3">' in html
    assert re.search(r'<button class="btn btn-error"[^>]*type="submit"', html)


def test_in_a_dialog_focus_starts_on_the_way_out():
    html = asking()
    assert re.search(r'<button[^>]*data-dialog-close="ask"[^>]*autofocus', html) or re.search(
        r'<button[^>]*autofocus[^>]*data-dialog-close="ask"', html
    )
    assert 'id="ask-title"' in html
    assert 'id="ask-lost"' in html


def test_as_a_page_it_has_a_heading_of_its_own_and_a_link_back():
    html = asking(back="/list", level=1)
    assert '<h1 id="ask-title"' in html
    assert re.search(r'<a class="btn " href="/list"[^>]*>s*Keep</a>', html)
    assert "data-dialog-close" not in html


def test_a_dialog_that_asks_is_an_alert_tied_to_what_is_lost():
    html = str(MACROS.dialog("ask", "Close", alert=True))
    assert 'role="alertdialog"' in html
    assert 'aria-labelledby="ask-title"' in html
    assert 'aria-describedby="ask-lost"' in html
    assert "alertdialog" not in str(MACROS.dialog("edit", "Close"))


def test_a_link_that_asks_is_a_page_without_javascript_and_a_dialog_with_it():
    html = str(MACROS.confirm_link("Delete", "/orders/5/delete", "ask"))
    assert 'href="/orders/5/delete"' in html
    assert 'hx-get="/orders/5/delete"' in html
    assert 'hx-target="#ask-body"' in html
    assert 'aria-haspopup="dialog"' in html
