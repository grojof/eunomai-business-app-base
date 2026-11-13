---
type: reference
title: Two people on one row
description: "How a row keeps the version it was read at, so a save by one person never overwrites another's"
tags: [base, data, two-people-on-one-row]
---

# Two people on one row

A row that people edit has a version. The form carries the version it was read at, and a save compares it. Both the
planning editor and the work order form do this.

```python
class WorkOrder(Base):
    version: Mapped[int] = mapped_column(server_default="1")
    __mapper_args__ = {"version_id_col": version}
```

| What | How |
|---|---|
| Finding out | SQLAlchemy adds `AND version = ?` to each `UPDATE` and `DELETE`, and moves the number on. So a save that falls between another person's read and write changes no row, on either database, and `saved(session, change)`, from `app/core/database.py`, says so. A change of several steps goes in `change`, because loading anything flushes what came before it, and the check fires there. Comparing in Python alone could not catch that |
| Telling | The form comes back with what was typed and a [conflict notice](../components/conflict-notice.md) that lists what is saved now, with focus on it. A 409 page without JavaScript, the same dialog or form with htmx. Saving again replaces their work, knowingly: the form now carries the newest version |
| Saying the same | A late save that matches the row is no conflict, so a double click or two people who agree meet no message |
| Wrong values first | A form with errors shows those, and keeps its old version, so the conflict comes on the next save |
| Deleting | A confirmation names what will go, each file by name, and carries what it named, so if the row or its files changed it asks again with what is there now |
| Files | Adding or removing a file changes no version: two people can each add one and neither loses anything. A file sent with a conflict, or for a row that has gone, is taken away again on every way out, and the form says to choose it again |
| A row removed meanwhile | The same 404 as ever. A failed `WHERE version` is read again to tell the two apart |
| Limits | Only saves through these forms are compared. A script that writes with `update()` moves no version unless it says so |

To give another table a version: the two lines above and a migration, then a hidden `version` in the form,
`read_version` and `saved` in the route, as `app/demo/planning.py` does.
