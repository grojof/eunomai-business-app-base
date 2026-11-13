---
type: reference
title: Boards
description: "How to show cards in columns, such as work orders by state, moved on the server"
tags: [base, data, boards]
---

# Boards

`app/core/boards.py` and the macro `board` draw cards in columns on the server, as the board of work orders at `/board`
does, with one column per state. The route gives a `Board` its columns, each with its first cards, how many there are in
all and where the rest are; the caller of the macro writes a card's content.

| What | How |
|---|---|
| A card | `BoardCard` with `href` is drawn by the macro: its title as a link to its page, a few `lines`, and `actions` as small buttons, which a finger can hit. A card the caller draws puts its actions in the same buttons: a bare link beside another on a card is too small for WCAG 2.5.8 |
| Moving without a pointer | Each card a person may move carries a form behind a small "Change column" disclosure, a native `details`, so a card stays light: a select of columns and a Move button, a plain POST that puts it first in that column. It works by keyboard and without JavaScript, the disclosure and the select are named with the card, and after a move focus is back on the card's disclosure |
| Dragging | `board.js` loads SortableJS, with its integrity, only for a board that can change. A pointer drags at once; a finger rests a moment first, so that a swipe still scrolls. A drop sends the same form, with `after`, the card it now follows. After htmx brings a board, its lists are wired again |
| The server decides | `read_move` reads the card, the column and the card to follow against their lists. The route checks the role, that the card to follow is in that column, and the card's version, so a card someone else moved first is a [conflict](../data/two-people-on-one-row.md#two-people-on-one-row) that moves nothing and says where it is now |
| Order | `place_card` and `column_lock` in `app/core/boards.py`, which the demo's board and a generated module's use. A big integer, `rank`, in each column, read with the primary key after it. A card takes the number half way between its neighbours in the whole column, not only in what the page showed; with no number left between them, or one that would pass 2⁶², the column is numbered again through the table, which moves no other card's version |
| Two moves at once | A move first locks the rows of the columns it reads and writes, in one order, where the database can: on PostgreSQL a second move waits, then reads the ranks the first left, and two moves cannot deadlock. SQLite has one writer at a time and takes no row locks. The test of the wait runs on PostgreSQL only |
| After a move | With htmx the board comes back with focus on the card's select and the move announced; without JavaScript a redirect, and the address says what moved for that one page |
| A phone | Columns stack, so the page never scrolls sideways |
| Settled attributes | htmx settles `class`, `width` and `height` only. A `style` attribute set by htmx is inline style, which the policy refuses, and SortableJS moves cards through the CSSOM: a test keeps the setting |
