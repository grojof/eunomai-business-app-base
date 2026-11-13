---
type: reference
title: The demo
description: "The demo's fictional company and its screens, and what each exercises"
tags: [base, the-demo]
---

# The demo

A fictional company maintains its equipment. The scenario needs no real data:

| Screen | What it exercises | Since |
|---|---|---|
| Dashboard | Stats, a table, badges, progress, steps, an empty state, formats, content replaced with focus and an announcement, and charts from the generated rows. Without those rows it keeps its fixed values and says what to run | Milestone 1 |
| Gallery | [Every component on offer](gallery.md#gallery), by category, with its status, its macro and every official example | Milestone 1 |
| Administration | Visible only to one role, proving permissions | Milestone 1 |
| Equipment list, `/equipment` | Server table with 50,000 rows, search, filters, sorting, paging, row actions, its empty and no-results states, Excel export | Milestone 2 |
| Equipment by state and by location | Two charts above the list, whose parts and table rows filter it in place | Milestone 4 |
| Equipment detail, `/equipment/<id>` | Breadcrumbs, description list, tabs as links, history of work orders, status label, print style | Milestone 2 |
| Planning, `/planning` | Rich table: groups on the server, and one row edited at a time in a dialog | Milestone 2 |
| Planning's filters | In a side panel that can be hidden, with its state in the address | Milestone 4 |
| Board, `/board` | Work orders by state: a form on each card, dragging, order and conflicts on the server | Milestone 4 |
| Planning's timeline, `/planning?show=timeline` | The page's work orders as bars beside their table, with what each waits for, at a scale of days, weeks or months | Milestone 4 |
| Calendar, `/calendar` | Inspection visits and planned work orders by month, week and agenda: dragging, a form for each visit, the time zone, conflicts | Milestone 4 |
| Work order form, `/work-orders/new` and `/work-orders/<id>/edit` | All form fields, validation, decimals, dates, file upload, delete with a confirmation | Milestone 3 |
| Import | Long task with progress, its result and its errors | Milestone 5 |

The demo's tables, `equipment` and `work_order`, with `work_order_file` for what people attach, hold what `app/demo/generate.py` makes: 50,000 pieces of equipment and
10,000 work orders, from a seed, with no third-party package. Each row comes from a hash of the seed and its position, so
the same seed gives the same rows on any computer and Python version. Work orders fall unevenly, so a detail page can
show a history of three, of two, of one, or none. Generating refuses to run outside development, because it replaces what
those tables hold.

The data tells one story, and every screen reads the same one. It ends on a fixed day, `LAST_DAY` in `app/demo/models.py`,
which is the demo's today whenever it is read, so what is overdue does not change with the calendar. Orders open from
1 January to that day. Those opened more than 60 days earlier are nearly all closed, about 96 %, and the few left open are
really late; newer ones spread across the states. Moments fall at noon at the ends of that range, so no time zone moves
one to another month. The dashboard's figures, charts and Overdue card come from these rows, Overdue leads to Planning's
own overdue filter, and `overdue()` is the one definition of the word. One fictional role exists, `admin`.

A first run stays `cp .env.example .env` and one command, with no database to prepare. Generating is one more command,
in seconds, and it can run while the server does. A screen that reads the rows asks first, in `app/demo/data.py`: if the
SQLite file is not there it does not connect, so showing a page never creates one. Without the rows, or with migrations
behind the code, it shows the command to run, and with a database that does not answer it says so. Every other
screen keeps working.
