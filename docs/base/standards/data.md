---
type: reference
title: "Standards: Data"
description: "The rules that hold for data on both databases, each with its source and check."
tags: [data, standards]
---

# Data

Where the two databases [differ](../data/where-the-two-databases-differ.md#where-the-two-databases-differ) is stated in the specification. These
rules are what holds on both. The tests of `DATA-02` to `DATA-06` and `LANG-15` run on SQLite everywhere, and on PostgreSQL
in the Ubuntu job.

| ID | Rule | Source | Check |
|---|---|---|---|
| DATA-01 | Production runs on PostgreSQL: the application refuses to start on anything else, and SQLite is the default only with `APP_ENVIRONMENT=development` | [SQLite: appropriate uses](https://www.sqlite.org/whentouse.html) | Automatic |
| DATA-02 | Money and quantities use one exact column type: `Numeric(38, 20)` on PostgreSQL, text on SQLite, written in one form. A float is refused, on writing and in a query, and so is a value the column cannot hold whole. No model or migration declares another decimal type | [PostgreSQL numeric types](https://www.postgresql.org/docs/current/datatype-numeric.html), [Python decimal](https://docs.python.org/3/library/decimal.html) | Automatic |
| DATA-03 | On SQLite, ordering and comparing an exact column are numeric, and a sum, a function, arithmetic, a cast or a case over one, built with SQLAlchemy, fails loudly instead of going through a float. `total()` gives the same exact sum on both databases | [SQLite collation](https://www.sqlite.org/datatype3.html#collation), [SQLite aggregates](https://www.sqlite.org/lang_aggfunc.html) | Automatic |
| DATA-04 | Foreign keys hold on both databases | [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html#fk_enable) | Automatic |
| DATA-05 | A route that uses the database is declared with `def`, so a query runs in a worker thread and does not stop the server | [FastAPI: concurrency](https://fastapi.tiangolo.com/async/) | Automatic |
| DATA-06 | Models and migrations say the same on both databases, every migration goes down and up again, and a batch change keeps the rows that point to its table | [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html), [Alembic batch](https://alembic.sqlalchemy.org/en/latest/batch.html) | Automatic |
| DATA-07 | Demo data is generated: the same seed and the same number of rows give the same rows on any computer and Python, and no real person or company appears | Project decision | Automatic |
