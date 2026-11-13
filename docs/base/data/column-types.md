---
type: reference
title: Column types
description: "Which column type to use in a model for money, quantities, dates, times and text, and what each becomes on both databases"
tags: [base, data, column-types]
---

# Column types

Models inherit from `Base`, in `app/core/database.py`. Annotations choose the type, so the exact one needs no asking.

| In a model | PostgreSQL | SQLite | In Python |
|---|---|---|---|
| `Mapped[Decimal]`: money and quantities, 18 digits and 20 decimals | `numeric(38, 20)` | Text in one form: `1.50` is `1.5`, with the collation `exact_decimal` | `Decimal`, without trailing zeros on both |
| `Mapped[datetime]`: a moment | `timestamptz` | Text of a fixed width, in UTC | An aware `datetime`, in UTC |
| `Mapped[date]`: a day in the calendar | `date` | Text, `2027-03-15` | `date` |

A float is refused on writing and in a query, and so is a `datetime` without its time zone. So is a value the column
cannot hold whole: PostgreSQL alone would round extra decimals without a word, so both databases refuse them here.
