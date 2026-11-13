---
type: reference
title: A new module
description: "How tools/new_module.py writes a module from a short description: list, detail, form, and optionally board, calendar and timeline"
tags: [base, a-new-module]
---

# A new module

`tools/new_module.py` writes a complete module of screens from a short description: a list with search, filters and
pages, a page for each row, and one form to add or change a row, and, if the description asks, a board, a calendar and
a timeline of the same rows. Each module is a package of `app/`.

```bash
uv run --frozen python tools/new_module.py --example > module.toml   # a commented description to start from
uv run --frozen python tools/new_module.py --spec module.toml
```

| In the description | What it says |
|---|---|
| `package`, `entity`, `title`, `singular`, `plural` | The package (`app/assets/`), the model's class, and the words the pages use, in English: they go through the translations |
| `path`, `icon`, `description`, `role`, `edit_role` | Optional: the address (`/assets`), a Lucide icon for the navigation, a line under the title, who may open it and who may change it (`admin` for both; `signed_in` is everyone identified, and its tests prove the 401 instead of the 403) |
| `[[field]]` | `name`, `label` and `type`: `text`, `long_text`, `integer`, `decimal`, `date`, `datetime`, `boolean`, `choice` or `reference`. Then `required`, `unique` (a text, a whole number or a date, and required), `search` (a text), `filter` (a choice, a yes or no, or a reference), `list` (a column), `hint`, and the limits of its type: `longest`, `low`, `high`, `places`, `choices` |
| `[board]` | `field`, a choice: a card for each row, in a column for each of its values, moved by its own form or by dragging, at `<path>/board` |
| `[calendar]` | `start`, a date or a date and time, and `end`, of the same type, if each row has one: each row on its day or at its time, moved by dragging or through its form, at `<path>/calendar` |
| `[timeline]` | `start`, a date, and `end`, a date, if each row has one: each row as a bar on its days, the earliest first, at `<path>/timeline` |
| A `reference` | `to`, the package of another module this tool made: each row points to one of its rows. The form offers its rows by name, with a box to search them; the list shows the name as a link to that row, and can filter by it, so `/guests?visit=3` lists one visit's guests, and each visit's page leads there, with how many there are, in a button at its top beside *Edit*: `RelatedList` in `app/core/tables.py`, which the module that points adds to `application.state.related`. Make the module it points to first. The column is `<name>_id`, so a field cannot be called that too |

The first field shown in the list names each row: a required text. A description that breaks a rule is refused with
what to fix, and nothing is written; so is a package that exists.

| It writes | As the base does it |
|---|---|
| `models.py` | A model on `Base`, exact decimals and moments in UTC, a check constraint for each choice, an index on what is sorted or filtered, and a version column |
| The migration | `alembic revision --autogenerate`, against a database at the newest migration, as a person makes one |
| `routes.py` | A `ListView` with its columns, filters and search; a page per row; a form read at its edge with `app/core/forms.py`, every problem by field and what was typed kept; a unique value checked before saving and by the database; a save on an old page shows what the other person changed, and saves nothing |
| `templates/` | Only the base's macros: `server_table`, `filter_bar`, `description_list`, the field macros, `error_summary` and `conflict_notice`; for its other views `board`, `calendar` and `gantt`, with `tabs` between them and the list |
| `views.py` | With a board, a calendar or a timeline: their pages and moves, on `app/core/boards.py` (`column_lock`, `place_card`), `app/core/calendars.py` (`agenda`) and `app/core/gantt.py`. A board gives the table a `rank` column |
| `sample_data.py` | Made-up rows, the same on every run, which a preview fills by itself. A reference points to the other module's rows, which `AFTER` fills first |
| `module.toml` | Its entity, table, address and the field that names each row: what another module's reference reads |
| `locales/` | Every text in every language's catalogue. The texts every module has (*Save*, *Cancel*, what a board or a calendar says) come translated, from `tools/module_template/locales/`; the module's own, where its words and their gender matter, are left untranslated: a person translates them, and until then `tools/translations.py check` names them |
| `tests/test_<package>.py` | The list, search, filters, a new row, a refused value, an edit, an edit on an old page, a unique value, a reference to a row that is not there, a card moved and a move on an old page, a calendar's events and a drop, the timeline, the role, each page opening, a row that does not exist, the sample data, and the accessibility scan of each screen in both themes. They read the rows the database has, not fixed places of the sample data, so they still pass once the made-up rows are replaced with ones that look like the application's |

It also adds the module to `app/main.py` and its models to `migrations/env.py`, and formats what it wrote with the
project's formatter. On a failure, everything it wrote goes. The stylesheet already holds every class the module's
templates use, so nothing has to be built again.

| Decision | Why | Instead of |
|---|---|---|
| A generator, not a pattern to copy | What can be written by code is written the same way every time, and it passes the checks from the first run: an assistant spends its time on what is particular to the application, not on learning the base | Copying a screen of the demo and adapting it, which reads most of the base first and drifts with each copy |
| Plain code, as a person writes it | What it writes belongs to the application from then on: it is read and changed like any other code, with no tie back to the generator | Code that calls the generator at run time, or a framework of generic screens |
| One kind of module, with its other views | A list, a page and a form cover most of what a business application holds. A board, a calendar and a timeline of the same rows are options of the module, since one written by hand starts by reading the base's pieces, which costs more than the rest of the module. A dashboard reads several modules, so it stays the application's own, on `stats` and `chart` | A generator for every screen; or views left to be written by hand from `app/core/` |
| Texts left for a person | Machine translations are not accepted as they are, so the tests name every text of the module's own until a person has read it. The texts every module shares were read once, here | Translations written by the tool |
