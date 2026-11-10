"""A new module of screens for an application, complete and working: a list with search and filters, a detail page and a
form to add or change one row, with its model, migration, sample data, texts and tests. Then customise what it wrote.

uv run --frozen python tools/new_module.py --example > module.toml   # a commented description to start from
uv run --frozen python tools/new_module.py --spec module.toml

It writes `app/<package>/`, its migration and `tests/test_<package>.py`, adds the module to `app/main.py` and to
`migrations/env.py`, and adds its texts to every catalogue, where a person translates them. It never overwrites: a
package that exists is refused. What it writes follows the rules of docs/base/standards.md and passes the
application's checks, once its texts are translated. See docs/base/specification.md#a-new-module
"""

import argparse
import keyword
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from string import Template
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "module_template"
TYPES = ("text", "long_text", "integer", "decimal", "date", "datetime", "boolean", "choice", "reference")
NAME = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
ENTITY = re.compile(r"[A-Z][A-Za-z0-9]{0,39}\Z")
WORDS = re.compile(r"[A-Za-z0-9][^\"\\%{}<>$\n]{0,79}\Z")
"""Text that becomes a message to translate, in a template and in Python: no quotes, braces, markup or placeholders."""
CHOICE = re.compile(r"[a-z][a-z0-9_]{0,23}\Z")
ICON = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*\Z")
RESERVED_FIELDS = {"id", "version", "rank", "back", "saved", "moved", "q", "sort", "dir", "size", "page", "panel"}
"""The table's own columns, a board's place in its column, the form's hidden fields and the words an address uses."""
SHARED = {"core", "ui", "brand", "demo"}
LIMITS = {"text": 255, "long_text": 10000}
DEFAULTS: dict[str, dict[str, Any]] = {
    "text": {"longest": 80},
    "long_text": {"longest": 2000},
    "integer": {"low": 0, "high": 1_000_000},
    "decimal": {"low": 0, "high": 999_999_999, "places": 2},
    "date": {},
    "datetime": {},
    "boolean": {},
    "choice": {},
    "reference": {},
}
EARLIEST, LATEST = date(2000, 1, 1), date(2100, 12, 31)
ROWS = 24
"""Sample rows: enough to page through at the smallest page size, few enough to read."""
EXAMPLE = """# A module for tools/new_module.py. Texts are in English: they go through the translations, as any text.
package = "assets"          # app/assets/: lower case letters, digits and underscores
entity = "Asset"            # the model's class
title = "Assets"            # the list's title and its place in the navigation
singular = "asset"          # in sentences: "No assets yet", "%(count)s asset"
plural = "assets"
description = "Every asset, its state and who has it."
icon = "package"            # a Lucide icon: uv run --frozen python tools/icons.py search <word>
role = "admin"              # who may open it; edit_role, who may change it, is the same unless it says otherwise

# Field types: text, long_text, integer, decimal, date, datetime, boolean, choice. Each may say: required, unique (text,
# integer or date, and then required), search (text), filter (choice or boolean), list (shown as a column), hint.
# text and long_text take longest; integer and decimal take low and high; decimal takes places; choice takes choices.
# The first field shown in the list names each row: a required text.

[[field]]
name = "serial_number"
label = "Serial number"
type = "text"
longest = 40
required = true
unique = true
search = true
list = true

[[field]]
name = "model"
label = "Model"
type = "text"
search = true
list = true

[[field]]
name = "state"
label = "State"
type = "choice"
choices = [["in_use", "In use"], ["in_stock", "In stock"], ["in_repair", "In repair"], ["retired", "Retired"]]
filter = true
list = true

[[field]]
name = "bought_on"
label = "Bought on"
type = "date"
list = true

[[field]]
name = "cost"
label = "Cost"
type = "decimal"
places = 2

[[field]]
name = "notes"
label = "Notes"
type = "long_text"

# A reference points to a row of another module made by this tool, by its package: a list to choose from in the form,
# its name as a link in the list, and a filter. Make the module it points to first.
# [[field]]
# name = "location"
# label = "Location"
# type = "reference"
# to = "locations"
# required = true
# filter = true
# list = true

# Other views of the same rows, each optional, each a page with tabs between them and the list:
[board]                     # a card for each row, in a column for each value of a choice, moved by form or by dragging
field = "state"

[calendar]                  # each row on its day: a date or a date and time, and an end of the same type if it has one
start = "bought_on"

[timeline]                  # each row as a bar on its days: a date, and an end date if it has one
start = "bought_on"
"""
DESCRIPTION = "module.toml"
"""What another module's reference reads of this one: written beside its code, with the names it was made with."""
REFERENCE_KEYS = {"name", "label", "type", "to", "required", "filter", "list", "hint"}


class Refused(Exception):
    """The description cannot make a module: what is wrong, said so that it can be fixed."""


@dataclass(frozen=True)
class Target:
    """The module a reference points to, as its module.toml describes it."""

    package: str
    entity: str
    table: str
    path: str
    name: str
    """The field that names each of its rows: what a list to choose from shows."""


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str
    required: bool
    unique: bool
    search: bool
    filter: bool
    listed: bool
    hint: str
    longest: int
    low: int
    high: int
    places: int
    choices: tuple[tuple[str, str], ...]
    target: Target | None = None

    @property
    def column(self) -> str:
        """The table's column: a reference keeps the number of the row it points to."""
        return f"{self.name}_id" if self.kind == "reference" else self.name

    @property
    def identifier(self) -> str:
        return "field-" + self.name.replace("_", "-")

    @property
    def constant(self) -> str:
        return self.name.upper()

    @property
    def optional(self) -> bool:
        """Empty is a value of its own: a number, a date or a row not known yet. A text keeps it as an empty text."""
        return not self.required and self.kind in ("integer", "decimal", "date", "datetime", "reference")

    @property
    def phrase(self) -> str:
        """The label inside a sentence, in English, where the texts are written."""
        return self.label[0].lower() + self.label[1:] if not self.label[:2].isupper() else self.label


@dataclass(frozen=True)
class Span:
    """The fields a calendar or a timeline places each row by: its start, and its end if it has one."""

    start: Field
    end: Field | None = None


@dataclass(frozen=True)
class Module:
    package: str
    entity: str
    table: str
    path: str
    title: str
    singular: str
    plural: str
    description: str
    icon: str
    role: str
    edit_role: str
    fields: tuple[Field, ...]
    board: Field | None = None
    calendar: Span | None = None
    timeline: Span | None = None

    @property
    def views(self) -> list[str]:
        """The pages besides the list, in the order of their tabs."""
        return [name for name in ("board", "calendar", "timeline") if getattr(self, name)]

    @property
    def first(self) -> Field:
        return next(field for field in self.fields if field.listed)

    def having(self, kind: str) -> bool:
        return any(field.kind == kind for field in self.fields)

    @property
    def references(self) -> tuple[Field, ...]:
        return tuple(field for field in self.fields if field.kind == "reference")

    @property
    def targets(self) -> dict[str, Target]:
        """Each module pointed to, once, by package."""
        return {field.target.package: field.target for field in self.references if field.target}


def _words(value: object, what: str) -> str:
    if not isinstance(value, str) or not WORDS.match(value.strip()):
        raise Refused(
            f"{what}: up to 80 characters of plain text, starting with a letter or a digit, with no quotes, "
            "backslashes, %, $, braces or angle brackets"
        )
    return value.strip()


def _flag(spec: dict[str, Any], key: str) -> bool:
    value = spec.get(key, False)
    if not isinstance(value, bool):
        raise Refused(f"{key} is true or false")
    return value


def _whole(spec: dict[str, Any], key: str, default: int, what: str) -> int:
    value = spec.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise Refused(f"{what}: {key} is a whole number")
    return value


def read_target(app: Path, package: object, name: str) -> Target:
    """The module a reference points to: one this tool made, still where it was put."""
    if not isinstance(package, str) or not NAME.match(package) or package in SHARED:
        raise Refused(f"field {name}: to is the package of another module, such as locations")
    described = app / package / DESCRIPTION
    if not described.is_file():
        raise Refused(
            f"field {name}: app/{package}/{DESCRIPTION} is missing: a reference points to a module tools/new_module.py "
            "made, so make that one first"
        )
    try:
        found = tomllib.loads(described.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as problem:
        raise Refused(f"app/{package}/{DESCRIPTION} cannot be read: {problem}") from None
    values = {key: found.get(key) for key in ("entity", "table", "path", "name")}
    if not all(isinstance(value, str) and value for value in values.values()):
        raise Refused(f"app/{package}/{DESCRIPTION} needs entity, table, path and name")
    models = app / package / "models.py"
    code = models.read_text(encoding="utf-8") if models.is_file() else ""
    if f"class {values['entity']}(" not in code or f"    {values['name']}: Mapped[" not in code:
        raise Refused(
            f"field {name}: app/{package}/models.py no longer has {values['entity']} with {values['name']}: "
            f"correct app/{package}/{DESCRIPTION} as it is now"
        )
    return Target(package, *(str(values[key]) for key in ("entity", "table", "path", "name")))


def read_field(spec: object, position: int, app: Path) -> Field:
    if not isinstance(spec, dict):
        raise Refused(f"field {position} is a [[field]] table")
    name = spec.get("name")
    if not isinstance(name, str) or not NAME.match(name) or keyword.iskeyword(name) or name in RESERVED_FIELDS:
        raise Refused(
            f"field {position}: name is lower case letters, digits and underscores, starting with a letter, "
            f"and none of {', '.join(sorted(RESERVED_FIELDS))}"
        )
    known = {
        "name",
        "label",
        "type",
        "required",
        "unique",
        "search",
        "filter",
        "list",
        "hint",
        "longest",
        "low",
        "high",
        "places",
        "choices",
        "to",
    }
    unknown = sorted(set(spec) - known)
    if unknown:
        raise Refused(f"field {name}: unknown keys {', '.join(unknown)}")
    kind = spec.get("type")
    if kind not in TYPES:
        raise Refused(f"field {name}: type is one of {', '.join(TYPES)}")
    if kind == "reference" and set(spec) - REFERENCE_KEYS:
        raise Refused(f"field {name}: a reference takes {', '.join(sorted(REFERENCE_KEYS - {'name', 'type'}))}")
    if "to" in spec and kind != "reference":
        raise Refused(f"field {name}: to is for a reference")
    defaults = DEFAULTS[kind]
    label = _words(spec.get("label"), f"field {name}: label")
    hint = _words(spec["hint"], f"field {name}: hint") if "hint" in spec else ""
    required, unique = _flag(spec, "required"), _flag(spec, "unique")
    search, filtered, listed = _flag(spec, "search"), _flag(spec, "filter"), _flag(spec, "list")
    longest = _whole(spec, "longest", defaults.get("longest", 0), f"field {name}")
    low = _whole(spec, "low", defaults.get("low", 0), f"field {name}")
    high = _whole(spec, "high", defaults.get("high", 0), f"field {name}")
    places = _whole(spec, "places", defaults.get("places", 0), f"field {name}")
    if kind in LIMITS and not 1 <= longest <= LIMITS[kind]:
        raise Refused(f"field {name}: longest is between 1 and {LIMITS[kind]}")
    if kind in ("integer", "decimal") and not -(10**12) <= low < high <= 10**12:
        raise Refused(f"field {name}: low is less than high, both within a million millions")
    if kind == "decimal" and not 0 <= places <= 20:
        raise Refused(f"field {name}: places is between 0 and 20")
    choices: tuple[tuple[str, str], ...] = ()
    if kind == "choice":
        given = spec.get("choices")
        if not isinstance(given, list) or len(given) < 2:
            raise Refused(f"field {name}: choices is a list of at least two [value, label] pairs")
        for pair in given:
            if not (isinstance(pair, list) and len(pair) == 2 and isinstance(pair[0], str) and CHOICE.match(pair[0])):
                raise Refused(
                    f"field {name}: each choice is [value, label], the value in lower case letters, digits "
                    "and underscores"
                )
            choices += ((pair[0], _words(pair[1], f"field {name}: the label of {pair[0]}")),)
        if len({value for value, _label in choices}) != len(choices):
            raise Refused(f"field {name}: two choices have the same value")
        required = True  # its first choice is the default
    if unique and kind not in ("text", "integer", "date"):
        raise Refused(f"field {name}: unique is for a text, a whole number or a date")
    if unique and not required:
        raise Refused(f"field {name}: a unique value is required, or two empty ones would collide")
    if search and kind not in ("text", "long_text"):
        raise Refused(f"field {name}: search is for a text")
    if listed and kind == "long_text":
        raise Refused(f"field {name}: a long text is not a column: it goes on the detail page")
    if filtered and kind not in ("choice", "boolean", "reference"):
        raise Refused(f"field {name}: filter is for a choice, a yes or no, or a reference")
    target = read_target(app, spec.get("to"), name) if kind == "reference" else None
    return Field(
        name, label, kind, required, unique, search, filtered, listed, hint, longest, low, high, places, choices, target
    )


def read_module(spec: dict[str, Any], app: Path) -> Module:
    known = {
        "package",
        "entity",
        "table",
        "path",
        "title",
        "singular",
        "plural",
        "description",
        "icon",
        "role",
        "edit_role",
        "field",
        "board",
        "calendar",
        "timeline",
    }
    unknown = sorted(set(spec) - known)
    if unknown:
        raise Refused(f"unknown keys {', '.join(unknown)}")
    package = spec.get("package")
    if not isinstance(package, str) or not NAME.match(package) or keyword.iskeyword(package) or package in SHARED:
        raise Refused("package is lower case letters, digits and underscores, and none of " + ", ".join(sorted(SHARED)))
    if (app / package).exists():
        raise Refused(f"app/{package} exists already: nothing was written. Choose another package, or change it there")
    entity = spec.get("entity")
    if not isinstance(entity, str) or not ENTITY.match(entity):
        raise Refused("entity is a class name, such as Asset")
    table = spec.get("table", re.sub(r"(?<!^)(?=[A-Z])", "_", entity).lower())
    if not isinstance(table, str) or not NAME.match(table):
        raise Refused("table is lower case letters, digits and underscores")
    path = spec.get("path", "/" + package.replace("_", "-"))
    if not isinstance(path, str) or not re.fullmatch(r"(/[a-z0-9]+(-[a-z0-9]+)*)+", path):
        raise Refused("path is an address such as /assets: lower case letters, digits and hyphens")
    icon = spec.get("icon", "list")
    if not isinstance(icon, str) or not ICON.match(icon):
        raise Refused("icon is a Lucide name, such as package")
    role = spec.get("role", "admin")
    edit_role = spec.get("edit_role", role)
    for value, key in ((role, "role"), (edit_role, "edit_role")):
        if not isinstance(value, str) or not NAME.match(value):
            raise Refused(f"{key} is a role's name, such as admin")
    fields = spec.get("field")
    if not isinstance(fields, list) or not fields:
        raise Refused("at least one [[field]]")
    read = tuple(read_field(field, number, app) for number, field in enumerate(fields, 1))
    names = [field.name for field in read] + [field.column for field in read if field.column != field.name]
    if len(set(names)) != len(names):
        raise Refused("two fields have the same name: a reference called owner also takes owner_id")
    if not any(field.listed for field in read):
        raise Refused("at least one field is shown in the list: say list = true")
    module = Module(
        package,
        entity,
        table,
        path,
        _words(spec.get("title"), "title"),
        _words(spec.get("singular"), "singular"),
        _words(spec.get("plural"), "plural"),
        _words(spec["description"], "description") if "description" in spec else "",
        icon,
        role,
        edit_role,
        read,
    )
    if module.first.kind != "text" or not module.first.required:
        raise Refused(f"the first field shown in the list names each row: {module.first.name} is a required text")
    return replace(
        module,
        board=read_board(spec.get("board"), read),
        calendar=read_span(spec.get("calendar"), read, "calendar", ("date", "datetime")),
        timeline=read_span(spec.get("timeline"), read, "timeline", ("date",)),
    )


def read_board(spec: object, fields: tuple[Field, ...]) -> Field | None:
    if spec is None:
        return None
    named = {field.name: field for field in fields if field.kind == "choice"}
    if not isinstance(spec, dict) or set(spec) != {"field"} or str(spec["field"]) not in named:
        raise Refused("[board] says field = a choice of this module: its values are the columns")
    return named[spec["field"]]


def read_span(spec: object, fields: tuple[Field, ...], view: str, kinds: tuple[str, ...]) -> Span | None:
    if spec is None:
        return None
    named = {field.name: field for field in fields}
    what = " or ".join("a date" if kind == "date" else "a date and time" for kind in kinds)
    if not isinstance(spec, dict) or not set(spec) <= {"start", "end"} or "start" not in spec:
        raise Refused(f"[{view}] says start = a field, and end = another if each row has one")
    start = named.get(spec["start"]) if isinstance(spec["start"], str) else None
    if start is None or start.kind not in kinds:
        raise Refused(f"[{view}] start is {what} of this module")
    if "end" not in spec:
        return Span(start)
    end = named.get(spec["end"]) if isinstance(spec["end"], str) else None
    if end is None or end.kind != start.kind or end is start:
        raise Refused(f"[{view}] end is another field of the same type as start")
    return Span(start, end)


# --- the model ----------------------------------------------------------------------------------------------------

PYTHON_TYPES = {
    "text": "str",
    "long_text": "str",
    "integer": "int",
    "decimal": "Decimal",
    "date": "date",
    "datetime": "datetime",
    "boolean": "bool",
    "choice": "str",
}


def column_line(field: Field) -> str:
    if field.target:
        nullable = " | None" if field.optional else ""
        return (
            f"    {field.column}: Mapped[int{nullable}] = "
            f'mapped_column(ForeignKey("{field.target.table}.id"), index=True)\n'
            f"    {field.name}: Mapped[{field.target.entity}{nullable}] = relationship(foreign_keys=[{field.column}])"
        )
    kind = PYTHON_TYPES[field.kind]
    annotation = f"{kind} | None" if field.optional else kind
    arguments = []
    if field.kind == "text":
        arguments.append(f"String({field.longest})")
    elif field.kind == "long_text":
        arguments.append("Text")
    elif field.kind == "choice":
        arguments.append(f"String({max(len(value) for value, _label in field.choices)})")
    if field.unique:
        arguments.append("unique=True")
    elif field.listed or field.filter:
        arguments.append("index=True")  # a column people sort or filter by
    if field.kind in ("text", "long_text") and not field.required:
        arguments.append('server_default=""')
    if field.kind == "boolean":
        arguments.append("server_default=false()")
    if field.kind == "choice":
        arguments.append(f"server_default={field.choices[0][0]!r}".replace("'", '"'))
    if not arguments:
        return f"    {field.name}: Mapped[{annotation}]"
    return f"    {field.name}: Mapped[{annotation}] = mapped_column({', '.join(arguments)})"


def models_code(module: Module) -> str:
    """Imports may be more than it uses: `tidy` takes away the unused ones and puts the rest in order."""
    lines = [
        f'"""The table of {module.plural}. Made by tools/new_module.py: change it as this application needs, then make',
        'a migration with `uv run --frozen alembic revision --autogenerate -m "What changed"` and read it."""',
        "",
        "from datetime import date, datetime",
        "from decimal import Decimal",
        "",
        "from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, Text, false",
        "from sqlalchemy.orm import Mapped, mapped_column, relationship",
        "",
        "from app.core.database import Base",
        *(f"from app.{target.package}.models import {target.entity}" for target in module.targets.values()),
        "",
    ]
    for field in module.fields:
        if field.kind == "choice":
            values = ", ".join(f'"{value}"' for value, _label in field.choices)
            lines.append(f"{field.constant}_CHOICES = ({values})")
    lines += ["", "", f"class {module.entity}(Base):", f'    __tablename__ = "{module.table}"']
    checks = [field for field in module.fields if field.kind == "choice"]
    if checks:
        constraints = []
        for field in checks:
            allowed = ", ".join(f"'{value}'" for value, _label in field.choices)
            constraints.append(f'CheckConstraint("{field.name} IN ({allowed})", name="{field.name}")')
        lines.append(f"    __table_args__ = ({', '.join(constraints)},)")
    lines += ["", "    id: Mapped[int] = mapped_column(primary_key=True)"]
    lines += [column_line(field) for field in module.fields]
    if module.board:
        lines.append('    rank: Mapped[int] = mapped_column(BigInteger, server_default="0", index=True)')
    lines += [
        '    version: Mapped[int] = mapped_column(server_default="1")',
        "",
        '    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012  # how SQLAlchemy asks for it',
        "",
    ]
    return "\n".join(lines)


# --- the routes ---------------------------------------------------------------------------------------------------


def reader(field: Field) -> str:
    """How the form's text for one field becomes the value to save, at the edge."""
    sent = f'sent["{field.name}"]'
    if field.target:
        find = f"lambda number: session.get({field.target.entity}, number)"
        message = f'_("{field.label}: choose one from the list.")'
        return f"read_reference({sent}, {find}, {message}, needed={field.required})"
    if field.kind in ("text", "long_text"):
        missing = f', missing=_("Enter the {field.phrase}.")' if field.required else ""
        lines = ", lines=True" if field.kind == "long_text" else ""
        return f"read_text({sent}, longest={field.longest}{missing}{lines})"
    if field.kind == "integer":
        read = f"read_whole(text, {field.low}, {field.high})"
    elif field.kind == "decimal":
        read = f"read_decimal(text, {field.low}, {field.high}, {field.places})"
    elif field.kind == "date":
        needed = ", needed=True" if field.required else ""
        return f'read_date({sent}, EARLIEST, LATEST, _("{field.label}: enter a date."){needed})'
    elif field.kind == "datetime":
        needed = "True" if field.required else "False"
        return f'read_moment({sent}, zone, _("{field.label}: enter a date and a time."), needed={needed})'
    elif field.kind == "boolean":
        return f"read_flag({sent})"
    else:
        return f'read_choice({sent}, {field.constant}_CHOICES, _("{field.label}: choose one from the list."))'
    if field.required:
        return read.replace("text", sent, 1)
    return f"or_none({sent}, lambda text: {read})"


def form_value(field: Field) -> str:
    """The stored value as the form's field shows it."""
    value = f"item.{field.name}"
    if field.target:
        number = f"item.{field.column}"
        return f'"" if {number} is None else str({number})' if field.optional else f"str({number})"
    if field.kind == "integer":
        return f'"" if {value} is None else str({value})' if field.optional else f"str({value})"
    if field.kind == "decimal":
        shown = f"format_decimal({value}, {field.places})"
        return f'"" if {value} is None else {shown}' if field.optional else shown
    if field.kind == "date":
        return f'{value}.isoformat() if {value} else ""' if field.optional else f"{value}.isoformat()"
    if field.kind == "datetime":
        return f"moment_text({value}, zone)"
    return value


def blank_value(field: Field) -> str:
    if field.kind == "boolean":
        return "False"
    if field.kind == "choice":
        return f'"{field.choices[0][0]}"'
    return '""'


def shown_text(field: Field) -> str:
    """The stored value in words, for a conflict: what the other person saved."""
    value = f"item.{field.name}"
    if field.target:
        name = f"{value}.{field.target.name}"
        return f'_("Not given") if {value} is None else {name}' if field.optional else name
    if field.kind in ("text", "long_text"):
        return f'{value} or _("Not given")' if not field.required else value
    if field.kind == "integer":
        text = f"format_decimal({value})"
    elif field.kind == "decimal":
        text = f"format_decimal({value}, {field.places})"
    elif field.kind == "date":
        text = f"format_date({value})"
    elif field.kind == "datetime":
        text = f"format_datetime({value}, zone.key)"
    elif field.kind == "boolean":
        return f'_("Yes") if {value} else _("No")'
    else:
        return f"_({field.constant}_LABELS[{value}])"
    return f'_("Not given") if {value} is None else {text}' if field.optional else text


def related_lines(module: Module) -> list[str]:
    """Each reference a list can filter by: the page of the row pointed to leads to this module's rows of it."""
    pointing = [field for field in module.references if field.filter and field.target]
    lines = []
    for field in pointing:
        assert field.target  # noqa: S101  # references alone
        target = field.target
        same = [other for other in pointing if other.target and other.target.package == target.package]
        label = module.title if len(same) == 1 else f"{module.title} ({field.label})"
        lines += [
            f'    related = RelatedList(N_("{label}"), PATH, "{field.name}", rows_of_{field.name}, ROLE, '
            f'"{module.icon}")',
            f'    application.state.related.setdefault("{target.package}", []).append(related)',
        ]
    return lines


def related_counts(module: Module) -> list[str]:
    lines = []
    for field in module.references:
        if field.filter:
            lines += [
                f"def rows_of_{field.name}(session: Session, number: int) -> int:",
                f'    """How many {module.plural} point to it: what its page says beside the link to them."""',
                f"    pointing = {module.entity}.{field.column} == number",
                f"    found = select(func.count()).select_from({module.entity}).where(pointing)",
                "    return session.scalar(found) or 0",
                "",
                "",
            ]
    return lines


def routes_code(module: Module) -> str:
    """Imports may be more than it uses: `tidy` takes away the unused ones and puts the rest in order."""
    fields = module.fields
    zone_needed = module.having("datetime")
    choice_fields = [f for f in fields if f.kind == "choice"]
    optional_fields = [f for f in fields if f.optional and f.kind != "datetime"]
    unique_fields = [f for f in fields if f.unique]
    searched = [f for f in fields if f.search]
    listed = [f for f in fields if f.listed]
    filtered = [f for f in fields if f.filter]
    model_imports = ", ".join([*(f"{f.constant}_CHOICES" for f in choice_fields), module.entity])
    entity = module.entity
    joined = [f for f in listed if f.target]
    lines = [
        f'"""{module.title}: the list with search and filters, a page for each one, and the form to add or change one.',
        "Made by tools/new_module.py: change it as this application needs. See docs/base/specification.md#a-new-module",
        '"""',
        "",
        "import re",
        "from collections.abc import Callable, Mapping",
        "from datetime import UTC, date, datetime",
        "from typing import Annotated, Any",
        "from urllib.parse import urlencode",
        "from zoneinfo import ZoneInfo",
        "",
        "from fastapi import Depends, FastAPI, HTTPException, Request",
        "from fastapi.responses import Response",
        "from sqlalchemy import func, select",
        "from sqlalchemy.exc import IntegrityError",
        "from sqlalchemy.orm import Session, aliased, contains_eager",
        "",
        "from app.core.database import DatabaseSession, saved",
        "from app.core.formatters import format_date, format_datetime, format_decimal",
        "from app.core.forms import Refused, read_choice, read_date, read_decimal, read_fields, read_flag, "
        "read_reference, read_text, read_whole",
        "from app.core.i18n import N_, _",
        "from app.core.identity import Person, require_role",
        "from app.core.tables import Column, Filter, ListView, RelatedList, fragment_requested, list_query, "
        "reference_options, related_lists, render_list, whole_page",
        "from app.core.templating import render",
        f"from app.{module.package}.models import {model_imports}",
        *(f"from app.{target.package}.models import {target.entity}" for target in module.targets.values()),
        "",
        f'ROLE, EDIT_ROLE = "{module.role}", "{module.edit_role}"',
        "Reader = Annotated[Person, Depends(require_role(ROLE))]",
        "Editor = Annotated[Person, Depends(require_role(EDIT_ROLE))]",
        f'PATH = "{module.path}"',
        "LARGEST_ID = 2**31 - 1",
        '"""The database\'s integer. A longer number in an address is a page that does not exist, not an error."""',
    ]
    if module.having("date") or zone_needed:
        lines += [
            f"EARLIEST, LATEST = date({EARLIEST.year}, {EARLIEST.month}, {EARLIEST.day}), "
            f"date({LATEST.year}, {LATEST.month}, {LATEST.day})",
            '"""The dates a form takes: a year typed as 0026 is a mistake, and a valid date."""',
        ]
    if zone_needed:
        lines += [
            'MOMENT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-2][0-9]:[0-5][0-9]")',
            '"""What a `datetime-local` field sends: a date and a time on the person\'s clock, with no time zone."""',
        ]
    for field in choice_fields:
        labels = ", ".join(f'"{value}": N_("{label}")' for value, label in field.choices)
        lines.append(f"{field.constant}_LABELS = {{{labels}}}")
    if choice_fields:
        lines.append("LABELS = {" + ", ".join(f'"{f.name}": {f.constant}_LABELS' for f in choice_fields) + "}")
        lines.append('"""The words for each stored choice, for the templates."""')
    else:
        lines.append("LABELS: dict[str, dict[str, str]] = {}")
    names = ", ".join(f'"{f.name}"' for f in fields)
    lines += [
        f"FIELDS = ({names}{',' if len(fields) == 1 else ''})",
        '"""The form\'s fields, in the order of the page: its error summary and a conflict follow it."""',
    ]
    if unique_fields:
        taken = ", ".join(
            f'"{f.name}": N_("Another {module.singular} already has this {f.phrase}.")' for f in unique_fields
        )
        lines += [f"TAKEN = {{{taken}}}", '"""Values no two rows may share, and what a person reads when one does."""']
    shown = ", ".join(f'"{f.name}": N_("{f.label}")' for f in fields)
    lines += [f"SHOWN = {{{shown}}}", '"""How a conflict names each field."""']
    for field in joined:
        assert field.target  # noqa: S101  # joined holds references alone
        lines.append(f'{field.constant} = aliased({field.target.entity}, name="{field.name}")')
    if joined:
        lines.append(
            '"""The rows a list shows beside its own, each under a name of its own: two may be of one table."""'
        )
    lines += ["", ""]

    if module.views:
        tab = {"board": "Board", "calendar": "Calendar", "timeline": "Timeline"}
        entries = " ".join(f'("{name}", N_("{tab[name]}"), "/{name}"),' for name in module.views)
        lines += [
            f'VIEWS = (("list", N_("List"), ""), {entries})',
            '"""This module\'s pages of the same rows: the tabs that lead from one to another."""',
            "",
            "",
            "def view_links() -> list[tuple[str, str, str]]:",
            "    return [(key, _(label), PATH + end) for key, label, end in VIEWS]",
            "",
            "",
        ]
    lines += [
        "def can_edit(request: Request) -> bool:",
        '    """Whether to offer it. The routes check again: hiding a link is not a control."""',
        '    person = getattr(request.state, "person", None)',
        "    return bool(person and EDIT_ROLE in person.roles)",
        "",
        "",
        "def identifier(name: str) -> str:",
        '    return "field-" + name.replace("_", "-")',
        "",
        "",
        "def read_version(text: str) -> int | None:",
        '    """What a form says it read. Anything else matches no row, so it saves nothing."""',
        "    return int(text) if text.isascii() and text.isdigit() and len(text) < 10 else None",
        "",
        "",
    ]
    if optional_fields:
        lines += [
            "def or_none[Value](text: str, read: Callable[[str], Value]) -> Value | None:",
            '    """An empty field is a value not known yet."""',
            "    return read(text) if text.strip() else None",
            "",
            "",
        ]
    if zone_needed:
        lines += [
            "def zone_of(request: Request) -> ZoneInfo:",
            "    return ZoneInfo(request.app.state.settings.time_zone)",
            "",
            "",
            "def read_moment(text: str, zone: ZoneInfo, message: str, *, needed: bool) -> datetime | None:",
            '    """A date and a time as the person\'s clock reads them, kept in UTC."""',
            "    if not text and not needed:",
            "        return None",
            "    if not MOMENT.fullmatch(text):",
            "        raise Refused(message)",
            "    try:",
            "        local = datetime.fromisoformat(text)",
            "    except ValueError:",
            "        raise Refused(message) from None",
            "    if not EARLIEST <= local.date() <= LATEST:",
            "        raise Refused(message)",
            "    return local.replace(tzinfo=zone).astimezone(UTC)",
            "",
            "",
            "def moment_text(moment: datetime | None, zone: ZoneInfo) -> str:",
            '    """A stored moment as a `datetime-local` field shows it, on the person\'s clock."""',
            '    return moment.astimezone(zone).strftime("%Y-%m-%dT%H:%M") if moment else ""',
            "",
            "",
        ]
    columns = []
    for position, field in enumerate(listed):
        sort = f"{field.constant}.{field.target.name}" if field.target else f"{entity}.{field.name}"
        options = [f'"{field.name}"', f'_("{field.label}")', sort]
        if field.kind in ("integer", "decimal"):
            options.append("numeric=True")
        if position >= 2:
            options.append("wide_only=True")
        if field.optional:
            options.append("nullable=True")
        columns.append(f"            Column({', '.join(options)}),")
    filters = []
    for field in filtered:
        if field.target:
            target = field.target
            choices = f"reference_options(session, {target.entity}.id, {target.entity}.{target.name})"
            condition = f"lambda value: {entity}.{field.column} == int(value)"
        elif field.kind == "choice":
            choices = f"[(value, _(label)) for value, label in {field.constant}_LABELS.items()]"
            condition = f"lambda value: {entity}.{field.name} == value"
        else:
            choices = '[("yes", _("Yes")), ("no", _("No"))]'
            condition = f'lambda value: {entity}.{field.name} == (value == "yes")'
        filters += [
            "            Filter(",
            f'                "{field.name}",',
            f'                _("{field.label}"),',
            f"                {choices},",
            f"                {condition},",
            f'                every=_("Any {field.phrase}"),',
            "            ),",
        ]
    search_columns = ", ".join(f"{entity}.{f.name}" for f in searched)
    search_label = " or ".join(f.label if i == 0 else f.phrase for i, f in enumerate(searched))
    lines += [
        "def list_view(params: Mapping[str, str], session: Session) -> ListView:",
        "    return ListView.read(",
        f'        "{module.package}",',
        "        PATH,",
        "        params,",
        "        (",
        *columns,
        "        ),",
        f"        {entity}.id,",
        f'        "{module.first.name}",',
        "        (",
        *filters,
        "        ),",
        f"        ({search_columns}{',' if len(searched) == 1 else ''}),",
        f'        _("{search_label}"),' if searched else '        "",',
        "    )",
        "",
        "",
        "def item_list(request: Request, session: DatabaseSession, _person: Reader) -> Response:",
        "    view = list_view(request.query_params, session)",
        *(
            [
                f"    statement = select({entity})"
                + "".join(f".outerjoin({f.constant}, {entity}.{f.name})" for f in joined),
                "    shown_beside = ["
                + ", ".join(f"contains_eager({entity}.{f.name}.of_type({f.constant}))" for f in joined)
                + "]",
                "    view.load(session, statement, options=shown_beside)",
            ]
            if joined
            else [f"    view.load(session, select({entity}))"]
        ),
        "    return render_list(",
        "        request,",
        "        view,",
        f'        "{module.package}/list.html",',
        f'        "{module.package}/results.html",',
        "        can_edit=can_edit(request),",
        "        labels=LABELS,",
        *(["        views=view_links(),"] if module.views else []),
        "    )",
        "",
        "",
        f"def item_or_404(session: Session, item_id: int) -> {entity}:",
        f"    item = session.get({entity}, item_id) if item_id <= LARGEST_ID else None",
        "    if item is None:",
        "        raise HTTPException(status_code=404)",
        "    return item",
        "",
        "",
        'def list_address(request: Request, session: Session, sent: str = "") -> str:',
        '    """Back to the list a person came from, with its filters: input like any other, so it is read again."""',
        '    came_from = sent or request.query_params.get("back") or request.headers.get("referer", "")',
        "    return list_view(list_query(came_from, PATH), session).here",
        "",
        "",
        "def page_address(item_id: int, back: str, **outcome: str) -> str:",
        '    keep = {} if back == PATH else {"back": back}',
        "    query = urlencode(outcome | keep)",
        '    return f"{PATH}/{item_id}?{query}" if query else f"{PATH}/{item_id}"',
        "",
        "",
        "def item_page(request: Request, item_id: int, session: DatabaseSession, _person: Reader) -> Response:",
        "    item = item_or_404(session, item_id)",
        '    saved_now = "saved" in request.query_params',
        f'    outcome = _("%(name)s saved.") % {{"name": item.{module.first.name}}} if saved_now else ""',
        "    return render(",
        "        request,",
        f'        "{module.package}/detail.html",',
        "        item=item,",
        f"        heading=item.{module.first.name},",
        "        back=list_address(request, session),",
        "        outcome=outcome,",
        f'        related=related_lists(request, session, "{module.package}", item.id),',
        "        can_edit=can_edit(request),",
        "        labels=LABELS,",
        "    )",
        "",
        "",
        "async def sent_form(request: Request) -> dict[str, str]:",
        '    """What the form sent, as text, for its own fields only: anything else is not read."""',
        "    form = await request.form()",
        '    names = (*FIELDS, "back", "version")',
        '    return {name: value if isinstance(value := form.get(name, ""), str) else "" for name in names}',
        "",
        "",
        "Sent = Annotated[dict[str, str], Depends(sent_form)]",
        "",
        "",
    ]
    zone_parameter = ", zone: ZoneInfo" if zone_needed else ""
    zone_argument = ", zone" if zone_needed else ""
    readers = [f'            "{f.name}": lambda: {reader(f)},' for f in fields]
    lines += [
        "def checked(",
        f"    sent: Mapping[str, str], session: Session, item_id: int | None{zone_parameter}",
        ") -> tuple[dict[str, Any], dict[str, str]]:",
        '    """Every field, at the edge. The browser\'s `required` and `maxlength` help a person, decide nothing."""',
        "    clean, errors = read_fields(",
        "        {",
        *readers,
        "        }",
        "    )",
    ]
    if unique_fields:
        lines += [
            "    for name, message in TAKEN.items():",
            "        if name in clean and taken(session, name, clean[name], item_id):",
            "            errors[name] = _(message)",
        ]
    lines += ["    return clean, errors", "", ""]
    if unique_fields:
        lines += [
            "def taken(session: Session, name: str, value: Any, item_id: int | None) -> bool:",
            f"    found = session.scalar(select({entity}.id).where(getattr({entity}, name) == value))",
            "    return found is not None and found != item_id",
            "",
            "",
        ]
    else:
        lines = [
            line.replace(", item_id: int | None", "") if line.startswith("    sent: Mapping") else line
            for line in lines
        ]
    stored = [f'        "{f.name}": {form_value(f)},' for f in fields]
    blank = [f'        "{f.name}": {blank_value(f)},' for f in fields]
    booleans = [f for f in fields if f.kind == "boolean"]
    typed_flags = "".join(f' | {{"{f.name}": sent["{f.name}"] == "yes"}}' for f in booleans)
    shown_lines = [f'        "{f.name}": {shown_text(f)},' for f in fields]
    lines += [
        f"def stored(item: {entity}{zone_parameter}) -> dict[str, Any]:",
        '    """What the form shows for a row as it is saved."""',
        "    return {",
        *stored,
        '        "version": item.version,',
        "    }",
        "",
        "",
        "def blank() -> dict[str, Any]:",
        "    return {",
        *blank,
        '        "version": "",',
        "    }",
        "",
        "",
        "def typed(sent: Mapping[str, str]) -> dict[str, Any]:",
        '    """What the person typed, back in the form after a refusal or a conflict."""',
        f'    return {{name: sent[name] for name in (*FIELDS, "version")}}{typed_flags}',
        "",
        "",
        f"def shown(item: {entity}{zone_parameter}) -> dict[str, str]:",
        "    return {",
        *shown_lines,
        "    }",
        "",
        "",
        f"def differences(item: {entity}, clean: Mapping[str, Any]{zone_parameter}) -> list[tuple[str, str]]:",
        '    """What the row holds now that differs from what a person sent: their label, and the row\'s value."""',
        f"    now = shown(item{zone_argument})",
        "    return [(_(SHOWN[name]), now[name]) for name in FIELDS if clean[name] != getattr(item, name)]",
        "",
        "",
        "def form(",
        "    request: Request,",
        "    session: Session,",
        f"    item: {entity} | None,",
        "    back: str,",
        "    values: Mapping[str, Any],",
        "    errors: Mapping[str, str],",
        "    status_code: int = 200,",
        "    conflict: list[tuple[str, str]] | None = None,",
        ") -> Response:",
        '    partial = fragment_requested(request) and request.method == "POST"',
        "    return render(",
        "        request,",
        f'        "{module.package}/form.html" if partial else "{module.package}/page.html",',
        "        status_code=200 if partial else status_code,",
        "        item=item,",
        f'        heading=item.{module.first.name} if item else "",',
        '        action=f"{PATH}/{item.id}" if item else PATH,',
        "        back=back,",
        "        values=values,",
        "        errors=errors,",
        "        summary=[(identifier(name), errors[name]) for name in FIELDS if name in errors],",
        "        conflict=conflict or [],",
        "        options={",
        *(
            [
                "            **{name: [(value, _(label)) for value, label in words.items()] "
                "for name, words in LABELS.items()},"
            ]
            if choice_fields
            else []
        ),
        *(
            f'            "{f.name}": reference_options(session, {f.target.entity}.id, '
            f"{f.target.entity}.{f.target.name}),"
            for f in fields
            if f.target
        ),
        "        },",
    ]
    if module.having("date"):
        lines += ["        earliest=EARLIEST.isoformat(),", "        latest=LATEST.isoformat(),"]
    lines += [
        "    )",
        "",
        "",
        f"def apply(item: {entity}, clean: Mapping[str, Any]) -> None:",
        "    for name in FIELDS:",
        "        setattr(item, name, clean[name])",
        "",
        "",
    ]
    if unique_fields:
        lines += [
            "def save(session: Session, item: " + entity + ", clean: Mapping[str, Any]) -> bool | None:",
            '    """True when saved, False when someone changed the row since it was read, None when another row took',
            "    a unique value in between: the database's own checks, which two people saving at once cannot pass.",
            '    """',
            "",
            "    def change() -> None:",
            "        apply(item, clean)",
            "        session.add(item)",
            "",
            "    try:",
            "        return saved(session, change)",
            "    except IntegrityError:",
            "        session.rollback()",
            "        return None",
        ]
    else:
        lines += [
            "def save(session: Session, item: " + entity + ", clean: Mapping[str, Any]) -> bool:",
            '    """True when saved, False when someone changed the row since it was read: the database checks it."""',
            "",
            "    def change() -> None:",
            "        apply(item, clean)",
            "        session.add(item)",
            "",
            "    return saved(session, change)",
        ]
    check_call = "checked(sent, session, {item}" + zone_argument + ")"
    if not unique_fields:
        check_call = "checked(sent, session" + zone_argument + ")"
    zone_line = ["    zone = zone_of(request)"] if zone_needed else []
    taken_after_create = []
    taken_after_update = []
    if unique_fields:
        taken_after_create = [
            "    if outcome is None:  # another row took a unique value since it was checked",
            f"        errors = {check_call.format(item='None')}[1]",
            "        return form(request, session, None, back, typed(sent), errors, 422)",
        ]
        taken_after_update = [
            "    if outcome is None:",
            f"        errors = {check_call.format(item='item_id')}[1]",
            "        return form(request, session, item_or_404(session, item_id), back, typed(sent), errors, 422)",
        ]
    lines += [
        "",
        "",
        "def new_form(request: Request, session: DatabaseSession, _person: Editor) -> Response:",
        "    return form(request, session, None, list_address(request, session), blank(), {})",
        "",
        "",
        "def create(request: Request, session: DatabaseSession, _person: Editor, sent: Sent) -> Response:",
        '    back = list_address(request, session, sent["back"])',
        *zone_line,
        f"    clean, errors = {check_call.format(item='None')}",
        "    if errors:",
        "        return form(request, session, None, back, typed(sent), errors, 422)",
        f"    item = {entity}()",
        "    outcome = save(session, item, clean)" if unique_fields else "    save(session, item, clean)",
        *taken_after_create,
        '    return whole_page(request, page_address(item.id, back, saved="1"))',
        "",
        "",
        "def edit_form(request: Request, item_id: int, session: DatabaseSession, _person: Editor) -> Response:",
        "    item = item_or_404(session, item_id)",
        *zone_line,
        f"    return form(request, session, item, list_address(request, session), stored(item{zone_argument}), {{}})",
        "",
        "",
        "def update(",
        "    request: Request, item_id: int, session: DatabaseSession, _person: Editor, sent: Sent",
        ") -> Response:",
        "    item = item_or_404(session, item_id)",
        '    back = list_address(request, session, sent["back"])',
        *zone_line,
        f"    clean, errors = {check_call.format(item='item_id')}",
        "    if errors:",
        "        return form(request, session, item, back, typed(sent), errors, 422)",
        '    late = read_version(sent["version"]) != item.version',
        f"    if late and (changes := differences(item, clean{zone_argument})):",
        '        return form(request, session, item, back, typed(sent) | {"version": item.version}, {}, 409, changes)',
        "    outcome = save(session, item, clean)",
        *taken_after_update,
        "    if outcome is False:  # someone saved in between: what they saved, and the person's own work, still typed",
        "        item = item_or_404(session, item_id)",
        f"        changes = differences(item, clean{zone_argument})",
        '        return form(request, session, item, back, typed(sent) | {"version": item.version}, {}, 409, changes)',
        '    return whole_page(request, page_address(item.id, back, saved="1"))',
        "",
        "",
        *related_counts(module),
        "def install(application: FastAPI) -> None:",
        *related_lines(module),
        "    add = application.add_api_route",
        "    add(PATH, item_list, include_in_schema=False)",
        '    add(f"{PATH}/new", new_form, include_in_schema=False)',
        '    add(PATH, create, methods=["POST"], include_in_schema=False)',
        '    add(f"{PATH}/{{item_id:int}}", item_page, include_in_schema=False)',
        '    add(f"{PATH}/{{item_id:int}}/edit", edit_form, include_in_schema=False)',
        '    add(f"{PATH}/{{item_id:int}}", update, methods=["POST"], include_in_schema=False)',
        "",
    ]
    return "\n".join(lines)


def package_code(module: Module) -> str:
    description = [module.description, ""] if module.description else []
    return "\n".join(
        [
            f'"""{module.title}: its list, its pages and its form.',
            "",
            *description,
            'Made by tools/new_module.py: change it as this application needs."""',
            "",
            "from pathlib import Path",
            "",
            "from fastapi import FastAPI",
            "",
            "from app.core.i18n import N_",
            "from app.core.templating import NavigationItem, add_templates",
            f"from app.{module.package} import routes" + (", views" if module.views else ""),
            "",
            "HERE = Path(__file__).resolve().parent",
            "",
            "",
            "def install(application: FastAPI) -> None:",
            '    add_templates(HERE / "templates")',
            '    application.state.languages.add_folder(HERE / "locales")',
            f'    item = NavigationItem(N_("{module.title}"), routes.PATH, "{module.icon}", role=routes.ROLE)',
            "    application.state.navigation.append(item)",
            "    routes.install(application)",
            *(["    views.install(application)"] if module.views else []),
            "",
        ]
    )


# --- other views of the same rows -------------------------------------------------------------------------------


def chunk(name: str, values: dict[str, str]) -> str:
    return Template((TEMPLATES / name).read_text(encoding="utf-8")).substitute(values)


def views_code(module: Module) -> str:
    """Imports may be more than it uses: `tidy` takes away the unused ones and puts the rest in order."""
    entity, zone = module.entity, module.having("datetime")
    names = [{"board": "a board", "calendar": "a calendar", "timeline": "a timeline"}[name] for name in module.views]
    from_models, from_routes = [entity], ["LARGEST_ID", "PATH", "SHOWN", "Editor", "Reader", "can_edit", "shown"]
    from_routes += ["view_links", *(["zone_of"] if zone else [])]
    board, calendar, plan = module.board, module.calendar, module.timeline
    if board:
        from_models.append(f"{board.constant}_CHOICES")
        from_routes.append(f"{board.constant}_LABELS")
    code = chunk(
        "views.py.txt",
        {
            "title": module.title,
            "names": " and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names),
            "model_import": f"from app.{module.package}.models import {', '.join(sorted(from_models))}",
            "route_import": f"from app.{module.package}.routes import {', '.join(from_routes)}",
            "entity": entity,
            "words": "shown(item, zone_of(request))" if zone else "shown(item)",
        },
    )
    common = {
        "entity": entity,
        "package": module.package,
        "first": module.first.name,
        "title": module.title,
        "singular": module.singular,
    }
    install = ["", "", "def install(application: FastAPI) -> None:", "    add = application.add_api_route"]
    if board:
        shown_lines = [f.name for f in module.fields if f.listed and f is not module.first and f is not board][:2]
        lines = ", ".join(f'"{name}"' for name in shown_lines) + ("," if len(shown_lines) == 1 else "")
        more = f'f"{{PATH}}?" + urlencode({{"{board.name}": key}})' if board.filter else "PATH"
        code += chunk(
            "board.py.txt",
            common
            | {
                "field": board.name,
                "phrase": board.phrase,
                "card_lines": lines,
                "labels": f"{board.constant}_LABELS",
                "choices": f"{board.constant}_CHOICES",
                "more": more,
            },
        )
        install += [
            "    add(BOARD_PATH, board_page, include_in_schema=False)",
            '    add(f"{BOARD_PATH}/move", move_card, methods=["POST"], include_in_schema=False)',
        ]
    if calendar:
        start, end = calendar.start.name, calendar.end.name if calendar.end else ""
        timed = calendar.start.kind == "datetime"
        if timed:
            ends = f"item.{end} if item.{end} and item.{end} > start else " if end else ""
            event_end = f"{ends}start + timedelta(hours=1)"
            bounds = (
                "    local = ZoneInfo(zone)\n"
                "    low = datetime.combine(first, time(), local).astimezone(UTC)\n"
                "    high = datetime.combine(after, time(), local).astimezone(UTC)"
            )
        else:
            event_end = f"max(item.{end}, start) if item.{end} else start" if end else "start"
            bounds = "    low, high = first, after"
        shift = (
            f"    if item.{end} is not None:\n        item.{end} = moved_to + (item.{end} - item.{start})"
            if end
            else ""
        )
        code += chunk(
            "calendar.py.txt",
            common
            | {
                "start": start,
                "start_phrase": calendar.start.phrase,
                "event_end": event_end,
                "bounds": bounds,
                "ends": f"func.coalesce({entity}.{end}, {entity}.{start})" if end else f"{entity}.{start}",
                "read_start": "read_moment(start)" if timed else "read_day(start)",
                "shift": shift,
                "when": "format_datetime(moved_to, request.app.state.settings.time_zone)"
                if timed
                else "format_date(moved_to)",
            },
        )
        install += [
            "    add(CALENDAR_PATH, calendar_page, include_in_schema=False)",
            '    add(f"{CALENDAR_PATH}/events", calendar_events, include_in_schema=False)',
            '    add(f"{CALENDAR_PATH}/move", move_event, methods=["POST"], include_in_schema=False)',
        ]
    if plan:
        start, end = plan.start.name, plan.end.name if plan.end else ""
        code += chunk(
            "timeline.py.txt",
            common
            | {
                "start": start,
                "start_phrase": plan.start.phrase,
                "task_end": f"item.{end} or item.{start}" if end else f"item.{start}",
            },
        )
        install.append("    add(TIMELINE_PATH, timeline_page, include_in_schema=False)")
    return code + "\n".join(install) + "\n"


def views_templates(module: Module) -> dict[str, str]:
    common = {"title": module.title, "package": module.package, "singular": module.singular, "path": module.path}
    written: dict[str, str] = {}
    if module.board:
        values = common | {"phrase": module.board.phrase}
        written |= {name: chunk(name, values) for name in ("board.html", "board_part.html")}
    if module.calendar:
        written["calendar.html"] = chunk("calendar.html", common | {"start_phrase": module.calendar.start.phrase})
    if module.timeline:
        start, end = module.timeline.start, module.timeline.end
        values = common | {
            "first": module.first.name,
            "first_label": module.first.label,
            "start": start.name,
            "start_label": start.label,
            "end_label": end.label if end else "Last day",
            "end_cell": f"item.{end.name}|date if item.{end.name} else item.{start.name}|date"
            if end
            else f"item.{start.name}|date",
        }
        written["timeline.html"] = chunk("timeline.html", values)
    return written


# --- sample data --------------------------------------------------------------------------------------------------


def sample_value(field: Field) -> str:
    """Made-up values, the same on every run: row `number` of the sample."""
    if field.kind == "text":
        stem = field.label[: max(field.longest - 4, 1)]
        return f'f"{stem} {{number + 1:03d}}"'
    if field.kind == "long_text":
        made_up = f'f"Made-up {field.phrase} for row {{number + 1}}."'
        return made_up if field.longest >= len(field.phrase) + 30 else f"{made_up}[:{field.longest}]"
    if field.kind == "integer":
        span = min(field.high - field.low, 100)
        return f"{field.low} + (number * 7) % {span + 1}"
    if field.kind == "decimal":
        span = min(field.high - field.low, 1000)
        start = f"Decimal({field.low}) + " if field.low else ""
        if field.places and span > 1:
            return f'{start}Decimal((number * 37) % {span}) + Decimal("1E-{field.places}") * (number % 10)'
        return f"{start}Decimal((number * 37) % {max(span, 1)})"
    if field.kind == "date":
        return "date(2026, 1, 5) + timedelta(days=number * 9)"
    if field.kind == "datetime":
        return "datetime(2026, 1, 5, 9, tzinfo=UTC) + timedelta(days=number * 3, hours=number % 8)"
    if field.kind == "boolean":
        return "number % 3 == 0"
    return f"{field.constant}_CHOICES[number % len({field.constant}_CHOICES)]"


def sample_code(module: Module) -> str:
    """Imports may be more than it uses: `tidy` takes away the unused ones and puts the rest in order."""
    choices = [f"{field.constant}_CHOICES" for field in module.fields if field.kind == "choice"]
    values = []
    for field in module.fields:
        if field.target:
            continue  # chosen in `fill`, from the rows that are there
        value = sample_value(field)
        if field.optional:
            value = f"None if number % 5 == 4 else {value}"
        values.append(f'        "{field.name}": {value},')
    if module.board:
        values.append('        "rank": (number + 1) * 1024,  # its place in its column on the board')
    after, numbers, chosen, pointed = [], [], [], ""
    if module.references:
        packages = ", ".join(f'"{package}"' for package in module.targets)
        after = [
            f"AFTER = ({packages},)",
            '"""The modules whose rows these point to: app.core.sample_data fills them first."""',
        ]
        numbers = [
            "def numbers(session: Session, model: Any) -> list[int]:",
            "    return list(session.scalars(select(model.id).order_by(model.id)))",
            "",
            "",
        ]
        for field in module.references:
            assert field.target  # noqa: S101  # references alone
            chosen.append(f"    {field.name}_rows = numbers(session, {field.target.entity})")
            if field.required:
                chosen += [
                    f"    if not {field.name}_rows:  # nothing to point to: no row can be made",
                    "        return",
                ]
            pick = f"{field.name}_rows[number % len({field.name}_rows)]"
            if field.optional:
                pick = f"None if number % 5 == 4 or not {field.name}_rows else {pick}"
            pointed += f", {field.column}={pick}"
    return "\n".join(
        [
            f'"""Made-up {module.plural}, so the list is not empty when the application is tried.',
            "",
            "They are invented: no real people, companies or things. See app/core/sample_data.py",
            '"""',
            "",
            "from datetime import UTC, date, datetime, timedelta",
            "from decimal import Decimal",
            "from typing import Any",
            "",
            "from sqlalchemy import delete, select",
            "from sqlalchemy.orm import Session",
            "",
            f"from app.{module.package}.models import {', '.join([*choices, module.entity])}",
            *(f"from app.{target.package}.models import {target.entity}" for target in module.targets.values()),
            "",
            f"ROWS = {ROWS}",
            *after,
            "",
            "",
            "def row(number: int) -> dict[str, Any]:",
            "    return {",
            *values,
            "    }",
            "",
            "",
            "def holds_rows(session: Session) -> bool:",
            f"    return session.scalar(select({module.entity}.id).limit(1)) is not None",
            "",
            "",
            "def empty(session: Session) -> None:",
            f"    session.execute(delete({module.entity}))",
            "",
            "",
            *numbers,
            "def fill(session: Session) -> None:",
            "    empty(session)",
            *chosen,
            f"    session.add_all({module.entity}(**row(number){pointed}) for number in range(ROWS))",
            "",
        ]
    )


# --- templates ----------------------------------------------------------------------------------------------------


def display(field: Field, item: str) -> str:
    """A stored value as a page shows it, in Jinja."""
    value = f"{item}.{field.name}"
    if field.target:
        name = f"{value}.{field.target.name}"
        return f'_("Not given") if {value} is none else {name}' if field.optional else name
    if field.kind in ("text", "long_text"):
        return value if field.required else f'{value} or _("Not given")'
    if field.kind == "integer":
        shown = f"{value}|decimal"
    elif field.kind == "decimal":
        shown = f"{value}|decimal({field.places})"
    elif field.kind == "date":
        shown = f"{value}|date"
    elif field.kind == "datetime":
        shown = f"local_datetime({value})"
    elif field.kind == "boolean":
        return f'_("Yes") if {value} else _("No")'
    else:
        return f"_(labels.{field.name}[{value}])"
    return f'_("Not given") if {value} is none else {shown}' if field.optional else shown


def form_field(field: Field) -> str:
    label = f'_("{field.label}")'
    arguments = [f'"{field.name}"', label]
    hint = f', hint=_("{field.hint}")' if field.hint else ""
    error = f'error=errors.get("{field.name}", "")'
    required = f"required={'true' if field.required else 'false'}"
    value = f"values.{field.name}"
    ident = f'"{field.identifier}"'
    if field.kind == "text":
        attributes = f'attributes={{"maxlength": {field.longest}, "autocomplete": "off"}}'
        call = f"input_field({', '.join(arguments)}, {value}, {ident}, {error}{hint}, {required}, {attributes})"
    elif field.kind == "long_text":
        attributes = f'attributes={{"maxlength": {field.longest}}}'
        call = f"textarea_field({', '.join(arguments)}, {value}, {ident}, {error}{hint}, {required}, {attributes})"
    elif field.kind == "integer":
        call = f"number_field({', '.join(arguments)}, {value}, {ident}, decimals=0, {error}{hint}, {required})"
    elif field.kind == "decimal":
        call = (
            f"number_field({', '.join(arguments)}, {value}, {ident}, decimals={field.places}, {error}{hint}, "
            f"{required})"
        )
    elif field.kind == "date":
        call = (
            f"date_field({', '.join(arguments)}, {value}, {ident}, {error}{hint}, {required}, earliest=earliest, "
            "latest=latest)"
        )
    elif field.kind == "datetime":
        call = (
            f'input_field({", ".join(arguments)}, {value}, {ident}, type="datetime-local", {error}{hint}, {required})'
        )
    elif field.kind == "boolean":
        call = f"checkbox_field({', '.join(arguments)}, {value}, {ident}, {error}{hint})"
    elif field.kind == "choice":
        options = f"options.{field.name}"
        call = f"select_field({', '.join(arguments)}, {options}, {value}, {ident}, {error}{hint}, required=true)"
    else:  # a reference: the rows of the module it points to, with a box to search them
        every = '_("Choose one")' if field.required else '_("None")'
        call = (
            f"searchable_select({', '.join(arguments)}, options.{field.name}, {value}, {ident}, every={every}, "
            f"{error}{hint}, {required})"
        )
    wide = " md:col-span-2" if field.kind in ("long_text", "boolean") else ""
    return f'    <div class="min-w-0{wide}">{{{{ {call} }}}}</div>'


def cell_line(field: Field, position: int, module: Module) -> str:
    if position == 0:
        return f'{{{{ row_header(row.{field.name}, "{module.path}/" ~ row.id) }}}}'
    options = ""
    if field.kind in ("integer", "decimal"):
        options += ", numeric=true"
    if position >= 2:
        options += ", wide_only=true"
    if field.target:
        address = f'"{field.target.path}/" ~ row.{field.column}'
        options += f", href={address} if row.{field.column} else none" if field.optional else f", href={address}"
    return f"{{{{ cell({display(field, 'row')}{options}) }}}}"


def templates(module: Module) -> dict[str, str]:
    listed = [field for field in module.fields if field.listed]
    values = {
        "title": module.title,
        "description": module.description,
        "new_label": f"New {module.singular}",
        "list_label": f"List of {module.plural}",
        "package": module.package,
        "path": module.path,
        "singular": module.singular,
        "plural": module.plural,
        "caption": f"{module.title}: " + ", ".join(field.phrase for field in listed),
        "icon": module.icon,
        "first": module.first.name,
        "cells": "\n".join(cell_line(field, position, module) for position, field in enumerate(listed)),
        "details": ",\n".join(f'    (_("{field.label}"), {display(field, "item")})' for field in module.fields),
        "fields": "\n".join(form_field(field) for field in module.fields),
        "views": (
            f'{{% from "ui/macros.html" import tabs %}}\n{{{{ tabs(_("{module.title}: views"), views, "list") }}}}\n'
            if module.views
            else ""
        ),
    }
    written = {}
    for name in ("list", "results", "detail", "page", "form"):
        text = Template((TEMPLATES / f"{name}.html").read_text(encoding="utf-8")).substitute(values)
        if not module.description:
            text = text.replace(', _("")', "")
        written[f"{name}.html"] = text
    return written


# --- tests --------------------------------------------------------------------------------------------------------


def typed_value(field: Field) -> str:
    """A value a person could type in the field, as the form sends it."""
    if field.kind == "text":
        return f"New {field.phrase}"[: field.longest]
    if field.kind == "long_text":
        return f"What a person wrote about the {field.phrase}."[: field.longest]
    if field.kind == "integer":
        return str(field.low + min(7, field.high - field.low))
    if field.kind == "decimal":
        whole = field.low + min(12, field.high - field.low - 1) if field.high - field.low > 1 else field.low
        return f"{whole}.{'5' * field.places}" if field.places else str(whole)
    if field.kind == "date":
        return "2026-05-04"
    if field.kind == "datetime":
        return "2026-05-04T09:30"
    if field.kind == "boolean":
        return "yes"
    if field.target:
        return "1"  # the first row of the module it points to, which the sample data made
    return field.choices[-1][0]


def view_tests(module: Module) -> list[str]:
    """The board, the calendar and the timeline: each opens, and each moves what it can move, as a person would."""
    path, lines = module.path, []
    if module.views:
        lines += [
            "def test_the_list_leads_to_the_other_views(filled, person):",
            "    client, _url = filled",
            f'    page = client.get("{path}", headers=person)',
            *(f"    assert 'href=\"{path}/{name}\"' in page.text" for name in module.views),
            "",
            "",
        ]
    if board := module.board:
        first_label = board.choices[0][1]
        lines += [
            "def test_the_board_shows_its_columns_and_a_card_moves_to_another(filled, person):",
            "    client, url = filled",
            f'    page = client.get("{path}/board", headers=person)',
            f'    assert page.status_code == 200 and "{first_label}" in page.text',
            "    assert any(shown(item) in page.text for item in rows(url))",
            "    item = rows(url)[0]",
            f"    to = next(value for value in {board.constant}_CHOICES if value != item.{board.name})",
            '    move = {"card": str(item.id), "to": to, "after": "", "version": str(item.version)}',
            f'    sent = client.post("{path}/board/move", data=move, headers=SAME_SITE | person, '
            "follow_redirects=False)",
            "    assert sent.status_code == 303",
            f"    assert rows(url)[0].{board.name} == to",
            f'    again = client.post("{path}/board/move", data=move, headers=SAME_SITE | person)',
            '    assert again.status_code == 409, "a move made on an old page moves nothing"',
            "",
            "",
        ]
    if calendar := module.calendar:
        start, timed = calendar.start.name, calendar.start.kind == "datetime"
        day, later, sent_start = (
            (f"item.{start}.date()", "timedelta(hours=1)", 'to.strftime("%Y-%m-%dT%H:%M:%SZ")')
            if timed
            else (f"item.{start}", "timedelta(days=1)", "to.isoformat()")
        )
        lines += [
            "def test_the_calendar_gives_the_events_of_its_days_and_one_moves(filled, person):",
            "    client, url = filled",
            f"    item = next(found for found in rows(url) if found.{start} is not None)",
            f"    day = {day}",
            '    month = {"view": "month", "date": day.isoformat()}',
            f'    page = client.get("{path}/calendar", params=month, headers=person)',
            "    assert page.status_code == 200 and shown(item) in page.text",
            '    days = {"start": (day - timedelta(days=1)).isoformat(), "end": (day + timedelta(days=2)).isoformat()}',
            f'    events = client.get("{path}/calendar/events", params=days, headers=person).json()',
            f'    assert str(item.{module.first.name}) in [event["title"] for event in events]',
            f"    to = item.{start} + {later}",
            f'    drop = {{"event": f"{module.package}-{{item.id}}", "start": {sent_start}, '
            '"version": str(item.version)}',
            f'    moved = client.post("{path}/calendar/move", data=drop, headers=SAME_SITE | person)',
            "    assert moved.status_code == 200, moved.text",
            f"    assert one(url, item.id).{start} == to",
            f'    late = client.post("{path}/calendar/move", data=drop, headers=SAME_SITE | person)',
            '    assert late.status_code == 409, "a drop made on an old page moves nothing"',
            "",
            "",
        ]
    if module.timeline:
        lines += [
            "def test_the_timeline_shows_each_row_with_a_date(filled, person):",
            "    client, url = filled",
            f'    page = client.get("{path}/timeline", params={{"scale": "month"}}, headers=person)',
            "    assert page.status_code == 200",
            "    assert any(shown(item) in page.text for item in rows(url))",
            "",
            "",
        ]
    return lines


def tests_code(module: Module) -> str:
    first = module.first
    valid = "\n".join(f'    "{field.name}": "{typed_value(field)}",' for field in module.fields)
    other_text = next((f for f in module.fields if f.kind in ("text", "long_text") and f is not first), None)
    searched = next((f for f in module.fields if f.search), None)
    searched_values = ", ".join(f"item.{f.name}" for f in module.fields if f.search) + ","
    filtered = next((f for f in module.fields if f.filter and not f.target), None)
    unique = next((f for f in module.fields if f.unique), None)
    pointing = next((f for f in module.fields if f.target and f.filter), None)
    reference = next((f for f in module.fields if f.target), None)
    path = module.path
    lines = [
        f'"""{module.title}: what tools/new_module.py made, proved. Change these tests with the module."""',
        "",
        "from collections.abc import Iterator",
        "from datetime import timedelta",
        "from typing import Any",
        "",
        "import pytest",
        "from fastapi.testclient import TestClient",
        "from markupsafe import escape",
        "from sqlalchemy import select",
        "from sqlalchemy.orm import Session",
        "",
        "from app.core.database import create_database_engine, migrate",
        "from app.core.sample_data import fill_all",
        f"from app.{module.package} import sample_data",
        f"from app.{module.package}.models import {module.entity}"
        + (f", {module.board.constant}_CHOICES" if module.board else ""),
        "from app.main import create_app",
        "from tests.conftest import build_settings, page_opener, running_server",
        "from tests.helpers import plain, run_axe_in_both_themes, shows_only",
        "",
        'SAME_SITE = {"Sec-Fetch-Site": "same-origin"}',
        'OUTSIDER = {"X-Remote-User": "someone.else", "X-Remote-Name": "Someone Else", "X-Remote-Groups": "staff"}',
        '"""Someone who signed in, without the role this module asks for."""',
        'ENGLISH = {"default_language": "en"}',
        '"""The texts\' own language, whatever the application\'s default: in Spanish, 12.5 would read 125."""',
        "VALID = {",
        valid,
        "}",
        '"""A form a person could send, every field filled."""',
        "",
        "",
        "def filled_database(url: str) -> str:",
        '    """Every module\'s made-up rows: a row may point to another module\'s."""',
        "    migrate(url)",
        "    engine = create_database_engine(url)",
        "    with Session(engine) as session:",
        "        fill_all(session)",
        "        session.commit()",
        "    engine.dispose()",
        "    return url",
        "",
        "",
        "@pytest.fixture",
        "def filled(database_url: str) -> Iterator[tuple[TestClient, str]]:",
        "    url = filled_database(database_url)",
        "    application = create_app(build_settings(database_url=url, **ENGLISH))",
        "    yield TestClient(application, raise_server_exceptions=False), url",
        "",
        "",
        f"def rows(url: str) -> list[{module.entity}]:",
        "    engine = create_database_engine(url)",
        "    with Session(engine) as session:",
        f"        found = list(session.scalars(select({module.entity}).order_by({module.entity}.id)))",
        "    engine.dispose()",
        "    return found",
        "",
        "",
        f"def one(url: str, number: int) -> {module.entity}:",
        "    return next(item for item in rows(url) if item.id == number)",
        "",
        "",
        f"def shown(item: {module.entity}) -> str:",
        '    """Its name as a page writes it. These tests read the rows there are: the sample data can change."""',
        f"    return str(escape(item.{first.name}))",
        "",
        "",
        "def test_the_list_shows_its_rows(filled, person):",
        "    client, url = filled",
        f'    page = client.get("{path}", headers=person)',
        "    assert page.status_code == 200",
        "    assert any(shown(item) in page.text for item in rows(url))",
        "",
        "",
    ]
    if searched:
        lines += [
            "def test_a_search_finds_the_row_it_names(filled, person):",
            "    client, url = filled",
            "    found = rows(url)",
            f"    wanted = str(next(item.{searched.name} for item in found if item.{searched.name}))",
            f'    page = client.get("{path}", params={{"q": wanted, "size": 100}}, headers=person)',
            "    texts = {item.id: plain(' '.join(str(text or '') for text in "
            f"({searched_values}))) for item in found}}",
            "    named = [item for item in found if plain(wanted) in texts[item.id]]",
            "    others = [shown(item) for item in found if item not in named]",
            "    shows_only(page.text, [shown(item) for item in named], others)",
            "",
            "",
        ]
    if filtered:
        flag = filtered.kind == "boolean"
        value = '"yes"' if flag else f"kept.{filtered.name}"
        lines += [
            "def test_a_filter_keeps_only_its_rows(filled, person):",
            "    client, url = filled",
            "    found = rows(url)",
            f"    kept = next(item for item in found if item.{filtered.name})" if flag else "    kept = found[0]",
            f'    page = client.get("{path}", params={{"{filtered.name}": {value}, "size": 100}}, headers=person)',
            f"    inside = [shown(item) for item in found if item.{filtered.name} == kept.{filtered.name}]",
            f"    outside = [shown(item) for item in found if item.{filtered.name} != kept.{filtered.name}]",
            "    shows_only(page.text, inside, outside)",
            "",
            "",
        ]
    if pointing:
        lines += [
            f"def test_a_filter_keeps_only_the_rows_of_one_{pointing.name}(filled, person):",
            "    client, url = filled",
            "    found = rows(url)",
            f"    first = next(item for item in found if item.{pointing.column} is not None)",
            f'    page = client.get("{path}", params={{"{pointing.name}": first.{pointing.column}, "size": 100}}, '
            "headers=person)",
            f"    inside = [shown(item) for item in found if item.{pointing.column} == first.{pointing.column}]",
            f"    outside = [shown(item) for item in found if item.{pointing.column} != first.{pointing.column}]",
            "    shows_only(page.text, inside, outside)",
            "",
            "",
        ]
    if pointing and pointing.target:
        lines += [
            f"def test_the_page_of_a_{pointing.name}_leads_to_its_{module.package}(filled, person):",
            "    client, url = filled",
            f"    number = next(item.{pointing.column} for item in rows(url) if item.{pointing.column} is not None)",
            f'    page = client.get(f"{pointing.target.path}/{{number}}", headers=person)',
            f"    assert f'href=\"{path}?{pointing.name}={{number}}\"' in page.text",
            "",
            "",
        ]
    if reference:
        lines += [
            f"def test_a_{reference.name}_that_is_not_there_is_refused(filled, person):",
            "    client, url = filled",
            "    before = len(rows(url))",
            f'    sent = client.post("{path}", data=VALID | {{"{reference.name}": "999999"}}, '
            "headers=SAME_SITE | person)",
            "    assert sent.status_code == 422",
            f'    assert "{reference.label}: choose one from the list." in sent.text',
            "    assert len(rows(url)) == before",
            "",
            "",
        ]
    lines += [
        "def test_a_new_one_is_saved_and_shown(filled, person):",
        "    client, url = filled",
        "    before = len(rows(url))",
        f'    sent = client.post("{path}", data=VALID, headers=SAME_SITE | person, follow_redirects=False)',
        "    assert sent.status_code == 303",
        '    page = client.get(sent.headers["location"], headers=person)',
        f'    assert VALID["{first.name}"] in page.text',
        "    assert len(rows(url)) == before + 1",
        "",
        "",
        "def test_a_refused_value_keeps_what_was_typed(filled, person):",
        "    client, url = filled",
        "    before = len(rows(url))",
        f'    sent = client.post("{path}", data=VALID | {{"{first.name}": ""}}, headers=SAME_SITE | person)',
        "    assert sent.status_code == 422",
        f'    assert "Enter the {first.phrase}." in sent.text',
    ]
    if other_text:
        lines.append(f'    assert VALID["{other_text.name}"] in sent.text')
    lines += [
        "    assert len(rows(url)) == before",
        "",
        "",
        "def test_an_edit_is_saved(filled, person):",
        "    client, url = filled",
        "    item = rows(url)[-1]",
        '    form = VALID | {"version": str(item.version)}',
        f'    sent = client.post(f"{path}/{{item.id}}", data=form, headers=SAME_SITE | person, follow_redirects=False)',
        "    assert sent.status_code == 303",
        f'    assert one(url, item.id).{first.name} == VALID["{first.name}"]',
        "",
        "",
        "def test_an_edit_made_on_an_old_page_says_what_changed_and_saves_nothing(filled, person):",
        "    client, url = filled",
        "    item = rows(url)[-1]",
        '    first = VALID | {"version": str(item.version)}',
        f'    client.post(f"{path}/{{item.id}}", data=first, headers=SAME_SITE | person)',
        f'    late = VALID | {{"{first.name}": "Typed on an old page", "version": str(item.version)}}',
        f'    sent = client.post(f"{path}/{{item.id}}", data=late, headers=SAME_SITE | person)',
        "    assert sent.status_code == 409",
        f'    assert "Someone else changed this {module.singular}" in sent.text',
        f'    assert one(url, item.id).{first.name} == VALID["{first.name}"]',
        "",
        "",
    ]
    if unique:
        lines += [
            "def test_a_value_another_row_has_is_refused(filled, person):",
            "    client, url = filled",
            "    before = len(rows(url))",
            f'    taken = VALID | {{"{unique.name}": str(rows(url)[0].{unique.name})}}',
            f'    sent = client.post("{path}", data=taken, headers=SAME_SITE | person)',
            "    assert sent.status_code == 422",
            f'    assert "Another {module.singular} already has this {unique.phrase}." in sent.text',
            "    assert len(rows(url)) == before",
            "",
            "",
        ]
    lines += view_tests(module)
    lines += [
        "def test_without_the_role_nothing_opens_and_nothing_changes(filled):",
        "    client, url = filled",
        "    before = len(rows(url))",
        f'    assert client.get("{path}", headers=OUTSIDER).status_code == 403',
        f'    assert client.get("{path}/1", headers=OUTSIDER).status_code == 403',
        f'    assert client.post("{path}", data=VALID, headers=SAME_SITE | OUTSIDER).status_code == 403',
        "    assert len(rows(url)) == before",
        "",
        "",
        "def test_each_page_opens(filled, person):",
        '    """The scan in a browser, below, would pass on an error page too."""',
        "    client, url = filled",
        "    number = rows(url)[0].id",
        f'    for address in ("{path}", f"{path}/{{number}}", "{path}/new", f"{path}/{{number}}/edit"):',
        "        assert client.get(address, headers=person).status_code == 200, address",
        "",
        "",
        "def test_a_row_that_does_not_exist_is_not_found(filled, person):",
        "    client, _url = filled",
        f'    assert client.get("{path}/999999", headers=person).status_code == 404',
        f'    assert client.get("{path}/99999999999999", headers=person).status_code == 404',
        "",
        "",
        "def test_the_sample_data_fills_an_empty_table(database_url):",
        "    migrate(database_url)",
        "    engine = create_database_engine(database_url)",
        "    with Session(engine) as session:",
        "        assert not sample_data.holds_rows(session)",
        "        fill_all(session)",
        "        session.commit()",
        "        assert sample_data.holds_rows(session)",
        "    engine.dispose()",
        "",
        "",
        '@pytest.fixture(scope="module")',
        "def filled_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:",
        "    url = filled_database(f\"sqlite:///{(tmp_path_factory.mktemp('browser') / 'filled.db').as_posix()}\")",
        '    who = {"fake_identity": True, "fake_groups": ["admins"], "trusted_proxies": []}',
        "    settings = build_settings(database_url=url, **ENGLISH, **who)",
        "    with running_server(create_app(settings)) as port:",
        '        yield f"http://127.0.0.1:{port}"',
        "",
        "",
        "@pytest.mark.browser",
        f'@pytest.mark.parametrize("path", ["{path}", "{path}/1", "{path}/new", "{path}/1/edit"'
        + "".join(f', "{path}/{name}"' for name in module.views)
        + "])",
        "def test_no_detectable_accessibility_failure(browser: Any, filled_server: str, path: str):",
        "    with page_opener(browser, filled_server) as open_page:",
        "        assert run_axe_in_both_themes(open_page(path, bypass_csp=True)) == []",
        "",
    ]
    return "\n".join(lines)


# --- putting it in place -------------------------------------------------------------------------------------------


def added_import(text: str, line: str, before: str) -> str:
    """`line` among the imports of its kind, in order, so that the formatter leaves the file as it is."""
    lines = text.splitlines(keepends=True)
    prefix = line.split(" ")[0] + " app."
    kin = [index for index, existing in enumerate(lines) if existing.startswith(prefix) and "# demo" not in existing]
    for index in kin:
        if lines[index].split("#")[0].strip() > line.split("#")[0].strip():
            lines.insert(index, line + "\n")
            return "".join(lines)
    anchor = next(index for index, existing in enumerate(lines) if existing.startswith(before))
    target = kin[-1] + 1 if kin and kin[-1] >= anchor else anchor
    lines.insert(target, line + "\n")
    return "".join(lines)


def install_in_main(text: str, package: str) -> str:
    text = added_import(text, f"from app.{package} import install as install_{package}", "from app.core.settings")
    marker = "    install_home(application)\n"
    if marker not in text:
        raise Refused("app/main.py has no install_home(application): add the module's install there by hand")
    return text.replace(marker, f"    install_{package}(application)\n{marker}", 1)


def import_in_env(text: str, package: str) -> str:
    return added_import(text, f"import app.{package}.models  # noqa: F401", "from app.core.database")


def tidy(files: list[Path], rules: str = "I,F401") -> None:
    """The generated Python as the project's formatter writes it, with only the imports it uses. `migrations/env.py`
    keeps every import, which is how Alembic sees each table: there, only a `noqa` that has nothing to silence goes."""
    ruff = [sys.executable, "-m", "ruff"]
    names = [str(path) for path in files]
    # F401 is read, so a needed `noqa` is seen as needed, but in env.py it never takes an import away
    fixes = ["--unfixable", "F401"] if "F401" not in rules else []
    rules = rules if "F401" in rules else f"{rules},F401"
    subprocess.run([*ruff, "check", "--quiet", "--fix", "--exit-zero", *fixes, "--select", rules, *names], check=True)
    subprocess.run([*ruff, "format", "--quiet", *names], check=True)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


_SQLITE_BOOLEAN_DEFAULT = re.compile(r"""(sa\.Boolean\(\).*?server_default=)sa\.text\((["'])([01])\2\)""")


def portable_defaults(migration: str) -> str:
    """A boolean's default as both databases read it. Alembic writes what SQLite holds, 0 or 1, and PostgreSQL refuses
    an integer as a boolean column's default; `sa.false()` and `sa.true()` are what the demo's migrations use."""
    return _SQLITE_BOOLEAN_DEFAULT.sub(
        lambda found: found[1] + ("sa.true()" if found[3] == "1" else "sa.false()"), migration
    )


def migration(root: Path, module: Module) -> None:
    """Written by Alembic from the model, against a database at the newest migration, as a person would make it."""
    from alembic import command
    from alembic.config import Config

    sys.path.insert(0, str(root))
    from app.core.database import migrate, next_revision

    # Alembic formats what it writes with ruff, from the environment this runs in
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as folder:
        url = f"sqlite:///{(Path(folder) / 'now.db').as_posix()}"
        migrate(url)
        config = Config(toml_file=str(root / "pyproject.toml"))
        config.attributes["database_url"] = url
        revision = next_revision(root / "migrations" / "versions")
        command.revision(config, message=f"{module.title}: their table", autogenerate=True, rev_id=revision)
    for written in (root / "migrations" / "versions").glob(f"{revision}_*.py"):
        lines = portable_defaults(written.read_text(encoding="utf-8")).splitlines(keepends=True)
        kept = "".join(line for line in lines if "### " not in line)  # Alembic's own reminders: read it, as the rest
        written.write_text(re.sub(r"\n\n\n+(?=\n*def |\Z)", "\n\n\n", kept), encoding="utf-8", newline="\n")
        tidy([written])


def description(module: Module) -> str:
    return "\n".join(
        [
            "# What tools/new_module.py made this module with. A reference from another module reads it: if the model",
            "# changes these names, change them here too.",
            f'entity = "{module.entity}"',
            f'table = "{module.table}"',
            f'path = "{module.path}"',
            f'name = "{module.first.name}"',
            "",
        ]
    )


def make(module: Module, root: Path = ROOT, catalogues: bool = True) -> list[str]:
    """Writes the module, and gives back what is left for a person. On a failure, what it wrote goes."""
    if (root / "app" / "demo").exists():
        raise Refused(
            "this is the base, with its demo: start an application with tools/remove_demo.py, then run it there"
        )
    app = root / "app" / module.package
    main, env = root / "app" / "main.py", root / "migrations" / "env.py"
    tests = root / "tests" / f"test_{module.package}.py"
    if tests.exists():
        raise Refused(f"{tests.relative_to(root).as_posix()} exists already: nothing was written")
    before = {path: path.read_text(encoding="utf-8") for path in (main, env)}
    versions = set((root / "migrations" / "versions").glob("*.py"))
    try:
        write(app / "__init__.py", package_code(module))
        write(app / "models.py", models_code(module))
        write(app / "routes.py", routes_code(module))
        write(app / "sample_data.py", sample_code(module))
        write(app / DESCRIPTION, description(module))
        for name, text in (templates(module) | views_templates(module)).items():
            write(app / "templates" / module.package / name, text)
        if module.views:
            write(app / "views.py", views_code(module))
        write(tests, tests_code(module))
        write(main, install_in_main(before[main], module.package))
        write(env, import_in_env(before[env], module.package))
        tidy([*sorted(app.glob("*.py")), tests, main])
        tidy([env], "I,RUF100")
        migration(root, module)
        if catalogues:  # in a process of its own, which finds the new package among the others
            subprocess.run([sys.executable, str(root / "tools" / "translations.py"), "update"], cwd=root, check=True)
    except BaseException:
        shutil.rmtree(app, ignore_errors=True)
        tests.unlink(missing_ok=True)
        for path, text in before.items():
            path.write_text(text, encoding="utf-8", newline="\n")
        for added in set((root / "migrations" / "versions").glob("*.py")) - versions:
            added.unlink()
        raise
    return [
        f"app/{module.package}/ and tests/test_{module.package}.py are written, the module is in app/main.py and its "
        "migration in migrations/versions/: read them, and change what this application needs.",
        f"Translate its texts in app/{module.package}/locales/, then `uv run --frozen python tools/translations.py "
        "check`: the tests refuse a text a person has not translated.",
        "Then `uv run --frozen python -m app.core.sample_data` for its made-up rows, and the tests.",
    ]


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Writes a new module of screens: list, detail and form.")
    parser.add_argument("--spec", type=Path, help="the module's description, in TOML")
    parser.add_argument("--example", action="store_true", help="print a commented description to start from")
    options = parser.parse_args(arguments)
    if options.example:
        print(EXAMPLE, end="")
        return 0
    if not options.spec:
        parser.error("--spec or --example")
    try:
        spec = tomllib.loads(options.spec.read_text(encoding="utf-8"))
        for line in make(read_module(spec, ROOT / "app")):
            print(line)
    except (Refused, tomllib.TOMLDecodeError, OSError) as problem:
        print(f"Nothing was written: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
