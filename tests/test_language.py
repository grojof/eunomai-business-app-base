from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core import formatters
from app.core.i18n import PSEUDO, Languages, _, ngettext
from app.main import create_app
from tests.conftest import build_settings
from tests.helpers import ROOT, untranslated
from tools import translations

ALLOWED = ("Business App", "Demo Person")


def activate(language: str) -> None:
    languages = Languages(["en", "es", "ca"], "en")
    languages.add_folder(ROOT / "locales")
    languages.activate(language)


@pytest.mark.rule("LANG-14")
@pytest.mark.rule("LANG-03")
@pytest.mark.rule("LANG-13")
def test_every_catalogue_is_complete_and_consistent():
    assert translations.check() == []


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", ["/", "/missing"])
def test_no_page_has_text_outside_translation(client, person, path):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get(path, headers=person).text, ALLOWED) == []


@pytest.mark.rule("LANG-01")
def test_the_identity_error_is_translated_too(client):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get("/").text, ALLOWED) == []


def test_the_pseudo_language_does_not_exist_in_production(person):
    client = TestClient(create_app(build_settings(environment="production")))
    client.cookies.set("language", PSEUDO)
    assert "⟦" not in client.get("/", headers=person).text


@pytest.mark.rule("LANG-10")
@pytest.mark.parametrize("language", ["en", "es", "ca"])
def test_the_page_declares_its_language(client, person, language):
    client.cookies.set("language", language)
    assert f'<html lang="{language}"' in client.get("/", headers=person).text


@pytest.mark.rule("LANG-10")
def test_each_language_option_declares_its_own(client, person):
    html = client.get("/", headers=person).text
    assert 'lang="ca"' in html
    assert 'lang="es"' in html


@pytest.mark.parametrize(
    ("saved", "accept", "expected"),
    [
        ("ca", "es-ES,es;q=0.9", "ca"),
        (None, "es-ES,es;q=0.9,en;q=0.8", "es"),
        (None, "de-DE,de;q=0.9", "en"),
        (None, None, "en"),
        ("xx", "ca", "ca"),
    ],
)
def test_the_language_is_chosen_in_order(saved, accept, expected):
    assert Languages(["en", "es", "ca"], "en").choose(saved, accept) == expected


@pytest.mark.rule("LANG-12")
def test_the_selector_names_each_language_in_itself_without_flags(client, person):
    html = client.get("/", headers=person).text
    for name in ("English", "Español", "Català"):
        assert name in html
    assert not any(0x1F1E6 <= ord(character) <= 0x1F1FF for character in html)


@pytest.mark.rule("LANG-13")
def test_a_missing_text_falls_back_and_is_never_blank():
    activate("es")
    assert _("A text nobody translated") == "A text nobody translated"


@pytest.mark.rule("LANG-04")
def test_plurals_follow_the_language():
    assert translations.read(ROOT / "locales" / "es" / "LC_MESSAGES" / "messages.po", "es").num_plurals == 2
    activate("en")
    assert ngettext("one", "many", 1) == "one"
    assert ngettext("one", "many", 2) == "many"


@pytest.mark.rule("LANG-06")
@pytest.mark.parametrize(
    ("language", "value", "expected"),
    [
        ("en", Decimal("1250.5"), "1,250.5"),
        ("es", Decimal("1250.5"), "1250,5"),
        ("es", Decimal("12500.5"), "12.500,5"),
        ("ca", Decimal("12500.5"), "12.500,5"),
    ],
)
def test_numbers_follow_the_language(language, value, expected):
    activate(language)
    assert formatters.format_decimal(value) == expected


@pytest.mark.rule("LANG-06")
def test_dates_follow_the_language():
    activate("es")
    assert "2027" in formatters.format_date(date(2027, 3, 15))
    assert "mar" in formatters.format_date(date(2027, 3, 15))
    activate("en")
    assert formatters.format_date(date(2027, 3, 15)) == "Mar 15, 2027"


@pytest.mark.rule("LANG-08")
@pytest.mark.parametrize("language", ["en", "es", "ca"])
@pytest.mark.parametrize(
    "value",
    [Decimal("0.00000000000000000001"), Decimal("123456789012345678.12345678901234567890"), Decimal("-1250.10")],
)
def test_a_decimal_survives_writing_and_reading_exactly(language, value):
    activate(language)
    assert formatters.parse_decimal(formatters.format_decimal(value)) == value


@pytest.mark.rule("LANG-07")
def test_a_number_is_read_as_the_language_writes_it():
    activate("es")
    assert formatters.parse_decimal("1.250,50") == Decimal("1250.50")
    activate("en")
    assert formatters.parse_decimal("1,250.50") == Decimal("1250.50")


@pytest.mark.rule("LANG-07")
def test_a_number_in_the_wrong_format_is_refused_not_guessed():
    activate("en")
    with pytest.raises(ValueError):
        formatters.parse_decimal("1.250,50")


@pytest.mark.rule("LANG-09")
def test_a_moment_is_shown_in_the_time_zone():
    activate("en")
    moment = datetime(2026, 10, 30, 23, 30, tzinfo=UTC)
    assert "12:30" in formatters.format_datetime(moment, "Europe/Madrid")
    assert "Oct 31" in formatters.format_datetime(moment, "Europe/Madrid")
