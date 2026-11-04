"""tools/new_module.py: what it accepts, what it refuses before writing anything, and what it writes, read without
running it. tests/demo/test_new_module.py runs it in a clean application, with that application's whole suite."""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

from app.core.templating import environment
from tests.helpers import ROOT
from tools import new_module

EVERY_TYPE = """
package = "visits"
entity = "Visit"
title = "Visits"
singular = "visit"
plural = "visits"

[[field]]
name = "reference"
label = "Reference"
type = "text"
required = true
unique = true
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

[[field]]
name = "budget"
label = "Budget"
type = "decimal"
places = 4

[[field]]
name = "booked_on"
label = "Booked on"
type = "date"

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
choices = [["customer", "Customer"], ["audit", "Audit"]]
filter = true

[[field]]
name = "summary"
label = "Summary"
type = "long_text"
"""


def spec(text: str = EVERY_TYPE) -> dict[str, Any]:
    return tomllib.loads(text)


NOWHERE = Path(__file__).resolve().parent / "no-application"
"""Where no package exists, so a description is read on its own, whatever modules this application has."""


def module(text: str = EVERY_TYPE, app: Path = NOWHERE) -> new_module.Module:
    return new_module.read_module(spec(text), app)


def test_the_example_reads_as_a_module():
    example = new_module.read_module(tomllib.loads(new_module.EXAMPLE), NOWHERE)
    assert example.package == "assets" and example.first.name == "serial_number"
    assert [field.kind for field in example.fields] == ["text", "text", "choice", "date", "decimal", "long_text"]


def test_every_type_is_read_with_its_defaults():
    read = module()
    assert read.path == "/visits" and read.table == "visit" and read.role == read.edit_role == "admin"
    assert {field.kind for field in read.fields} == set(new_module.TYPES)
    budget = next(field for field in read.fields if field.name == "budget")
    assert (budget.low, budget.high, budget.places, budget.optional) == (0, 999_999_999, 4, True)
    kind = next(field for field in read.fields if field.name == "kind")
    assert kind.required, "a choice always has one: its first"


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (EVERY_TYPE.replace('package = "visits"', 'package = "core"'), "package"),
        (EVERY_TYPE.replace('package = "visits"', 'package = "Visits"'), "package"),
        (EVERY_TYPE.replace('entity = "Visit"', 'entity = "visit"'), "entity"),
        (EVERY_TYPE.replace('title = "Visits"', 'title = "Visits {{ evil }}"'), "title"),
        (EVERY_TYPE.replace('label = "Summary"', 'label = "Say \\"hello\\""'), "label"),
        (EVERY_TYPE.replace('name = "summary"', 'name = "version"'), "name"),
        (EVERY_TYPE.replace('name = "summary"', 'name = "class"'), "name"),
        (EVERY_TYPE.replace('name = "summary"', 'name = "reference"'), "same name"),
        (EVERY_TYPE.replace('type = "long_text"', 'type = "long_text"\nlist = true'), "long text is not a column"),
        (EVERY_TYPE.replace('type = "long_text"', 'type = "long_text"\nunique = true'), "unique"),
        (EVERY_TYPE.replace('type = "date"', 'type = "date"\nunique = true'), "unique value is required"),
        (EVERY_TYPE.replace('type = "date"', 'type = "date"\nsearch = true'), "search is for a text"),
        (EVERY_TYPE.replace('type = "date"', 'type = "date"\nfilter = true'), "filter is for"),
        (
            EVERY_TYPE.replace('choices = [["customer", "Customer"], ["audit", "Audit"]]', 'choices = [["x", "X"]]'),
            "at least two",
        ),
        (EVERY_TYPE.replace('["audit", "Audit"]', '["Audit", "Audit"]'), "lower case"),
        (EVERY_TYPE.replace('["audit", "Audit"]', '["customer", "Again"]'), "same value"),
        (EVERY_TYPE.replace("low = 1\nhigh = 40", "low = 40\nhigh = 1"), "low is less than high"),
        (EVERY_TYPE.replace("places = 4", "places = 21"), "places"),
    ],
)
def test_a_description_that_cannot_make_a_module_is_refused_with_what_to_fix(text, said):
    with pytest.raises(new_module.Refused, match=re.escape(said)):
        module(text)


def test_the_first_column_names_each_row_so_it_is_a_required_text():
    text = EVERY_TYPE.replace(
        'type = "text"\nrequired = true\nunique = true\nsearch = true\nlist = true', 'type = "text"\nsearch = true'
    )
    with pytest.raises(new_module.Refused, match="names each row"):
        module(text)


def test_a_package_that_exists_is_refused_before_anything_is_written(tmp_path):
    (tmp_path / "visits").mkdir()
    with pytest.raises(new_module.Refused, match="exists already: nothing was written"):
        module(app=tmp_path)


def test_what_it_writes_is_python_and_jinja_with_nothing_left_to_fill():
    read = module()
    for name, code in (
        ("models", new_module.models_code(read)),
        ("routes", new_module.routes_code(read)),
        ("package", new_module.package_code(read)),
        ("sample", new_module.sample_code(read)),
        ("tests", new_module.tests_code(read)),
    ):
        compile(code, name, "exec")
    for name, text in new_module.templates(read).items():
        assert "$" not in text, name
        environment.parse(text)


def test_every_text_it_writes_goes_through_the_translations():
    """No English left on a page outside `_()`: the template's own texts and each label are messages."""
    written = new_module.templates(module())
    assert '_("Reference")' in written["form.html"] and '_("Visits")' in written["list.html"]
    assert 'ngettext("%(count)s visit", "%(count)s visits"' in written["results.html"]
    assert '_("Kind: choose one from the list.")' in new_module.routes_code(module())


def test_a_new_import_goes_among_its_kind_in_order():
    main = (
        "from fastapi import FastAPI\n\n"
        "from app.core.application import create_core, install_home\n"
        "from app.core.settings import Settings, get_settings\n"
        "from app.zones import install as install_zones\n\n\n"
        "def create_app(settings):\n"
        "    application = create_core(settings)\n"
        "    install_zones(application)\n"
        "    install_home(application)\n"
    )
    written = new_module.install_in_main(main, "visits")
    lines = written.splitlines()
    assert (
        lines.index("from app.core.settings import Settings, get_settings")
        < lines.index("from app.visits import install as install_visits")
        < lines.index("from app.zones import install as install_zones")
    )
    assert "    install_visits(application)\n    install_home(application)\n" in written
    first = new_module.install_in_main(main.replace("from app.zones import install as install_zones\n", ""), "alpha")
    assert first.index("from app.alpha") < first.index("from app.core.application")


def test_the_models_are_imported_where_alembic_reads_them():
    env = "from alembic import context\n\nfrom app.core.database import Base\n"
    written = new_module.import_in_env(env, "visits")
    assert "import app.visits.models  # noqa: F401\nfrom app.core.database import Base\n" in written


def test_its_migration_takes_the_next_number(tmp_path):
    assert new_module.next_revision(tmp_path) == "0001"
    (tmp_path / "0007_something.py").write_text("", encoding="utf-8")
    assert new_module.next_revision(tmp_path) == "0008"


def test_the_stylesheet_reads_the_templates_it_copies():
    """A new module needs no new build of the stylesheet: its classes are in the base's from the start."""
    source = (ROOT / "app" / "ui" / "styles" / "app.css").read_text(encoding="utf-8")
    assert '@source "../../../tools/module_template";' in source
    copied = {
        name
        for path in new_module.TEMPLATES.glob("*.html")
        for name in re.findall(r'class="([^"$]+)"', path.read_text(encoding="utf-8"))
    }
    assert "min-w-0 md:col-span-2" in copied, "the generated fields' wrappers are written in the template too"
