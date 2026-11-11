# eunomai-business-app-base

A demo business application to clone and adapt. Its gallery shows every daisyUI component with an honest status and
every official example, and the approved ones are built to one standard of accessibility, usability and language
support, so a new application starts from working, tested pieces instead of from a blank page. People and AI assistants
both build faster that way.

**For whom:** teams that build internal applications, with or without AI, and want them to look and behave alike.

**What it is not:** a framework or a dependency. There is nothing to install and nothing to stay tied to. Clone it, keep
what helps, change the rest.

```mermaid
flowchart LR
    b[eunomai-business-app-base<br/>the demo] -->|tools/make_template.py<br/>with your brand| o[Your organization's template]
    o -->|a new repository from it| a[Application]
    o -->|a new repository from it| c[Application]
    classDef data fill:#ede9fe,stroke:#7c3aed,color:#4c1d95
    classDef step fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    class b,o data
    class a,c step
```

> **Status:** milestone 1: the application's shell with its layouts, a settings menu and a command palette (Ctrl+K or
> Cmd+K), the gallery, identity, languages, themes and every check running. Milestone 2: PostgreSQL and SQLite with exact
> decimals, a server table on 50,000 rows with Excel export, an equipment detail with tabs and a print style, charts with
> their tables, and a planning screen that groups rows and edits one at a time. Milestone 3, in review: every form field,
> a work order form with validation at the edge, file upload, a confirmation dialog, and two people on one row finding
> out. Milestone 4, in progress: lists that a person can make dense and as wide as the screen, the page's title in
> the top bar, filters in a side panel that can be hidden, charts whose parts filter a list, a board of work orders, a timeline in Planning, and a calendar of visits and work orders. The rest is in the [milestones](docs/base/specification.md#milestones).

<a id="run-it"></a>

## Try it

Needs [uv](https://docs.astral.sh/uv/). A copy of `.env.example` gives a fake identity for local work.

```bash
cp .env.example .env
uv run --frozen uvicorn app.main:app --reload --no-proxy-headers
```

Keep `--no-proxy-headers`: without it, Uvicorn replaces the proxy's address with the one in `X-Forwarded-For`, the
address stops being trusted, and everyone gets 401.

No database is needed for that. Without `.env` the application refuses to start, because production is the default and
production never runs on SQLite.

Equipment, planning and the dashboard's charts read generated rows. They say so, and show this command, which takes
seconds, makes a SQLite file under `.data/` and can run while the server does. Then reload the page. Everything else
works without it.

```bash
uv run --frozen python -m app.demo.generate
```

For PostgreSQL, set `APP_DATABASE_URL` and apply the migrations, then generate if you want the rows. The database tests
run on it too if `TEST_DATABASE_URL` gives one. [Data](docs/base/specification.md#data) says how the two differ.

```bash
uv run --frozen alembic upgrade head
```

The whole suite runs on a computer before each push. On GitHub the tests run on Ubuntu, with SQLite and PostgreSQL,
when started by hand: *Actions*, *Tests*, *Run workflow*, or `gh workflow run tests.yml --ref <branch>`. Do it before
publishing, and after a change to the database layer.

An organization makes its template from this with `tools/make_template.py` and its brand, as
[An organization's template](docs/base/specification.md#an-organizations-template) says, and starts each application
from that template. To try the base alone, clone this, then run `uv run --frozen python tools/remove_demo.py` and
`uv run --frozen python tools/css.py`. The first is what turns the clone into an application: the demo goes, and
`AGENTS.md` stops describing a neutral base and describes an application, so real work belongs there. `README.md` becomes
the application's own map, and this documentation stays in `docs/base/`. Fill in *What this application is* at the top
of `AGENTS.md` before anything else: every assistant reads it first. The step runs once, and a second
run changes nothing, so what you wrote stays. Each module of screens then starts with `tools/new_module.py`, which
writes its list, its pages, its form, its migration and its tests from a short description, as
[A new module](docs/base/specification.md#a-new-module) says.

## Documentation

The base's documentation is in `docs/base/`, where every application keeps it as its reference.

| Page | What it contains |
|---|---|
| [Specification](docs/base/specification.md) | What the base contains, its data, its components, its icons and illustrations, the demo, how it is adapted, a new module, an organization's template, and the milestones |
| [Standards](docs/base/standards.md) | Every rule of accessibility, usability, language, components, data and security, with its official source and its check |
| [Components](docs/base/components/README.md) | Every component on offer, one page each, with its status |
| [Decisions](docs/base/decisions.md) | Why it is built this way, and what is still open |
| [Deployment](docs/base/deployment.md) | Running an application on a server: settings, database, service and the identity proxy in front |

How to work in this repository: [AGENTS.md](AGENTS.md).

## Licence

[MIT](LICENSE). The libraries it carries keep their own licences: [third-party notices](THIRD-PARTY-NOTICES.md).
To report a security problem: [security policy](SECURITY.md).
