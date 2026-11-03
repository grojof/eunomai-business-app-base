# AGENTS.md — business-app-base

For anyone working in this repository, person or AI assistant. The repository is in English and names no organization,
person or real system: it stays neutral so anyone can clone it.

## What goes where

| Folder | Contents | Rule |
|---|---|---|
| `app/core/` | Identity, roles, settings, the database and its column types, lists on the server, reading forms, uploads, languages, formatters, errors, health | Never imports from `app/demo/` |
| `app/ui/` | Components as macros, the settings menu, the command palette, the stylesheet's source, the few JavaScript files, Lucide's icons, the illustrations | Screens call macros; daisyUI classes stay here where possible |
| `app/brand/` | The theme, logos, the organization's own icons | The only folder an organization must change |
| `app/demo/` | Demo screens, models, generated data, the gallery and their translations | Deleting it leaves a working application |
| `migrations/` | Alembic's setup, and one file per change of the models | A model that changes needs its migration: a test compares them on both databases |

## Components

Before using a component, read [`docs/components/README.md`](docs/components/README.md), then
[`rules.md`](docs/components/rules.md) once, and only the page of each component you use: never the whole official file.
Prefer `approved` components; an approved component needs a macro. Those pages are generated: change
`app/ui/catalog.py`, then run `tools/components.py`. `app/demo/examples/` is generated too, from daisyUI's documentation:
never edit it, run `tools/gallery.py`. To see a component live, open `/gallery/<name>` in the demo.
Add your own components as [the specification](docs/specification.md#adapting-it) says.

## Rules

- Read [Standards](docs/standards.md) before writing a screen or a component. It is the only home of the rules: each
  has an identifier, an official source and a check. A change that breaks one is not finished, whatever else it does.
- Base decisions on those sources, not on what seems right. A new rule needs its source and its test, or it says
  *Project decision*. A test names the rule it proves: `@pytest.mark.rule("A11Y-05")`.
- Build the plain HTML first: it must work with a keyboard and a screen reader before any behaviour is added on top.
- Every text a user can see goes through translation. Every number, date and time goes through the locale's formatter.
- Colours come from the brand. No invented values such as `bg-[#ff0000]`, `text-[13px]` or `[color:#ff0000]`: a test
  refuses them.
- Use the existing macros before writing anything new: screens call `button`, not a raw `.btn`. daisyUI's examples in
  the gallery are reference material, not a model for a screen. After changing templates, run
  `uv run --frozen python tools/css.py`.
- An icon comes from Lucide's set or the organization's own icons in `app/brand/icons/`, and only through the `icon`
  macro or a macro that takes an icon's name. Find one with `uv run --frozen python tools/icons.py search <words>`, in
  English, Spanish or Catalan. Never draw an SVG inline, never bring another collection, never edit Lucide's folder:
  `tools/vendor.py` keeps it, as [Icons and illustrations](docs/specification.md#icons-and-illustrations) says.
- An illustration is a file in `app/ui/static/illustrations/`, made with the organization's own tools if it has them,
  and shown with `<img src>` or as a CSS background, never inline.
- Each screen handles its empty, loading, error and no-permission states.
- A new component needs its page in the demo and its tests, in the same change.
- Money and quantities are `Mapped[Decimal]`, moments `Mapped[datetime]` with their time zone. Never a float. On SQLite,
  a sum in SQL raises `InexactQuery`: use `total()`. [Data](docs/specification.md#data) says how the two databases differ.
- A route that uses the database takes `DatabaseSession`, is declared with `def`, and commits itself.
- A long list uses `ListView` from `app/core/tables.py`, whose values are checked against lists, never text from the
  address in SQL: read [Lists on the server](docs/specification.md#lists-on-the-server). Charts come from
  `app/core/charts.py` and the `chart` macro, always with a summary. Excel comes from `app/core/excel.py`. A board
  comes from `app/core/boards.py`, a timeline from `app/core/gantt.py` and a calendar from `app/core/calendars.py`,
  each with its macro: the server decides every move.
- A form uses the field macros and reads every value with `app/core/forms.py`, at the edge: read
  [Forms](docs/specification.md#forms). It is `novalidate`, and a failed save keeps what was typed.
- Add a dependency only if the [stack](docs/specification.md#stack) needs it. Pin it and check it for known
  vulnerabilities.
- No secrets in the repository, and no real people or companies in demo data.

## Checks

Automatic checks are what protect this repository; these rules only explain them. While working, run only the tests near
the change. Run them all once, at the end, before calling something done, and say plainly what was not checked. Where a
check cannot tell, such as how a screen reader announces a change, test by hand and record it in the pull request.

```bash
uv lock --check
uv run --frozen ruff check && uv run --frozen ruff format --check && uv run --frozen mypy
uv run --frozen python tools/vendor.py check
uv run --frozen python tools/css.py check
uv run --frozen python tools/components.py check     # after changing the catalogue: tools/components.py
uv run --frozen python tools/gallery.py check        # generated from daisyUI's documentation: tools/gallery.py
uv run --frozen python tools/icons.py check          # icons, their names, and every SVG shown as an image
uv run --frozen python tools/translations.py check   # after changing texts: tools/translations.py update
uv run --frozen pytest -q                            # with TEST_DATABASE_URL, the database tests run on PostgreSQL too
```

Start the server with `--no-proxy-headers`, as the [README](README.md#try-it) does. Browser tests use the Chrome
already on the computer, or the browser `APP_BROWSER_CHANNEL` names (`msedge` for Edge); nothing is downloaded. After
upgrading Babel, a test may ask for `uv run --frozen python tools/cldr_grouping.py`.

## In a sandbox

An assistant's sandbox may cut a shell command at about 3 minutes, and may have no Chrome and no PostgreSQL. Everything
but the browser tests, in two commands that each fit; if one is cut, split it by file:

```bash
uv run --frozen pytest -q -m "not browser" --ignore=tests/demo
uv run --frozen pytest -q -m "not browser" tests/demo
```

- `tests/demo/test_clean_application.py` needs Tailwind's executable, which `tools/css.py` downloads to `.cache/`. Without
  it and without network, add `--ignore=tests/demo/test_clean_application.py` and say so.
- Browser tests are left for CI: say so in the pull request.
- Never run git in the project folder from a sandbox shell.
- Never ask a person to run a command: what cannot run here goes in the pull request as not checked.
