"""Reading a form at its edge: what stays in an application after the demo is deleted."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI, Form
from fastapi.testclient import TestClient

from app.core import i18n
from app.core.forms import (
    Refused,
    read_choice,
    read_date,
    read_decimal,
    read_fields,
    read_flag,
    read_text,
    read_whole,
)
from app.main import create_app
from tests.conftest import PERSON, build_settings

EARLY = date(2000, 1, 1)
LATE = date(2099, 12, 31)


@pytest.fixture(autouse=True)
def english():
    i18n._language.set("en")


@pytest.mark.rule("SEC-03")
def test_text_loses_its_outer_spaces_and_keeps_the_rest():
    assert read_text("  Oil change  ", longest=80) == "Oil change"


@pytest.mark.rule("SEC-03")
def test_text_that_is_needed_and_empty_says_what_to_do():
    with pytest.raises(Refused, match="Enter a title"):
        read_text("   ", longest=80, missing="Enter a title.")
    assert read_text("", longest=80) == ""


@pytest.mark.rule("SEC-03")
def test_text_has_a_length_on_both_databases():
    assert read_text("x" * 80, longest=80)
    with pytest.raises(Refused, match="80"):
        read_text("x" * 81, longest=80)


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize(
    "value",
    ["a\x00b", "a\nb", "a\tb", "a\x7fb", "a\x1bb", "a\x85b", "a\u2028b", "a\u2029b", "a\u202eb", "a\u2066b"],
)
def test_a_line_of_text_refuses_control_characters(value):
    """PostgreSQL refuses a NUL inside text: left alone it would be an error page there, and stored on SQLite."""
    with pytest.raises(Refused):
        read_text(value, longest=80)


@pytest.mark.rule("SEC-03")
def test_several_lines_keep_their_line_breaks_in_one_form_and_nothing_else():
    assert read_text("one\r\ntwo\n\tthree", longest=80, lines=True) == "one\ntwo\n\tthree"
    with pytest.raises(Refused):
        read_text("a\x00b", longest=80, lines=True)


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize("value", ["a\x85b", "a\u202eb", "a\u2066b", "a\u200fb"])
def test_several_lines_refuse_by_category_too(value):
    with pytest.raises(Refused):
        read_text(value, longest=80, lines=True)


@pytest.mark.parametrize(
    ("pasted", "kept"), [("\ufeffPump", "Pump"), ("in\u00adspection", "inspection"), ("a\u200bb", "ab")]
)
def test_marks_that_word_processors_leave_in_pasted_text_go_quietly(pasted, kept):
    """A person cannot see these, so a refusal would give them nothing to remove."""
    assert read_text(pasted, longest=80) == kept


@pytest.mark.parametrize("emoji", ["\U0001f469\u200d\U0001f527", "\u0dc1\u0dca\u200d\u0dbb\u0dd3"])
def test_a_joiner_is_part_of_what_a_person_wrote(emoji):
    assert read_text(emoji, longest=80) == emoji


def test_a_separator_from_a_pdf_is_a_line_break_where_lines_are_allowed():
    assert read_text("one\u2028two\u2029three", longest=80, lines=True) == "one\ntwo\nthree"


def test_a_lone_carriage_return_is_a_line_break():
    assert read_text("one\rtwo", longest=80, lines=True) == "one\ntwo"


@pytest.mark.rule("SEC-03")
def test_a_choice_must_be_on_its_list():
    assert read_choice("low", ("low", "high"), "Choose one.") == "low"
    with pytest.raises(Refused, match="Choose one"):
        read_choice("' OR 1=1 --", ("low", "high"), "Choose one.")


@pytest.mark.rule("SEC-03")
def test_a_tick_is_there_or_not_and_nothing_else():
    assert read_flag("yes") is True
    assert read_flag("") is False
    with pytest.raises(Refused):
        read_flag("maybe")


@pytest.mark.rule("LANG-07")
@pytest.mark.parametrize(("language", "text", "expected"), [("en", "1,234.5", "1234.5"), ("es", "1234,5", "1234.5")])
def test_a_decimal_is_read_as_the_persons_language_writes_it(language, text, expected):
    i18n._language.set(language)
    assert read_decimal(text, 0, 9999, 2) == Decimal(expected)


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("many", "number"),
        ("", "number"),
        ("1e3", "number"),
        ("١٢", "number"),
        ("NaN", "number"),
        ("Infinity", "number"),
        ("1" * 200, "number"),
        ("-1", "between"),
        ("10000", "between"),
        ("1.234", "decimals"),
    ],
)
def test_a_decimal_refuses_what_is_not_one_in_words_that_help(text, message):
    with pytest.raises(Refused, match=message):
        read_decimal(text, 0, 9999, 2)


@pytest.mark.rule("LANG-08")
def test_a_decimal_stays_exact_and_trailing_zeros_are_no_extra_decimals():
    assert read_decimal("1.230", 0, 9999, 2) == Decimal("1.23")
    value = read_decimal("0.12345678901234567890", 0, 1, 20)
    assert value == Decimal("0.12345678901234567890")
    assert isinstance(value, Decimal)


def test_a_minus_zero_is_a_zero():
    assert str(read_decimal("-0", 0, 9, 2)) == "0"


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize("text", ["1.5", "many", "", "0", "51"])
def test_a_whole_number_refuses_the_rest(text):
    with pytest.raises(Refused):
        read_whole(text, 1, 50)


def test_a_whole_number_is_an_int():
    assert read_whole("3", 1, 50) == 3
    assert type(read_whole("3", 1, 50)) is int


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize("text", ["not a date", "2027-02-30", "20270315", "2027-W11-1", "27-01-01", "incomplete"])
def test_a_date_is_read_in_its_one_form(text):
    with pytest.raises(Refused, match="Enter a date"):
        read_date(text, EARLY, LATE, "Enter a date.")


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize("text", ["0001-01-01", "1999-12-31", "2100-01-01"])
def test_a_date_stays_within_its_limits(text):
    with pytest.raises(Refused, match="between"):
        read_date(text, EARLY, LATE, "Enter a date.")


def test_a_date_may_be_empty_unless_it_is_needed():
    assert read_date("", EARLY, LATE, "Enter a date.") is None
    assert read_date("2027-03-15", EARLY, LATE, "Enter a date.") == date(2027, 3, 15)
    with pytest.raises(Refused, match="Enter a date"):
        read_date("", EARLY, LATE, "Enter a date.", needed=True)


def test_fields_are_read_one_by_one_and_each_problem_stays_with_its_field():
    def wrong() -> str:
        raise Refused("Fix this.")

    clean, errors = read_fields({"good": lambda: 1, "bad": wrong, "other": lambda: 2})
    assert clean == {"good": 1, "other": 2}
    assert errors == {"bad": "Fix this."}


@pytest.mark.rule("SEC-03")
def test_a_form_that_is_not_what_it_should_be_is_a_page_and_echoes_nothing():
    """FastAPI's own answer is JSON that repeats what was sent."""
    application: FastAPI = create_app(build_settings())

    def route(title: str = Form()) -> str:
        return title

    application.add_api_route("/sample", route, methods=["POST"])
    client = TestClient(application, raise_server_exceptions=False)
    response = client.post("/sample", files={"title": ("x.txt", b"<b>sent</b>")}, headers=PERSON)
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/html")
    assert "sent" not in response.text


@pytest.mark.rule("SEC-03")
def test_a_part_too_long_for_any_field_is_a_page_too():
    application: FastAPI = create_app(build_settings())

    def route(title: str = Form()) -> str:
        return title

    application.add_api_route("/sample", route, methods=["POST"])
    client = TestClient(application, raise_server_exceptions=False)
    response = client.post("/sample", data={"title": "x" * 2_000_000}, files={"other": ("", b"")}, headers=PERSON)
    assert response.status_code == 400
    assert "could not be read" in response.text


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize("digits", [20, 4301, 5000, 20000])
def test_an_id_too_long_for_any_row_is_not_found_on_every_route_a_clone_adds(digits):
    application: FastAPI = create_app(build_settings())

    def route(number: int) -> int:
        return number

    application.add_api_route("/things/{number:int}", route)
    client = TestClient(application, raise_server_exceptions=False)
    assert client.get(f"/things/{'1' * digits}", headers=PERSON).status_code == 404
    assert client.get("/things/1", headers=PERSON).json() == 1
