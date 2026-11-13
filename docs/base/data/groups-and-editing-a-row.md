---
type: reference
title: Groups and editing a row
description: "How to group rows and edit one among thousands with a native table and form, instead of a grid"
tags: [base, data, groups-and-editing-a-row]
---

# Groups and editing a row

The planning screen is what a spreadsheet-like grid would be asked for, without one. People who need to change one work
order among thousands get a native table and a native form, which a screen reader and a keyboard already know, with
nothing to learn in between.

| What | How |
|---|---|
| Groups | `grouped_table` writes one `<tbody>` per group, with a header row and `scope="rowgroup"`. The group goes first in `ORDER BY`, so paging and sorting work inside it. Grouping is a filter with no condition: it lives in the address like the rest |
| Totals | The whole group's, not the page's. `totals_by` groups in SQL on PostgreSQL. SQLite cannot add exact columns, so it adds in Python, with the same answer. A group cut by a page says *continued* |
| Editing | One row at a time, in a native `<dialog>` that htmx fills. The browser keeps the keyboard inside, and Escape closes it. Without JavaScript the same address is a page of its own |
| Saving | A POST, checked by `_context` as [SEC-07](../standards.md#security) says: a request from another site is refused before it reaches the route. Editing needs the `admin` role, on the server, and without it the Edit action is not offered |
| Errors | Listed at the top of the form, each a link to its field, with focus on the list. What was typed stays. [Forms](../data/forms.md#forms) grow from this |
| After a save | The list comes back in the order and on the page it was, because the row may now belong to another group, or to none. Focus returns to the row's Edit link, or to the table if the row left the list. A message says what was saved, on screen and to a screen reader, and without JavaScript too: the address carries `saved` for that one page |
