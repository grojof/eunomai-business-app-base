---
type: reference
title: Decimals on SQLite
description: "Why exact numbers need care on SQLite, and what to use instead of SUM or a sort that would go wrong"
tags: [base, data, decimals-on-sqlite]
---

# Decimals on SQLite

SQLite has no exact number. Stored as text, an exact column would order as letters, 100 before 9, and `SUM` would turn it
into a float. Neither is allowed to happen in silence:

| Over an exact column | On SQLite | What to use |
|---|---|---|
| `ORDER BY`, `<`, `>`, `BETWEEN`, `=`, `min`, `max`, `count` | Numeric: the collation compares each pair as `Decimal`, in Python | The same query as on PostgreSQL |
| `sum`, `avg` or any other function, arithmetic, `CAST`, `CASE` | `InexactQuery`, before the statement runs | `total()`, which sums in SQL on PostgreSQL and in Python on SQLite, or `exact_sum()` on values already read |

`exact_sum()` exists because Python's own `sum` rounds to 28 digits without an error.

`InexactQuery` reads statements built with SQLAlchemy. **SQL written by hand with `text()` is not read**: its `ORDER BY`
is still numeric, because the collation belongs to the column, but its `SUM(cost)` gives a float. Such a query over an
exact column is for a person to catch in review.
