---
type: reference
title: "Filter panel"
description: "The same form in a side panel that can be hidden, for a list with many filters."
tags: [component, data-input, available]
---

# Filter panel

**Status:** available. **Category:** data-input. **In the demo:** `/gallery/filter-panel`, and Planning.

The [filter bar](filter-bar.md)'s form, in an `aside` beside the list. A list with many filters, or that needs its width,
uses it instead of the bar. Read the `ListView` with `panelled=True`, and the panel's state lives in the address as
`panel`: `shown`, `hidden`, or nothing, which shows it beside the list on a wide screen and keeps it closed on a narrow
one, so it never pushes the rows out of sight.

```python
view = ListView.read("orders", "/orders", params, columns, Order.id, "opened", filters, searched, label, panelled=True)
```

```jinja
{% call list_with_filters(view) %}
  {% include "orders/results.html" %}
{% endcall %}
```

In the results, `filter_panel(view, refill=true)` takes the place of `filter_bar(view, refill=true)`. `list_summary`
then starts with the panel's button. With JavaScript it is a button with `aria-controls` and an `aria-expanded` that
`app.js` keeps true to what is on screen, and a press asks the server for the other state, so the address and every link
of the list keep it, and focus stays on the button. Without JavaScript a link does the same.
