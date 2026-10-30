---
type: reference
title: Specification
description: "What business-app-base contains: its structure, stack, components, demo, how an organization adapts it, how it is checked, and the milestones."
tags: [specification, components, demo, template]
related: [standards.md, decisions.md]
---

# Specification

`business-app-base` is a working application that demonstrates its own components. An organization clones it once and
adds its brand; each new application is then a clone of that copy, with the demo deleted.

Success means three things, each testable:

| Goal | Test |
|---|---|
| Adapting it to an organization is cheap | Changing only `app/brand/` and the settings gives that organization's look |
| A new application starts clean | With `app/demo/` deleted, every check still passes |
| The components hold the standard | Every component has a demo page that passes the [standards](standards.md) |

## Structure

```text
app/
  core/      identity, roles, settings, database, languages, formatters, errors, health
  ui/        components: Jinja macros, CSS, vendored JavaScript
  brand/     tokens.css, fonts, logos
  demo/      screens, models, sample data, translations
locales/     the translations of core and ui
migrations/  Alembic
tests/
deploy/      example service files and the registration file
docs/
```

## Stack

| Piece | Choice |
|---|---|
| Server | Python 3.12+, FastAPI, Pydantic v2, Uvicorn; uv with `uv.lock` |
| Data | PostgreSQL, SQLAlchemy 2, Alembic, psycopg 3 |
| Reading another system's SQL Server | pyodbc with Microsoft's ODBC Driver 18 and a read-only user; optional |
| Pages | Jinja2 with escaping always on, htmx 2.0, Alpine.js in its CSP build |
| Tables | Made on the server; Tabulator only where grouping or editing needs it ([open](decisions.md#open-questions)) |
| Charts | Apache ECharts ([open](decisions.md#open-questions)) |
| Excel | XlsxWriter, on the server |
| Languages | gettext catalogues through Babel and Jinja2's i18n extension |

No Node, no build step and no file loaded from another server. JavaScript files are copied into the repository with
their version, origin and hash (`vendor.json`), and served with Subresource Integrity.

Exact versions live in `uv.lock` and `vendor.json`, not in this page.

## Dependencies

A daily workflow keeps dependencies current, and every clone inherits it. It updates to the newest version the rules
allow, runs the tests and proposes one pull request. A person merges it. If no allowed version solves a problem, it
keeps an issue open until one does.

| Rule | Decision |
|---|---|
| Known vulnerability | Blocked, always |
| Yanked, deprecated or a pre-release | Blocked |
| Released less than two weeks ago | Waits, unless it fixes a vulnerability in every older version |
| No release in three years, or no public source repository | Blocked, unless the organization makes an exception |
| New major version | Never automatic: it takes a decision, as htmx 4 does |

The workflow covers `uv.lock` and `vendor.json`: a copied JavaScript file gets the same rules, and its update brings the
new hash. The job that runs upgraded code can only read; a separate job, which runs no project code, opens the pull
request, and accepts only the files the update produces.

## Identity

The application has no login of its own. A trusted reverse proxy authenticates the person and passes who they are in
headers; the header names and the mapping from groups to roles are settings. Those headers are believed only from the
proxy: the application listens on `127.0.0.1` and refuses a request without them, except for its health check. For local
work, a fake identity is available and refuses to start outside development.

## Components

A component is one Jinja macro and its CSS, using only the brand's variables. Each has a demo page showing every state,
and tests.

| Group | Components |
|---|---|
| Structure | Page layout, header with the person's identity, navigation, skip link, breadcrumbs, page heading, language selector, theme selector, footer with version |
| Data | Server table (paging, sorting, filtering, state in the URL, row actions), rich table, filter bar, pagination, description list, tabs, status label, indicator tile, chart with its data table |
| Forms | Text, text area, select, checkbox, radio, date, number and decimal, searchable select, file upload, error summary, field error, form actions |
| Feedback | Message banner, announcement region, confirmation dialog, empty state, loading state, progress of a long task |
| Pages | Not found, no permission, server error, service unavailable |
| Output | Excel export, print style |

A component is left out until a real need appears for it. The base stays small enough to read.

## The demo

A fictional company maintains its equipment. The scenario needs no real data and uses every component:

| Screen | What it exercises |
|---|---|
| Dashboard | Indicators, charts with their tables, states |
| Equipment list | Server table with 50,000 rows, filters, sorting, Excel export |
| Equipment detail | Description list, tabs, history |
| Work order form | All form fields, validation, decimals, dates, file upload |
| Planning | Rich table: grouping and editing, or its accessible replacement |
| Import | Long task with progress, its result and its errors |
| Administration | Visible only to one role, proving permissions |
| Component catalogue | Every component in every state, with its code |

Sample data is generated and reproducible. Two fictional roles show what each one may see and do.

## Adapting it

| To do this | Change |
|---|---|
| Your colours, fonts and logos | `app/brand/` |
| Your languages | Settings, and `locales/` |
| Your identity proxy | Settings |
| Start an application | Clone your copy, delete `app/demo/`, remove its line from `app/main.py` |
| Add a component | `app/ui/`, with its page in the catalogue |

An application that needs something different changes it: the code belongs to whoever cloned it. There is no update
mechanism. When the base improves, an application compares versions and takes what it wants; each release says what
changed and how to apply it.

`AGENTS.md`, the documentation and the checks travel with every clone. Any of them can be removed and the application
still runs.

## Checks

| Check | What it proves |
|---|---|
| Unit and integration tests | Behaviour, including permissions per role |
| Tests with `app/demo/` deleted | The base works without the demo |
| Accessibility scan of every catalogue state, in both themes | No automatically detectable failure |
| Keyboard tests of each interactive component | Reachable, operable, focus visible and in order |
| Language checks | See [Standards](standards.md#how-language-is-checked) |
| Hard-coded value check | No colour or size outside the brand's variables |
| Linter, type checker, lock file, [dependency rules](#dependencies) | The code and its dependencies |

Browser tests use Playwright for Python and a vendored axe-core. Both are development tools and never reach a server.

## Registration

`deploy/registration.toml` describes the application to the platform that hosts it: identifier, name, group, icon, port,
limits, public paths, and each role with the directory group that grants it. A hosting platform can generate its web
server and access configuration from this file. Its fields are fixed in milestone 5, against a real platform.

## Milestones

| # | Milestone | Done when |
|---|---|---|
| 0 | Specification | Reviewed |
| 1 | Skeleton | Layout, identity, languages, themes, every check and the dependency workflow running on one screen |
| 2 | Data | Server table with 50,000 rows, filters, export, indicators, charts |
| 3 | Forms | Every field, with validation in three languages |
| 4 | Feedback and long tasks | Every state in the catalogue |
| 5 | Registration | Deployed behind a real identity proxy |
| 6 | Proof | One organization's copy made by changing only its brand and settings |

The accessibility and language checks run from milestone 1, so nothing is built without them.
