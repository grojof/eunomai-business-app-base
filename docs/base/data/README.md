---
type: reference
title: Data
description: "The databases (PostgreSQL in production, SQLite for the demo and previews), their settings, migrations, and an index of the data pages"
tags: [base, data]
---

# Data

PostgreSQL is the real database. SQLite is the default for the demo and for previews, so a clone runs with nothing
installed. It never runs in production.

| Setting | Effect |
|---|---|
| `APP_DATABASE_URL` | Where the data is. By default `sqlite:///.data/app.db`, a file git ignores, made by the first connection |
| `APP_ENVIRONMENT` | `production` by default, and production refuses anything but PostgreSQL. `.env.example` sets `development` |

So a server with neither setting stops as it starts, and says what to set.

```bash
uv run --frozen alembic upgrade head               # applies the migrations
uv run --frozen python -m app.demo.generate        # applies them too, then fills the demo's tables, in seconds
uv run --frozen python -m app.demo.generate --if-empty   # the same, but leaves tables that hold rows as they are
uv run --frozen alembic revision --autogenerate -m "What changed"   # after changing a model; read what it wrote
```

A route asks for a session and declares itself with `def`, so a query runs in a worker thread instead of stopping the
server. Nothing is saved unless the route commits, so a failed commit can still reach the person:

```python
def close_order(order_id: int, session: DatabaseSession) -> Response:
    session.get(WorkOrder, order_id).closed_at = datetime.now(UTC)
    session.commit()
```

## Pages

- [Column types](column-types.md): Which column type to use in a model for money, quantities, dates, times and text, and what each becomes on both databases.
- [Decimals on SQLite](decimals-on-sqlite.md): Why exact numbers need care on SQLite, and what to use instead of SUM or a sort that would go wrong.
- [Where the two databases differ](where-the-two-databases-differ.md): Where PostgreSQL and SQLite behave differently, with the cost of each difference.
- [Lists on the server](lists-on-the-server.md): How to build a long list with search, filters, sorting and pages on the server: ListView and its macros.
- [Charts](charts.md): How to draw a chart: the numbers worked out on the server, the chart macro, its table and its colours.
- [Boards](boards.md): How to show cards in columns, such as work orders by state, moved on the server.
- [Timelines](timelines.md): How to show rows on a calendar as bars beside their table: the gantt macro.
- [Calendars](calendars.md): How to show events by month, week or agenda with the calendar macro, over what the server sends.
- [Groups and editing a row](groups-and-editing-a-row.md): How to group rows and edit one among thousands with a native table and form, instead of a grid.
- [Two people on one row](two-people-on-one-row.md): How a row keeps the version it was read at, so a save by one person never overwrites another's.
- [Forms](forms.md): How to build a form to add or change a row: field macros, validation, errors and what is kept after a failed save.
- [Uploads](uploads.md): How an attached file is checked and stored: allowed kinds, signatures, sizes and where files live.
- [Excel](excel.md): How to export a list to Excel with its filters and order, row by row, for large lists.
