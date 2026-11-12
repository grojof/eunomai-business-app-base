import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from babel.core import get_cldr_version
from fastapi.testclient import TestClient

from app.core import formatters
from app.core.i18n import PSEUDO, Languages, _, ngettext
from app.core.settings import Settings
from app.main import create_app
from tests.conftest import build_settings
from tests.helpers import ROOT, untranslated
from tools import translations

ALLOWED = ("Business App", "Demo Person", "Mar 15, 2027", "Nov 20, 2026", "Jan 12, 2027", "Nov 9, 2026", "May 3, 2027")
SOURCE_LANGUAGE = "en"  # the language of the texts in the code: it has no folder
OFFERED = [SOURCE_LANGUAGE, *translations.REQUIRED]


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
@pytest.mark.parametrize("language", OFFERED)
def test_the_page_declares_its_language(client, person, language):
    client.cookies.set("language", language)
    assert f'<html lang="{language}"' in client.get("/", headers=person).text


@pytest.mark.rule("LANG-10")
def test_each_language_option_declares_its_own(client, person):
    html = client.get("/", headers=person).text
    for language in translations.REQUIRED:  # an application may keep fewer: tools/remove_demo.py --languages
        assert f'lang="{language}"' in html


@pytest.mark.parametrize(
    ("saved", "accept", "expected"),
    [
        ("ca", "es-ES,es;q=0.9", "ca"),
        (None, "es-ES,es;q=0.9,en;q=0.8", "es"),
        (None, "de-DE,de;q=0.9", "en"),
        (None, None, "en"),
        ("xx", "ca", "ca"),
        (None, "ES", "es"),
        (None, "ES-es,CA;q=0.5", "es"),
    ],
)
def test_the_language_is_chosen_in_order(saved, accept, expected):
    assert Languages(["en", "es", "ca"], "en").choose(saved, accept) == expected


@pytest.mark.rule("LANG-12")
def test_the_selector_names_each_language_in_itself_without_flags(client, person):
    html = client.get("/", headers=person).text
    names = {"en": "English", "es": "Español", "ca": "Català"}
    for language in OFFERED:
        assert names.get(language, "") in html
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
@pytest.mark.parametrize("language", OFFERED)
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


@pytest.mark.rule("LANG-06")
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("es", "1250,5"),
        ("es_ES", "1250,5"),
        ("es_419", "1,250.5"),
        ("es_MX", "1,250.5"),
        ("pl", "1250,5"),
        ("it", "1250,5"),
        ("pt_PT", "1250,5"),
        ("pt_BR", "1.250,5"),
        ("de", "1.250,5"),
        ("ca", "1.250,5"),
        ("en", "1,250.5"),
    ],
)
def test_four_digit_numbers_follow_cldr_in_each_language(language, expected):
    activate(language)
    assert formatters.format_decimal(Decimal("1250.5")) == expected


@pytest.mark.rule("LANG-06")
def test_the_grouping_data_is_from_the_cldr_version_babel_uses():
    data = json.loads((ROOT / "app" / "core" / "cldr_grouping.json").read_text(encoding="utf-8"))
    assert data["cldr"].split(".")[0] == str(get_cldr_version())


@pytest.mark.parametrize("value", ["-0.001", "-0.004", "-0"])
def test_an_amount_that_rounds_to_nothing_has_no_sign(value):
    assert str(formatters.rounded(Decimal(value))) == "0.00"


@pytest.mark.rule("LANG-08")
@pytest.mark.parametrize("language", OFFERED)
def test_no_length_of_decimal_is_cut(language):
    activate(language)
    value = Decimal("1" * 150 + "." + "2" * 150)
    assert formatters.parse_decimal(formatters.format_decimal(value)) == value


@pytest.mark.rule("LANG-07")
@pytest.mark.parametrize("text", ["NaN", "nan", "Infinity", "-Infinity", "sNaN", "1e5x", ""])
def test_something_that_is_not_a_number_is_refused(text):
    activate("en")
    with pytest.raises(ValueError):
        formatters.parse_decimal(text)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_a_special_value_does_not_break_the_page(value):
    activate("es")
    assert formatters.format_decimal(value)


@pytest.mark.rule("LANG-04")
def test_plurals_keep_the_language_rule_when_catalogues_are_merged(tmp_path):
    header = (
        'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
        '"Plural-Forms: nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);\\n"\n\n'
    )
    plural = 'msgid "one"\nmsgid_plural "many"\nmsgstr[0] "a"\nmsgstr[1] "b"\nmsgstr[2] "c"\n'
    other = 'msgid "other"\nmsgstr "inny"\n'
    languages = Languages(["pl"], "pl")
    for folder, body in (("first", plural), ("second", other)):
        path = tmp_path / folder / "pl" / "LC_MESSAGES" / "messages.po"
        path.parent.mkdir(parents=True)
        path.write_text(header + body, encoding="utf-8")
        languages.add_folder(tmp_path / folder)
    languages.activate("pl")
    assert [ngettext("one", "many", n) for n in (1, 3, 5, 22)] == ["a", "b", "c", "b"]
    assert _("other") == "inny"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("es;q=0.5, ca;q=0.9", "ca"),
        ("ca;q=0, es", "es"),
        ("de, ca;q=0.8, es;q=0.9", "es"),
        ("*", "en"),
        ("es;q=broken", "es"),
    ],
)
def test_the_browser_preference_follows_its_weights(header, expected):
    assert Languages(["en", "es", "ca"], "en").choose(None, header) == expected


def test_every_folder_in_locales_is_a_required_language(tmp_path):
    assert translations.REQUIRED == translations.languages_in(ROOT / "locales")
    (tmp_path / "fr").mkdir()
    (tmp_path / "de").mkdir()
    (tmp_path / "notes.txt").write_text("not a language", encoding="utf-8")
    assert translations.languages_in(tmp_path) == ["de", "fr"]


def test_the_bases_texts_come_first_and_each_package_keeps_its_own():
    catalogues = [domain.catalogues for domain in translations.DOMAINS]
    assert catalogues[0] == ROOT / "locales"
    assert all(path.name == "locales" and path.parent.parent == ROOT / "app" for path in catalogues[1:])


def test_a_new_folder_of_screens_has_its_texts_found_with_nothing_to_register(tmp_path):
    app = tmp_path / "app"
    for folder in ("core", "ui/templates", "orders/templates", "notes"):
        (app / folder).mkdir(parents=True)
    for package in ("core", "ui", "orders", "notes"):
        (app / package / "__init__.py").write_text("", encoding="utf-8")
    (app / "orders" / "routes.py").write_text('_("Order saved")\n', encoding="utf-8")
    (app / "orders" / "templates" / "list.html").write_text('{{ _("Open orders") }}\n', encoding="utf-8")
    (app / "notes" / "routes.py").write_text('_("Note kept")\n', encoding="utf-8")
    found = translations.domains(app)
    assert [domain.catalogues for domain in found] == [
        tmp_path / "locales",
        app / "notes" / "locales",
        app / "orders" / "locales",
    ]
    assert {message.id for message in translations.extract(found[2]) if message.id} == {"Order saved", "Open orders"}
    assert {message.id for message in translations.extract(found[1]) if message.id} == {"Note kept"}


def test_every_default_language_has_its_folder_or_is_the_source_language():
    assert set(Settings.model_fields["languages"].default) - set(translations.REQUIRED) == {SOURCE_LANGUAGE}


def test_the_time_zone_is_neutral_until_an_application_sets_it():
    assert build_settings().time_zone == "UTC"
    assert "APP_TIME_ZONE=" in (ROOT / ".env.example").read_text(encoding="utf-8")


def test_a_language_name_keeps_its_own_capitals():
    names = dict(Languages(["pt_BR", "de_CH"], "pt_BR").options())
    assert names == {"pt_BR": "Português (Brasil)", "de_CH": "Deutsch (Schweiz)"}


@pytest.mark.rule("LANG-10")
def test_a_regional_language_uses_a_valid_tag(person):
    client = TestClient(create_app(build_settings(languages=["en", "pt_BR"], default_language="en")))
    client.cookies.set("language", "pt_BR")
    html = client.get("/", headers=person).text
    assert '<html lang="pt-BR"' in html
    assert re.search(r'value="pt_BR"\s+lang="pt-BR"', html)


@pytest.mark.rule("LANG-08")
@pytest.mark.parametrize("value", [0, 3, 1250, Decimal("0"), Decimal("0.5"), Decimal("1E+3"), Decimal("-7")])
def test_small_and_whole_numbers_format_without_error(value):
    activate("es")
    assert formatters.parse_decimal(formatters.format_decimal(value)) == Decimal(value)


@pytest.mark.rule("LANG-01")
def test_no_template_has_text_outside_translation_even_if_no_test_visits_it():
    for template in (ROOT / "app").rglob("*.html"):
        text = re.sub(r"\{#.*?#\}|\{%.*?%\}|\{\{.*?\}\}", "", template.read_text(encoding="utf-8"), flags=re.S)
        assert untranslated(text, ("AB", "example.org")) == [], template


@pytest.mark.rule("LANG-07")
@pytest.mark.parametrize(
    "text",
    [
        "1e3",
        "1E3",
        "1e-2",
        "0e400",
        "1_0",
        "1_000",
        "\uff11\uff12",
        "\u0661\u0662",
        "0x10",
        "1\u00a0000",
        "1 000",
        "1'000",
    ],
)
@pytest.mark.parametrize("language", ["en", "es", "ca"])
def test_what_no_language_writes_is_refused(language, text):
    activate(language)
    with pytest.raises(ValueError):
        formatters.parse_decimal(text)


@pytest.mark.rule("LANG-07")
@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [
        ("en", "1,234.5", "1234.5"),
        ("es", "1234,5", "1234.5"),
        ("es", "12.345,5", "12345.5"),
        ("ca", "1.234,5", "1234.5"),
        ("en", " 7 ", "7"),
        ("en", "-1", "-1"),
    ],
)
def test_what_a_language_writes_is_read(language, text, expected):
    activate(language)
    assert formatters.parse_decimal(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["2027-03-15", "2028-02-29"])
def test_a_date_in_its_one_form_is_read(text):
    assert formatters.parse_date(text).isoformat() == text


@pytest.mark.parametrize(
    "text",
    ["20270315", "2027-W11-1", "2027-W11", "2027-074", "2027-03-15T10:00", "2027-3-5", " 2027-03-15", "2027-02-30", ""],
)
def test_any_other_date_is_refused(text):
    with pytest.raises(ValueError):
        formatters.parse_date(text)


@pytest.mark.parametrize(
    "text", ["\u0662\u0660\u0662\u0667-\u0660\u0663-\u0661\u0665", "\uff12\uff10\uff12\uff17-03-15"]
)
def test_a_date_in_other_digits_is_refused(text):
    with pytest.raises(ValueError):
        formatters.parse_date(text)


def test_a_catalogue_changes_only_when_its_texts_do(tmp_path, monkeypatch):
    """A module's new texts left the base's catalogues with a new date in their header: an update of the template
    then found a change on both sides of them, and could not come in on its own."""
    app = tmp_path / "app"
    for package, text in (("core", "Shared"), ("orders", "Orders")):
        (app / package).mkdir(parents=True)
        (app / package / "__init__.py").write_text("", encoding="utf-8")
        (app / package / "texts.py").write_text(f'_("{text}")\n', encoding="utf-8")
    monkeypatch.setattr(translations, "DOMAINS", translations.domains(app))
    monkeypatch.setattr(translations, "REQUIRED", ["es"])
    translations.update()
    base = tmp_path / "locales" / "es" / "LC_MESSAGES" / "messages.po"
    first = base.read_bytes()
    (app / "orders" / "texts.py").write_text('_("Orders")\n_("New order")\n', encoding="utf-8")
    translations.update()
    assert base.read_bytes() == first  # the base's catalogue, untouched
    module = app / "orders" / "locales" / "es" / "LC_MESSAGES" / "messages.po"
    assert b'msgid "New order"' in module.read_bytes()
