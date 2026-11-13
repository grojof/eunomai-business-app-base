---
type: reference
title: Lists on the server
description: "How to build a long list with search, filters, sorting and pages on the server: ListView and its macros"
tags: [base, data, lists-on-the-server]
---

# Lists on the server

`app/core/tables.py` is what a long list needs, and it stays when the demo goes. A route describes its columns and filters
in a `ListView`, which reads the address, and the macros `filter_bar`, `list_summary`, `server_table` and `pagination`
draw it:

```python
view = ListView.read("orders", "/orders", request.query_params, columns, Order.id, "opened", filters, searched, label)
view.load(session, select(Order))
return render_list(request, view, "orders/list.html", "orders/results.html")
```

| What | How |
|---|---|
| State | In the address: `q`, each filter, `sort`, `dir`, `size`, `page`. Defaults are left out, so one state has one address, and it can be bookmarked, reloaded and shared |
| Input | `q`, `sort`, `dir`, `size`, `page` and `panel` belong to the list's address, so a `Filter` with one of those names is refused where it is written. Each value is checked against its list in `ListView.read`, and `list_query` reads the address a person came from, keeping blank values, which mean something, and ignoring what it cannot read. A value outside its list is ignored, so an old bookmark still opens. A sort name selects a `Column` by key, so nothing from the address reaches SQL as text, and the search term is a bound parameter with `%` and `_` escaped |
| Order | A tiebreak on the primary key keeps rows from moving between pages. A column marked `nullable` puts empty values last on both databases, which by themselves disagree |
| A label sorts as read | The database cannot sort what it does not hold. `case` gives each stored value its position, as the demo's locations do in the person's language and its states by what needs attention first. Such a column uses no index: about 10 milliseconds at 50,000 rows |
| Without JavaScript | Headers and pages are links, and filters are a GET form with an Apply button |
| Filters in a side panel | `filter_panel` puts the same form in an `aside` beside the list, for a list with many filters, as Planning has. `ListView.read(..., panelled=True)` reads its state from the address as `panel`, `shown` or `hidden`, and every link and the form carry it. Without one, it is beside the list on a wide screen and closed on a narrow one, so it never pushes the rows out of sight. The button at the start of the summary has `aria-expanded`, which `app.js` keeps true to what is on screen, and asks the server for the other state; without JavaScript a link does |
| With htmx | The same address answers with its results alone, and `whole_page` sends a person to a whole page when there are no results to give, because htmx would put a redirected page inside the fragment. `Vary: HX-Request` keeps the two apart, and `HX-Push-Url` gives the address its one form. History is not kept in the browser: going back reloads the address, so a form can never show an older state than the table, and no row is left in `localStorage` |
| Focus | htmx puts it back on an element that kept its id, as a sort header does. If none did, as the Next link on the last page, `data-focus-fallback` takes it. A link that arrives works at once: htmx wires it in the same step as the swap |
| A request that fails | `app.js` shows a message for every htmx failure, on any screen, inside an open dialog if there is one, with `role="alert"`. A 404 says the thing is no longer there, and a row removed while it was being saved gets that same 404 |
| Announcement | `data-announce` on the summary goes to the announcement region after each change: rows, order and direction |
| Wide and dense | Dense rows sit in a taller box, so a default page of 25 fits a 1920 by 1080 screen, and a smaller screen scrolls it under its pinned header; a dense row's action buttons stay within its cell, so a table whose columns fit never scrolls sideways, which a test checks at 1280, 1440 and 1920 in both densities. Two toggles at the end of the summary, each a form to `/preferences` that comes back to the same address: the whole width of the screen, and dense rows. They are the person's `list_width` and `list_density`, kept as the other layout choices are and offered in the settings menu too, so every list looks the same way for one person. With htmx the list comes back alone, focus stays on the toggle and `aria-pressed` says its state. `render_list` reads them through `arrange`; an application that fixes them in its settings offers neither |

Measured on one laptop, on SQLite with 50,000 rows and the demo's indexes: the first page takes 0.6 milliseconds whether
it sorts by code or by cost, the last page 4, a search 27. A whole request, with its page drawn, takes 10 to 30.
