"""tools/new_module.py in an organization's template, as a person would run it: a module with every type of field, a
second one whose rows point to the first's, their texts translated, and the application's whole suite, browser checks
included, run as a person's computer runs it.

That one run proves three things at once: the demo goes cleanly (a template is the base without its demo), a layer's
brand and languages work, and a generated module fits. Each once ran the same suite on its own, three times over;
tests/demo/test_clean_application.py and tests/demo/test_template.py keep their own quick checks. It goes with the
demo: in an application, tests/test_new_module.py stays.

It downloads Tailwind's executable once, as tests/demo/test_clean_application.py does, so it is left out where nothing
may be downloaded.
"""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from babel.messages.pofile import read_po, write_po

from tests.demo.test_clean_application import own_tests_pass, succeeded
from tests.demo.test_template import a_layer, make
from tests.helpers import ROOT, run_in
from tools import new_module

EVERY_TYPE = """
package = "visits"
entity = "Visit"
title = "Visits"
singular = "visit"
plural = "visits"
description = "Who comes, when, and whether it is confirmed."
icon = "calendar-check"

[[field]]
name = "reference"
label = "Reference"
type = "text"
longest = 24
required = true
unique = true
search = true
list = true

[[field]]
name = "place"
label = "Place"
type = "text"
search = true
list = true

[[field]]
name = "starts_at"
label = "Starts at"
type = "datetime"
required = true
list = true

[[field]]
name = "people"
label = "People"
type = "integer"
low = 1
high = 40
required = true
list = true

[[field]]
name = "badge_number"
label = "Badge number"
type = "integer"

[[field]]
name = "budget"
label = "Budget"
type = "decimal"
places = 4
high = 50000

[[field]]
name = "booked_on"
label = "Booked on"
type = "date"
required = true
unique = true

[[field]]
name = "ends_at"
label = "Ends at"
type = "datetime"

[[field]]
name = "confirmed"
label = "Confirmed"
type = "boolean"
filter = true
list = true

[[field]]
name = "kind"
label = "Kind"
type = "choice"
choices = [["customer", "Customer"], ["supplier", "Supplier"], ["audit", "Audit"]]
filter = true

[[field]]
name = "summary"
label = "Summary"
type = "long_text"
longest = 500
"""


REFERENCES = """
package = "guests"
entity = "Guest"
title = "Guests"
singular = "guest"
plural = "guests"
icon = "users"

[[field]]
name = "full_name"
label = "Full name"
type = "text"
required = true
search = true
list = true

[[field]]
name = "visit"
label = "Visit"
type = "reference"
to = "visits"
required = true
filter = true
list = true

[[field]]
name = "next_visit"
label = "Next visit"
type = "reference"
to = "visits"
list = true
"""
"""Two references to one module's rows, one required and filtered, one that may be empty."""


def translate_like_a_person(folder: Path) -> None:
    """Every new text gets a translation, accepted: what a person does after the generator, and no test may skip."""
    for path in sorted(folder.rglob("messages.po")):
        language = path.parent.parent.name
        with path.open("rb") as file:
            catalog = read_po(file, locale=language)
        for message in catalog:
            if message.id:
                texts = message.id if isinstance(message.id, tuple) else (message.id,)
                translated = tuple(f"[{language}] {text}" for text in texts)
                message.string = translated if isinstance(message.id, tuple) else translated[0]
                message.flags.discard("fuzzy")
        with path.open("wb") as file:
            write_po(file, catalog, omit_header=False, sort_output=True, no_location=True, ignore_obsolete=True)


@pytest.fixture(scope="module")
def application(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("module")
    copy = folder / "application"
    succeeded(make(a_layer(folder / "layer"), copy), "tools/make_template.py")
    (copy / "visits.toml").write_text(EVERY_TYPE, encoding="utf-8")
    succeeded(run_in(copy, "tools/new_module.py", "--spec", "visits.toml"), "tools/new_module.py")
    (copy / "guests.toml").write_text(REFERENCES, encoding="utf-8")
    succeeded(run_in(copy, "tools/new_module.py", "--spec", "guests.toml"), "tools/new_module.py, a reference")
    return copy


def test_it_writes_the_module_and_puts_it_in_place(application):
    folder = application / "app" / "visits"
    for name in ("__init__.py", "models.py", "routes.py", "sample_data.py"):
        assert (folder / name).is_file(), name
    for name in ("list.html", "results.html", "detail.html", "page.html", "form.html"):
        assert (folder / "templates" / "visits" / name).is_file(), name
    assert "install_visits(application)\n    install_guests(application)\n    install_home(application)" in (
        application / "app" / "main.py"
    ).read_text(encoding="utf-8")
    assert "import app.visits.models" in (application / "migrations" / "env.py").read_text(encoding="utf-8")
    [migration] = (application / "migrations" / "versions").glob("0001_*.py")
    written = migration.read_text(encoding="utf-8")
    assert "ExactDecimal()" in written
    assert "server_default=sa.false()" in written, "PostgreSQL refuses 0 as a boolean's default"
    assert not re.search(r"Boolean\(\).*server_default=sa\.text", written)
    assert (application / "tests" / "test_visits.py").is_file()
    assert 'path = "/visits"' in (folder / "module.toml").read_text(encoding="utf-8")
    [pointing] = (application / "migrations" / "versions").glob("0002_*.py")
    written = pointing.read_text(encoding="utf-8")
    assert "sa.ForeignKeyConstraint(" in written and '["next_visit_id"]' in written and '["visit.id"]' in written


def test_its_texts_wait_for_a_person_and_nothing_else_does(application):
    check = run_in(application, "tools/translations.py", "check")
    assert check.returncode != 0 and "app/visits/locales/" in check.stdout
    for other in ("ruff check", "ruff format --check", "mypy"):
        succeeded(run_in(application, "-m", *other.split()), other)
    succeeded(run_in(application, "tools/css.py", "check"), "the stylesheet already has every class it uses")


def test_a_second_run_writes_nothing(application):
    before = (application / "app" / "main.py").read_text(encoding="utf-8")
    again = run_in(application, "tools/new_module.py", "--spec", "visits.toml")
    assert again.returncode == 1 and "Nothing was written" in again.stderr
    assert (application / "app" / "main.py").read_text(encoding="utf-8") == before
    assert len(list((application / "migrations" / "versions").glob("*.py"))) == 2


@pytest.mark.long
def test_the_applications_whole_suite_passes_with_the_module_and_a_start_page_that_reads_its_table(application):
    """The base's own tests open the start page. One that reads the module's table finds it, empty: the tests' default
    database has every migration, the application's own included, so no base file had to change for it. The suite runs
    with tools/test.py, as `[tests]` runs it on a person's computer, so the template's brand and its one language are
    proved with it. The catalogues and the routes are left as they were found: the other tests share the application,
    and one of them reads that its texts still wait for a person."""
    kept = {path: path.read_bytes() for path in (application / "app").rglob("*") if path.suffix in (".po", ".mo")}
    routes = application / "app" / "visits" / "routes.py"
    kept[routes] = routes.read_bytes()
    try:
        whole_suite_with_a_start_page(application, routes)
    finally:
        for path, content in kept.items():
            path.write_bytes(content)


def whole_suite_with_a_start_page(application: Path, routes: Path) -> None:
    for package in ("visits", "guests"):
        translate_like_a_person(application / "app" / package / "locales")
    succeeded(run_in(application, "tools/translations.py", "check"), "translations")
    text = routes.read_text(encoding="utf-8")
    route = "    add(PATH, item_list, include_in_schema=False)\n"
    assert route in text
    start_page = (
        "\n\ndef start_page(request: Request, session: DatabaseSession) -> Response:\n"
        '    """The start page, for anyone signed in, reads the module\'s table, as a start page often does."""\n'
        "    session.scalar(select(Visit.id).limit(1))\n"
        '    return render(request, "home.html")\n'
    )
    text = text.replace(route, route + '    add("/", start_page, include_in_schema=False)\n') + start_page
    routes.write_text(text, encoding="utf-8", newline="\n")
    own_tests_pass(application)


def test_a_preview_starts_with_its_sample_rows(application, tmp_path):
    """What a person's preview runs: the migrations, then each module's made-up rows, and only once. The rows that
    point to others come after them."""
    setup = tomllib.loads((application / ".eunomai" / "project.toml").read_text(encoding="utf-8"))["preview"]["setup"]
    assert setup == [["python", "-m", "app.core.sample_data", "--if-empty"]]
    url = f"sqlite:///{(tmp_path / 'preview.db').as_posix()}"
    environment = os.environ | {"APP_ENVIRONMENT": "development", "APP_DATABASE_URL": url}
    for expected in ("filled visits, guests", "left as they were: visits, guests"):
        done = subprocess.run(
            [sys.executable, "-m", "app.core.sample_data", "--if-empty"],
            cwd=application,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        succeeded(done, "sample data")
        assert expected in done.stdout


def test_in_the_base_it_refuses_and_writes_nothing():
    """It is proved in an application, where the demo has gone: there is where modules belong."""
    before = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    with pytest.raises(new_module.Refused, match=re.escape("tools/remove_demo.py")):
        new_module.make(new_module.read_module(tomllib.loads(EVERY_TYPE), ROOT / "nowhere"), ROOT)
    assert (ROOT / "app" / "main.py").read_text(encoding="utf-8") == before
    assert not (ROOT / "app" / "visits").exists()
