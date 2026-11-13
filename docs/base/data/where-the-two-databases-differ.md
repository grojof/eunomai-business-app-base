---
type: reference
title: Where the two databases differ
description: "Where PostgreSQL and SQLite behave differently, with the cost of each difference"
tags: [base, data, where-the-two-databases-differ]
---

# Where the two databases differ

| What | PostgreSQL | SQLite |
|---|---|---|
| Ordering an exact column | Native, and can use an index | A Python call per comparison. With an index on the column a page of 50,000 rows takes under a millisecond, because the comparisons were paid when the index was written. Without one, about 0.65 seconds |
| Reading the file with another tool | Not applicable | Ordering an exact column stops with `no such collation sequence`, and foreign keys may be off |
| Sums and arithmetic in SQL | Exact | Refused, as above |
| `String(40)` | Enforced | Not enforced: longer text is stored |
| `LIKE` | Tells capitals apart | Does not, for ASCII |
| Ordering text | By the database's collation | By bytes |
| Writers at once | Many | One |
| A migration that fails | Undone whole | May stay half applied: delete `.data/` and generate again |
| Changing a table | `ALTER TABLE` | Batch mode: copies the table, drops the old one, renames the copy. Foreign keys are off for that, and checked after it. SQLite reports no collation when a table is read, so `app/core/database.py` listens to every reflected table and puts it back. `alembic check` cannot see a lost one: a test walks each migration down one and up one and compares what the file really holds |
| Foreign keys | Always on | On per connection, by `create_database_engine` |

The tests of the database layer run on both, so a difference that breaks them shows. Those that stay are the table above:
a query that depends on one passes on one database and not the other.
