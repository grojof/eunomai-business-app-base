---
type: reference
title: "Chart"
description: "A figure with its text summary and its data as a table, drawn with Chart.js."
tags: [component, data-display, available]
---

# Chart

**Status:** available. **Category:** data-display. **In the demo:** `/gallery/chart`.

The [specification](../specification.md#charts) says how it works and which types to use.

```python
data = chart_data(months, [Series(_("Planned"), planned), Series(_("Worked"), worked)], _("Month"), unit=_("h"))
```

```jinja
{{ chart(_("Hours planned and worked"), _("Hours worked stayed within 6 % of the plan."), data, "bar", "chart-hours") }}
```

The summary is required, and says what the chart shows, not what it is. Every figure brings its table, so a person who
cannot see the canvas misses nothing.

A chart can be a way to choose. `links`, one address per label, make each row of its table a link, and a click on a
part of the picture follows the link of its row, so the keyboard's way in and the pointer's lead to the same place. To
filter a list on the same page in its place, pass the list's view as `into`: htmx then sends the list's own form with
the chart's one value instead of the form's, so the other filters, the order and the panel stay.

```python
data = chart_data(
    places, [Series(_("Equipment"), counts)], _("Location"), links=[view.link(location=p) for p in places]
)
```

```jinja
{{ chart(_("Equipment by location"), summary, data, "bar", "figure-locations", into=view) }}
```
