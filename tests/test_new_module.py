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
    assert {field.kind for field in read.fields} == set(new_module.TYPES) - {"reference"}, "read below, with a module"
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


PLACES = 'entity = "Place"\ntable = "place"\npath = "/places"\nname = "name"\n'
"""What tools/new_module.py writes beside a module it made: a reference reads it."""
WITH_REFERENCES = (
    EVERY_TYPE
    + """
[[field]]
name = "place"
label = "Place"
type = "reference"
to = "places"
required = true
filter = true
list = true

[[field]]
name = "backup_place"
label = "Backup place"
type = "reference"
to = "places"
list = true
"""
)


def an_application(folder: Path, models: str = "class Place(Base):\n    name: Mapped[str]\n") -> Path:
    (folder / "places").mkdir()
    (folder / "places" / "module.toml").write_text(PLACES, encoding="utf-8")
    (folder / "places" / "models.py").write_text(models, encoding="utf-8")
    return folder


def test_a_reference_points_to_a_module_it_made(tmp_path):
    read = module(WITH_REFERENCES, an_application(tmp_path))
    place, backup = read.references
    assert place.target == backup.target == new_module.Target("places", "Place", "place", "/places", "name")
    assert (place.column, place.required, place.optional, backup.optional) == ("place_id", True, False, True)
    assert list(read.targets) == ["places"]


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (('to = "places"\nrequired', 'to = "nowhere"\nrequired'), "app/nowhere/module.toml is missing"),
        (('to = "places"\nrequired', 'to = "core"\nrequired'), "to is the package of another module"),
        (('to = "places"\nrequired', 'to = "places"\nsearch = true\nrequired'), "a reference takes"),
        (('type = "date"', 'type = "date"\nto = "places"'), "to is for a reference"),
        (('name = "backup_place"', 'name = "place_id"'), "also takes owner_id"),
    ],
)
def test_a_reference_that_cannot_be_made_is_refused_with_what_to_fix(tmp_path, change, said):
    with pytest.raises(new_module.Refused, match=re.escape(said)):
        module(WITH_REFERENCES.replace(*change), an_application(tmp_path))


def test_a_reference_to_a_module_that_changed_its_names_is_refused(tmp_path):
    with pytest.raises(new_module.Refused, match=re.escape("no longer has Place with name")):
        module(WITH_REFERENCES, an_application(tmp_path, "class Location(Base):\n    name: Mapped[str]\n"))


def test_what_it_writes_for_references_is_python_and_jinja(tmp_path):
    read = module(WITH_REFERENCES, an_application(tmp_path))
    models = new_module.models_code(read)
    assert 'place_id: Mapped[int] = mapped_column(ForeignKey("place.id"), index=True)' in models
    assert "backup_place: Mapped[Place | None] = relationship(foreign_keys=[backup_place_id])" in models
    routes = new_module.routes_code(read)
    assert 'BACKUP_PLACE = aliased(Place, name="backup_place")' in routes, "two references to one table, two names"
    sample = new_module.sample_code(read)
    assert 'AFTER = ("places",)' in sample and "def empty(session: Session)" in sample
    for name, code in (
        ("models", models),
        ("routes", routes),
        ("sample", sample),
        ("tests", new_module.tests_code(read)),
    ):
        compile(code, name, "exec")
    for name, text in new_module.templates(read).items():
        assert "$" not in text, name
        environment.parse(text)
    assert 'searchable_select("place", _("Place"), options.place' in new_module.templates(read)["form.html"]


WITH_VIEWS = (
    EVERY_TYPE
    + """
[board]
field = "kind"

[calendar]
start = "starts_at"

[timeline]
start = "booked_on"
"""
)


def test_its_other_views_are_read_and_written_as_python_and_jinja():
    read = module(WITH_VIEWS)
    assert read.views == ["board", "calendar", "timeline"]
    assert read.board and read.board.name == "kind" and read.calendar and read.calendar.end is None
    assert 'rank: Mapped[int] = mapped_column(BigInteger, server_default="0", index=True)' in new_module.models_code(
        read
    )
    code = new_module.views_code(read)
    for name in ("def board_page(", "def move_card(", "def calendar_page(", "def move_event(", "def timeline_page("):
        assert name in code, name
    compile(code, "views", "exec")
    compile(new_module.tests_code(read), "tests", "exec")
    written = new_module.views_templates(read)
    assert set(written) == {"board.html", "board_part.html", "calendar.html", "timeline.html"}
    for name, text in [*written.items(), *new_module.templates(read).items()]:
        assert "$" not in text, name
        environment.parse(text)
    assert '{{ tabs(_("Visits: views"), views, "list") }}' in new_module.templates(read)["list.html"]


@pytest.mark.parametrize(
    ("view", "said"),
    [
        ('[board]\nfield = "confirmed"', "[board] says field = a choice"),
        ('[board]\nfield = ["kind"]', "[board] says field = a choice"),
        ('[calendar]\nstart = "people"', "[calendar] start is a date or a date and time"),
        ('[calendar]\nstart = "starts_at"\nend = "booked_on"', "[calendar] end is another field of the same type"),
        ('[calendar]\nend = "starts_at"', "[calendar] says start = a field"),
        ('[timeline]\nstart = "starts_at"', "[timeline] start is a date of this module"),
    ],
)
def test_a_view_that_cannot_be_made_is_refused_with_what_to_fix(view, said):
    with pytest.raises(new_module.Refused, match=re.escape(said)):
        module(EVERY_TYPE + "\n" + view + "\n")


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


def test_a_booleans_default_in_a_migration_is_one_postgresql_accepts():
    """Alembic writes what SQLite holds; on 2026-11-04 GitHub's PostgreSQL refused `DEFAULT 0` for a boolean."""
    written = (
        'sa.Column("confirmed", sa.Boolean(), server_default=sa.text("0"), nullable=False),\n'
        "sa.Column('active', sa.Boolean(), server_default=sa.text('1'), nullable=False),\n"
        'sa.Column("people", sa.Integer(), server_default=sa.text("0"), nullable=False),\n'
    )
    portable = new_module.portable_defaults(written)
    assert "sa.Boolean(), server_default=sa.false(), nullable" in portable
    assert "sa.Boolean(), server_default=sa.true(), nullable" in portable
    assert 'sa.Integer(), server_default=sa.text("0")' in portable, "only a boolean's default changes"
