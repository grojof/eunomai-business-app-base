---
type: reference
title: "Board"
description: "Cards in columns, each with a form that moves it, and dragging for a pointer or a finger."
tags: [component, data-display, available]
---

# Board

**Status:** available. **Category:** data-display. **In the demo:** `/gallery/board`, and the board of work orders at
`/board`.

A board drawn on the server, from a `Board` of `app/core/boards.py`: columns, each with its title, its first cards and
how many there are in all, with a link to the rest. The caller writes a card's content; `card.item` is its row.

```python
board = Board("board", _("Work orders by state"), columns, "/board/move", can_move=can_edit(request), focus=moved_id)
```

```jinja
{% call(card) board(board, message) %}
<h3 class="font-semibold">{{ card.item.title }}</h3>
{% endcall %}
```

Each card a person may move carries a plain form: a select of columns and a Move button, which puts it first in that
column. It works by keyboard and without JavaScript. `board.js` loads SortableJS, only for a board that can change, so a
pointer or a finger can drag a card; it sends the same form with `after`, the card it now follows. It wires the lists
again after htmx brings a new board.

The route reads the move with `read_move`, against its lists, and checks the role, that the card to follow is in that
column, and the card's version. It gives the card `rank_between` its neighbours, or numbers the column again with
`renumbered` when there is no room left, through the table so that no other card's version moves. With htmx it answers
with the board, `focus` on the card that moved and its move in `message`; without JavaScript, a redirect that says it.
